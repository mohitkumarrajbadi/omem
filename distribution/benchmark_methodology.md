# Benchmark methodology notes

## Local quality versus tokens

The comparison that runs without API keys is
[`benchmarks/bakeoff.py`](../benchmarks/bakeoff.py). It scores answer-string
containment and mean prompt tokens on one small fixture.

Always-on arms:

- OMem recall
- OMem pack (answer inside a token budget)
- naive full history (every write is the prompt)
- summarize-plus-RAG (first 12 words of each write, then lexical overlap)

Mem0, Zep, Letta, and Graphiti are optional. If the flag or the key is missing,
the row is `skipped` and has no hit rate and no latency. This file does not
publish a modeled Mem0 latency, a 163× ratio, or a third-party fee estimate.
Those older figures were a model of a different pipeline, not a measurement,
and they are withdrawn.

Chart: [`quality_cost.svg`](./quality_cost.svg).
Numbers: [`bakeoff_results.json`](./bakeoff_results.json).

The fixture is four short cases. Full history is only a few dozen tokens, so this chart will not show a 95% reduction. That reduction, against a large naive dump, is the separate KV probe, and it is not a competitor bakeoff. On this fixture summarize-plus-RAG uses fewer tokens and misses a case. Read both axes.

```bash
python -m benchmarks.bakeoff --json --out distribution/bakeoff_results.json --chart distribution/quality_cost.svg
```

## Public retrieval suites

STATE-Bench, LongMemEval, LoCoMo, and the synthetic BEAM-style check are in
[`public_benchmark_results.json`](./public_benchmark_results.json). The README
quotes that file. Retrieval hit is not an LLM-judge QA score. The BEAM-style
suite is not the official BEAM leaderboard.

KV-cache economics, including the history-rewrite loss, are in
[`kv_cache_results.json`](./kv_cache_results.json). `prompt_eval_count` is null.
That file is a prefix-stability proxy, not a provider cache bill.
