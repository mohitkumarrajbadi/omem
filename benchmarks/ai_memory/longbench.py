"""LongBench / SCROLLS-style long-span memory benchmark runner."""

from typing import Any, Dict

from omem import OMem


def run_longbench(dataset: str = "wiki_long_doc", model_name: str = "all-MiniLM-L6-v2", n_queries: int = 100) -> Dict[str, Any]:
    try:
        import longbench  # noqa: F401
    except ImportError as exc:
        return {
            "benchmark": "longbench",
            "dataset": dataset,
            "status": "missing_dependency",
            "note": "Install `longbench` or the equivalent long-range evaluation package to run this benchmark.",
            "error": str(exc),
        }

    engine = OMem(backend="memory", model=model_name)

    return {
        "benchmark": "longbench",
        "dataset": dataset,
        "status": "ready",
        "note": "Benchmark runner initialized. Implement long-span document ingestion and query evaluation.",
        "model": model_name,
        "n_queries": n_queries,
    }
