"""V2 governance layer — Phase 8 of the implementation plan.

Purpose: make production AI memory controllable — retention policies,
audit queries, namespace deletion, RBAC for cloud deployments.

APIs (implemented in Phase 8):
    GovernanceOS.set_policy()        — define retention rules
    GovernanceOS.audit()             — query the audit log
    GovernanceOS.delete_scope()      — delete user / namespace / memory
    GovernanceOS.enforce_retention() — apply retention policies now

See: docs/roadmap/FULL_IMPLEMENTATION_PLAN.md — Phase 8
"""

from .audit import AuditLogger
from .encryption import EncryptionManager
from .layer import (
    ROLE_ADMIN,
    ROLE_EDITOR,
    ROLE_VIEWER,
    DeletionPolicy,
    DeletionReport,
    GovernanceOS,
    RetentionPolicy,
    RetentionReport,
    Role,
)

__all__ = [
    "AuditLogger",
    "EncryptionManager",
    "GovernanceOS",
    "RetentionPolicy",
    "DeletionPolicy",
    "DeletionReport",
    "RetentionReport",
    "Role",
    "ROLE_ADMIN",
    "ROLE_EDITOR",
    "ROLE_VIEWER",
]
