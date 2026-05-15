"""Async audit trail stored in a separate audit.db (WAL mode)."""

import json
import logging
import os
import queue
import sqlite3
import threading
import time
import uuid
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class AuditLogger:
    """Non-blocking audit trail that persists operations to a separate SQLite DB.

    All ``log()`` calls are non-blocking — they enqueue to an in-memory queue
    and a background thread flushes to ``~/.omem/audit.db``.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            db_path = os.path.expanduser("~/.omem/audit.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._db_path = db_path
        self._queue: queue.Queue = queue.Queue()
        self._running = True
        self._thread = threading.Thread(
            target=self._worker, daemon=True, name="omem-audit"
        )
        self._thread.start()
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id          TEXT PRIMARY KEY,
                ts          REAL NOT NULL,
                operation   TEXT NOT NULL,
                memory_id   TEXT DEFAULT '',
                namespace   TEXT DEFAULT '',
                trace_id    TEXT DEFAULT '',
                source      TEXT DEFAULT '',
                extra       TEXT DEFAULT '{}'
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_op ON audit_log(operation)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_ns ON audit_log(namespace)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts)")
        conn.commit()
        conn.close()

    def log(
        self,
        operation: str,
        memory_id: str = "",
        namespace: str = "",
        trace_id: str = "",
        source: str = "",
        **extra,
    ) -> None:
        """Enqueue an audit entry (non-blocking)."""
        entry = {
            "id": str(uuid.uuid4()),
            "ts": time.time(),
            "operation": operation,
            "memory_id": memory_id,
            "namespace": namespace,
            "trace_id": trace_id,
            "source": source,
            "extra": json.dumps(extra, default=str),
        }
        self._queue.put(entry)

    def _worker(self) -> None:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        while self._running:
            batch = []
            try:
                entry = self._queue.get(timeout=1.0)
                batch.append(entry)
                # Drain remaining queued items
                while not self._queue.empty():
                    try:
                        batch.append(self._queue.get_nowait())
                    except queue.Empty:
                        break
            except queue.Empty:
                continue

            if batch:
                try:
                    conn.executemany(
                        """INSERT OR IGNORE INTO audit_log
                           (id, ts, operation, memory_id, namespace, trace_id, source, extra)
                           VALUES (:id, :ts, :operation, :memory_id, :namespace,
                                   :trace_id, :source, :extra)""",
                        batch,
                    )
                    conn.commit()
                except Exception as exc:
                    logger.error("Audit flush error: %s", exc)

        # Final flush on shutdown
        remaining = []
        while not self._queue.empty():
            try:
                remaining.append(self._queue.get_nowait())
            except queue.Empty:
                break
        if remaining:
            try:
                conn.executemany(
                    """INSERT OR IGNORE INTO audit_log
                       (id, ts, operation, memory_id, namespace, trace_id, source, extra)
                       VALUES (:id, :ts, :operation, :memory_id, :namespace,
                               :trace_id, :source, :extra)""",
                    remaining,
                )
                conn.commit()
            except Exception as exc:
                logger.error("Audit final flush error: %s", exc)
        conn.close()

    def get_audit_log(
        self,
        limit: int = 100,
        operation: Optional[str] = None,
        namespace: Optional[str] = None,
        memory_id: Optional[str] = None,
        since_ts: Optional[float] = None,
    ) -> List[Dict]:
        """Query the audit log with optional filters."""
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            conditions = []
            params: list = []
            if operation:
                conditions.append("operation = ?")
                params.append(operation)
            if namespace:
                conditions.append("namespace = ?")
                params.append(namespace)
            if memory_id:
                conditions.append("memory_id = ?")
                params.append(memory_id)
            if since_ts is not None:
                conditions.append("ts >= ?")
                params.append(since_ts)

            where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
            params.append(limit)
            rows = conn.execute(
                f"SELECT * FROM audit_log {where} ORDER BY ts DESC LIMIT ?",
                params,
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def stop(self) -> None:
        """Graceful shutdown — waits for queue to drain."""
        self._running = False
        if self._thread.is_alive():
            self._thread.join(timeout=5.0)
