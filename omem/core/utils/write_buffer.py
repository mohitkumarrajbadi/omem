"""Async Write Buffer — decouples add() latency from persistence.

Accepts Memory objects into an in-memory queue and persists them
to the backend in a background thread. Makes add() near-zero latency.
Includes crash-safe WAL (Write-Ahead Log) so enqueued writes survive
process crashes.

v0.7.0 Production hardening (H).
"""

import base64
import json
import logging
import os
import queue
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_WAL_PATH = os.path.expanduser("~/.omem/write_buffer.wal")


class WriteBuffer:
    """Background persistence buffer with crash-safe WAL.

    Usage::

        buf = WriteBuffer(backend=sqlite_backend)
        buf.enqueue(memory)  # returns immediately
        # ... background thread persists
        buf.flush()          # force-persist all pending
        buf.stop()           # graceful shutdown
    """

    def __init__(
        self,
        backend: Optional[object] = None,
        flush_interval: float = 1.0,
        wal_path: Optional[str] = None,
    ):
        self._queue: queue.Queue = queue.Queue()
        self._backend = backend
        self._flush_interval = flush_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._total_written = 0
        self._total_errors = 0
        self._wal_path = wal_path or _DEFAULT_WAL_PATH
        self._wal_lock = threading.Lock()

        # Ensure WAL directory exists
        wal_dir = os.path.dirname(self._wal_path)
        if wal_dir:
            os.makedirs(wal_dir, exist_ok=True)

        # Re-enqueue any memories that survived a crash
        self._recover_from_wal()

    # ------------------------------------------------------------------
    # WAL helpers
    # ------------------------------------------------------------------

    def _serialize_memory(self, memory) -> str:
        """Serialize a Memory to a single-line JSON string."""
        vec = memory.vector
        vec_b64 = base64.b64encode(vec.tobytes()).decode("ascii") if vec is not None else ""
        return json.dumps({
            "id": memory.id,
            "type": memory.type.value,
            "content": memory.content,
            "vector_b64": vec_b64,
            "timestamp": memory.timestamp,
            "importance": memory.importance,
            "utility_score": memory.utility_score,
            "access_count": memory.access_count,
            "last_accessed": memory.last_accessed,
            "namespace": memory.namespace,
            "source": memory.source,
            "active": memory.active,
            "status": memory.status.value,
            "consensus_score": memory.consensus_score,
            "logical_hash": memory.logical_hash,
            "metadata": memory.metadata,
            "score": memory.score,
        }, default=str)

    def _deserialize_memory(self, line: str):
        """Reconstruct a Memory object from a WAL line."""
        import numpy as np

        from ...types import Memory, MemoryStatus, MemoryType  # type: ignore[attr-defined]

        d = json.loads(line)
        vec_b64 = d.get("vector_b64", "")
        if vec_b64:
            vec = np.frombuffer(base64.b64decode(vec_b64), dtype=np.float32).copy()
        else:
            vec = np.zeros(384, dtype=np.float32)
        return Memory(
            id=d["id"],
            type=MemoryType(d["type"]),
            content=d["content"],
            vector=vec,
            timestamp=d["timestamp"],
            importance=d["importance"],
            utility_score=d["utility_score"],
            access_count=d["access_count"],
            last_accessed=d["last_accessed"],
            namespace=d["namespace"],
            source=d["source"],
            active=d["active"],
            status=MemoryStatus(d["status"]),
            consensus_score=d["consensus_score"],
            logical_hash=d["logical_hash"],
            metadata=d.get("metadata", {}),
            score=d.get("score", 0.0),
        )

    def _wal_append(self, memory) -> None:
        """Append a serialized memory to the WAL file with fsync."""
        with self._wal_lock:
            try:
                line = self._serialize_memory(memory)
                with open(self._wal_path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
                    f.flush()
                    os.fsync(f.fileno())
            except Exception as exc:
                logger.warning("WAL append failed (non-fatal): %s", exc)

    def _wal_remove(self, persisted_ids: set) -> None:
        """Rewrite WAL excluding flushed IDs (atomic via os.replace)."""
        with self._wal_lock:
            if not os.path.exists(self._wal_path):
                return
            tmp_path = self._wal_path + ".tmp"
            try:
                kept_lines = []
                with open(self._wal_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            d = json.loads(line)
                            if d.get("id") not in persisted_ids:
                                kept_lines.append(line)
                        except json.JSONDecodeError:
                            pass  # skip malformed lines

                with open(tmp_path, "w", encoding="utf-8") as f:
                    for line in kept_lines:
                        f.write(line + "\n")
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, self._wal_path)
            except Exception as exc:
                logger.warning("WAL cleanup failed (non-fatal): %s", exc)

    def _recover_from_wal(self) -> int:
        """Re-enqueue memories from WAL that haven't been persisted yet."""
        if not os.path.exists(self._wal_path):
            return 0

        recovered = 0
        with self._wal_lock:
            try:
                with open(self._wal_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except Exception as exc:
                logger.warning("WAL read failed during recovery: %s", exc)
                return 0

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                mem = self._deserialize_memory(line)
                self._queue.put(mem)
                recovered += 1
            except Exception as exc:
                logger.warning("WAL recovery: skipping malformed entry — %s", exc)

        if recovered:
            logger.info("WAL recovery: re-enqueued %d memories", recovered)
        return recovered

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background persistence thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._worker, daemon=True, name="omem-write-buffer"
        )
        self._thread.start()
        logger.debug("Write buffer started (interval=%.1fs)", self._flush_interval)

    def stop(self) -> None:
        """Stop the background thread and flush remaining items."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self.flush()  # flush any remaining

    def enqueue(self, memory) -> None:
        """Add a memory to the write queue (non-blocking)."""
        self._wal_append(memory)
        self._queue.put(memory)

    def enqueue_batch(self, memories) -> int:
        """Enqueue many memories for async classify→index→persist drain.

        Returns count accepted. Prefer this path for ingest throughput benches.
        """
        count = 0
        for memory in memories:
            self.enqueue(memory)
            count += 1
        return count

    def pending_count(self) -> int:
        return self._queue.qsize()

    def flush(self) -> int:
        """Force-persist all pending memories. Returns count written."""
        if self._backend is None:
            count = 0
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                    count += 1
                except queue.Empty:
                    break
            return count

        count = 0
        batch = []
        while not self._queue.empty():
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break

        if batch:
            try:
                if hasattr(self._backend, "save_batch"):
                    self._backend.save_batch(batch)
                else:
                    for mem in batch:
                        self._backend.save(mem)
                count = len(batch)
                self._total_written += count
                self._wal_remove({m.id for m in batch})
            except Exception as e:
                self._total_errors += 1
                logger.error("Write buffer flush error: %s", e)
                # Re-enqueue failed items (WAL entry already exists)
                for mem in batch:
                    self._queue.put(mem)

        return count

    def _worker(self) -> None:
        """Background worker that periodically flushes the queue."""
        while self._running:
            time.sleep(self._flush_interval)
            if not self._queue.empty():
                self.flush()
        # Final flush on shutdown
        self.flush()

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    @property
    def stats(self) -> dict:
        return {
            "pending": self.pending,
            "total_written": self._total_written,
            "total_errors": self._total_errors,
            "running": self._running,
        }
