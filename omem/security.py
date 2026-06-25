"""Removed in v3.0 — use ``omem.governance`` instead.

See docs/architecture/adr/003-v3-release.md
"""

raise ImportError(
    "omem.security was removed in v3.0. Use: from omem.governance.audit import AuditLogger"
)
