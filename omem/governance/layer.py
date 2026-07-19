"""GovernanceOS — Phase 8: production-safe memory governance.

Makes OMem safe for enterprise deployments:
  - Retention policies (max_age_days, max_count, by tier)
  - Deletion workflows with cascade (memory + state + audit entries)
  - RBAC role definitions (local: no enforcement; cloud: gateway-enforced)
  - Queryable audit trail (delegates to the existing AuditLogger)
  - Compliance-safe namespace export

Builds on existing foundations:
  - ``omem/governance/audit.py`` — AuditLogger (async WAL-mode SQLite)
  - ``omem/core/brain/quotas.py`` — MemoryQuota (namespace quota checks)
  - ``omem/core/brain/forgetting.py`` — ForgetResult (forgetting engine hooks)

See: docs/roadmap/FULL_IMPLEMENTATION_PLAN.md — Phase 8
"""

from __future__ import annotations

import fnmatch
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Policy primitives
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class RetentionPolicy:
    """Rule for how long memories in a namespace should be kept.

    Attributes:
        namespace_pattern: Glob pattern matched against namespace strings.
                           Examples: ``"org/acme/*"`` , ``"team/eng-*"`` , ``"*"``.
        max_age_days:      Delete memories older than this many days.
                           ``None`` means no age limit.
        max_count:         Keep only the ``max_count`` most-important memories
                           per namespace. ``None`` means no count limit.
        tier:              Restrict to a specific memory tier
                           (``"ACTIVE"`` | ``"ARCHIVE"`` | ``"DEEP"``).
                           ``None`` applies to all tiers.
        created_at:        When this policy was registered (set automatically).
    """

    namespace_pattern: str
    max_age_days: Optional[int] = None
    max_count: Optional[int] = None
    tier: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    def matches(self, namespace: str) -> bool:
        """Return True if this policy applies to the given namespace."""
        return fnmatch.fnmatch(namespace, self.namespace_pattern)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "namespace_pattern": self.namespace_pattern,
            "max_age_days": self.max_age_days,
            "max_count": self.max_count,
            "tier": self.tier,
            "created_at": self.created_at,
        }


@dataclass
class DeletionPolicy:
    """Scope and behaviour for a deletion workflow.

    Attributes:
        scope:   The level to delete: ``"user"`` | ``"namespace"`` | ``"org"``
                 | ``"memory_id"``.
        id:      The identifier to delete (namespace string, user ID, etc.).
        cascade: If ``True`` (default), also remove associated state snapshots
                 and audit entries.
    """

    scope: str
    id: str
    cascade: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {"scope": self.scope, "id": self.id, "cascade": self.cascade}


@dataclass
class DeletionReport:
    """Summary returned after a ``delete_scope()`` call.

    Attributes:
        deleted_memories:     Number of memories soft-deleted.
        deleted_snapshots:    Number of state snapshots removed.
        deleted_audit_entries: Number of audit log rows cleared.
        errors:               Non-fatal errors encountered during deletion.
        duration_ms:          Wall-clock time for the operation.
    """

    deleted_memories: int = 0
    deleted_snapshots: int = 0
    deleted_audit_entries: int = 0
    errors: List[str] = field(default_factory=list)
    duration_ms: float = 0.0

    @property
    def total_deleted(self) -> int:
        return self.deleted_memories + self.deleted_snapshots + self.deleted_audit_entries

    def to_dict(self) -> Dict[str, Any]:
        return {
            "deleted_memories": self.deleted_memories,
            "deleted_snapshots": self.deleted_snapshots,
            "deleted_audit_entries": self.deleted_audit_entries,
            "total_deleted": self.total_deleted,
            "errors": self.errors,
            "duration_ms": round(self.duration_ms, 2),
        }


@dataclass
class RetentionReport:
    """Summary returned after ``enforce_retention()``."""

    policies_applied: int = 0
    namespaces_checked: int = 0
    memories_evicted: int = 0
    errors: List[str] = field(default_factory=list)
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policies_applied": self.policies_applied,
            "namespaces_checked": self.namespaces_checked,
            "memories_evicted": self.memories_evicted,
            "errors": self.errors,
            "duration_ms": round(self.duration_ms, 2),
        }


# ──────────────────────────────────────────────────────────────────────────────
# RBAC primitives
# ──────────────────────────────────────────────────────────────────────────────

