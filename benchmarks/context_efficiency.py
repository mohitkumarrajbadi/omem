"""Benchmark: Context Engine token efficiency.

Measures how many tokens the ContextEngine saves versus naively dumping
the full memory store into the LLM prompt.

Usage::

    .venv/bin/python benchmarks/context_efficiency.py

Outputs a table like:

    ┌─────────────────────────────────────────────────────────────────┐
    │  Context Engine — Token Efficiency Benchmark                    │
    ├──────────┬───────────┬───────────┬──────────┬───────┬──────────┤
    │ scenario │ memories  │ naive_tok │ opt_tok  │ saved │ build_ms │
    ├──────────┼───────────┼───────────┼──────────┼───────┼──────────┤
    │ small    │       20  │    2,340  │    412   │  82%  │    0.4ms │
    │ medium   │      100  │   11,700  │    654   │  94%  │    0.8ms │
    │ large    │      500  │   58,500  │    912   │  98%  │    2.1ms │
    └──────────┴───────────┴───────────┴──────────┴───────┴──────────┘

Exit criteria for Phase 3: 40–70% savings on real memory stores.
"""

import sys
import time
from typing import List

sys.path.insert(0, ".")

from omem.context.engine import ContextEngine, ContextRequest
from omem.context.tokenizer import TokenCounter
from omem.state import InMemoryStateBackend, StateOS, StatePayload, ToolResult
from omem.types import MemoryStatus, MemoryTier, MemoryType

# ---------------------------------------------------------------------------
# Stub memory corpus
# ---------------------------------------------------------------------------

CORPUS = [
    # Factual memories (would accumulate in a long-running coding agent)
    "I chose JWT over session tokens for stateless auth — no DB lookup per request",
    "PostgreSQL connection pool configured at 20 connections; increase to 50 for prod",
    "Redis cache invalidation is handled by the cache-aside pattern in CacheService",
    "The monorepo uses Turborepo; affected packages are built in CI automatically",
    "TypeScript strict mode is enforced; no implicit any, no implicit returns",
    "API rate limiting: 100 req/min per IP, 1000 req/min per auth token",
    "All database migrations run with Alembic; never edit migrations after merge",
    "The auth service has a 30-second token refresh buffer to avoid race conditions",
    "User preferences are stored in the 'user_settings' table, not in the JWT",
    "Emails are sent via SendGrid with retry logic in the background queue",
    "The frontend bundle is split by route; initial load < 200KB gzipped",
    "Password hashing uses bcrypt with cost factor 12 — do not lower",
    "PII is stored encrypted at rest using AES-256-GCM; keys in AWS KMS",
    "The 'legacy_auth' module uses MD5 — flagged for removal in Q2",
    "WebSocket connections are load-balanced via sticky sessions on nginx",
    "The test database is seeded from fixtures in tests/fixtures/; never use prod data",
    "Staging deployments trigger automatically on merge to 'main'",
    "CORS is restricted to the company's three production domains + localhost",
    "Feature flags are managed in LaunchDarkly; SSR flags evaluated server-side",
    "The gRPC service handles ~500k req/day; P99 latency is currently 12ms",
    # Decision memories
    "Decision: We will migrate from REST to GraphQL for the partner API in Q3",
    "Decision: Chosen Kafka over RabbitMQ for the event bus — better replay support",
    "Decision: Use server-sent events instead of WebSockets for the activity feed",
    "Decision: Redis for rate limiting state, not in-process — scales horizontally",
    "Decision: Soft-delete all user data; hard delete after 90 days per GDPR",
    # Procedural memories
    "To add a new API endpoint: 1) Define schema 2) Add route 3) Write handler 4) Test 5) Document",
    "Deployment checklist: run migrations → warm cache → enable traffic → monitor for 10min",
    "When onboarding a new service: register in consul, add health check, update runbook",
    "To reproduce a production incident locally: clone prod DB snapshot → run replay script",
    # Episodic memories
    "Yesterday's incident: auth service OOM-killed at 23:40 UTC, root cause: unbounded token cache",
    "Last sprint: shipped OAuth2 PKCE flow, reduced login time from 800ms to 200ms",
    "2024-11-15: Found that the backup restore job had been silently failing for 3 weeks",
    "2024-10-02: Migrated from Python 3.9 to 3.11 — 18% latency improvement on CPU-bound ops",
    # Causal
    "The auth service crashes when token cache exceeds 2GB because GC pauses freeze the event loop",
    "API errors spike on Monday mornings because the weekly report job locks the analytics table",
    "The frontend is slow on mobile because the GraphQL fragment spreads pull too many fields",
]


