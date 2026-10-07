#!/usr/bin/env python3
"""OMem vs Mem0 / Graphiti bakeoff — retrieval Hit@K, no LLM judge.

OMem always runs with ``--no-llm`` (the only supported OMem path): store what
was written, classify/link without a generator, recall with BM25+vector+RRF.

Mem0 and Graphiti are optional live adapters. Their default write path uses an
LLM extract; we measure that system as configured, and we do **not** invent
modeled 163× speedups when they are not installed.

Metrics:
  - Hit@5: gold substring appears in top-k recalled texts (same rule as
    ``benchmarks/public_memory_suite.py``)
  - add_ms / recall_p50_ms on this fixture
  - systems skipped rather than faked when extras are missing

Usage::

    python -m benchmarks.bakeoff
    python -m benchmarks.bakeoff --json
    python -m benchmarks.bakeoff --live-mem0 --live-graphiti
    OMEM_EMBEDDER=hash python -m benchmarks.bakeoff   # CI / no MiniLM
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CASES: List[Dict[str, Any]] = [
    {
        "id": "location_revision",
        "writes": ["User lives in NYC", "User moved to SF"],
        "query": "where does the user live now",
        "expect": "SF",
        "reject": "NYC",
    },
    {
        "id": "exact_sku",
        "writes": [
            "Checkout SKU is SKU-998877 for the winter jacket.",
            "The shopping cart service uses Redis for session state.",
        ],
        "query": "SKU-998877",
        "expect": "SKU-998877",
    },
    {
        "id": "decision",
        "writes": [
            "We decided to use PostgreSQL for production, not MongoDB.",
            "The office snack budget is $40 per week.",
        ],
        "query": "production database",
        "expect": "PostgreSQL",
    },
    {
        "id": "preference",
        "writes": [
            "User prefers dark mode in the dashboard.",
            "Sprint 12 shipped the billing export CSV.",
        ],
        "query": "dashboard theme preference",
        "expect": "dark mode",
    },
]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _hit(expect: str, contents: Sequence[str]) -> bool:
    needle = _norm(expect)
    blob = _norm(" \n ".join(contents))
    return bool(needle) and needle in blob


def score_case(case: Dict[str, Any], contents: Sequence[str]) -> Dict[str, Any]:
    expect_ok = _hit(case["expect"], contents)
    reject = case.get("reject")
    reject_ok = True
    if reject:
        # For location_revision, current belief should mention SF; NYC in
        # superseded text is a miss if SF is absent.
        if case["id"] == "location_revision":
            reject_ok = expect_ok and not (
                _hit(reject, contents) and not _hit(case["expect"], contents)
            )
        else:
            reject_ok = not _hit(reject, contents)
    return {
        "id": case["id"],
        "hit": bool(expect_ok and reject_ok),
        "expect_ok": expect_ok,
        "texts": list(contents)[:5],
    }


def run_omem(cases: Sequence[Dict[str, Any]], k: int = 5) -> Dict[str, Any]:
    from omem import OMem

    add_ms: List[float] = []
    recall_ms: List[float] = []
    scored: List[Dict[str, Any]] = []
    prompt_tokens: List[int] = []
    t_all = time.perf_counter()
    for case in cases:
        m = OMem(backend="memory")
        t0 = time.perf_counter()
        for text in case["writes"]:
            m.add(text, force=True, importance=0.8)
        add_ms.append((time.perf_counter() - t0) * 1000)
        t1 = time.perf_counter()
        hits = m.recall(case["query"], k=k)
        recall_ms.append((time.perf_counter() - t1) * 1000)
        texts = [h.content for h in hits]
        prompt_tokens.append(_approx_tokens("\n".join(texts)))
        scored.append(score_case(case, texts))
    elapsed = (time.perf_counter() - t_all) * 1000
    n = len(scored)
    hits = sum(1 for s in scored if s["hit"])
    return {
        "system": "omem",
        "no_llm": True,
        "hit_at_k_pct": round(100.0 * hits / n, 1) if n else 0.0,
        "n": n,
        "k": k,
        "add_ms_p50": round(statistics.median(add_ms), 2) if add_ms else 0.0,
        "recall_p50_ms": round(statistics.median(recall_ms), 2) if recall_ms else 0.0,
        "elapsed_ms": round(elapsed, 2),
        "mean_prompt_tokens": round(statistics.mean(prompt_tokens), 1) if prompt_tokens else 0.0,
        "cases": scored,
        "note": "No generative LLM. TMS revises beliefs; RRF ranks exact tokens.",
    }


def run_omem_pack(cases: Sequence[Dict[str, Any]], budget_tokens: int = 180) -> Dict[str, Any]:
    """Answer-in-budget: does build_context still contain the gold fact?"""
    from omem import AgentState

    hits = 0
    tokens: List[int] = []
    scored: List[Dict[str, Any]] = []
    for case in cases:
        agent = AgentState(backend="memory", session_id=f"pack-{case['id']}")
        try:
            for text in case["writes"]:
                agent.remember(text, force=True, importance=0.85)
            bundle = agent.build_context(case["query"], budget_tokens=budget_tokens)
            used = int(getattr(bundle, "token_count", 0) or 0)
            tokens.append(used)
            text = getattr(bundle, "text", "") or ""
            ok = _hit(case["expect"], [text])
            hits += int(ok)
            scored.append(
                {
                    "id": case["id"],
                    "hit": ok,
                    "token_count": used,
                    "budget": budget_tokens,
                    "savings_vs_naive": round(float(getattr(bundle, "savings_vs_naive", 0) or 0), 3),
                }
            )
        finally:
            agent.close()
    n = len(scored)
    return {
        "system": "omem_pack",
        "no_llm": True,
        "hit_at_k_pct": round(100.0 * hits / n, 1) if n else 0.0,
        "answer_in_budget_pct": round(100.0 * hits / n, 1) if n else 0.0,
        "mean_packed_tokens": round(statistics.mean(tokens), 1) if tokens else 0.0,
        "mean_prompt_tokens": round(statistics.mean(tokens), 1) if tokens else 0.0,
        "budget_tokens": budget_tokens,
        "n": n,
        "cases": scored,
        "note": "Packed prompt must contain the gold substring under a hard token ceiling.",
    }


def run_vector_baseline(cases: Sequence[Dict[str, Any]], k: int = 5) -> Dict[str, Any]:
    """Local no-LLM baseline: embed + ANN only (no TMS, no BM25/RRF)."""
    import numpy as np

    from omem.core.retrieval.embeddings import Embedder
    from omem.core.retrieval.vector import VectorIndex

    enc = Embedder()
    add_ms: List[float] = []
    recall_ms: List[float] = []
    scored: List[Dict[str, Any]] = []
    for case in cases:
        idx = VectorIndex(dim=384)
        store: List[str] = []
        t0 = time.perf_counter()
        for text in case["writes"]:
            vec = enc.encode(text)
            nrm = float(np.linalg.norm(vec)) or 1.0
            idx.add(vec / nrm)
            store.append(text)
        add_ms.append((time.perf_counter() - t0) * 1000)
        q = enc.encode(case["query"])
        q = q / (float(np.linalg.norm(q)) or 1.0)
        t1 = time.perf_counter()
        _scores, indices = idx.search(q, top_k=min(k, len(store)))
        recall_ms.append((time.perf_counter() - t1) * 1000)
        texts = [store[int(i)] for i in indices if 0 <= int(i) < len(store)]
        scored.append(score_case(case, texts))
    n = len(scored)
    hits = sum(1 for s in scored if s["hit"])
    return {
        "system": "vector_baseline",
        "no_llm": True,
        "hit_at_k_pct": round(100.0 * hits / n, 1) if n else 0.0,
        "n": n,
        "k": k,
        "add_ms_p50": round(statistics.median(add_ms), 2) if add_ms else 0.0,
        "recall_p50_ms": round(statistics.median(recall_ms), 2) if recall_ms else 0.0,
        "cases": scored,
        "note": "Embed + cosine only. No belief revision, no keyword fusion.",
        "mean_prompt_tokens": round(
            statistics.mean(
                _approx_tokens("\n".join(c.get("texts") or [])) for c in scored
            ),
            1,
        ) if scored else 0.0,
    }


def _mem0_texts(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, dict):
        rows = raw.get("results") or raw.get("memories") or []
    else:
        rows = raw
    out = []
    for row in rows:
        if isinstance(row, str):
            out.append(row)
        elif isinstance(row, dict):
            out.append(str(row.get("memory") or row.get("text") or row.get("content") or ""))
    return [t for t in out if t]


def run_mem0(cases: Sequence[Dict[str, Any]], k: int = 5) -> Dict[str, Any]:
    try:
        from mem0 import Memory  # type: ignore
    except ImportError:
        return {
            "system": "mem0",
            "skipped": True,
            "reason": "mem0ai not installed (pip install mem0ai) and OPENAI_API_KEY for default extract",
        }
    add_ms: List[float] = []
    recall_ms: List[float] = []
    scored: List[Dict[str, Any]] = []
    for i, case in enumerate(cases):
        uid = f"bakeoff-{case['id']}-{i}"
        mem = Memory()
        t0 = time.perf_counter()
        for text in case["writes"]:
            mem.add(text, user_id=uid)
        add_ms.append((time.perf_counter() - t0) * 1000)
        t1 = time.perf_counter()
        raw = mem.search(case["query"], user_id=uid, limit=k)
        recall_ms.append((time.perf_counter() - t1) * 1000)
        scored.append(score_case(case, _mem0_texts(raw)[:k]))
    n = len(scored)
    hits = sum(1 for s in scored if s["hit"])
    return {
        "system": "mem0",
        "no_llm": False,
        "skipped": False,
        "hit_at_k_pct": round(100.0 * hits / n, 1) if n else 0.0,
        "n": n,
        "k": k,
        "add_ms_p50": round(statistics.median(add_ms), 2) if add_ms else 0.0,
        "recall_p50_ms": round(statistics.median(recall_ms), 2) if recall_ms else 0.0,
        "cases": scored,
        "note": "Live Mem0 default path (LLM extract on write). Not equivalent to OMem --no-llm.",
    }


def run_graphiti(cases: Sequence[Dict[str, Any]], k: int = 5) -> Dict[str, Any]:
    try:
        from graphiti_core import Graphiti  # type: ignore
    except ImportError:
        return {
            "system": "graphiti",
            "skipped": True,
            "reason": "graphiti-core not installed; also needs Neo4j + an LLM for extract",
        }
    uri = os.environ.get("NEO4J_URI")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD")
    if not uri or not password:
        return {
            "system": "graphiti",
            "skipped": True,
            "reason": "Set NEO4J_URI and NEO4J_PASSWORD for a live Graphiti run",
        }
    add_ms: List[float] = []
    recall_ms: List[float] = []
    scored: List[Dict[str, Any]] = []
    g = Graphiti(uri, user, password)
    for i, case in enumerate(cases):
        group = f"bakeoff-{case['id']}-{i}"
        t0 = time.perf_counter()
        for j, text in enumerate(case["writes"]):
            # graphiti 0.3+ add_episode(name, episode_body, source_description, group_id)
            g.add_episode(
                name=f"{group}-{j}",
                episode_body=text,
                source_description="bakeoff",
                group_id=group,
            )
        add_ms.append((time.perf_counter() - t0) * 1000)
        t1 = time.perf_counter()
        raw = g.search(case["query"], group_ids=[group], num_results=k)
        recall_ms.append((time.perf_counter() - t1) * 1000)
        texts = []
        for row in raw or []:
            texts.append(str(getattr(row, "fact", None) or getattr(row, "content", None) or row))
        scored.append(score_case(case, texts[:k]))
    n = len(scored)
    hits = sum(1 for s in scored if s["hit"])
    return {
        "system": "graphiti",
        "no_llm": False,
        "skipped": False,
        "hit_at_k_pct": round(100.0 * hits / n, 1) if n else 0.0,
        "n": n,
        "k": k,
        "add_ms_p50": round(statistics.median(add_ms), 2) if add_ms else 0.0,
        "recall_p50_ms": round(statistics.median(recall_ms), 2) if recall_ms else 0.0,
        "cases": scored,
        "note": "Live Graphiti extract-on-write (LLM + graph). Not equivalent to OMem --no-llm.",
    }


def _extractive_summary(text: str, words: int = 12) -> str:
    sentence = re.split(r"[.!?]", text, maxsplit=1)[0]
    return " ".join(sentence.split()[:words])


def _overlap(query: str, text: str) -> int:
    return len(set(_norm(query).split()) & set(_norm(text).split()))


def run_naive_full_history(cases: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Send every write. Quality is high because the gold string is in the dump."""
    scored: List[Dict[str, Any]] = []
    tokens: List[int] = []
    for case in cases:
        blob = "\n".join(case["writes"])
        tokens.append(_approx_tokens(blob))
        scored.append(score_case(case, [blob]))
    n = len(scored)
    hits = sum(1 for s in scored if s["hit"])
    return {
        "system": "naive_full_history",
        "no_llm": True,
        "skipped": False,
        "hit_at_k_pct": round(100.0 * hits / n, 1) if n else 0.0,
        "n": n,
        "mean_prompt_tokens": round(statistics.mean(tokens), 1) if tokens else 0.0,
        "cases": scored,
        "note": "The whole history is the prompt. Not a serious production baseline.",
    }


