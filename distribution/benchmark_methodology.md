# Benchmark methodology notes

## Appendix: modeled comparison vs. other systems
**(not an apples-to-apples benchmark — see caveat)**

Tested on Apple M-series · 5,000 memories · 500 queries · `all-MiniLM-L6-v2` ·
reproduce with `python distribution/benchmark_vs_mem0.py`

**Methodology:** OMem uses a fully local heuristic classification and
embedding/scoring path. The default script compares that measured local path
with a modeled Mem0 baseline representing an LLM-based extraction/scoring
configuration; use `--live-mem0` for a live Mem0 run. These are different
operation pipelines, so the latency ratios describe the tested configurations,
not equivalent underlying operations.

| System | Cold Start | Add | RAG p50 | RAG p99 | Est. third-party API fees / 1M recalls |
|---|---:|---:|---:|---:|---:|
| **OMem** | **4 ms** | **65 ops/s** | **1.8 ms** | **3.9 ms** | **$0** |
| Mem0 | 15,000 ms | <1 ops/s | 420 ms | 638 ms | ~$20 |
| ChromaDB | 507 ms | 277 ops/s | — | 4 ms | $0 |
| LanceDB | 8 ms | 82,000 ops/s | — | 7 ms | $0 |

**In this configuration, OMem measured 3.9 ms p99 local recall versus the
modeled Mem0 baseline of 638 ms (a 163× latency ratio), with $0 third-party API
fees. Local infrastructure costs are not included.**

OMem's `add()` does more than raw storage: embed, classify, deduplicate, sync
the knowledge graph, and persist asynchronously. The benchmark reflects each
system's configured workflow, not a raw vector-insert comparison.

For measured public-suite numbers (STATE-Bench, LongMemEval, LoCoMo,
BEAM-style), see the README Benchmarks section and
[`public_benchmark_results.json`](./public_benchmark_results.json).
