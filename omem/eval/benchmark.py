"""OMem v0.2.0 Evaluation Harness.

Compares OMem (Cognitive) vs. Vanilla RAG (Vector-only) for consistency,
hallucination, and accuracy across multi-session contexts.
"""

import json
import logging

from ..api import OMem

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VanillaRAGMock:
    """A baseline RAG implementation that only uses vector similarity."""

    def __init__(self):
        # We use OMem but manually bypass TMS and Reflection for the baseline
        self.omem = OMem(backend="sqlite", db_path=":memory:")

    def add(self, content: str):
        # Simple add without any cognitive checks
        return self.omem.add(content, force=True)

    def query(self, prompt: str) -> str:
        # Standard RAG retrieval (top-k vector search only)
        # We simulate the LLM by just returning the retrieved context for evaluation
        results = self.omem.recall(prompt, top_k=3)
        return " ".join([r.content for r in results])


class OMemEvaluator:
    """The OMem v0.2.0 upgrade with full cognitive capabilities."""

    def __init__(self):
        self.omem = OMem(backend="sqlite", db_path=":memory:")

    def add(self, content: str):
        return self.omem.add(content)

    def query(self, prompt: str) -> str:
        # Full cognitive retrieval
        results = self.omem.recall(prompt, top_k=3)
        return " ".join([r.content for r in results])


def run_benchmark(scenarios_path: str):
    with open(scenarios_path, "r") as f:
        scenarios = json.load(f)

    results = []

    for scenario in scenarios:
        logger.info(f"Running scenario: {scenario['id']} - {scenario['description']}")

        vanilla = VanillaRAGMock()
        omem = OMemEvaluator()

        # Load multi-session inputs
        for session in scenario["sessions"]:
            vanilla.add(session["input"])
            omem.add(session["input"])

        # Execute queries
        for q in scenario["queries"]:
            v_ans = vanilla.query(q["prompt"]).lower()
            o_ans = omem.query(q["prompt"]).lower()

            # Simple keyword-based scoring for evaluation
            v_correct = (
                q["expected"].lower() in v_ans and q["negative"].lower() not in v_ans
            )
            o_correct = (
                q["expected"].lower() in o_ans and q["negative"].lower() not in o_ans
            )

            # Hallucination check: Does it still contain the OLD (negative) fact?
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

    # Summary
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
    print("OMem v0.2.0 BENCHMARK RESULTS")
    print("=" * 40)
    print(f"Vanilla RAG Accuracy: {v_acc * 100:.1f}%")
    print(f"OMem Accuracy:        {o_acc * 100:.1f}%")
    print(f"Vanilla Hallucination: {v_hall * 100:.1f}%")
    print(f"OMem Hallucination:    {o_hall * 100:.1f}%")
    print("=" * 40)

    return summary


if __name__ == "__main__":
    run_benchmark("/Users/mohitbadi/Downloads/Projects/omem/omem/eval/scenarios.json")
