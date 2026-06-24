"""Governance layer — Phase 8 of the v2 implementation plan.

Builds on the existing partial foundations:
    - omem/security/audit.py      (audit trail)
    - omem/core/brain/quotas.py   (namespace quotas)
    - omem/core/brain/forgetting.py (forgetting engine)

Phase 8 adds: retention policy DSL, deletion workflows, RBAC primitives,
and compliance-safe export.

Implementation target: docs/roadmap/FULL_IMPLEMENTATION_PLAN.md Phase 8.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RetentionPolicy:
    """Rule for how long memories in a namespace should be kept."""

    namespace_pattern: str
    max_age_days: Optional[int] = None
    max_count: Optional[int] = None
    tier: Optional[str] = None  # MemoryTier value name


@dataclass
class DeletionPolicy:
    """Scope and behaviour for a deletion workflow."""

    scope: str  # user | namespace | org | memory_id
    id: str
    cascade: bool = True  # delete associated state snapshots too


@dataclass
class DeletionReport:
    """Summary returned after a delete_scope call."""

    deleted_memories: int = 0
    deleted_snapshots: int = 0
    deleted_audit_entries: int = 0
    errors: List[str] = field(default_factory=list)


@dataclass
class Role:
    """Basic RBAC role — enforced at the API gateway in cloud mode."""

    name: str  # admin | editor | viewer
    namespaces: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)  # read | write | delete | admin


class GovernanceOS:
    """V2 governance layer.

    ``GovernanceOS`` makes OMem safe for production systems. It controls
    what is kept, what is deleted, who can read or write, and provides
    a queryable audit trail.

    This class is a typed stub. All methods raise ``NotImplementedError``
    until Phase 8 is implemented.

    In local mode: single-user (all permissions, no enforcement).
    In cloud mode: RBAC enforced at the API gateway; policies enforced
    server-side.

    Example (after Phase 8)::

        gov = GovernanceOS(omem=agent.memory.omem)
        gov.set_policy(RetentionPolicy(
            namespace_pattern="org/acme/*",
            max_age_days=90,
        ))
        report = gov.delete_scope("user", user_id, cascade=True)
    """

    def set_policy(self, policy: RetentionPolicy) -> None:
        """Register a retention policy for a namespace pattern."""
        raise NotImplementedError("Phase 8 — see docs/roadmap/FULL_IMPLEMENTATION_PLAN.md")

    def audit(self, **filters: Any) -> List[Dict[str, Any]]:
        """Query the audit log with optional filters (namespace, op, time range)."""
        raise NotImplementedError("Phase 8 — see docs/roadmap/FULL_IMPLEMENTATION_PLAN.md")

    def delete_scope(
        self,
        scope: str,
        id: str,
        cascade: bool = True,
    ) -> DeletionReport:
        """Delete all data for a user, namespace, org, or specific memory ID."""
        raise NotImplementedError("Phase 8 — see docs/roadmap/FULL_IMPLEMENTATION_PLAN.md")

    def enforce_retention(self) -> Dict[str, int]:
        """Apply all active retention policies now. Returns counts of evicted items."""
        raise NotImplementedError("Phase 8 — see docs/roadmap/FULL_IMPLEMENTATION_PLAN.md")