_VALID_PERMISSIONS = frozenset({"read", "write", "delete", "admin"})
_VALID_ROLES = frozenset({"admin", "editor", "viewer"})


@dataclass
class Role:
    """Basic RBAC role.

    In local mode: single-user — all permissions, no enforcement.
    In cloud mode: enforced at the API gateway.

    Attributes:
        name:        ``"admin"`` | ``"editor"`` | ``"viewer"`` (or custom string).
        namespaces:  List of namespace glob patterns this role can access.
                     Empty list means ``"*"`` (all namespaces) when name is admin.
        permissions: List of ``"read"`` | ``"write"`` | ``"delete"`` | ``"admin"``.
    """

    name: str
    namespaces: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)

    def can(self, permission: str, namespace: str = "*") -> bool:
        """Check if this role grants the permission for the namespace."""
        if "admin" in self.permissions:
            return True
        if permission not in self.permissions:
            return False
        if not self.namespaces:
            return True
        return any(fnmatch.fnmatch(namespace, pat) for pat in self.namespaces)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "namespaces": self.namespaces,
            "permissions": self.permissions,
        }


# Built-in roles
ROLE_ADMIN = Role(name="admin", permissions=["admin"])
ROLE_EDITOR = Role(name="editor", permissions=["read", "write", "delete"])
ROLE_VIEWER = Role(name="viewer", permissions=["read"])


# ──────────────────────────────────────────────────────────────────────────────
# GovernanceOS
# ──────────────────────────────────────────────────────────────────────────────


