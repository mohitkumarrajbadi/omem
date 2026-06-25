"""AI Memory benchmark suite for OMem.

This package hosts schema and runner helpers for the core AI memory
benchmarks: MTEB, BEIR, LongBench/SCROLLS, and LAMA/LAMA-UHN.
"""

from .beir import run_beir
from .config import AVAILABLE_BENCHMARKS, DEFAULT_DATASETS, DEFAULT_MODEL
from .lama import run_lama
from .longbench import run_longbench
from .mteb import run_mteb
from .runner import run_ai_memory_benchmarks

__all__ = [
    "AVAILABLE_BENCHMARKS",
    "DEFAULT_DATASETS",
    "DEFAULT_MODEL",
    "run_mteb",
    "run_beir",
    "run_longbench",
    "run_lama",
    "run_ai_memory_benchmarks",
]
