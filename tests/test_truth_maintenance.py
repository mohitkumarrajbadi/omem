import pytest

from omem import MemoryStatus, OMem
from omem.core.brain.tms import extract_triplet


def test_truth_maintenance_dob_correction():
    """Test that OMem identifies and flags conflicting facts (e.g., DOB)."""
    m = OMem(backend="memory")

    # 1. Add conflicting memories
    id1 = m.add("My DOB is 15 March", importance=0.8)
    m.add("My DOB is 05 Oct", importance=0.9)

    # 2. Check statuses
    all_mems = m.all(include_inactive=True)
    deprecated = [mem for mem in all_mems if mem.status == MemoryStatus.DEPRECATED]

    # In v1.0 Temporal Resolution, the older memory is marked DEPRECATED
    assert len(deprecated) >= 1
    # The first (older) memory must be the one deprecated
    assert any(mem.id == id1 for mem in deprecated), (
        "The older DOB memory must be DEPRECATED"
    )


def test_conflict_detection_logic():
    """Test the v1.0.0 triplet extraction and conflict hash logic."""
    from omem.core.brain.tms import compute_logical_hash

    # "My DOB is 15 March" -> (entity, attribute, value)
    t1 = extract_triplet("My DOB is 15 March")
    assert t1 is not None
    assert t1[0] == "dob"
    assert t1[2] == "15 march"

    # "My DOB is 05 Oct" -> same entity/attribute, different value
    t2 = extract_triplet("My DOB is 05 Oct")
    assert t2 is not None
    assert t1[0] == t2[0], "Both triplets must have the same entity"
    assert t1[1] == t2[1], "Both triplets must have the same attribute"
    assert t1[2] != t2[2], "But different values — this is the conflict"

    # They should produce the same logical hash (same entity+attribute)
    h1 = compute_logical_hash(t1[0], t1[1])
    h2 = compute_logical_hash(t2[0], t2[1])
    assert h1 == h2, "Same entity+attribute must produce the same logical hash"


def test_no_conflict_when_nonconflicting_facts():
    """Unrelated facts must not be marked as conflicts."""
    m = OMem(backend="memory")

    m.add("The capital of France is Paris", importance=0.7)
    m.add("Python was created by Guido van Rossum", importance=0.7)

    all_mems = m.all(include_inactive=True)
    # Neither should be deprecated — they don't conflict
    deprecated = [mem for mem in all_mems if mem.status == MemoryStatus.DEPRECATED]
    # Both memories should be active
    assert len(deprecated) == 0, (
        "Unrelated facts must not be marked as DEPRECATED"
    )


def test_conflict_preserves_both_records():
    """After conflict resolution, both the old and new memory must be stored."""
    m = OMem(backend="memory")

    id1 = m.add("My favorite language is Java")
    id2 = m.add("My favorite language is Python")

    all_mems = m.all(include_inactive=True)
    all_ids = {mem.id for mem in all_mems}

    # Both must still exist (old is inactive, new is active)
    assert id1 in all_ids, "Old memory must be retained (soft-deprecated)"
    assert id2 in all_ids, "New memory must be stored"


def test_newer_memory_has_higher_importance_wins():
    """When both facts have equal importance, the newer one must win."""
    m = OMem(backend="memory")

    m.add("My city is Mumbai", importance=0.8)
    id2 = m.add("My city is Berlin", importance=0.8)

    mem2 = m.get(id2)
    assert mem2 is not None
    assert mem2.active is True, "Newer memory must remain active"
    assert mem2.status == MemoryStatus.ACTIVE


if __name__ == "__main__":
    pytest.main([__file__])
