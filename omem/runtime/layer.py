"""RuntimeOS — Phase 9: multi-agent runtime coordination.

Supports multiple agents sharing state safely within a namespace.
Agents register themselves, emit heartbeats, sync their state, and
recover after crashes without losing progress.

Architecture:
  - In-memory registry backed by SQLite for crash persistence
  - Agent heartbeat tracking with stale-agent eviction
  - State sync via StateOS (reads latest checkpoint)
  - Crash recovery via StateOS.resume_latest()
  - Scheduler hooks: sleep/maintenance per namespace

Exit criteria (from the implementation plan):
  "Agent B reads state written by Agent A in same namespace."

See: docs/roadmap/FULL_IMPLEMENTATION_PLAN.md — Phase 9
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Public data types
# ──────────────────────────────────────────────────────────────────────────────

_VALID_STATUSES = frozenset({"active", "idle", "crashed", "done"})


@dataclass
class AgentRegistration:
    """A registered agent entry in the runtime registry.

    Attributes:
        agent_id:       Unique identifier for the agent process/instance.
        session_id:     The StateOS session this agent is operating on.
        namespace:      The namespace this agent belongs to.
        capabilities:   List of capability strings (e.g. ``["filesystem", "git"]``).
        status:         ``"active"`` | ``"idle"`` | ``"crashed"`` | ``"done"``.
        registered_at:  Unix timestamp when this agent first registered.
        last_heartbeat: Unix timestamp of the most recent heartbeat.
        metadata:       Arbitrary key-value pairs for agent-specific context.
    """

    agent_id: str
    session_id: str
    namespace: str = "default"
    capabilities: List[str] = field(default_factory=list)
    status: str = "active"
    registered_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "namespace": self.namespace,
            "capabilities": self.capabilities,
            "status": self.status,
            "registered_at": self.registered_at,
            "last_heartbeat": self.last_heartbeat,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> AgentRegistration:
        return cls(
            agent_id=d["agent_id"],
            session_id=d["session_id"],
            namespace=d.get("namespace", "default"),
            capabilities=d.get("capabilities", []),
            status=d.get("status", "active"),
            registered_at=d.get("registered_at", 0.0),
            last_heartbeat=d.get("last_heartbeat", 0.0),
            metadata=d.get("metadata", {}),
        )


# ──────────────────────────────────────────────────────────────────────────────
# SQLite persistence for the registry
# ──────────────────────────────────────────────────────────────────────────────


class _RegistryDB:
    """Thin SQLite wrapper for persisting agent registration across crashes."""

    _SCHEMA = """
        CREATE TABLE IF NOT EXISTS agent_registry (
            agent_id       TEXT PRIMARY KEY,
            session_id     TEXT NOT NULL,
            namespace      TEXT NOT NULL DEFAULT 'default',
            capabilities   TEXT NOT NULL DEFAULT '[]',
            status         TEXT NOT NULL DEFAULT 'active',
            registered_at  REAL NOT NULL,
            last_heartbeat REAL NOT NULL,
            metadata       TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_reg_ns     ON agent_registry(namespace);
        CREATE INDEX IF NOT EXISTS idx_reg_status ON agent_registry(status);
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        if db_path != ":memory:":
            parent = os.path.dirname(db_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
        self._init()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init(self) -> None:
        with self._conn() as conn:
            conn.executescript(self._SCHEMA)

    def upsert(self, reg: AgentRegistration) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO agent_registry
                    (agent_id, session_id, namespace, capabilities, status,
                     registered_at, last_heartbeat, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(agent_id) DO UPDATE SET
                    session_id     = excluded.session_id,
                    namespace      = excluded.namespace,
                    capabilities   = excluded.capabilities,
                    status         = excluded.status,
                    last_heartbeat = excluded.last_heartbeat,
                    metadata       = excluded.metadata
                """,
                (
                    reg.agent_id,
                    reg.session_id,
                    reg.namespace,
                    json.dumps(reg.capabilities),
                    reg.status,
                    reg.registered_at,
                    reg.last_heartbeat,
                    json.dumps(reg.metadata, default=str),
                ),
            )

    def get(self, agent_id: str) -> Optional[AgentRegistration]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM agent_registry WHERE agent_id = ?", (agent_id,)
            ).fetchone()
        if row is None:
            return None
        return self._row_to_reg(row)

    def list_by_namespace(
        self,
        namespace: str,
        status: Optional[str] = None,
    ) -> List[AgentRegistration]:
        with self._conn() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM agent_registry WHERE namespace = ? AND status = ?",
                    (namespace, status),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM agent_registry WHERE namespace = ?",
                    (namespace,),
                ).fetchall()
        return [self._row_to_reg(r) for r in rows]

    def update_heartbeat(self, agent_id: str, ts: float, status: Optional[str] = None) -> bool:
        with self._conn() as conn:
            if status:
                cur = conn.execute(
                    "UPDATE agent_registry SET last_heartbeat = ?, status = ? WHERE agent_id = ?",
                    (ts, status, agent_id),
                )
            else:
                cur = conn.execute(
                    "UPDATE agent_registry SET last_heartbeat = ? WHERE agent_id = ?",
                    (ts, agent_id),
                )
        return cur.rowcount > 0

    def delete(self, agent_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM agent_registry WHERE agent_id = ?", (agent_id,)
            )
        return cur.rowcount > 0

    def evict_stale(self, max_idle_seconds: float) -> int:
        """Mark agents with no heartbeat as 'crashed'. Return count updated."""
        cutoff = time.time() - max_idle_seconds
        with self._conn() as conn:
            cur = conn.execute(
                """
                UPDATE agent_registry SET status = 'crashed'
                WHERE last_heartbeat < ? AND status = 'active'
                """,
                (cutoff,),
            )
        return cur.rowcount

    @staticmethod
    def _row_to_reg(row: sqlite3.Row) -> AgentRegistration:
        return AgentRegistration(
            agent_id=row["agent_id"],
            session_id=row["session_id"],
            namespace=row["namespace"],
            capabilities=json.loads(row["capabilities"]),
            status=row["status"],
            registered_at=row["registered_at"],
            last_heartbeat=row["last_heartbeat"],
            metadata=json.loads(row["metadata"]),
        )


# ──────────────────────────────────────────────────────────────────────────────
# RuntimeOS — public API
# ──────────────────────────────────────────────────────────────────────────────


class RuntimeOS:
    """Phase 9 runtime coordination layer — fully implemented.

    Manages multi-agent environments where multiple agents share state
    within a namespace. Key guarantees:

    1. **Registration persistence** — agent registrations survive process
       crashes via a WAL-mode SQLite registry.
    2. **State sync** — ``sync()`` retrieves the latest authoritative state
       payload for a session from ``StateOS``.
    3. **Crash recovery** — ``recover()`` finds an agent's last checkpoint
       and returns the recoverable state payload.
    4. **Heartbeat tracking** — ``heartbeat()`` updates the last-seen
       timestamp; ``evict_stale()`` marks silent agents as ``"crashed"``.

    Usage::

        runtime = agent.runtime
        runtime.register("researcher", session_id="sess-1",
                         capabilities=["web_search", "rag"])
        runtime.register("coder", session_id="sess-2",
                         capabilities=["filesystem", "git"])

        agents = runtime.list_agents("default", status="active")
        print([a.agent_id for a in agents])  # ["researcher", "coder"]

        state = runtime.sync("sess-1")
        recovered = runtime.recover("researcher")

    Thread safety: All methods are thread-safe (in-memory dict + RLock for
    fast path; SQLite for persistence).
    """

    DEFAULT_STALE_SECONDS: float = 300.0   # 5 minutes
    DEFAULT_DB_PATH: str = os.path.expanduser("~/.omem/runtime.db")

    def __init__(
        self,
        state: Any = None,
        db_path: Optional[str] = None,
    ) -> None:
        """Initialise RuntimeOS.

        Args:
            state:    ``StateOS`` instance for state sync and crash recovery.
            db_path:  SQLite DB path for registry persistence.
                      Defaults to ``~/.omem/runtime.db``.
        """
        self._state = state
        self._db = _RegistryDB(db_path or self.DEFAULT_DB_PATH)
        self._in_mem: Dict[str, AgentRegistration] = {}
        self._lock = threading.RLock()
        self._load_from_db()
        logger.debug("RuntimeOS initialized (db=%s)", db_path or self.DEFAULT_DB_PATH)

    # ------------------------------------------------------------------
    # Bootstrap: load persisted registrations into memory
    # ------------------------------------------------------------------

    def _load_from_db(self) -> None:
        """Restore in-memory registry from SQLite on startup."""
        try:
            # List all agents by querying the DB directly
            with sqlite3.connect(self._db._db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM agent_registry WHERE status != 'done'"
                ).fetchall()
            with self._lock:
                for row in rows:
                    reg = _RegistryDB._row_to_reg(row)
                    self._in_mem[reg.agent_id] = reg
            logger.debug("RuntimeOS: loaded %d agents from registry DB", len(self._in_mem))
        except Exception as exc:
            logger.warning("RuntimeOS: failed to load registry from DB: %s", exc)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        agent_id: str,
        session_id: str,
        namespace: str = "default",
        capabilities: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AgentRegistration:
        """Register an agent with its active session.

        If the agent is already registered, the existing registration is
        updated with the new session_id and status is set to ``"active"``.

        Args:
            agent_id:    Unique identifier for the agent.
            session_id:  The StateOS session this agent is operating on.
            namespace:   The namespace this agent belongs to.
            capabilities: Optional list of capability strings.
            metadata:    Optional key-value context.

        Returns:
            The ``AgentRegistration`` that was created or updated.
        """
        now = time.time()
        with self._lock:
            existing = self._in_mem.get(agent_id)
            reg = AgentRegistration(
                agent_id=agent_id,
                session_id=session_id,
                namespace=namespace,
                capabilities=capabilities or [],
                status="active",
                registered_at=existing.registered_at if existing else now,
                last_heartbeat=now,
                metadata=metadata or {},
            )
            self._in_mem[agent_id] = reg

        try:
            self._db.upsert(reg)
        except Exception as exc:
            logger.warning("RuntimeOS.register: DB upsert failed: %s", exc)

        logger.info("RuntimeOS: registered agent %r → session %r", agent_id, session_id)
        return reg

    def deregister(self, agent_id: str) -> bool:
        """Mark an agent as done and remove it from the active registry.

        Args:
            agent_id: The agent to deregister.

        Returns:
            ``True`` if the agent was found and deregistered.
        """
        with self._lock:
            reg = self._in_mem.pop(agent_id, None)

        if reg is not None:
            try:
                self._db.update_heartbeat(agent_id, time.time(), status="done")
            except Exception as exc:
                logger.warning("RuntimeOS.deregister: DB update failed: %s", exc)
            logger.info("RuntimeOS: deregistered agent %r", agent_id)
            return True
        return False

    # ------------------------------------------------------------------
    # Heartbeat
    # ------------------------------------------------------------------

    def heartbeat(
        self,
        agent_id: str,
        status: Optional[str] = None,
    ) -> bool:
        """Update the last-seen timestamp for an agent.

        Call this periodically (e.g. every 30 seconds) to prevent the
        agent from being evicted by ``evict_stale()``.

        Args:
            agent_id: The agent to update.
            status:   Optional new status (e.g. ``"idle"``, ``"active"``).

        Returns:
            ``True`` if the agent was found; ``False`` if it is not registered.
        """
        now = time.time()
        with self._lock:
            reg = self._in_mem.get(agent_id)
            if reg is None:
                return False
            reg.last_heartbeat = now
            if status and status in _VALID_STATUSES:
                reg.status = status

        try:
            self._db.update_heartbeat(agent_id, now, status=status)
        except Exception as exc:
            logger.warning("RuntimeOS.heartbeat: DB update failed: %s", exc)
        return True

    def evict_stale(
        self,
        max_idle_seconds: Optional[float] = None,
    ) -> List[str]:
        """Mark agents that haven't heartbeated as ``"crashed"``.

        Args:
            max_idle_seconds: Agents silent for longer than this are evicted.
                              Defaults to ``DEFAULT_STALE_SECONDS`` (300s).

        Returns:
            List of agent IDs that were marked as crashed.
        """
        idle = max_idle_seconds if max_idle_seconds is not None else self.DEFAULT_STALE_SECONDS
        cutoff = time.time() - idle
        evicted: List[str] = []
        with self._lock:
            for agent_id, reg in self._in_mem.items():
                if reg.status == "active" and reg.last_heartbeat < cutoff:
                    reg.status = "crashed"
                    evicted.append(agent_id)

        if evicted:
            try:
                self._db.evict_stale(idle)
            except Exception as exc:
                logger.warning("RuntimeOS.evict_stale: DB update failed: %s", exc)
            logger.warning("RuntimeOS: evicted stale agents: %s", evicted)
        return evicted

    # ------------------------------------------------------------------
    # State access
    # ------------------------------------------------------------------

    def sync(self, session_id: str) -> Dict[str, Any]:
        """Retrieve the latest state payload for a session.

        Other agents can call this to read state written by a peer agent
        in the same namespace, enabling cross-agent state sharing.

        Args:
            session_id: The session to sync.

        Returns:
            The latest ``StatePayload`` serialised as a dict.

        Raises:
            RuntimeError: If StateOS is not available or session not found.
        """
        if not self._state:
            raise RuntimeError("StateOS not available — pass state= to RuntimeOS")

        try:
            payload = self._state.load(session_id)
        except Exception as exc:
            raise RuntimeError(f"sync: failed to load session {session_id!r}: {exc}") from exc

        return {
            "session_id": payload.session_id,
            "goal": payload.goal,
            "status": payload.status,
            "step": payload.step,
            "plan": payload.plan,
            "namespace": payload.namespace,
            "updated_at": payload.updated_at,
            "version": payload.version,
        }

    def recover(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Find the latest checkpoint for a crashed agent and return its state.

        This implements the standard crash recovery pattern:
          1. Look up the agent's session ID in the registry.
          2. Ask StateOS for the most recent checkpoint.
          3. Return the recovered ``StatePayload`` as a dict.

        Args:
            agent_id: The agent to recover.

        Returns:
            Recovered state dict, or ``None`` if no checkpoint is found.
        """
        if not self._state:
            logger.warning("RuntimeOS.recover: StateOS not available")
            return None

        with self._lock:
            reg = self._in_mem.get(agent_id)
        if reg is None:
            # Try DB fallback
            reg = self._db.get(agent_id)
        if reg is None:
            logger.warning("RuntimeOS.recover: agent %r not found", agent_id)
            return None

        try:
            payload = self._state.resume_latest(reg.session_id)
        except Exception as exc:
            logger.warning(
                "RuntimeOS.recover: no checkpoint for %r / session %r: %s",
                agent_id, reg.session_id, exc,
            )
            return None

        # Re-register with active status after recovery
        self.register(
            agent_id=agent_id,
            session_id=reg.session_id,
            namespace=reg.namespace,
            capabilities=reg.capabilities,
            metadata={**reg.metadata, "recovered": True},
        )
        return {
            "session_id": payload.session_id,
            "goal": payload.goal,
            "status": payload.status,
            "step": payload.step,
            "plan": payload.plan,
            "namespace": payload.namespace,
            "updated_at": payload.updated_at,
            "recovered_for_agent": agent_id,
        }

    # ------------------------------------------------------------------
    # Registry queries
    # ------------------------------------------------------------------

    def list_agents(
        self,
        namespace: str,
        status: Optional[str] = None,
    ) -> List[AgentRegistration]:
        """List agents registered in a namespace.

        Args:
            namespace: The namespace to query.
            status:    Optional filter: ``"active"`` | ``"idle"`` |
                       ``"crashed"`` | ``"done"``.

        Returns:
            List of ``AgentRegistration`` objects.
        """
        with self._lock:
            agents = [
                reg for reg in self._in_mem.values()
                if reg.namespace == namespace
            ]
        if status:
            agents = [a for a in agents if a.status == status]
        return sorted(agents, key=lambda a: a.registered_at)

    def get_agent(self, agent_id: str) -> Optional[AgentRegistration]:
        """Return the registration for a specific agent, or None."""
        with self._lock:
            reg = self._in_mem.get(agent_id)
        if reg is None:
            reg = self._db.get(agent_id)
        return reg

    def namespace_summary(self, namespace: str) -> Dict[str, Any]:
        """Return a health summary for all agents in a namespace.

        Returns:
            Dict with: active, idle, crashed, done, total counts + list of agents.
        """
        agents = self.list_agents(namespace)
        by_status: Dict[str, int] = {"active": 0, "idle": 0, "crashed": 0, "done": 0}
        for a in agents:
            by_status[a.status] = by_status.get(a.status, 0) + 1
        return {
            "namespace": namespace,
            "total": len(agents),
            **by_status,
            "agents": [a.to_dict() for a in agents],
        }
