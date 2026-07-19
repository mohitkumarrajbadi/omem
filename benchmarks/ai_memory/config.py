"""OMem AI Memory Benchmark Suite

Prefer the public suite for publishable numbers:

```bash
python -m benchmarks.public_memory_suite --subset 40 --k 5
```

This folder also has older stubs for MTEB / BEIR / LongBench / LAMA.
"""

AVAILABLE_BENCHMARKS = ["mteb", "beir", "longbench", "lama"]
DEFAULT_MODEL = "all-MiniLM-L6-v2"
DEFAULT_DATASETS = {
    "mteb": "msmarco-passage",
    "beir": "ms_marco",
    "longbench": "wiki_long_doc",
    "lama": "open_lama",
}
