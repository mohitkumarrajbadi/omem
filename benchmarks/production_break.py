"""Production-break harness — fail the process when the store would lose data.

The public memory suite (STATE-Bench / LongMemEval / LoCoMo) is a *quality*
smoke test on tiny corpora. This module is the opposite: durable SQLite,
scale, concurrent writers, restart, isolation, and latency SLOs with
hard pass/fail gates.

Usage::

    python -m benchmarks.production_break
    python -m benchmarks.production_break --profile quick
    python -m benchmarks.production_break --profile break
    python -m benchmarks.production_break --profile smoke   # CI

Profiles:
  smoke  ~seconds, for pytest (hash embeddings ok)
  quick  a few minutes, 2k rows
  prod   default — 10k rows, 8 threads, stratified LongMemEval
  break  50k rows, 16 threads — intended to find the wall
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DATA = Path(__file__).resolve().parent / "data"

PROFILES: Dict[str, Dict[str, Any]] = {
    "smoke": {
        "n": 80,
        "needles": 6,
        "threads": 2,
        "ops": 8,
        "queries": 10,
        "lme_n": 0,
        "p95_ms": 400.0,
        "needle_min_hit": 0.75,
    },
    "quick": {
        "n": 2_000,
        "needles": 20,
        "threads": 4,
        "ops": 60,
        "queries": 40,
        "lme_n": 8,
        "p95_ms": 200.0,
        "needle_min_hit": 0.85,
    },
    "prod": {
        "n": 10_000,
        "needles": 40,
        "threads": 8,
        "ops": 150,
        "queries": 80,
        "lme_n": 20,
        "p95_ms": 150.0,
        "needle_min_hit": 0.90,
    },
    "break": {
        "n": 50_000,
        "needles": 50,
        "threads": 16,
        "ops": 250,
        "queries": 120,
        "lme_n": 40,
        "p95_ms": 250.0,
        "needle_min_hit": 0.90,
    },
}


@dataclass
class Case:
    name: str
    passed: bool
    detail: str
    metrics: Dict[str, Any] = field(default_factory=dict)


def _pct(data: Sequence[float], p: float) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    k = min(int(len(s) * p / 100.0), len(s) - 1)
    return float(s[k])


def _rss_mb() -> float:
    try:
        import resource

        ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return ru / (1024 * 1024) if sys.platform == "darwin" else ru / 1024.0
    except Exception:
        return 0.0


def _make_agent(db_path: str, session_id: str, namespace: str = "default"):
    from omem import AgentState

    return AgentState(
        backend="sqlite",
        db_path=db_path,
        session_id=session_id,
        namespace=namespace,
    )


def _close(agent) -> None:
    try:
        agent.flush()
    except Exception:
        pass
    try:
        agent.close()
    except Exception:
        pass


def _sku(i: int) -> str:
    return f"canarytoken{i:04d}zx9q"


def _distractor(i: int) -> str:
    region = ("iad", "sfo", "fra", "nrt")[i % 4]
    return (
        f"Ops log {i}: service svc-{i % 47} handled incident INC-{i:06d} "
        f"in region {region} with latency {i % 97}ms and retry {i % 5}."
    )


def _needle_text(i: int) -> str:
    return (
        f"Canonical runbook for {_sku(i)}: page the oncall rotation immediately "
        f"and open the SEV-1 bridge."
    )


def case_durable_restart(cfg: Dict[str, Any], work: Path) -> Case:
    db = str(work / "restart.db")
    n = int(cfg["n"])
    sku0 = _sku(0)
    t0 = time.perf_counter()
    a = _make_agent(db, "break-restart")
    try:
        a.remember(_needle_text(0), importance=0.95, force=True)
        for i in range(1, n):
            a.remember(_distractor(i), importance=0.3, force=True)
        a.flush()
    finally:
        _close(a)
    ingest_s = time.perf_counter() - t0

    b = _make_agent(db, "break-restart-2")
    try:
        listed = b.memory.list()
        count = len(listed)
        hits = b.recall(sku0, k=5)
        blob = " ".join(m.content for m in hits)
        found = sku0 in blob
    finally:
        _close(b)

    passed = count >= n and found
    return Case(
        name="durable_restart",
        passed=passed,
        detail=(
            f"wrote {n}, relisted {count}, needle_in_top5={found} "
            f"ingest={ingest_s:.1f}s"
        ),
        metrics={
            "n": n,
            "relisted": count,
            "needle_hit": found,
            "ingest_s": round(ingest_s, 2),
            "writes_per_s": round(n / ingest_s, 1) if ingest_s else 0.0,
        },
    )


def case_needle_haystack(cfg: Dict[str, Any], work: Path) -> Case:
    db = str(work / "haystack.db")
    n = int(cfg["n"])
    n_needles = int(cfg["needles"])
    min_hit = float(cfg["needle_min_hit"])
    a = _make_agent(db, "break-haystack")
    try:
        for i in range(n_needles):
            a.remember(_needle_text(i), importance=0.95, force=True)
        for i in range(n):
            a.remember(_distractor(i + 10_000), importance=0.25, force=True)
        a.flush()
        hits = 0
        lat: List[float] = []
        for i in range(n_needles):
            q = _sku(i)
            t0 = time.perf_counter()
            rec = a.recall(q, k=5)
            lat.append((time.perf_counter() - t0) * 1000)
            blob = " ".join(m.content for m in rec)
            hits += int(q in blob)
        rate = hits / n_needles if n_needles else 0.0
    finally:
        _close(a)

    passed = rate >= min_hit
    return Case(
        name="needle_haystack",
        passed=passed,
        detail=f"hit@5={100.0 * rate:.1f}% (gate {100.0 * min_hit:.0f}%) n={n} needles={n_needles}",
        metrics={
            "n_haystack": n,
            "n_needles": n_needles,
            "hit_at_5_pct": round(100.0 * rate, 1),
            "p50_ms": round(_pct(lat, 50), 2),
            "p95_ms": round(_pct(lat, 95), 2),
        },
    )


def case_concurrent_sqlite(cfg: Dict[str, Any], work: Path) -> Case:
    db = str(work / "concurrent.db")
    threads = int(cfg["threads"])
    ops = int(cfg["ops"])
    a = _make_agent(db, "break-conc")
    errors: List[str] = []
    add_lat: List[float] = []
    rec_lat: List[float] = []
    lock = threading.Lock()

    def worker(tid: int) -> None:
        rng = random.Random(tid * 997)
        for i in range(ops):
            try:
                if rng.random() < 0.45:
                    t0 = time.perf_counter()
                    a.recall(f"incident INC-{rng.randint(0, 50):06d}", k=5)
                    dt = (time.perf_counter() - t0) * 1000
                    with lock:
                        rec_lat.append(dt)
                else:
                    marker = f"<<W{tid}I{i}>>"
                    t0 = time.perf_counter()
                    mid = a.remember(
                        f"{marker} shared concurrent sqlite row",
                        importance=0.7,
                        force=True,
                    )
                    dt = (time.perf_counter() - t0) * 1000
                    if not mid:
                        raise RuntimeError(f"empty id {marker}")
                    with lock:
                        add_lat.append(dt)
            except Exception as exc:  # noqa: BLE001 — collect
                with lock:
                    errors.append(f"t{tid}/{i}: {exc}")

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=threads) as pool:
        futs = [pool.submit(worker, i) for i in range(threads)]
        for f in as_completed(futs):
            f.result()
    elapsed = time.perf_counter() - t0
    a.flush()
    contents = [m.content for m in a.memory.list()]
    listed = len(contents)
    present = sum(
        1
        for tid in range(threads)
        for i in range(ops)
        if any(f"<<W{tid}I{i}>>" in c for c in contents)
    )
    # ~55% of ops are writes; require most of that floor to land.
    expected_min = int(0.35 * threads * ops)
    _close(a)

    lost = present < expected_min
    passed = not errors and not lost and listed >= expected_min
    return Case(
        name="concurrent_sqlite",
        passed=passed,
        detail=(
            f"errors={len(errors)} listed={listed} write_markers={present} "
            f"min={expected_min} {elapsed:.1f}s"
        ),
        metrics={
            "threads": threads,
            "ops_per_thread": ops,
            "errors": len(errors),
            "error_sample": errors[:5],
            "listed": listed,
            "write_markers": present,
            "duration_s": round(elapsed, 2),
            "add_p50_ms": round(_pct(add_lat, 50), 2),
            "add_p99_ms": round(_pct(add_lat, 99), 2),
            "recall_p50_ms": round(_pct(rec_lat, 50), 2),
            "recall_p99_ms": round(_pct(rec_lat, 99), 2),
            "ops_per_s": round((threads * ops) / elapsed, 1) if elapsed else 0.0,
        },
    )


def case_belief_revision(work: Path) -> Case:
    db = str(work / "tms.db")
    a = _make_agent(db, "break-tms")
    try:
        a.remember("User lives in NYC", importance=0.85, force=True)
        a.remember("User moved to SF", importance=0.85, force=True)
        a.flush()
        rec = a.recall("where does the user live", k=5)
        blob = " ".join(m.content.lower() for m in rec)
        top = rec[0].content.lower() if rec else ""
        sf_wins = "sf" in top or "san francisco" in top
        nyc_stale = not ("nyc" in top and "sf" not in top)
        listed = a.memory.list(include_inactive=True)
        deprecated = [
            m
            for m in listed
            if "nyc" in m.content.lower() and not getattr(m, "active", True)
        ]
        passed = bool(rec) and sf_wins and nyc_stale
        detail = (
            f"top={rec[0].content[:60]!r} sf_wins={sf_wins} "
            f"deprecated_nyc={len(deprecated)}"
            if rec
            else "empty recall"
        )
    finally:
        _close(a)
    return Case(
        name="belief_revision",
        passed=passed,
        detail=detail,
        metrics={"sf_wins": sf_wins if rec else False, "deprecated_nyc": len(deprecated)},
    )


def case_namespace_isolation(work: Path) -> Case:
    db = str(work / "iso.db")
    a = _make_agent(db, "break-iso", namespace="tenant-a")
    try:
        a.remember("SECRET-ALPHA-ONLY credential vault", importance=0.9, force=True)
        a.remember(
            "SECRET-BETA-ONLY payroll dump",
            importance=0.9,
            force=True,
            namespace="tenant-b",
        )
        a.flush()
        hits_a = a.recall(
            "SECRET-BETA-ONLY", k=8, namespace="tenant-a", project_only=True
        )
        leak = any("SECRET-BETA-ONLY" in m.content for m in hits_a)
        hits_b = a.recall(
            "SECRET-BETA-ONLY", k=5, namespace="tenant-b", project_only=True
        )
        found_b = any("SECRET-BETA-ONLY" in m.content for m in hits_b)
        passed = (not leak) and found_b
        detail = f"leak_to_a={leak} beta_visible_in_b={found_b}"
    finally:
        _close(a)
    return Case(
        name="namespace_isolation",
        passed=passed,
        detail=detail,
        metrics={"leak": leak, "beta_found": found_b},
    )


def case_graph_and_checkpoint(work: Path) -> Case:
    db = str(work / "graph.db")
    sid = "break-graph"
    a = _make_agent(db, sid)
    try:
        a.set_goal("Ship production-break gates")
        a.learn("FastAPI", "uses", "Pydantic")
        ckpt = a.checkpoint()
        a.flush()
    finally:
        _close(a)

    b = _make_agent(db, sid)
    try:
        payload = b.resume()
        goal = getattr(payload, "goal", "") or ""
        sub = b.know_about("FastAPI", depth=1)
        preds = {e.predicate for e in sub.edges}
        passed = "Ship production-break" in goal and "uses" in preds and bool(ckpt)
        detail = f"goal={goal!r} predicates={sorted(preds)} ckpt={ckpt[:12]}…"
    finally:
        _close(b)
    return Case(
        name="graph_checkpoint_restart",
        passed=passed,
        detail=detail,
        metrics={"checkpoint_id": ckpt, "goal": goal, "predicates": sorted(preds)},
    )


def case_context_budget(work: Path) -> Case:
    db = str(work / "ctx.db")
    budget = 800
    a = _make_agent(db, "break-ctx")
    try:
        a.set_goal("Answer the oncall question")
        a.remember(_needle_text(1), importance=0.95, force=True)
        for i in range(120):
            a.remember(_distractor(i), importance=0.2, force=True)
        a.flush()
        bundle = a.build_context(
            f"How do I page oncall for {_sku(1)}?",
            budget_tokens=budget,
        )
        used = int(getattr(bundle, "token_count", 0) or 0)
        text = getattr(bundle, "text", "") or ""
        over = used > int(budget * 1.15)
        has_needle = _sku(1) in text
        passed = (not over) and used > 0
        detail = f"tokens={used}/{budget} over={over} needle_packed={has_needle}"
    finally:
        _close(a)
    return Case(
        name="context_budget",
        passed=passed,
        detail=detail,
        metrics={"token_count": used, "budget": budget, "needle_packed": has_needle},
    )


def case_latency_slo(cfg: Dict[str, Any], work: Path) -> Case:
    db = str(work / "slo.db")
    n = max(200, int(cfg["n"]) // 5)
    n_q = int(cfg["queries"])
    gate = float(cfg["p95_ms"])
    a = _make_agent(db, "break-slo")
    try:
        for i in range(n):
            a.remember(_distractor(i), importance=0.3, force=True)
        a.remember(_needle_text(3), importance=0.95, force=True)
        a.flush()
        queries = [
            f"incident INC-{i:06d} region"
            for i in range(min(n, max(n_q, 10)))
        ]
        for i in range(3):
            a.recall(queries[i % len(queries)], k=5)
        lat: List[float] = []
        for i in range(n_q):
            q = queries[i % len(queries)]
            # Unique suffix busts working-memory cache without changing retrieval.
            t0 = time.perf_counter()
            a.recall(f"{q} #{i}", k=5)
            lat.append((time.perf_counter() - t0) * 1000)
        p95 = _pct(lat, 95)
        p99 = _pct(lat, 99)
        passed = bool(lat) and p95 <= gate
        detail = f"p95={p95:.1f}ms p99={p99:.1f}ms gate={gate:.0f}ms n={n}"
    finally:
        _close(a)
    return Case(
        name="latency_slo",
        passed=passed,
        detail=detail,
        metrics={
            "n": n,
            "n_queries": n_q,
            "p50_ms": round(_pct(lat, 50), 2),
            "p95_ms": round(p95, 2),
            "p99_ms": round(p99, 2),
            "gate_p95_ms": gate,
        },
    )


def case_stratified_lme(cfg: Dict[str, Any], work: Path) -> Case:
    n = int(cfg["lme_n"])
    if n <= 0:
        return Case(
            name="stratified_longmemeval",
            passed=True,
            detail="skipped (profile lme_n=0)",
            metrics={"skipped": True},
        )
    path = DATA / "longmemeval_oracle.json"
    if not path.exists():
        return Case(
            name="stratified_longmemeval",
            passed=True,
            detail=f"skipped (missing {path})",
            metrics={"skipped": True},
        )
    from benchmarks.public_memory_suite import _answer_hit, _stratified_lme

    data = json.loads(path.read_text())
    subset = _stratified_lme(data, n)
    hits = 0
    lat: List[float] = []
    by_type: Dict[str, List[bool]] = {}
    for i, item in enumerate(subset):
        db = str(work / f"lme_{i}.db")
        a = _make_agent(db, f"lme-{i}")
        try:
            for session in item.get("haystack_sessions") or []:
                for turn in session:
                    content = turn.get("content") if isinstance(turn, dict) else None
                    if content:
                        role = turn.get("role", "user")
                        a.remember(f"[{role}] {content}", force=True)
            a.flush()
            q = item["question"]
            t0 = time.perf_counter()
            rec = a.recall(q, k=5)
            lat.append((time.perf_counter() - t0) * 1000)
            ok = _answer_hit(item.get("answer", ""), [m.content for m in rec])
            hits += int(ok)
            by_type.setdefault(item.get("question_type", "unknown"), []).append(ok)
        finally:
            _close(a)
    total = len(subset)
    rate = hits / total if total else 0.0
    # Quality signal, not the 0.1.0 bar — fail only if retrieval is broken.
    passed = rate >= 0.40
    type_scores = {
        t: round(100.0 * sum(v) / len(v), 1) if v else 0.0 for t, v in by_type.items()
    }
    return Case(
        name="stratified_longmemeval",
        passed=passed,
        detail=f"hit@5={100.0 * rate:.1f}% n={total} types={type_scores}",
        metrics={
            "n": total,
            "hit_at_5_pct": round(100.0 * rate, 1),
            "p50_ms": round(_pct(lat, 50), 2),
            "by_question_type": type_scores,
            "note": "Stratified mix, not first-50 temporal-reasoning.",
        },
    )


def run_suite(
    profile: str = "prod",
    workdir: Optional[str] = None,
    skip_lme: bool = False,
) -> Dict[str, Any]:
    if profile not in PROFILES:
        raise ValueError(f"unknown profile {profile!r}; choose {sorted(PROFILES)}")
    cfg = dict(PROFILES[profile])
    if skip_lme:
        cfg["lme_n"] = 0

    from omem.core.retrieval.embeddings import Embedder

    probe = Embedder()
    own_tmp = workdir is None
    tmp = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="omem-break-"))
    tmp.mkdir(parents=True, exist_ok=True)

    print(
        f"profile={profile} embedder={probe.kind} semantic={probe.is_semantic} "
        f"n={cfg['n']} threads={cfg['threads']} rss_start={_rss_mb():.0f}MB"
    )
    if profile in ("prod", "break") and probe.is_semantic:
        print(
            "NOTE: MiniLM ingest at this N is slow on purpose — that is the "
            "production path. Use --profile quick for a shorter gate."
        )

    cases: List[Case] = []
    order = [
        ("durable_restart", lambda: case_durable_restart(cfg, tmp)),
        ("needle_haystack", lambda: case_needle_haystack(cfg, tmp)),
        ("concurrent_sqlite", lambda: case_concurrent_sqlite(cfg, tmp)),
        ("belief_revision", lambda: case_belief_revision(tmp)),
        ("namespace_isolation", lambda: case_namespace_isolation(tmp)),
        ("graph_checkpoint_restart", lambda: case_graph_and_checkpoint(tmp)),
        ("context_budget", lambda: case_context_budget(tmp)),
        ("latency_slo", lambda: case_latency_slo(cfg, tmp)),
        ("stratified_longmemeval", lambda: case_stratified_lme(cfg, tmp)),
    ]
    t_all = time.perf_counter()
    for name, fn in order:
        print(f"=== {name} ===")
        case = fn()
        cases.append(case)
        flag = "PASS" if case.passed else "FAIL"
        print(f"  {flag}  {case.detail}")

    failed = [c.name for c in cases if not c.passed]
    report = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "profile": profile,
        "embedder": probe.kind,
        "semantic": probe.is_semantic,
        "duration_s": round(time.perf_counter() - t_all, 2),
        "rss_mb": round(_rss_mb(), 1),
        "passed": not failed,
        "failed": failed,
        "cases": {
            c.name: {"passed": c.passed, "detail": c.detail, "metrics": c.metrics}
            for c in cases
        },
        "methodology": (
            "Durable SQLite AgentState. Fail on data loss, isolation leak, "
            "budget overrun, p95 SLO miss, or TMS/graph restart miss. "
            "Not the public STATE-Bench / first-50 LongMemEval smoke."
        ),
    }
    if own_tmp:
        report["workdir"] = str(tmp)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="OMem production-break harness")
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILES),
        default="prod",
        help="smoke | quick | prod | break",
    )
    parser.add_argument(
        "--out",
        default=str(ROOT / "distribution" / "production_break_results.json"),
    )
    parser.add_argument("--skip-lme", action="store_true")
    parser.add_argument("--workdir", default=None)
    args = parser.parse_args()

    report = run_suite(
        profile=args.profile, workdir=args.workdir, skip_lme=args.skip_lme
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\nWrote {out}")
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "failed": report["failed"],
                "duration_s": report["duration_s"],
                "embedder": report["embedder"],
            },
            indent=2,
        )
    )
    sys.exit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
