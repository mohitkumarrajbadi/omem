import pytest

from omem import MemoryStatus, OMem
from omem.core.brain.tms import extract_triplet


def test_truth_maintenance_dob_correction():
    """Test that OMem identifies and flags conflicting facts (e.g., DOB)."""
    m = OMem()

    # 1. Add conflicting memories
    # The TMS should detect these in real-time during add()
    m.add("My DOB is 15 March", importance=0.8)
    m.add("My DOB is 05 Oct", importance=0.9)

    # 2. Check statuses
    all_mems = m.all(include_inactive=True)
    deprecated = [mem for mem in all_mems if mem.status == MemoryStatus.DEPRECATED]

    # In v1.0 Temporal Resolution, the older memory is marked DEPRECATED
    assert len(deprecated) >= 1


def test_conflict_detection_logic():
    """Test the v1.0.0 triplet extraction and conflict hash logic."""
    from omem.core.brain.tms import compute_logical_hash

    # "My DOB is 15 March" -> (user, fact, 15 march)
    t1 = extract_triplet("My DOB is 15 March")
    assert t1 is not None
    assert t1[0] == "dob"
    assert t1[2] == "15 march"

    # "My DOB is 05 Oct" -> (user, fact, 05 oct)
    t2 = extract_triplet("My DOB is 05 Oct")
    assert t2 is not None
    assert t1[0] == t2[0]  # Same entity
    assert t1[1] == t2[1]  # Same attribute

    # They should produce the same logical hash
    h1 = compute_logical_hash(t1[0], t1[1])
    h2 = compute_logical_hash(t2[0], t2[1])
    assert h1 == h2


if __name__ == "__main__":
    pytest.main([__file__])
