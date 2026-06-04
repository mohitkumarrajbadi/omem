"""Configuration and dataset defaults for AI memory benchmarks."""

AVAILABLE_BENCHMARKS = ["mteb", "beir", "longbench", "lama"]
DEFAULT_MODEL = "all-MiniLM-L6-v2"
DEFAULT_DATASETS = {
    "mteb": "msmarco-passage",
    "beir": "ms_marco",
    "longbench": "wiki_long_doc",
    "lama": "open_lama",
}
