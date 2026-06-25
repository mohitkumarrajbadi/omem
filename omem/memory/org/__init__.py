"""Organizational memory — namespace hierarchy and scoped recall (Layer 1 extension)."""

from .layer import NamespaceInfo, OrgMemoryOS, ShareResult
from .namespace import NamespaceNode, NamespaceResolver

__all__ = [
    "OrgMemoryOS",
    "NamespaceResolver",
    "NamespaceNode",
    "NamespaceInfo",
    "ShareResult",
]
