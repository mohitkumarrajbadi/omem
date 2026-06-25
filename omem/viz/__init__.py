"""Deprecated compatibility shim — dashboard lives under ``omem.observe.dashboard``."""

from omem.observe.dashboard.server import serve

__all__ = ["serve"]
