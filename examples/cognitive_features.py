# Run: python examples/cognitive_features.py
#
# Five runnable demos of OMem's cognitive features.
# Each section shows the state before an action, performs the action,
# then shows the state after.
#
# No external services required. Uses in-memory backend (no disk writes).

import time
from datetime import datetime, timedelta

from omem import OMem
from omem.types import MemoryType, MemoryPriority


def section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"=== {title} ===")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Demo 1 — Truth Maintenance System / Conflict Detection
# ---------------------------------------------------------------------------
section("1. TMS / Conflict Detection")

m = OMem(backend="memory")

m.add("Python version is 3.9", mem_type=MemoryType.SEMANTIC)
time.sleep(0.05)  # ensure timestamp ordering
m.add("Python version is 3.11", mem_type=MemoryType.SEMANTIC)

print("\nBefore resolve_conflict — both memories exist:")
for mem in m.recall("Python version", k=5):
    print(f"  [{mem.status}] {mem.content}")

m.resolve_conflict("Python version")

print("\nAfter resolve_conflict — older entry deprecated:")
for mem in m.all(include_inactive=True):
    if "Python version" in mem.content:
        print(f"  [{mem.status}] {mem.content}")


# ---------------------------------------------------------------------------
# Demo 2 — Forgetting / Decay
# ---------------------------------------------------------------------------
section("2. Forgetting / Decay")

m = OMem(backend="memory")

# Add a very low-importance memory
mem_id = m.add("Temporary debug note: checked log output", importance=0.1)
print(f"\nAdded low-importance memory: '{m.recall('debug note', k=1)[0].content}'")

# Patch its timestamp to 72 hours ago so the decay engine considers it stale
backend = m._backend  # type: ignore[attr-defined]
cutoff = datetime.utcnow() - timedelta(hours=72)
try:
    backend._conn.execute(
        "UPDATE memories SET created_at = ? WHERE id = ?",
        (cutoff.isoformat(), mem_id),
    )
    backend._conn.commit()
except Exception:
    # Different backend implementation — skip timestamp patch
    pass

print("Simulated 72-hour age on that memory.")
print("Running m.sleep()...")

stats = m.sleep()
print(f"Sleep stats: {stats}")

results = m.recall("debug note", k=5)
if results:
    print(f"Memory still present (decay threshold not reached): '{results[0].content}'")
else:
    print("Memory removed by decay — no longer returned in recall.")


# ---------------------------------------------------------------------------
# Demo 3 — Compression / Deduplication
# ---------------------------------------------------------------------------
section("3. Compression / Deduplication")

m = OMem(backend="memory")

near_duplicates = [
    "User clicked the login button",
    "User pressed sign-in",
    "User tapped the login link",
    "User selected login",
    "User initiated login flow",
]

for text in near_duplicates:
    m.add(text, mem_type=MemoryType.EPISODIC, importance=0.3)

before_count = len(m.all())
print(f"\nBefore sleep: {before_count} memories")
for mem in m.all():
    print(f"  {mem.content}")

stats = m.sleep()
after_count = len(m.all())

print(f"\nAfter sleep: {after_count} memories")
for mem in m.all():
    print(f"  {mem.content}")

print(f"\nCompressed {before_count} → {after_count} (removed {before_count - after_count})")


# ---------------------------------------------------------------------------
# Demo 4 — Reflection / Insight Generation
# ---------------------------------------------------------------------------
section("4. Reflection / Insight Generation")

m = OMem(backend="memory")

episodic_events = [
    "User spent 45 minutes on the dashboard configuration page",
    "User exported data to CSV three times today",
    "User asked support: how do I filter by date range?",
    "User repeated the same search query four times",
    "User opened the help docs for the filter feature",
    "User abandoned the filter wizard halfway through",
    "User sent feedback: the date filter is confusing",
    "User session ended without completing the filter setup",
]

for event in episodic_events:
    m.add(event, mem_type=MemoryType.EPISODIC)

print(f"\nAdded {len(episodic_events)} episodic memories about user behaviour.")
print("Running m.reflect()...")

insights = m.reflect()

if insights:
    print(f"\nGenerated {len(insights)} REFLECTION-type insight(s):")
    for i, insight in enumerate(insights, 1):
        print(f"\n  [{i}] {insight.content}")
        print(f"       type={insight.type}, importance={insight.importance:.2f}")
else:
    print("\nNo reflections generated (requires sufficient episodic density).")
    print("Try adding more related memories and re-running.")


# ---------------------------------------------------------------------------
# Demo 5 — Priority Scoring
# ---------------------------------------------------------------------------
section("5. Priority Scoring")

m = OMem(backend="memory")

m.add(
    "CORE: Production database credentials must rotate every 30 days",
    importance=1.0,
    mem_type=MemoryType.DECISION,
)
m.add(
    "HIGH: API rate limit is 1000 req/min per tenant",
    importance=0.8,
    mem_type=MemoryType.SEMANTIC,
)
m.add(
    "NORMAL: Default timeout is 30 seconds",
    importance=0.5,
    mem_type=MemoryType.SEMANTIC,
)

print("\nInspect score breakdown (ordered by final score):")
results = m.inspect("configuration limits credentials", top_k=10)
results_sorted = sorted(results, key=lambda x: x.final_score, reverse=True)

for r in results_sorted:
    mem_snippet = next(
        (mem.content[:60] for mem in m.all() if mem.id == r.memory_id),
        r.memory_id,
    )
    print(f"\n  Memory : {mem_snippet}...")
    print(f"  vector     = {r.vector_score:.4f}")
    print(f"  keyword    = {r.keyword_score:.4f}")
    print(f"  importance = {r.importance_score:.4f}")
    print(f"  recency    = {r.recency_score:.4f}")
    print(f"  FINAL      = {r.final_score:.4f}")

print("\nHigher-importance memories score significantly higher for the same query.")
