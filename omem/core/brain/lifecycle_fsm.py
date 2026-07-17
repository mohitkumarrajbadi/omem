"""Lifecycle stage finite-state machine for Memory OS charter.

Stages:
  new → reinforced → consolidated → compressed → archived → forgotten
"""

from __future__ import annotations

from typing import FrozenSet

from ...types import LifecycleStage, Memory, MemoryStatus, MemoryTier

# Allowed forward transitions
_TRANSITIONS: dict[str, FrozenSet[str]] = {
    LifecycleStage.NEW.value: frozenset(
        {
            LifecycleStage.REINFORCED.value,
            LifecycleStage.CONSOLIDATED.value,
            LifecycleStage.COMPRESSED.value,
            LifecycleStage.ARCHIVED.value,
            LifecycleStage.FORGOTTEN.value,
        }
    ),
    LifecycleStage.REINFORCED.value: frozenset(
        {
            LifecycleStage.CONSOLIDATED.value,
            LifecycleStage.COMPRESSED.value,
            LifecycleStage.ARCHIVED.value,
            LifecycleStage.FORGOTTEN.value,
        }
    ),
    LifecycleStage.CONSOLIDATED.value: frozenset(
        {
            LifecycleStage.COMPRESSED.value,
            LifecycleStage.ARCHIVED.value,
            LifecycleStage.FORGOTTEN.value,
        }
    ),
    LifecycleStage.COMPRESSED.value: frozenset(
        {
            LifecycleStage.ARCHIVED.value,
            LifecycleStage.FORGOTTEN.value,
        }
    ),
    LifecycleStage.ARCHIVED.value: frozenset({LifecycleStage.FORGOTTEN.value}),
    LifecycleStage.FORGOTTEN.value: frozenset(),
}


def current_stage(memory: Memory) -> str:
    return getattr(memory, "lifecycle_stage", None) or LifecycleStage.NEW.value


def can_transition(from_stage: str, to_stage: str) -> bool:
    return to_stage in _TRANSITIONS.get(from_stage, frozenset())


def advance_stage(memory: Memory, to_stage: str, *, force: bool = False) -> bool:
    """Advance memory lifecycle stage. Returns True if changed."""
    cur = current_stage(memory)
    if cur == to_stage:
        return False
    if not force and not can_transition(cur, to_stage):
        return False
    memory.lifecycle_stage = to_stage
    if to_stage == LifecycleStage.ARCHIVED.value:
        memory.tier = MemoryTier.ARCHIVE
        memory.level = "archive"
        memory.status = MemoryStatus.ARCHIVED
        memory.active = False
    elif to_stage == LifecycleStage.FORGOTTEN.value:
        memory.tier = MemoryTier.FORGOTTEN
        memory.active = False
        memory.status = MemoryStatus.DEPRECATED
    return True


def mark_reinforced(memory: Memory) -> bool:
    return advance_stage(memory, LifecycleStage.REINFORCED.value)


def mark_consolidated(memory: Memory) -> bool:
    return advance_stage(memory, LifecycleStage.CONSOLIDATED.value)


def mark_compressed(memory: Memory) -> bool:
    return advance_stage(memory, LifecycleStage.COMPRESSED.value)


def mark_archived(memory: Memory) -> bool:
    return advance_stage(memory, LifecycleStage.ARCHIVED.value)


def mark_forgotten(memory: Memory) -> bool:
    return advance_stage(memory, LifecycleStage.FORGOTTEN.value)