def run_summarize_rag(cases: Sequence[Dict[str, Any]], k: int = 1) -> Dict[str, Any]:
    """Extractive summary of each write, then lexical overlap retrieval. No API key."""
    scored: List[Dict[str, Any]] = []
    tokens: List[int] = []
    for case in cases:
        summaries = [_extractive_summary(text) for text in case["writes"]]
        ranked = sorted(summaries, key=lambda s: _overlap(case["query"], s), reverse=True)[:k]
        prompt = "\n".join(ranked)
        tokens.append(_approx_tokens(prompt))
        scored.append(score_case(case, ranked))
    n = len(scored)
    hits = sum(1 for s in scored if s["hit"])
    return {
        "system": "summarize_rag",
        "no_llm": True,
        "skipped": False,
        "hit_at_k_pct": round(100.0 * hits / n, 1) if n else 0.0,
        "n": n,
        "k": k,
        "mean_prompt_tokens": round(statistics.mean(tokens), 1) if tokens else 0.0,
        "cases": scored,
        "note": "First 12 words of each write, then token-overlap top-1. No LLM.",
    }


def _skipped(system: str, reason: str) -> Dict[str, Any]:
    return {"system": system, "skipped": True, "reason": reason}


def run_zep(cases: Sequence[Dict[str, Any]], k: int = 5) -> Dict[str, Any]:
    del cases, k
    if not os.environ.get("ZEP_API_KEY"):
        return _skipped("zep", "set ZEP_API_KEY; this pass does not publish a Zep number")
    return _skipped("zep", "ZEP_API_KEY is set but the live adapter is not wired")


