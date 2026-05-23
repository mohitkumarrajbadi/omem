"""
Data Integrity Benchmark - validate correctness under stress.

Verifies that OMem returns correct data even under heavy load:
- No data loss after bulk inserts
- No corruption after concurrent access
- RAG recall accuracy (does the right memory rank #1?)
- Deduplication correctness
- Backend <-> KV consistency
"""

import hashlib
import threading
from typing import Dict, Tuple

from omem import MemoryType, OMem


def test_no_data_loss(n: int = 10_000, verbose: bool = True) -> Tuple[bool, str]:
    """Verify all inserted memories are retrievable."""
    m = OMem()
    ids = []

    for i in range(n):
        mid = m.add(
            f"Integrity-{i}: unique content {hashlib.md5(str(i).encode()).hexdigest()}"
        )
        ids.append(mid)

    # Verify every memory exists
    stats = m.stats()
    unique_ids = set(ids)
    missing = []
    for mid in unique_ids:
        if m.get(mid) is None:
            missing.append(mid)

    ok = len(missing) == 0 and stats["total"] == len(unique_ids)
    msg = f"Inserted {n}, unique IDs={len(unique_ids)}, stored={stats['total']}, missing={len(missing)}"

    if verbose:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] No data loss: {msg}")

    return ok, msg


def test_dedup_correctness(verbose: bool = True) -> Tuple[bool, str]:
    """Verify deduplication works correctly."""
    m = OMem()
    content = "This exact content should be stored only once"

    id1 = m.add(content)
    id2 = m.add(content)
    id3 = m.add(content)

    ok = (id1 == id2 == id3) and m.stats()["total"] == 1
    msg = f"IDs match={id1 == id2 == id3}, count={m.stats()['total']}"

    if verbose:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] Dedup correctness: {msg}")

    return ok, msg


def test_recall_accuracy(verbose: bool = True) -> Tuple[bool, float]:
    """Test if the correct memory ranks #1 for targeted queries."""
    m = OMem()

    # Insert diverse memories with known content
    test_cases = [
        ("The capital of France is Paris", "Paris France capital"),
        ("Python was created by Guido van Rossum in 1991", "Python creator Guido"),
        (
            "Machine learning uses neural networks for predictions",
            "neural network ML predictions",
        ),
        ("Tokyo is the largest city in Japan", "Tokyo Japan city"),
        ("HTTP status code 404 means page not found", "404 not found HTTP"),
        ("The speed of light is approximately 3x10^8 m/s", "speed light meters"),
        (
            "Docker containers virtualize at the OS level",
            "Docker container virtualization",
        ),
        ("SQL JOIN combines rows from two tables", "SQL JOIN tables"),
        (
            "Kubernetes orchestrates container deployment",
            "Kubernetes container orchestration",
        ),
        ("Redis is an in-memory key-value data store", "Redis in-memory store"),
    ]

    memory_ids = {}
    for content, _ in test_cases:
        mid = m.add(content)
        memory_ids[content] = mid

    # Also add noise
    for i in range(100):
        m.add(f"Noise entry {i}: random filler content about category {i % 10}")

    # Test recall
    hits = 0
    for content, query in test_cases:
        results = m.recall(query, top_k=3)
        if results and results[0].content == content:
            hits += 1

    recall = hits / len(test_cases)
    ok = recall >= 0.5  # At least 50% recall@1 with hash embeddings

    if verbose:
        status = "OK" if ok else "WARN"
        print(
            f"  [{status}] Recall@1 accuracy: {recall:.0%} ({hits}/{len(test_cases)}) [threshold: 50%]"
        )

    return ok, recall


