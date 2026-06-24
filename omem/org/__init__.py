"""Phase 10 — Shared Organizational Memory.

Namespace hierarchy (personal → team → org → global) with scope-aware
recall and explicit memory promotion.
"""

from .layer import NamespaceInfo, OrgMemoryOS, ShareResult
from .namespace import NamespaceNode, NamespaceResolver

__all__ = [
    "OrgMemoryOS",
    "NamespaceResolver",
    "NamespaceNode",
    "NamespaceInfo",
    "ShareResult",
]
