"""
OMem Production Benchmark Suite
================================

Enterprise-grade performance testing for cloud deployment readiness.

Modules:
    latency     - p50/p95/p99 percentile profiling
    scalability - 1K -> 100K -> 500K memory scaling curves
    concurrency - thread-safety and parallel throughput
    memory      - RSS/heap profiling under load
    integrity   - data correctness under stress
    competitor  - head-to-head comparison framework
    report      - JSON/HTML report generation

Usage:
    python -m benchmarks.suite --all
    python -m benchmarks.suite --test latency --n 10000
    python -m benchmarks.suite --test concurrency --threads 16
    python -m benchmarks.suite --test scalability --max-n 500000
    python -m benchmarks.suite --report html
"""
