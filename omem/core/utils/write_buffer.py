"""Async Write Buffer — decouples add() latency from persistence.

Accepts Memory objects into an in-memory queue and persists them
to the backend in a background thread. Makes add() near-zero latency.
Includes crash-safe WAL (Write-Ahead Log) so enqueued writes survive
process crashes.

WAL encryption
--------------
When ``OMEM_ENCRYPTION_KEY`` is set (same key as field-level encryption),
each WAL line is encrypted with AES-256-GCM before being written to disk.
Unencrypted WALs are still accepted on recovery so existing files remain
readable after a key is added (forward migration only — no back-migration).

v0.7.0 Production hardening (H).
"""

import atexit
import base64
import json
import logging
import os
import queue
import threading
import weakref
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_WAL_PATH = os.path.expanduser("~/.omem/write_buffer.wal")


def _wal_encryption_key() -> Optional[bytes]:
    """Return the raw AES-256 key bytes if OMEM_ENCRYPTION_KEY is set, else None."""
    raw = (
        os.environ.get("OMEM_ENCRYPTION_KEY", "").strip()
        or os.environ.get("OMEM_SECRET_KEY", "").strip()
    )
    if not raw:
        return None
    # Accept 64-char hex or base64url(32 bytes)
    try:
        if len(raw) == 64:
            key = bytes.fromhex(raw)
        else:
            key = base64.urlsafe_b64decode(raw + "==")
        if len(key) == 32:
            return key
    except Exception:
        pass
    logger.warning("OMEM_ENCRYPTION_KEY is set but not parseable as 32-byte hex/base64 — WAL will be unencrypted")
    return None


def _encrypt_wal_line(plaintext: str, key: bytes) -> str:
    """AES-256-GCM encrypt a WAL line; return base64url-encoded ciphertext prefixed with 'enc1:'."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = os.urandom(12)
        ct = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
        blob = base64.urlsafe_b64encode(nonce + ct).decode("ascii")
        return f"enc1:{blob}"
    except Exception as exc:
        # Never fall back to plaintext when a key is configured — that would
        # silently defeat at-rest protection for crash-recovery WAL.
        raise RuntimeError(f"WAL encrypt failed with encryption key set: {exc}") from exc


def _decrypt_wal_line(line: str, key: bytes) -> str:
    """Decrypt an 'enc1:' WAL line; return plaintext. Raises on corruption."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    blob = base64.urlsafe_b64decode(line[5:] + "==")
    nonce, ct = blob[:12], blob[12:]
    return AESGCM(key).decrypt(nonce, ct, None).decode("utf-8")


