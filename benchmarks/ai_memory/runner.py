"""Entrypoint for the OMem AI memory benchmark suite."""

import argparse
from typing import Any, Dict, List, Optional

from .beir import run_beir
from .config import AVAILABLE_BENCHMARKS, DEFAULT_DATASETS, DEFAULT_MODEL
from .lama import run_lama
from .longbench import run_longbench
from .mteb import run_mteb


def _run_for_benchmark(name: str, dataset: Optional[str], model_name: str, n_queries: int) -> Dict[str, Any]:
    if name == "mteb":
        return run_mteb(dataset or DEFAULT_DATASETS["mteb"], model_name=model_name, n_queries=n_queries)
    if name == "beir":
        return run_beir(dataset or DEFAULT_DATASETS["beir"], model_name=model_name, n_queries=n_queries)
    if name == "longbench":
        return run_longbench(dataset or DEFAULT_DATASETS["longbench"], model_name=model_name, n_queries=n_queries)
    if name == "lama":
        return run_lama(dataset or DEFAULT_DATASETS["lama"], model_name=model_name, n_queries=n_queries)
    raise ValueError(f"Unknown benchmark: {name}")


def run_ai_memory_benchmarks(
    benchmarks: Optional[List[str]] = None,
    model_name: str = DEFAULT_MODEL,
    n_queries: int = 100,
    verbose: bool = True,
) -> Dict[str, Any]:
    if benchmarks is None:
        benchmarks = AVAILABLE_BENCHMARKS

    results = {}
    for name in benchmarks:
        if name not in AVAILABLE_BENCHMARKS:
            raise ValueError(f"Unsupported benchmark: {name}")
        if verbose:
            print(f"\n=== Running AI Memory benchmark: {name} ===")
        results[name] = _run_for_benchmark(name, None, model_name, n_queries)

    return {
        "benchmarks": benchmarks,
        "model": model_name,
        "n_queries": n_queries,
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="OMem AI Memory Benchmark Runner")
    parser.add_argument(
        "--benchmark",
        type=str,
        nargs="+",
        choices=AVAILABLE_BENCHMARKS,
        help="Select benchmark(s) to run.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help="Embedding model name to use for OMem.",
    )
    parser.add_argument(
        "--queries",
        type=int,
        default=100,
        help="Number of sample queries to execute.",
    )
    args = parser.parse_args()

    result = run_ai_memory_benchmarks(
        benchmarks=args.benchmark,
        model_name=args.model,
        n_queries=args.queries,
        verbose=True,
    )

    print("\nAI memory benchmark summary:")
    for name, bench in result["results"].items():
        print(f"- {name}: {bench.get('status', 'unknown')} ({bench.get('note', 'no note')})")


if __name__ == "__main__":
    main()
