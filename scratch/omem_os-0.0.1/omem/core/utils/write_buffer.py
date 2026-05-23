"""Async Write Buffer — decouples add() latency from persistence.

Accepts Memory objects into an in-memory queue and persists them
to the backend in a background thread. Makes add() near-zero latency.

v0.6.0 Performance boost (G).
"""

import logging
import queue
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)


class WriteBuffer:
    """Background persistence buffer.

    Usage::

        buf = WriteBuffer(backend=sqlite_backend)
        buf.enqueue(memory)  # returns immediately
        # ... background thread persists
        buf.flush()          # force-persist all pending
        buf.stop()           # graceful shutdown
    """

    def __init__(self, backend: Optional[object] = None, flush_interval: float = 1.0):
        self._queue: queue.Queue = queue.Queue()
        self._backend = backend
        self._flush_interval = flush_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._total_written = 0
        self._total_errors = 0

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
        self._queue.put(memory)

    def flush(self) -> int:
        """Force-persist all pending memories. Returns count written."""
        if self._backend is None:
            # Drain queue without persisting
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
            except Exception as e:
                self._total_errors += 1
                logger.error("Write buffer flush error: %s", e)
                # Re-enqueue failed items
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
