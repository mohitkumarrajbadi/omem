"""Tests for cognitive features: Truth Maintenance and Hierarchical Reflection.

Rewritten from script-style (print-based) to proper pytest assertions.
Uses OMem(backend="memory") for speed and isolation.
"""

import pytest

from omem import OMem
from omem.types import MemoryStatus, MemoryType


def test_truth_maintenance_older_memory_deprecated():
    """When two conflicting facts are added, the older one must be DEPRECATED."""
    m = OMem(backend="memory")

    id1 = m.add("User's favorite color is blue")
    m.add("User's favorite color is red")

    all_mems = m.all(include_inactive=True)
    deprecated = [mem for mem in all_mems if mem.status == MemoryStatus.DEPRECATED]

    assert len(deprecated) >= 1, (
        "Expected at least one DEPRECATED memory after adding conflicting facts"
    )
    deprecated_ids = {mem.id for mem in deprecated}
    assert id1 in deprecated_ids, f"Older memory (id1={id1}) should be DEPRECATED"


def test_truth_maintenance_newer_stays_active():
    """After conflict resolution, the newer memory must remain ACTIVE."""
    m = OMem(backend="memory")

    m.add("User's favorite color is blue")
    id2 = m.add("User's favorite color is red")

    mem2 = m.get(id2)
    assert mem2 is not None
    assert mem2.active is True, "Newer memory must remain active after conflict"
    assert mem2.status == MemoryStatus.ACTIVE, (
        f"Newer memory status must be ACTIVE, got {mem2.status}"
    )


def test_truth_maintenance_deprecated_excluded_from_recall():
    """Deprecated (inactive) memories must not appear in recall results."""
    m = OMem(backend="memory")

    id1 = m.add("User's favorite color is blue")
    m.add("User's favorite color is red")

    mem1 = m.get(id1)
    if mem1 and not mem1.active:
        results = m.recall("favorite color")
        result_ids = {r.id for r in results}
        assert id1 not in result_ids, "Deprecated memory must not appear in recall"


def test_truth_maintenance_dob_example():
    """Classic DOB conflict: second entry must deprecate the first."""
    m = OMem(backend="memory")

    id1 = m.add("My DOB is 15 March", importance=0.8)
    m.add("My DOB is 05 Oct", importance=0.9)

    all_mems = m.all(include_inactive=True)
    deprecated = [mem for mem in all_mems if mem.status == MemoryStatus.DEPRECATED]

    assert len(deprecated) >= 1, "At least one DOB memory must be DEPRECATED"
    assert any(mem.id == id1 for mem in deprecated), (
        "First DOB memory should be DEPRECATED"
    )


def test_truth_maintenance_two_facts_both_stored():
    """Both memories must be stored (one active, one inactive) — no data loss."""
    m = OMem(backend="memory")

    m.add("My location is Mumbai")
    m.add("My location is Berlin")

    all_mems = m.all(include_inactive=True)
    assert len(all_mems) >= 2, "Both location memories must be stored"

    active = [mem for mem in all_mems if mem.active]
    inactive = [mem for mem in all_mems if not mem.active]
    assert len(active) >= 1, "At least one memory must remain active"
    assert len(inactive) >= 1, "At least one memory must be marked inactive"


def test_hierarchical_reflection_returns_list():
    """reflect() must return a list (empty is acceptable for small datasets)."""
    m = OMem(backend="memory")

    for text in [
        "User loves Python programming",
        "User joined the Python community yesterday",
        "User is building a Python web app",
        "Python is a versatile language for data science",
        "Developing in Python is efficient and fun",
    ]:
        m.add(text)

    reflections = m.reflect()
    assert isinstance(reflections, list), (
        f"reflect() must return a list, got {type(reflections)}"
    )


def test_hierarchical_reflection_second_pass_does_not_crash():
    """A second reflect() call after adding more memories must not raise."""
    m = OMem(backend="memory")

    for text in [
        "User loves Python programming",
        "User is building a Python web app",
        "Python is versatile for data science",
    ]:
        m.add(text)

    m.reflect()  # first pass

    m.add("User is learning Rust to optimize Python performance")
    m.add("Rust integration with Python is a powerful combo")
    m.add("Python and Rust together improve throughput significantly")

    second_pass = m.reflect()
    assert isinstance(second_pass, list), "Second reflect() must return a list"


def test_reflection_produces_correct_types():
    """Any reflection generated must have type REFLECTION or INSIGHT."""
    m = OMem(backend="memory")

    for i in range(8):
        m.add(f"Insight {i}: Python is excellent for building AI agents and tools")

    reflections = m.reflect(threshold=0.6)
    for ref in reflections:
        assert ref.type in (MemoryType.REFLECTION, MemoryType.INSIGHT), (
            f"Expected REFLECTION or INSIGHT type, got {ref.type}"
        )


def test_reflection_on_memories_are_stored():
    """Reflections produced by reflect() must be retrievable via all(include_inactive=True)."""
    m = OMem(backend="memory")

    for i in range(6):
        m.add(f"Python tip {i}: use list comprehensions, generators, and dataclasses")

    reflections = m.reflect(threshold=0.5)
    if reflections:
        all_mems = m.all(include_inactive=True)
        all_ids = {mem.id for mem in all_mems}
        for ref in reflections:
            assert ref.id in all_ids, (
                f"Reflection id={ref.id} not found in stored memories"
            )
