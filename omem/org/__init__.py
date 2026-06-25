"""Deprecated compatibility shim — org memory lives under ``omem.memory.org``."""

from omem.memory.org import NamespaceInfo, NamespaceNode, NamespaceResolver, OrgMemoryOS, ShareResult

__all__ = [
    "OrgMemoryOS",
    "NamespaceResolver",
    "NamespaceNode",
    "NamespaceInfo",
    "ShareResult",
]
