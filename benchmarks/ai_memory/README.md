# OMem AI Memory Benchmark Suite

This folder provides a structured benchmark package for evaluating OMem against:

- `MTEB` — embedding and retrieval evaluation
- `BEIR` — robustness across domains
- `LongBench` / `SCROLLS` — long-span retrieval and reasoning
- `LAMA` / `LAMA-UHN` — factual memory retention and recall

## Structure

- `config.py` — default benchmark names, dataset references, and model defaults
- `mteb.py` — MTEB-style benchmark runner
- `beir.py` — BEIR-style benchmark runner
- `longbench.py` — long-range benchmark runner
- `lama.py` — factual memory retention runner
- `runner.py` — unified CLI and suite entrypoint

## Usage

Install optional benchmark dependencies first:

```bash
pip install mteb beir datasets transformers sentence-transformers
```

Then run the suite:

```bash
python -m benchmarks.ai_memory.runner --benchmark mteb beir longbench lama --queries 100
```

## Notes

These modules are intentionally structured as a proper benchmark folder with a shared runner. Each benchmark stub is ready for dataset ingestion and evaluation logic to be implemented in the corresponding file.