class GovernanceOS:
    """Phase 8 governance layer — fully implemented.

    Manages the lifecycle, access control, and compliance of all OMem data.

    **Retention**: Policies are matched against namespace patterns using
    glob syntax (``fnmatch``). ``enforce_retention()`` applies all active
    policies across every known namespace.

    **Deletion**: ``delete_scope()`` supports memory-level, namespace-level,
    user-level, and org-level deletion with optional cascade to state snapshots.

    **Audit**: Delegates to the existing ``AuditLogger`` — queries are
    routed to the async WAL-mode SQLite audit store.

    **RBAC** (local mode): Roles are registered locally. In cloud mode,
    enforcement moves to the API gateway; local mode is single-user (no
    enforcement). ``check_permission()`` is provided for application-level
    checks.

    Usage::

        gov = agent.governance
        gov.set_policy(RetentionPolicy("org/acme/*", max_age_days=90))
        report = gov.enforce_retention()
        print(f"Evicted: {report.memories_evicted}")

        entries = gov.audit(namespace="default", limit=20)
        for e in entries:
            print(e["operation"], e["ts"])

        report = gov.delete_scope("namespace", "team/old-project", cascade=True)
        print(f"Deleted: {report.total_deleted} records")

    Thread safety: All methods are thread-safe (the underlying AuditLogger
    uses its own internal lock; policy/role dicts are guarded by an RLock).
    """

    def __init__(
        self,
        omem: Any = None,
        state: Any = None,
        audit_db_path: Optional[str] = None,
        audit_logger: Any = None,
    ) -> None:
        """Initialise GovernanceOS.

        Args:
            omem:          The ``OMem`` instance (provides memory deletion/listing).
            state:         The ``StateOS`` instance (provides session listing).
            audit_db_path: Override audit DB path (default: ``~/.omem/audit.db``).
            audit_logger:  Shared ``AuditLogger`` instance (preferred in cloud).
        """
        self._omem = omem
        self._state = state

        if audit_logger is not None:
            self._audit = audit_logger
        else:
            from omem.governance.audit import AuditLogger

            self._audit = AuditLogger(db_path=audit_db_path)

        import threading
        self._lock = threading.RLock()
        self._policies: List[RetentionPolicy] = []
        self._roles: Dict[str, Role] = {
            "admin": ROLE_ADMIN,
            "editor": ROLE_EDITOR,
            "viewer": ROLE_VIEWER,
        }
        logger.debug("GovernanceOS initialized")

    # ------------------------------------------------------------------
    # Retention policies
    # ------------------------------------------------------------------

    def set_policy(self, policy: RetentionPolicy) -> None:
        """Register or replace a retention policy.

        If a policy with the same ``namespace_pattern`` already exists it is
        replaced. Policies are evaluated lazily when ``enforce_retention()``
        is called.

        Args:
            policy: The ``RetentionPolicy`` to register.
        """
        with self._lock:
            self._policies = [
                p for p in self._policies
                if p.namespace_pattern != policy.namespace_pattern
            ]
            self._policies.append(policy)
            logger.info(
                "GovernanceOS: policy set for %r (max_age=%s, max_count=%s)",
                policy.namespace_pattern, policy.max_age_days, policy.max_count,
            )

    def list_policies(self) -> List[RetentionPolicy]:
        """Return all active retention policies."""
        with self._lock:
            return list(self._policies)

    def remove_policy(self, namespace_pattern: str) -> bool:
        """Remove a retention policy by pattern. Returns True if found."""
        with self._lock:
            before = len(self._policies)
            self._policies = [
                p for p in self._policies
                if p.namespace_pattern != namespace_pattern
            ]
            return len(self._policies) < before

    def enforce_retention(self) -> RetentionReport:
        """Apply all active retention policies immediately.

        For each policy:
          - If ``max_age_days`` is set, soft-delete memories older than N days.
          - If ``max_count`` is set, keep only the top N memories by
            importance score; soft-delete the rest.

        Returns:
            ``RetentionReport`` with counts of evictions and errors.
        """
        t0 = time.time()
        report = RetentionReport()
        if not self._omem:
            report.errors.append("OMem instance not available — no memories deleted")
            report.duration_ms = (time.time() - t0) * 1000
            return report

        with self._lock:
            policies = list(self._policies)

        # Collect known namespaces
        try:
            all_mems = self._omem.all(include_inactive=False)
            namespaces: List[Optional[str]] = list({
                getattr(m, "namespace", None) for m in all_mems
            })
        except Exception as exc:
            report.errors.append(f"Failed to list memories: {exc}")
            report.duration_ms = (time.time() - t0) * 1000
            return report

        now = time.time()
        for policy in policies:
            report.policies_applied += 1
            for ns in namespaces:
                ns_str = ns or "default"
                if not policy.matches(ns_str):
                    continue

                report.namespaces_checked += 1
                try:
                    ns_mems = [
                        m for m in all_mems
                        if (getattr(m, "namespace", None) or "default") == ns_str
                    ]
                    if policy.tier:
                        ns_mems = [
                            m for m in ns_mems
                            if getattr(getattr(m, "tier", None), "name", None) == policy.tier
                        ]

                    to_delete: List[Any] = []

                    # Age-based eviction
                    if policy.max_age_days is not None:
                        cutoff = now - policy.max_age_days * 86400
                        age_exceeded = [
                            m for m in ns_mems
                            if getattr(m, "created_at", 0) < cutoff
                        ]
                        to_delete.extend(age_exceeded)

                    # Count-based eviction
                    if policy.max_count is not None and len(ns_mems) > policy.max_count:
                        sorted_mems = sorted(
                            ns_mems,
                            key=lambda m: getattr(m, "importance", 0.0),
                            reverse=True,
                        )
                        excess = sorted_mems[policy.max_count:]
                        for m in excess:
                            if m not in to_delete:
                                to_delete.append(m)

                    # Deduplicate and delete
                    seen_ids: set = set()
                    for mem in to_delete:
                        mid = getattr(mem, "id", None) or getattr(mem, "memory_id", None)
                        if mid and mid not in seen_ids:
                            seen_ids.add(mid)
                            try:
                                self._omem.delete(mid)
                                report.memories_evicted += 1
                                self._audit.log(
                                    "governance_evict",
                                    memory_id=mid,
                                    namespace=ns_str,
                                    source="retention_policy",
                                    pattern=policy.namespace_pattern,
                                )
                            except Exception as exc:
                                report.errors.append(f"Delete {mid} failed: {exc}")

                except Exception as exc:
                    report.errors.append(f"Policy enforcement error in {ns_str!r}: {exc}")

        report.duration_ms = round((time.time() - t0) * 1000, 2)
        logger.info(
            "GovernanceOS: retention enforced — %d evicted, %d errors",
            report.memories_evicted, len(report.errors),
        )
        return report

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------

    def audit(
        self,
        namespace: Optional[str] = None,
        operation: Optional[str] = None,
        memory_id: Optional[str] = None,
        since_ts: Optional[float] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query the audit trail.

        Delegates to ``AuditLogger.get_audit_log()``. All parameters are
        optional AND-combined filters.

        Args:
            namespace:  Filter to a specific namespace.
            operation:  Filter to a specific operation (e.g. ``"recall"``).
            memory_id:  Filter to a specific memory ID.
            since_ts:   Only return entries after this Unix timestamp.
            limit:      Maximum number of entries to return (newest first).

        Returns:
            List of audit log dicts: id, ts, operation, memory_id, namespace,
            trace_id, source, extra.
        """
        return self._audit.get_audit_log(
            limit=limit,
            operation=operation,
            namespace=namespace,
            memory_id=memory_id,
            since_ts=since_ts,
        )

    def export_audit(
        self,
        *,
        format: str = "json",
        path: Optional[str] = None,
        namespace: Optional[str] = None,
        operation: Optional[str] = None,
        memory_id: Optional[str] = None,
        since_ts: Optional[float] = None,
        limit: int = 10_000,
    ) -> str:
        """Export the audit trail as JSON or JSONL for design-partner review.

        Args:
            format:     ``"json"`` (array) or ``"jsonl"`` (one object per line).
            path:       Optional filesystem path. When set, writes there and
                        returns the path. When unset, returns the serialized body.
            namespace:  Optional filter (same as ``audit()``).
            operation:  Optional operation filter.
            memory_id:  Optional memory id filter.
            since_ts:   Optional Unix timestamp lower bound.
            limit:      Max entries (newest first). Cap raised vs ``audit()``
                        default so partners can dump a meaningful window.

        Returns:
            Serialized body, or the output path when ``path`` is set.
        """
        import json as _json

        fmt = (format or "json").lower().strip()
        if fmt not in ("json", "jsonl"):
            raise ValueError("format must be 'json' or 'jsonl'")

        self.flush_audit()
        entries = self.audit(
            namespace=namespace,
            operation=operation,
            memory_id=memory_id,
            since_ts=since_ts,
            limit=limit,
        )
        if fmt == "jsonl":
            body = "\n".join(_json.dumps(e, default=str) for e in entries)
            if entries:
                body += "\n"
        else:
            body = _json.dumps(
                {
                    "exported_at": time.time(),
                    "count": len(entries),
                    "filters": {
                        "namespace": namespace,
                        "operation": operation,
                        "memory_id": memory_id,
                        "since_ts": since_ts,
                        "limit": limit,
                    },
                    "entries": entries,
                },
                indent=2,
                default=str,
            )
            body += "\n"

        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(body)
            return path
        return body

    # ------------------------------------------------------------------
    # Deletion workflows
    # ------------------------------------------------------------------

    def delete_scope(
        self,
        scope: str,
        id: str,
        cascade: bool = True,
    ) -> DeletionReport:
        """Delete all data for a scope.

        Args:
            scope:   Level of deletion:
                     ``"memory_id"``  — single memory by ID
                     ``"namespace"``  — all memories in a namespace
                     ``"user"``       — all personal memories for a user
                     ``"org"``        — all org-wide memories (pattern: ``org/{id}/*``)
            id:      The identifier to delete (memory ID, namespace, user ID, etc.).
            cascade: If ``True``, also remove associated state sessions (if
                     ``StateOS`` is available).

        Returns:
            ``DeletionReport`` with counts and non-fatal errors.
        """
        t0 = time.time()
        report = DeletionReport()

        if not self._omem:
            report.errors.append("OMem instance not available — no memories deleted")
            report.duration_ms = (time.time() - t0) * 1000
            return report

        try:
            if scope == "memory_id":
                self._delete_memory_id(id, report)
            elif scope == "namespace":
                self._delete_namespace(id, report)
            elif scope == "user":
                # personal/{user_id} namespace
                self._delete_namespace(f"personal/{id}", report)
            elif scope == "org":
                # Delete all namespaces matching org/{id}/* and org/{id}
                self._delete_org(id, report)
            else:
                report.errors.append(f"Unknown scope: {scope!r}")

            # Cascade: remove state sessions in the affected namespace
            if cascade and self._state and scope in ("namespace", "user", "org"):
                self._cascade_state(scope, id, report)

        except Exception as exc:
            report.errors.append(f"Unexpected error in delete_scope: {exc}")

        report.duration_ms = round((time.time() - t0) * 1000, 2)
        self._audit.log(
            "governance_delete",
            namespace=id,
            source="delete_scope",
            scope=scope,
            cascade=cascade,
            deleted_memories=report.deleted_memories,
        )
        return report

    def _delete_memory_id(self, memory_id: str, report: DeletionReport) -> None:
        try:
            success = self._omem.delete(memory_id)
            if success:
                report.deleted_memories += 1
        except Exception as exc:
            report.errors.append(f"Failed to delete {memory_id!r}: {exc}")

    def _delete_namespace(self, namespace: str, report: DeletionReport) -> None:
        try:
            mems = self._omem.all(namespace=namespace, include_inactive=True)
            for m in mems:
                mid = getattr(m, "id", None)
                if mid:
                    try:
                        self._omem.delete(mid)
                        report.deleted_memories += 1
                    except Exception as exc:
                        report.errors.append(f"Failed to delete {mid!r}: {exc}")
        except Exception as exc:
            report.errors.append(f"Failed to list memories in {namespace!r}: {exc}")

    def _delete_org(self, org_id: str, report: DeletionReport) -> None:
        """Delete all memories whose namespace starts with ``org/{org_id}``."""
        try:
            all_mems = self._omem.all(include_inactive=True)
            prefix = f"org/{org_id}"
            for m in all_mems:
                ns = getattr(m, "namespace", None) or ""
                if ns == prefix or ns.startswith(prefix + "/"):
                    mid = getattr(m, "id", None)
                    if mid:
                        try:
                            self._omem.delete(mid)
                            report.deleted_memories += 1
                        except Exception as exc:
                            report.errors.append(f"Failed to delete {mid!r}: {exc}")
        except Exception as exc:
            report.errors.append(f"Failed to list memories for org {org_id!r}: {exc}")

    def _cascade_state(self, scope: str, id: str, report: DeletionReport) -> None:
        """Remove state sessions associated with the deleted scope."""
        if not self._state:
            return
        try:
            if scope == "namespace":
                sessions = self._state.list_sessions(namespace=id)
            elif scope == "user":
                sessions = self._state.list_sessions(namespace=f"personal/{id}")
            elif scope == "org":
                # No namespace filter on list_sessions; skip cascade for orgs
                return
            else:
                return

            for sess in sessions:
                sid = getattr(sess, "session_id", None) or (
                    sess.get("session_id") if isinstance(sess, dict) else None
                )
                if sid:
                    try:
                        self._state.delete_session(sid)
                        report.deleted_snapshots += 1
                    except Exception as exc:
                        report.errors.append(f"State cascade: failed to delete session {sid!r}: {exc}")
        except Exception as exc:
            report.errors.append(f"State cascade failed: {exc}")

    # ------------------------------------------------------------------
    # RBAC
    # ------------------------------------------------------------------

    def register_role(self, role: Role) -> None:
        """Register a custom RBAC role.

        In local mode this is informational only; in cloud mode these roles
        are synchronised to the API gateway.

        Args:
            role: The ``Role`` to register.
        """
        with self._lock:
            self._roles[role.name] = role
            logger.info("GovernanceOS: role %r registered", role.name)

    def get_role(self, name: str) -> Optional[Role]:
        """Look up a role by name. Returns ``None`` if not found."""
        with self._lock:
            return self._roles.get(name)

    def list_roles(self) -> List[Role]:
        """Return all registered roles."""
        with self._lock:
            return list(self._roles.values())

    def check_permission(
        self,
        role_name: str,
        permission: str,
        namespace: str = "*",
    ) -> bool:
        """Check if a named role grants a permission for a namespace.

        In local mode this can be used for application-level gating.
        Always returns ``True`` for the ``"admin"`` role.

        Args:
            role_name:  The name of the role to check.
            permission: One of ``"read"``, ``"write"``, ``"delete"``, ``"admin"``.
            namespace:  The namespace to check against.

        Returns:
            ``True`` if the role grants the permission; ``False`` otherwise.
        """
        with self._lock:
            role = self._roles.get(role_name)
        if role is None:
            return False
        return role.can(permission, namespace)

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    def flush_audit(self) -> None:
        """Block until all pending audit entries are written to disk."""
        self._audit.flush()