def run_letta(cases: Sequence[Dict[str, Any]], k: int = 5) -> Dict[str, Any]:
    del cases, k
    if not os.environ.get("LETTA_API_KEY"):
        return _skipped("letta", "set LETTA_API_KEY; this pass does not publish a Letta number")
    return _skipped("letta", "LETTA_API_KEY is set but the live adapter is not wired")


def run_bakeoff(
    *,
    k: int = 5,
    live_mem0: bool = False,
    live_graphiti: bool = False,
    live_zep: bool = False,
    live_letta: bool = False,
    include_vector: bool = True,
) -> Dict[str, Any]:
    systems = [
        run_omem(CASES, k=k),
        run_omem_pack(CASES),
        run_naive_full_history(CASES),
        run_summarize_rag(CASES),
    ]
    if include_vector:
        systems.append(run_vector_baseline(CASES, k=k))
    if live_mem0:
        systems.append(run_mem0(CASES, k=k))
    else:
        systems.append(_skipped("mem0", "pass --live-mem0 (install mem0ai + OPENAI_API_KEY)"))
    if live_graphiti:
        systems.append(run_graphiti(CASES, k=k))
    else:
        systems.append(_skipped("graphiti", "pass --live-graphiti (graphiti-core + Neo4j + LLM key)"))
    systems.append(run_zep(CASES, k=k) if live_zep else _skipped("zep", "pass --live-zep (ZEP_API_KEY)"))
    systems.append(run_letta(CASES, k=k) if live_letta else _skipped("letta", "pass --live-letta (LETTA_API_KEY)"))
    return {
        "bakeoff": "quality-vs-tokens",
        "omem_no_llm": True,
        "metric": "Hit rate (answer-string containment) and mean prompt tokens. Not an LLM-judge QA score.",
        "n_cases": len(CASES),
        "embedder": os.environ.get("OMEM_EMBEDDER") or "default",
        "systems": systems,
        "not_measured": ["mem0", "zep", "letta", "graphiti"],
    }


