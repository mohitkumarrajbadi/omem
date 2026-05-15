import sys
import os

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from omem import OMem
from omem.types import MemoryStatus


def test_truth_maintenance():
    print("\n--- Testing Truth Maintenance System ---")
    m = OMem(backend="sqlite", db_path=":memory:")

    # Add a fact
    print("Adding: User's favorite color is blue")
    id1 = m.add("User's favorite color is blue")

    # Add a contradictory fact
    print("Adding: User's favorite color is red")
    id2 = m.add("User's favorite color is red")

    # Check status
    mem1 = m.get(id1)
    mem2 = m.get(id2)

    print(f"Memory 1 ({mem1.content}) Status: {mem1.status.name}")
    print(f"Memory 2 ({mem2.content}) Status: {mem2.status.name}")

    if mem1.status == MemoryStatus.CONFLICTED:
        print("PASS Conflict detected successfully!")
    else:
        print("FAIL Conflict detection failed.")


def test_hierarchical_reflection():
    print("\n--- Testing Hierarchical Reflection ---")
    m = OMem(backend="sqlite", db_path=":memory:")

    # Add some base memories
    m.add("User loves Python programming")
    m.add("User joined the Python community yesterday")
    m.add("User is building a Python web app")
    m.add("Python is a versatile language for data science")
    m.add("Developing in Python is efficient and fun")

    # Trigger reflection
    print("Triggering base reflection...")
    reflections = m.reflect()
    print(f"Generated {len(reflections)} base reflections.")
    for r in reflections:
        print(f" - {r.content}")

    # Trigger hierarchical reflection (reflection on reflections)
    print("Triggering hierarchical reflection...")
    m.add("User is learning Rust to optimize Python performance")
    m.add("Rust integration with Python is a powerful combo")

    hier_reflections = m.reflect()
    print(f"Generated {len(hier_reflections)} reflections (including hierarchical).")
    for r in hier_reflections:
        is_hier = r.metadata.get("hierarchical", False)
        print(f" - {r.content} (Hierarchical: {is_hier})")


if __name__ == "__main__":
    test_truth_maintenance()

    test_hierarchical_reflection()
