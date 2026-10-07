"""Optional governance adapters around third-party memory stores."""

from __future__ import annotations

from typing import Any

__all__ = ["GovernedMem0"]


def __getattr__(name: str) -> Any:
    if name == "GovernedMem0":
        from .mem0 import GovernedMem0

        return GovernedMem0
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