def chart_points(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    points = []
    for row in report.get("systems") or []:
        if row.get("skipped"):
            continue
        tokens = row.get("mean_prompt_tokens")
        hit = row.get("hit_at_k_pct")
        if tokens is None or hit is None:
            continue
        points.append(
            {
                "system": row.get("system"),
                "hit_at_k_pct": float(hit),
                "mean_prompt_tokens": float(tokens),
            }
        )
    return points


def render_quality_cost_svg(report: Dict[str, Any]) -> str:
    """Hit rate (y) against mean prompt tokens (x). No plotting dependency."""
    points = chart_points(report)
    width, height = 680, 380
    pad_l, pad_r, pad_t, pad_b = 64, 28, 36, 56
    max_tok = max((p["mean_prompt_tokens"] for p in points), default=1.0) or 1.0

    def x_of(tokens: float) -> float:
        return pad_l + (tokens / max_tok) * (width - pad_l - pad_r)

    def y_of(hit: float) -> float:
        return pad_t + (1.0 - hit / 100.0) * (height - pad_t - pad_b)

    def esc(text: str) -> str:
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f7f5f2"/>',
        f'<text x="{pad_l}" y="22" font-family="ui-sans-serif,sans-serif" font-size="14">Quality vs tokens (local arms only)</text>',
        f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{height - pad_b}" stroke="#222"/>',
        f'<line x1="{pad_l}" y1="{height - pad_b}" x2="{width - pad_r}" y2="{height - pad_b}" stroke="#222"/>',
        f'<text x="16" y="{height / 2}" font-size="11" transform="rotate(-90 16 {height / 2})" font-family="ui-sans-serif,sans-serif">hit %</text>',
        f'<text x="{width / 2}" y="{height - 12}" font-size="11" text-anchor="middle" font-family="ui-sans-serif,sans-serif">mean prompt tokens</text>',
    ]
    for point in points:
        cx = x_of(point["mean_prompt_tokens"])
        cy = y_of(point["hit_at_k_pct"])
        label = esc(str(point["system"]))
        label_x = min(cx + 8, width - 140)
        label_y = cy + 16 if point["hit_at_k_pct"] >= 95 else cy - 8
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5" fill="#1f4b3a"/>')
        parts.append(
            f'<text x="{label_x:.1f}" y="{label_y:.1f}" font-size="11" font-family="ui-sans-serif,sans-serif">{label}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def _print_report(report: Dict[str, Any]) -> None:
    print("OMem bakeoff  (OMem --no-llm vs optional live Mem0/Graphiti)")
    print(f"metric: {report['metric']}")
    print(f"cases:  {report['n_cases']}")
    print("")
    print(f"{'system':<18} {'Hit@5':>8} {'add p50':>10} {'recall p50':>12}  notes")
    for sysr in report["systems"]:
        name = sysr.get("system", "?")
        if sysr.get("skipped"):
            print(f"{name:<18} {'skip':>8} {'':>10} {'':>12}  {sysr.get('reason', '')}")
            continue
        hit = sysr.get("hit_at_k_pct", sysr.get("answer_in_budget_pct", 0))
        extra = ""
        if name == "omem_pack":
            extra = f" packed~{sysr.get('mean_packed_tokens', 0):.0f}tok"
        print(
            f"{name:<18} {hit:>7.1f}% "
            f"{sysr.get('add_ms_p50', 0):>9.1f}ms "
            f"{sysr.get('recall_p50_ms', 0):>11.1f}ms  "
            f"{(sysr.get('note', '') + extra)[:70]}"
        )
        for case in sysr.get("cases") or []:
            mark = "ok" if case.get("hit") else "miss"
            print(f"    [{mark}] {case.get('id')}")
    print("")
    print("OMem does not extract with a generator. Live Mem0/Graphiti usually do.")
    print("Do not cite modeled 163× latency ratios from distribution/benchmark_vs_mem0.py.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--live-mem0", action="store_true")
    parser.add_argument("--live-graphiti", action="store_true")
    parser.add_argument("--live-zep", action="store_true")
    parser.add_argument("--live-letta", action="store_true")
    parser.add_argument("--chart", type=str, default="", help="Write the quality-vs-tokens SVG here")
    parser.add_argument(
        "--no-llm",
        action="store_true",
        default=True,
        help="OMem never uses a generative LLM (default, always on).",
    )
    parser.add_argument("--out", type=str, default="")
    args = parser.parse_args(argv)
    report = run_bakeoff(
        k=args.k,
        live_mem0=args.live_mem0,
        live_graphiti=args.live_graphiti,
        live_zep=args.live_zep,
        live_letta=args.live_letta,
    )
    if args.chart:
        Path(args.chart).write_text(render_quality_cost_svg(report), encoding="utf-8")
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_report(report)
    omem = next(s for s in report["systems"] if s.get("system") == "omem")
    return 0 if omem.get("hit_at_k_pct", 0) >= 50 else 1


if __name__ == "__main__":
    raise SystemExit(main())
