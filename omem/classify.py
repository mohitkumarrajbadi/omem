"""Deprecated compatibility shim — classification lives in ``omem.core.brain.classify``."""

from omem.core.brain.classify import auto_classify, auto_classify_multi

__all__ = ["auto_classify", "auto_classify_multi"]
