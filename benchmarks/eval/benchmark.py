"""OMem evaluation harness — cognitive vs vanilla RAG.

Compares OMem (cognitive) vs vector-only RAG for consistency, hallucination,
and accuracy across multi-session contexts.

Run::

    python -m benchmarks.eval.benchmark
    python benchmarks/eval/benchmark.py
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from omem.api import OMem

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_SCENARIOS = Path(__file__).resolve().parent / "scenarios.json"


class VanillaRAGMock:
    """Baseline RAG: vector similarity only (no cognitive checks)."""

    def __init__(self) -> None:
        self.omem = OMem(backend="sqlite", db_path=":memory:")

    def add(self, content: str) -> str:
        return self.omem.add(content, force=True)

    def query(self, prompt: str) -> str:
        results = self.omem.recall(prompt, top_k=3)
        return " ".join(r.content for r in results)


class OMemEvaluator:
    """Full cognitive retrieval path."""

    def __init__(self) -> None:
        self.omem = OMem(backend="sqlite", db_path=":memory:")

    def add(self, content: str) -> str:
        return self.omem.add(content)

    def query(self, prompt: str) -> str:
        results = self.omem.recall(prompt, top_k=3)
        return " ".join(r.content for r in results)


def run_benchmark(scenarios_path: str | Path | None = None) -> dict:
    path = Path(scenarios_path) if scenarios_path else _SCENARIOS
    with path.open(encoding="utf-8") as f:
        scenarios = json.load(f)

    results = []

    for scenario in scenarios:
        logger.info("Running scenario: %s — %s", scenario["id"], scenario["description"])

        vanilla = VanillaRAGMock()
        omem = OMemEvaluator()

        for session in scenario["sessions"]:
            vanilla.add(session["input"])
            omem.add(session["input"])

        for q in scenario["queries"]:
            v_ans = vanilla.query(q["prompt"]).lower()
            o_ans = omem.query(q["prompt"]).lower()

            v_correct = q["expected"].lower() in v_ans and q["negative"].lower() not in v_ans
            o_correct = q["expected"].lower() in o_ans and q["negative"].lower() not in o_ans
            v_hallucinated = q["negative"].lower() in v_ans
            o_hallucinated = q["negative"].lower() in o_ans

            results.append(
                {
                    "scenario": scenario["id"],
                    "query": q["prompt"],
                    "vanilla": {
                        "correct": v_correct,
                        "hallucinated": v_hallucinated,
                        "output": v_ans,
                    },
                    "omem": {
                        "correct": o_correct,
                        "hallucinated": o_hallucinated,
                        "output": o_ans,
                    },
                }
            )

    v_acc = sum(1 for r in results if r["vanilla"]["correct"]) / len(results)
    o_acc = sum(1 for r in results if r["omem"]["correct"]) / len(results)
    v_hall = sum(1 for r in results if r["vanilla"]["hallucinated"]) / len(results)
    o_hall = sum(1 for r in results if r["omem"]["hallucinated"]) / len(results)

    summary = {
        "metrics": {
            "vanilla_accuracy": v_acc,
            "omem_accuracy": o_acc,
            "vanilla_hallucination_rate": v_hall,
            "omem_hallucination_rate": o_hall,
        },
        "details": results,
    }

    print("\n" + "=" * 40)
    print("OMem EVALUATION RESULTS")
    print("=" * 40)
    print(f"Vanilla RAG Accuracy:  {v_acc * 100:.1f}%")
    print(f"OMem Accuracy:         {o_acc * 100:.1f}%")
    print(f"Vanilla Hallucination: {v_hall * 100:.1f}%")
    print(f"OMem Hallucination:    {o_hall * 100:.1f}%")
    print("=" * 40)

    return summary


if __name__ == "__main__":
    run_benchmark()