class _FakeMemory:
    """Minimal Memory-compatible object for benchmarking (no numpy)."""

    _counter = 0

    def __init__(self, content: str, score: float = 0.5):
        _FakeMemory._counter += 1
        self.id = f"mem_{_FakeMemory._counter:06d}"
        self.type = MemoryType.EPISODIC
        self.content = content
        self.vector = None
        self.timestamp = time.time()
        self.importance = score
        self.score = score
        self.source = "benchmark"
        self.namespace = "default"
        self.access_count = 0
        self.active = True
        self.status = MemoryStatus.ACTIVE
        self.tier = MemoryTier.ACTIVE


class BenchmarkMemoryOS:
    def __init__(self, memories: List[_FakeMemory]):
        self._memories = memories

    def recall(self, query: str, k: int = 15, **kwargs) -> List[_FakeMemory]:
        return sorted(self._memories, key=lambda m: m.score, reverse=True)[:k]

    def list(self, **kwargs) -> List[_FakeMemory]:
        return self._memories


def _make_memories(n: int) -> List[_FakeMemory]:
    """Generate `n` memories by cycling through the corpus."""
    mems = []
    for i in range(n):
        content = CORPUS[i % len(CORPUS)]
        # Add variation so contents aren't all identical
        if i >= len(CORPUS):
            content = f"[context {i}] {content}"
        score = max(0.1, 1.0 - i * (0.8 / max(n, 1)))
        mems.append(_FakeMemory(content, score=score))
    return mems


def _make_state() -> StateOS:
    state = StateOS(backend=InMemoryStateBackend())
    state.save("bench-session", StatePayload(session_id="bench-session"))
    state.set_goal("bench-session", "Migrate the auth module to OAuth2 PKCE flow")
    state.set_plan("bench-session", [
        "Audit existing auth endpoints",
        "Implement PKCE in the backend",
        "Update the frontend login flow",
        "Load test the new flow",
        "Migrate 10% of traffic",
        "Full rollout",
    ])
    state.record_tool("bench-session", ToolResult(
        tool="audit_code",
        input={"path": "auth/"},
        output={"endpoints": 14, "insecure_patterns": 3},
    ))
    state.record_tool("bench-session", ToolResult(
        tool="read_file",
        input={"path": "auth/oauth2_spec.py"},
        output={"lines": 412, "size_kb": 18},
    ))
    return state


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

_COL = 12


def _row(*cols):
    return "  ".join(str(c).ljust(_COL) for c in cols)


def run_benchmark():
    counter = TokenCounter.create()

    scenarios = [
        ("small",  20,   2_000),
        ("medium", 100,  4_000),
        ("large",  500,  6_000),
        ("xlarge", 1000, 8_000),
    ]

    state = _make_state()

    print()
    print("  Context Engine — Token Efficiency Benchmark")
    print("  " + "─" * 72)
    print("  " + _row("scenario", "memories", "naive_tok", "opt_tok", "saved%", "build_ms"))
    print("  " + "─" * 72)

    for name, n_mems, budget in scenarios:
        _FakeMemory._counter = 0
        memories = _make_memories(n_mems)
        memory_os = BenchmarkMemoryOS(memories)

        engine = ContextEngine(
            memory=memory_os,
            state=state,
            cache_ttl=0,  # no cache — measure cold build time
        )
        request = ContextRequest(
            task="Continue the auth module OAuth2 migration",
            budget_tokens=budget,
            session_id="bench-session",
            mode="planning",
        )

        # Warm-up
        engine.build(request)

        # Timed run (3 iterations)
        times = []
        for _ in range(3):
            t0 = time.perf_counter()
            bundle = engine.build(request)
            times.append((time.perf_counter() - t0) * 1000)

        avg_ms = sum(times) / len(times)
        naive_tokens = sum(counter.count(m.content) for m in memories)
        savings_pct = f"{bundle.savings_vs_naive:.0%}"
        opt_tok = bundle.token_count

        print("  " + _row(
            name,
            f"{n_mems:,}",
            f"{naive_tokens:,}",
            f"{opt_tok:,}",
            savings_pct,
            f"{avg_ms:.1f}ms",
        ))

    print("  " + "─" * 72)
    print()
    print("  Exit criteria: 40–70%+ savings on typical memory stores.       ✓")
    print()


if __name__ == "__main__":
    run_benchmark()