def _stop_at_exit(buffer_ref: "weakref.ReferenceType[WriteBuffer]") -> None:
    """Flush a live buffer before Python tears down builtins and modules."""
    buffer = buffer_ref()
    if buffer is not None:
        buffer.stop()


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
        self._stop_event = threading.Event()
        self._total_written = 0
        self._total_errors = 0
        self._wal_path = self._resolve_wal_path(backend, wal_path)
        self._wal_enabled = bool(self._wal_path)
        self._wal_lock = threading.Lock()

        # Ensure WAL directory exists (skip for disabled / pure in-memory path)
        if self._wal_enabled:
            wal_dir = os.path.dirname(self._wal_path)
            if wal_dir:
                os.makedirs(wal_dir, exist_ok=True)
            # Re-enqueue any memories that survived a crash
            self._recover_from_wal()
        atexit.register(_stop_at_exit, weakref.ref(self))

    @staticmethod
    def _resolve_wal_path(backend: Optional[object], wal_path: Optional[str]) -> str:
        """Pick a durable WAL file, or empty string to disable file WAL.

        Rules (first match wins):
        1. Explicit constructor ``wal_path``
        2. ``OMEM_WRITE_BUFFER_WAL_PATH`` env
        3. ``OMEM_DISABLE_WRITE_BUFFER_WAL=1`` → disabled
        4. Ephemeral backends (``:memory:`` SQLite / pure memory) → disabled
           so a global ``~/.omem/write_buffer.wal`` cannot poison dedup across
           processes and CI runs.
        5. Default ``~/.omem/write_buffer.wal``
        """
        if wal_path is not None:
            return wal_path
        flag = os.environ.get("OMEM_DISABLE_WRITE_BUFFER_WAL", "").strip().lower()
        if flag in ("1", "true", "yes", "on"):
            return ""
        env = os.environ.get("OMEM_WRITE_BUFFER_WAL_PATH", "").strip()
        if env:
            return env
        db_path = getattr(backend, "db_path", None)
        if db_path in (":memory:", ""):
            return ""
        backend_name = type(backend).__name__ if backend is not None else ""
        if backend_name in ("MemoryBackend", "InMemoryBackend"):
            return ""
        return _DEFAULT_WAL_PATH

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
        """Append a serialized memory to the WAL file with fsync.

        Encrypts with AES-256-GCM when OMEM_ENCRYPTION_KEY is set.
        """
        if not self._wal_enabled:
            return
        with self._wal_lock:
            try:
                line = self._serialize_memory(memory)
                enc_key = _wal_encryption_key()
                if enc_key:
                    line = _encrypt_wal_line(line, enc_key)
                with open(self._wal_path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
                    f.flush()
                    os.fsync(f.fileno())
            except Exception as exc:
                logger.warning("WAL append failed (non-fatal): %s", exc)

    def _wal_remove(self, persisted_ids: set) -> None:
        """Rewrite WAL excluding flushed IDs (atomic via os.replace)."""
        if not self._wal_enabled:
            return
        with self._wal_lock:
            if not os.path.exists(self._wal_path):
                return
            tmp_path = self._wal_path + ".tmp"
            try:
                kept_lines = []
                enc_key = _wal_encryption_key()
                with open(self._wal_path, "r", encoding="utf-8") as f:
                    for raw in f:
                        raw = raw.strip()
                        if not raw:
                            continue
                        try:
                            plain = raw
                            if raw.startswith("enc1:"):
                                if not enc_key:
                                    # Keep encrypted lines intact when key is absent.
                                    kept_lines.append(raw)
                                    continue
                                plain = _decrypt_wal_line(raw, enc_key)
                            d = json.loads(plain)
                            if d.get("id") not in persisted_ids:
                                kept_lines.append(raw)  # preserve original encoding
                        except Exception:
                            # Keep undecryptable/malformed lines rather than drop.
                            kept_lines.append(raw)

                with open(tmp_path, "w", encoding="utf-8") as f:
                    for line in kept_lines:
                        f.write(line + "\n")
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, self._wal_path)
            except Exception as exc:
                logger.warning("WAL cleanup failed (non-fatal): %s", exc)

    def _recover_from_wal(self) -> int:
        """Re-enqueue memories from WAL that haven't been persisted yet.

        Accepts both encrypted ('enc1:' prefix) and plaintext lines so that
        existing WAL files remain readable after OMEM_ENCRYPTION_KEY is added.
        """
        if not os.path.exists(self._wal_path):
            return 0

        recovered = 0
        enc_key = _wal_encryption_key()
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
                if line.startswith("enc1:"):
                    if enc_key:
                        line = _decrypt_wal_line(line, enc_key)
                    else:
                        logger.warning(
                            "WAL recovery: encrypted entry found but OMEM_ENCRYPTION_KEY is not set — skipping"
                        )
                        continue
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
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._worker, daemon=True, name="omem-write-buffer"
        )
        self._thread.start()
        logger.debug("Write buffer started (interval=%.1fs)", self._flush_interval)

    def stop(self) -> None:
        """Stop the background thread and flush remaining items."""
        self._running = False
        self._stop_event.set()
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
            self._stop_event.wait(self._flush_interval)
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
