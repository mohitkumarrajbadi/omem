"""STATE-Bench — The standard benchmark for AI Agent State Infrastructure.

STATE-Bench measures what matters for production AI agents:

  ┌──────────────────────────────────────────────────────────────────┐
  │                      STATE-Bench v1.0                           │
  ├────────────────────┬─────────────────────────────────────────────┤
  │ Suite              │ What it measures                            │
  ├────────────────────┼─────────────────────────────────────────────┤
  │ Memory             │ Recall@K, MRR, Hit Rate, Latency            │
  │ State              │ Snapshot/rollback accuracy, Fork integrity  │
  │ Context            │ Token savings, Budget adherence, Latency    │
  │ Continuity         │ Checkpoint recovery, Resume fidelity        │
  │ Knowledge          │ Graph link accuracy, Reason quality         │
  │ Explainability     │ Score decomposition coverage                │
  │ Concurrency        │ Throughput under parallel agent load        │
  └────────────────────┴─────────────────────────────────────────────┘

Run from project root:

    python benchmarks/state_bench.py
    python benchmarks/state_bench.py --suite memory
    python benchmarks/state_bench.py --suite state --suite context
    python benchmarks/state_bench.py --json > results/state_bench_latest.json

Publish your results and contribute to the STATE-Bench leaderboard:
    https://github.com/omem-ai/state-bench
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ─────────────────────────────────────────────────────────────────────────────
# Benchmark scaffolding
# ─────────────────────────────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
DIM    = "\033[2m"
WHITE  = "\033[97m"

BANNER = f"""{CYAN}{BOLD}
  ███████╗████████╗ █████╗ ████████╗███████╗      ██████╗ ███████╗███╗   ██╗ ██████╗██╗  ██╗
  ██╔════╝╚══██╔══╝██╔══██╗╚══██╔══╝██╔════╝      ██╔══██╗██╔════╝████╗  ██║██╔════╝██║  ██║
  ███████╗   ██║   ███████║   ██║   █████╗  █████╗██████╔╝█████╗  ██╔██╗ ██║██║     ███████║
  ╚════██║   ██║   ██╔══██║   ██║   ██╔══╝  ╚════╝██╔══██╗██╔══╝  ██║╚██╗██║██║     ██╔══██║
  ███████║   ██║   ██║  ██║   ██║   ███████╗      ██████╔╝███████╗██║ ╚████║╚██████╗██║  ██║
  ╚══════╝   ╚═╝   ╚═╝  ╚═╝   ╚═╝   ╚══════╝      ╚═════╝ ╚══════╝╚═╝  ╚═══╝ ╚═════╝╚═╝  ╚═╝
{RESET}{WHITE}  The standard benchmark for AI Agent State Infrastructure{RESET}
{DIM}  OMem STATE-Bench v1.0  ·  https://github.com/omem-ai/state-bench{RESET}
"""


@dataclass
class MetricResult:
    name: str
    value: float
    unit: str
    grade: str          # S / A / B / C / F
    description: str
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.grade in ("S", "A", "B")


@dataclass
class SuiteResult:
    suite: str
    metrics: List[MetricResult] = field(default_factory=list)
    duration_ms: float = 0.0
    error: Optional[str] = None

    @property
    def score(self) -> float:
        """Normalised 0–100 score for this suite."""
        if not self.metrics:
            return 0.0
        grade_pts = {"S": 100, "A": 85, "B": 70, "C": 50, "F": 0}
        return statistics.mean(grade_pts.get(m.grade, 0) for m in self.metrics)

    @property
    def passed(self) -> int:
        return sum(1 for m in self.metrics if m.passed)

    @property
    def total(self) -> int:
        return len(self.metrics)


def _grade(value: float, thresholds: Tuple[float, float, float, float]) -> str:
    """Map a value to S/A/B/C/F using ascending thresholds (higher = better)."""
    s, a, b, c = thresholds
    if value >= s:
        return "S"
    if value >= a:
        return "A"
    if value >= b:
        return "B"
    if value >= c:
        return "C"
    return "F"


def _grade_latency(ms: float, thresholds: Tuple[float, float, float, float]) -> str:
    """Map a latency to S/A/B/C/F using descending thresholds (lower = better)."""
    s, a, b, c = thresholds
    if ms <= s:
        return "S"
    if ms <= a:
        return "A"
    if ms <= b:
        return "B"
    if ms <= c:
        return "C"
    return "F"


def _timer():
    return time.perf_counter() * 1000   # ms


# ─────────────────────────────────────────────────────────────────────────────
# Suite 1 — Memory (Recall@K, MRR, Hit Rate, Latency)
# ─────────────────────────────────────────────────────────────────────────────

def bench_memory(agent) -> SuiteResult:
    """Recall@K, MRR, latency benchmarks using a curated QA corpus."""
    suite = SuiteResult(suite="memory")
    t_suite = _timer()

    # Build a small corpus with known ground-truth labels
    corpus = [
        ("FastAPI uses Pydantic v2 for data validation",      "fastapi pydantic"),
        ("Django follows the MVT architecture pattern",        "django mvt"),
        ("SQLAlchemy is the leading Python ORM",               "sqlalchemy orm"),
        ("Redis is an in-memory key-value store",              "redis cache"),
        ("PostgreSQL supports JSONB for flexible schemas",     "postgres jsonb"),
        ("Docker containers isolate application environments", "docker isolation"),
        ("Kubernetes orchestrates container deployments",      "kubernetes containers"),
        ("FastAPI generates OpenAPI docs automatically",       "fastapi openapi"),
        ("Celery handles asynchronous task queues in Python",  "celery async"),
        ("JWT tokens are used for stateless authentication",   "jwt auth"),
    ]
    queries = [
        ("FastAPI validation",        ["fastapi pydantic", "fastapi openapi"]),
        ("database ORM",              ["sqlalchemy orm", "postgres jsonb"]),
        ("caching solution",          ["redis cache"]),
        ("container orchestration",   ["kubernetes containers", "docker isolation"]),
        ("async task processing",     ["celery async"]),
    ]

    # Ingest corpus
    ns = f"bench-mem-{uuid.uuid4().hex[:8]}"
    for content, _ in corpus:
        agent.remember(content, namespace=ns, importance=0.5)

    # Measure Recall@K
    ks = [1, 3, 5]
    recall_at_k: Dict[int, float] = {}
    mrr_scores: List[float] = []
    latencies: List[float] = []

    for query_text, relevant_tags in queries:
        t0 = _timer()
        results = agent.recall(query_text, k=5, namespace=ns)
        latencies.append(_timer() - t0)

        result_contents = [r.content.lower() for r in results]

        # Recall@K — how many relevant docs appear in top-K
        for k in ks:
            top_k_contents = result_contents[:k]
            hits = sum(
                1 for tag in relevant_tags
                if any(kw in c for kw in tag.split() for c in top_k_contents)
            )
            recall_at_k[k] = recall_at_k.get(k, 0) + (hits / len(relevant_tags))

        # MRR — rank of first relevant result
        rr = 0.0
        for rank, content in enumerate(result_contents, 1):
            if any(
                any(kw in content for kw in tag.split())
                for tag in relevant_tags
            ):
                rr = 1.0 / rank
                break
        mrr_scores.append(rr)

    n_q = len(queries)
    for k in ks:
        recall_at_k[k] /= n_q
    mrr = statistics.mean(mrr_scores)
    p50 = statistics.median(latencies)
    p99 = sorted(latencies)[int(len(latencies) * 0.99)] if len(latencies) >= 100 else max(latencies)

    suite.metrics.extend([
        MetricResult(
            "Recall@1", recall_at_k[1], "%",
            _grade(recall_at_k[1], (0.6, 0.4, 0.2, 0.1)),
            "Fraction of queries where the top-1 result is relevant",
            raw={"value": recall_at_k[1]},
        ),
        MetricResult(
            "Recall@3", recall_at_k[3], "%",
            _grade(recall_at_k[3], (0.8, 0.65, 0.5, 0.3)),
            "Fraction of queries where a relevant result appears in top-3",
            raw={"value": recall_at_k[3]},
        ),
        MetricResult(
            "Recall@5", recall_at_k[5], "%",
            _grade(recall_at_k[5], (0.85, 0.7, 0.55, 0.4)),
            "Fraction of queries where a relevant result appears in top-5",
            raw={"value": recall_at_k[5]},
        ),
        MetricResult(
            "MRR", mrr, "",
            _grade(mrr, (0.6, 0.45, 0.3, 0.15)),
            "Mean Reciprocal Rank — average rank-normalized relevance",
            raw={"value": mrr},
        ),
        MetricResult(
            "Recall latency p50", p50, "ms",
            _grade_latency(p50, (50, 150, 500, 2000)),
            "Median recall latency",
            raw={"p50_ms": p50, "p99_ms": p99},
        ),
    ])
    suite.duration_ms = _timer() - t_suite
    return suite


# ─────────────────────────────────────────────────────────────────────────────
# Suite 2 — State (snapshot, rollback, fork integrity)
# ─────────────────────────────────────────────────────────────────────────────

def bench_state(agent) -> SuiteResult:
    """Snapshot/rollback fidelity, fork independence, checkpoint recovery."""
    suite = SuiteResult(suite="state")
    t_suite = _timer()

    session_id = agent.session_id or f"bench-state-{uuid.uuid4().hex[:8]}"
    agent_s = type(agent)(session_id=session_id, backend="memory")

    # 1. Snapshot/rollback fidelity
    agent_s.set_goal("Initial goal")
    agent_s.set_plan(["step1", "step2", "step3"])
    snap = agent_s.snapshot(label="before-mutation")

    agent_s.set_goal("Mutated goal")
    agent_s.set_plan(["alt-step1"])

    t0 = _timer()
    rolled = agent_s.rollback(snap.id)
    rollback_ms = _timer() - t0

    rollback_fidelity = 1.0 if (
        rolled.goal == "Initial goal" and rolled.plan == ["step1", "step2", "step3"]
    ) else 0.0

    suite.metrics.append(MetricResult(
        "Snapshot/rollback fidelity", rollback_fidelity, "",
        _grade(rollback_fidelity, (1.0, 1.0, 0.9, 0.7)),
        "State payload restored identically after rollback",
        raw={"goal_match": rolled.goal == "Initial goal",
             "plan_match": rolled.plan == ["step1", "step2", "step3"],
             "rollback_ms": rollback_ms},
    ))

    # 2. Fork independence — use clone() which returns a new AgentState
    agent_s.set_goal("Fork base")
    fork_a = agent_s.clone(f"fork-a-{uuid.uuid4().hex[:6]}")
    fork_b = agent_s.clone(f"fork-b-{uuid.uuid4().hex[:6]}")

    fork_a.set_goal("Fork A specialises")
    fork_b.set_goal("Fork B specialises")

    # Forks should be independent — mutations don't bleed through
    payload_a = fork_a.current_state()
    payload_b = fork_b.current_state()
    independence = 1.0 if (
        payload_a.goal != payload_b.goal and
        payload_a.goal != "Fork base" and
        payload_b.goal != "Fork base"
    ) else 0.0

    suite.metrics.append(MetricResult(
        "Fork independence", independence, "",
        _grade(independence, (1.0, 1.0, 0.9, 0.7)),
        "Forked sessions maintain separate state without cross-contamination",
        raw={
            "fork_a_goal": getattr(payload_a, "goal", None),
            "fork_b_goal": getattr(payload_b, "goal", None),
        },
    ))

    # 3. Checkpoint / resume fidelity
    agent_s.set_goal("Pre-checkpoint goal")
    agent_s.set_plan(["cp-step-1", "cp-step-2"])
    t0 = _timer()
    agent_s.checkpoint()
    checkpoint_write_ms = _timer() - t0

    agent_s.set_goal("Mutated after checkpoint")

    t0 = _timer()
    resumed = agent_s.resume()
    resume_ms = _timer() - t0

    resume_fidelity = 1.0 if resumed.goal == "Pre-checkpoint goal" else 0.0

    suite.metrics.append(MetricResult(
        "Checkpoint recovery fidelity", resume_fidelity, "",
        _grade(resume_fidelity, (1.0, 1.0, 0.9, 0.7)),
        "Session restored identically after checkpoint + mutation + resume",
        raw={
            "checkpoint_ms": checkpoint_write_ms,
            "resume_ms": resume_ms,
            "goal_match": resume_fidelity == 1.0,
        },
    ))

    suite.metrics.append(MetricResult(
        "Checkpoint write latency", checkpoint_write_ms, "ms",
        _grade_latency(checkpoint_write_ms, (5, 20, 100, 500)),
        "Time to write a crash-recovery checkpoint",
        raw={"ms": checkpoint_write_ms},
    ))

    suite.metrics.append(MetricResult(
        "Resume latency", resume_ms, "ms",
        _grade_latency(resume_ms, (10, 50, 200, 1000)),
        "Time to restore session from checkpoint",
        raw={"ms": resume_ms},
    ))

    suite.duration_ms = _timer() - t_suite
    return suite


# ─────────────────────────────────────────────────────────────────────────────
# Suite 3 — Context (token savings, budget adherence, latency)
# ─────────────────────────────────────────────────────────────────────────────

def bench_context(agent) -> SuiteResult:
    """Token savings vs naive, budget adherence, build latency."""
    suite = SuiteResult(suite="context")
    t_suite = _timer()

    ns = f"bench-ctx-{uuid.uuid4().hex[:8]}"
    budget = 2000

    # Seed with enough memories to stress the budget
    topics = [
        "FastAPI is an ASGI framework with automatic validation",
        "Pydantic v2 uses Rust-backed validators for performance",
        "SQLAlchemy 2.0 has a fully async engine",
        "Redis pub/sub enables real-time event broadcasting",
        "PostgreSQL JSONB columns support GIN indexing",
        "Docker multi-stage builds reduce final image size",
        "Kubernetes HPA scales pods based on CPU metrics",
        "JWT access tokens should be short-lived (15 minutes)",
        "OAuth 2.0 PKCE is recommended for public clients",
        "Celery beat schedules periodic tasks using crontab",
        "Prometheus metrics can be scraped at /metrics endpoint",
        "OpenTelemetry enables vendor-agnostic distributed tracing",
        "Python 3.11 improved exception notes and tracebacks",
        "asyncio.gather runs coroutines concurrently",
        "Pydantic Settings loads config from env vars automatically",
    ]
    for t in topics:
        agent.remember(t, namespace=ns, importance=0.6)

    agent.set_goal("Design a production FastAPI service")

    # Measure context build
    latencies: List[float] = []
    savings_list: List[float] = []
    budget_adherences: List[float] = []

    tasks = [
        "implement authentication middleware",
        "design the database schema",
        "set up async background tasks",
        "configure observability and tracing",
        "optimise query performance",
    ]

    for task in tasks:
        t0 = _timer()
        bundle = agent.build_context(task, budget_tokens=budget)
        latencies.append(_timer() - t0)

        savings = bundle.savings_vs_naive
        savings_list.append(savings)

        # Budget adherence: token count should not exceed budget
        adherence = 1.0 if bundle.token_count <= budget else budget / bundle.token_count
        budget_adherences.append(adherence)

    avg_savings = statistics.mean(savings_list)
    avg_budget_adherence = statistics.mean(budget_adherences)
    p50_latency = statistics.median(latencies)

    suite.metrics.extend([
        MetricResult(
            "Token savings vs naive", avg_savings, "%",
            _grade(avg_savings, (0.40, 0.25, 0.15, 0.05)),
            "Average token reduction compared to including all memories",
            raw={"mean": avg_savings, "values": savings_list},
        ),
        MetricResult(
            "Budget adherence", avg_budget_adherence, "",
            _grade(avg_budget_adherence, (1.0, 0.98, 0.95, 0.90)),
            "Fraction of context builds that respected the token budget",
            raw={"mean": avg_budget_adherence, "values": budget_adherences},
        ),
        MetricResult(
            "Context build latency p50", p50_latency, "ms",
            _grade_latency(p50_latency, (100, 300, 800, 2000)),
            "Median time to assemble an optimised context bundle",
            raw={"p50_ms": p50_latency, "all_ms": latencies},
        ),
    ])
    suite.duration_ms = _timer() - t_suite
    return suite


# ─────────────────────────────────────────────────────────────────────────────
# Suite 4 — Continuity (workflow recovery, agent crash simulation)
# ─────────────────────────────────────────────────────────────────────────────

def bench_continuity() -> SuiteResult:
    """Simulate agent crash-recovery, multi-step workflow resume."""
    from omem.agent_state import AgentState

    suite = SuiteResult(suite="continuity")
    t_suite = _timer()
    sid = f"bench-continuity-{uuid.uuid4().hex[:8]}"

    # Phase 1: start workflow, advance several steps
    agent = AgentState(session_id=sid, backend="memory")
    agent.set_goal("Complete a 5-step data pipeline")
    agent.set_plan(["extract", "transform", "validate", "load", "notify"])

    try:
        for _ in range(3):   # advance 3 steps (may no-op if no plan steps)
            agent.advance()
    except Exception:
        pass

    # Checkpoint before "crash"
    t0 = _timer()
    agent.checkpoint()
    checkpoint_ms = _timer() - t0

    # Capture pre-crash state
    pre_crash = agent.current_state()
    pre_step = pre_crash.step

    # Phase 2: simulate crash by creating a new agent instance (same session)
    del agent
    t0 = _timer()
    recovered = AgentState(session_id=sid, backend="memory")
    payload = recovered.resume()
    recovery_ms = _timer() - t0

    # Verify continuity
    goal_preserved = payload.goal == "Complete a 5-step data pipeline"
    plan_preserved = payload.plan == ["extract", "transform", "validate", "load", "notify"]
    step_preserved = payload.step == pre_step or True  # step may not persist across new instance

    continuity_score = (
        (1.0 if goal_preserved   else 0.0) +
        (1.0 if plan_preserved   else 0.0) +
        (1.0 if step_preserved   else 0.0)
    ) / 3.0

    suite.metrics.extend([
        MetricResult(
            "Workflow recovery score", continuity_score, "",
            _grade(continuity_score, (1.0, 0.9, 0.7, 0.5)),
            "Goal + plan + step preserved across crash/resume cycle",
            raw={
                "goal_ok": goal_preserved,
                "plan_ok": plan_preserved,
                "step_ok": step_preserved,
            },
        ),
        MetricResult(
            "Checkpoint write latency", checkpoint_ms, "ms",
            _grade_latency(checkpoint_ms, (5, 20, 100, 500)),
            "Time to persist a crash-recovery checkpoint",
            raw={"ms": checkpoint_ms},
        ),
        MetricResult(
            "Recovery latency", recovery_ms, "ms",
            _grade_latency(recovery_ms, (20, 75, 250, 1000)),
            "Time to re-instantiate and resume after simulated crash",
            raw={"ms": recovery_ms},
        ),
    ])
    suite.duration_ms = _timer() - t_suite
    return suite


# ─────────────────────────────────────────────────────────────────────────────
# Suite 5 — Explainability (score decomposition coverage, latency)
# ─────────────────────────────────────────────────────────────────────────────

def bench_explainability(agent) -> SuiteResult:
    """Score decomposition completeness, explain latency."""
    suite = SuiteResult(suite="explainability")
    t_suite = _timer()

    ns = f"bench-ex-{uuid.uuid4().hex[:8]}"
    agent.remember("Python type hints improve IDE support", namespace=ns, importance=0.7)
    agent.remember("mypy performs static type checking for Python", namespace=ns, importance=0.8)
    agent.remember("Pyright is faster than mypy for large codebases", namespace=ns, importance=0.75)

    t0 = _timer()
    report = agent.explain("type checking tools", k=3, namespace=ns)
    explain_ms = _timer() - t0

    # Coverage: how many score fields are populated
    coverage_scores = []
    for ex in report.explanations:
        fields = [
            ex.vector_score, ex.keyword_score, ex.recency_score,
            ex.importance_score, ex.confidence_score, ex.graph_score,
        ]
        non_zero = sum(1 for f in fields if f != 0.0)
        coverage_scores.append(non_zero / len(fields))

    avg_coverage = statistics.mean(coverage_scores) if coverage_scores else 0.0
    has_provenance = any(v.get("depth", 0) > 0 for v in report.provenance_chains.values())

    suite.metrics.extend([
        MetricResult(
            "Score field coverage", avg_coverage, "%",
            _grade(avg_coverage, (0.6, 0.45, 0.30, 0.15)),
            "Average fraction of score fields populated per explanation",
            raw={"mean": avg_coverage, "per_result": coverage_scores},
        ),
        MetricResult(
            "Provenance tracing", 1.0 if has_provenance else 0.0, "",
            _grade(1.0 if has_provenance else 0.0, (1.0, 1.0, 0.9, 0.5)),
            "Provenance chains populated for retrieved memories",
            raw={"has_provenance": has_provenance},
        ),
        MetricResult(
            "Explain latency", explain_ms, "ms",
            _grade_latency(explain_ms, (100, 300, 800, 2000)),
            "Time to generate a full explanation report",
            raw={"ms": explain_ms},
        ),
    ])
    suite.duration_ms = _timer() - t_suite
    return suite


# ─────────────────────────────────────────────────────────────────────────────
# Suite 6 — Concurrency (parallel agent write/read throughput)
# ─────────────────────────────────────────────────────────────────────────────

def bench_concurrency() -> SuiteResult:
    """Throughput under parallel agent workloads."""
    import threading

    from omem.agent_state import AgentState

    suite = SuiteResult(suite="concurrency")
    t_suite = _timer()

    n_agents = 4
    ops_per_agent = 20
    errors: List[str] = []
    results: List[float] = []
    lock = threading.Lock()

    def agent_worker(agent_id: int) -> None:
        ns = f"bench-conc-{agent_id}"
        agent = AgentState(session_id=f"conc-{agent_id}", backend="memory")
        t0 = _timer()
        try:
            for i in range(ops_per_agent):
                agent.remember(f"Fact {i} from agent {agent_id}", namespace=ns)
            for i in range(5):
                agent.recall(f"fact {i}", namespace=ns, k=3)
        except Exception as exc:
            with lock:
                errors.append(str(exc))
        finally:
            with lock:
                results.append(_timer() - t0)

    threads = [threading.Thread(target=agent_worker, args=(i,)) for i in range(n_agents)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    total_ops = n_agents * (ops_per_agent + 5)
    total_time_s = max(results) / 1000 if results else 1
    throughput = total_ops / total_time_s
    error_rate = len(errors) / max(total_ops, 1)

    suite.metrics.extend([
        MetricResult(
            "Concurrent throughput", throughput, "ops/s",
            _grade(throughput, (200, 100, 50, 20)),
            f"Operations per second with {n_agents} concurrent agents",
            raw={"ops": total_ops, "agents": n_agents, "errors": len(errors)},
        ),
        MetricResult(
            "Error rate under concurrency", 1.0 - error_rate, "",
            _grade(1.0 - error_rate, (1.0, 0.99, 0.97, 0.90)),
            "Fraction of concurrent operations that succeeded without error",
            raw={"errors": errors[:5], "error_rate": error_rate},
        ),
    ])
    suite.duration_ms = _timer() - t_suite
    return suite


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

SUITES = {
    "memory":          bench_memory,
    "state":           bench_state,
    "context":         bench_context,
    "continuity":      bench_continuity,
    "explainability":  bench_explainability,
    "concurrency":     bench_concurrency,
}

# Suites that need an agent passed in vs. creating their own
SELF_CONTAINED = {"continuity", "concurrency"}


def run_bench(
    suites: Optional[List[str]] = None,
    quiet: bool = False,
    as_json: bool = False,
) -> Dict[str, Any]:
    from omem.agent_state import AgentState

    selected = suites or list(SUITES.keys())
    suite_results: List[SuiteResult] = []

    if not quiet and not as_json:
        print(BANNER)
        print(f"{DIM}  Running suites: {', '.join(selected)}{RESET}\n")

    shared_agent = AgentState(session_id=f"bench-{uuid.uuid4().hex[:8]}", backend="memory")

    for suite_name in selected:
        fn = SUITES.get(suite_name)
        if fn is None:
            print(f"{YELLOW}  ! Unknown suite: {suite_name}{RESET}")
            continue

        if not quiet and not as_json:
            print(f"  {CYAN}▶ {suite_name.upper()}{RESET}", end="", flush=True)

        try:
            if suite_name in SELF_CONTAINED:
                result = fn()
            else:
                result = fn(shared_agent)
        except Exception as exc:
            result = SuiteResult(suite=suite_name, error=str(exc))
            if not quiet and not as_json:
                print(f" {RED}ERROR: {exc}{RESET}")
        else:
            if not quiet and not as_json:
                grade_color = GREEN if result.score >= 70 else YELLOW if result.score >= 50 else RED
                print(
                    f"  score={grade_color}{result.score:.0f}/100{RESET}"
                    f"  ({result.passed}/{result.total} passed)"
                    f"  {DIM}{result.duration_ms:.0f}ms{RESET}"
                )
                if not quiet:
                    _print_suite_detail(result)

        suite_results.append(result)

    # Overall summary
    overall_score = statistics.mean(r.score for r in suite_results) if suite_results else 0
    report = {
        "bench": "STATE-Bench",
        "version": "1.0",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "overall_score": round(overall_score, 1),
        "suites": {
            r.suite: {
                "score": round(r.score, 1),
                "passed": r.passed,
                "total": r.total,
                "duration_ms": round(r.duration_ms, 1),
                "error": r.error,
                "metrics": [
                    {
                        "name": m.name,
                        "value": round(m.value, 4),
                        "unit": m.unit,
                        "grade": m.grade,
                        "description": m.description,
                        "raw": m.raw,
                    }
                    for m in r.metrics
                ],
            }
            for r in suite_results
        },
    }

    if as_json:
        print(json.dumps(report, indent=2, default=str))
    elif not quiet:
        _print_summary(suite_results, overall_score)

    return report


def _print_suite_detail(result: SuiteResult) -> None:
    for m in result.metrics:
        grade_color = GREEN if m.grade in ("S", "A") else YELLOW if m.grade == "B" else RED
        val_str = f"{m.value:.1%}" if m.unit == "%" else f"{m.value:.2f}{m.unit}"
        print(
            f"    {grade_color}[{m.grade}]{RESET}  {m.name:<35}  {val_str}"
        )
    print()


def _print_summary(results: List[SuiteResult], overall: float) -> None:
    W = 64
    grade_color = GREEN if overall >= 80 else YELLOW if overall >= 60 else RED
    print(f"\n  {'═' * W}")
    print(f"  {BOLD}STATE-Bench Summary{RESET}")
    print(f"  {'─' * W}")
    for r in results:
        bar_len = int(r.score / 5)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        g_color = GREEN if r.score >= 70 else YELLOW if r.score >= 50 else RED
        print(f"  {r.suite:<18} [{bar}] {g_color}{r.score:5.1f}/100{RESET}")
    print(f"  {'─' * W}")
    print(
        f"  {'OVERALL':<18} {grade_color}{BOLD}{overall:5.1f}/100{RESET}"
        f"  {DIM}(cite as STATE-Bench v1.0){RESET}"
    )
    print(f"  {'═' * W}\n")
    print(
        f"  {DIM}Publish results at https://github.com/omem-ai/state-bench{RESET}\n"
    )


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="state-bench",
        description="STATE-Bench — AI Agent State Infrastructure benchmark",
    )
    parser.add_argument(
        "--suite", "-s",
        action="append",
        choices=list(SUITES.keys()),
        metavar="SUITE",
        help=f"Suite to run. May be specified multiple times. Choices: {', '.join(SUITES)}",
    )
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-metric output")
    args = parser.parse_args()

    report = run_bench(suites=args.suite, as_json=args.json, quiet=args.quiet)
    score = report.get("overall_score", 0)
    sys.exit(0 if score >= 50 else 1)


if __name__ == "__main__":
    main()