def test_type_classification_accuracy(verbose: bool = True) -> Tuple[bool, float]:
    """Test auto-classification accuracy on known inputs."""
    test_cases = [
        ("Step 1: clone the repo, Step 2: run npm install", MemoryType.PROCEDURAL),
        ("How to configure a reverse proxy", MemoryType.PROCEDURAL),
        ("Rain caused severe flooding in the valley", MemoryType.CAUSAL),
        ("Due to budget cuts the project was delayed", MemoryType.CAUSAL),
        ("We decided to use PostgreSQL over MySQL", MemoryType.DECISION),
        ("The team chose microservices architecture", MemoryType.DECISION),
        ("Yesterday we deployed the new release", MemoryType.EPISODIC),
        ("Last week the server went down twice", MemoryType.EPISODIC),
        ("Currently migrating the database", MemoryType.WORKING),
        ("Urgent: security patch needed immediately", MemoryType.ACTIVE),
        ("Python is a dynamically typed language", MemoryType.SEMANTIC),
        ("The Earth revolves around the Sun", MemoryType.SEMANTIC),
    ]

    m = OMem()
    correct = 0
    for content, expected_type in test_cases:
        mid = m.add(content)
        mem = m.get(mid)
        if mem and mem.type == expected_type:
            correct += 1

    accuracy = correct / len(test_cases)
    ok = accuracy >= 0.8  # 80% threshold

    if verbose:
        status = "OK" if ok else "WARN"
        print(
            f"  [{status}] Classification accuracy: {accuracy:.0%} ({correct}/{len(test_cases)}) [threshold: 80%]"
        )

    return ok, accuracy


def test_concurrent_integrity(
    n_threads: int = 8, n_per_thread: int = 200, verbose: bool = True
) -> Tuple[bool, str]:
    """Verify no data corruption under concurrent writes.

    Note: SQLite in-memory backend may throw on concurrent writes - that's
    expected.  We count successful adds and verify that every successful
    add is retrievable from the KV layer (no data corruption).
    """
    m = OMem()
    successful_contents: list = []
    lock = threading.Lock()
    error_count = 0

    def writer(tid: int):
        nonlocal error_count
        for i in range(n_per_thread):
            content = f"ConcurrentTest-T{tid}-{i}"
            try:
                m.add(content)
                with lock:
                    successful_contents.append(content)
            except Exception:
                with lock:
                    error_count += 1

    threads = [threading.Thread(target=writer, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Check: every successfully added content is in the KV cache
    all_mems = m.all()
    stored_contents = {mem.content for mem in all_mems}
    unique_successful = set(successful_contents)
    missing = unique_successful - stored_contents

    # Core invariant: no missing data among successful inserts
    ok = len(missing) == 0 and len(stored_contents) > 0
    msg = (
        f"Successful adds={len(unique_successful)}, stored={len(stored_contents)}, "
        f"missing={len(missing)}, backend_errors={error_count}"
    )

    if verbose:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] Concurrent integrity: {msg}")
        if error_count > 0:
            print(
                f"      INFO: {error_count} backend errors (expected with SQLite in-memory under concurrency)"
            )

    return ok, msg


def test_backend_consistency(n: int = 1000, verbose: bool = True) -> Tuple[bool, str]:
    """Verify KV cache and SQLite backend stay in sync."""
    m = OMem()

    for i in range(n):
        m.add(f"Consistency-{i}: test data")

    kv_count = m.brain.kv.size
    backend_count = m._backend.count()

    ok = kv_count == backend_count
    msg = f"KV={kv_count}, Backend={backend_count}"

    if verbose:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] Backend consistency: {msg}")

    return ok, msg


def run_integrity_suite(verbose: bool = True) -> Dict[str, bool]:
    """Run all data integrity tests."""
    if verbose:
        print("=" * 70)
        print("  OMem Data Integrity Suite - Correctness Under Stress")
        print("=" * 70)
        print()

    results = {}

    ok, _ = test_no_data_loss(10_000, verbose)
    results["no_data_loss"] = ok

    ok, _ = test_dedup_correctness(verbose)
    results["dedup"] = ok

    ok, _ = test_recall_accuracy(verbose)
    results["recall"] = ok

    ok, _ = test_type_classification_accuracy(verbose)
    results["classification"] = ok

    ok, _ = test_concurrent_integrity(8, 200, verbose)
    results["concurrent"] = ok

    ok, _ = test_backend_consistency(1000, verbose)
    results["backend_consistency"] = ok

    all_pass = all(results.values())
    if verbose:
        print()
        status = "PASS" if all_pass else "FAIL"
        passed = sum(1 for v in results.values() if v)
        print(f"  [{status}] Overall: {passed}/{len(results)} tests passed")

    return results


if __name__ == "__main__":
    run_integrity_suite()
