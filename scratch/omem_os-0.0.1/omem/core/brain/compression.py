"""Memory compression engine.

Reduces storage by clustering similar memories and merging them into summaries.
Supports optional LLM-based summarization.
"""

import logging
import re
from typing import List, Optional, Callable, Tuple

import numpy as np

try:
    import xxhash

    def _fast_hash(data: str) -> str:
        return xxhash.xxh64_hexdigest(data.encode("utf-8"))[:12]

    def _token_hash(t: str) -> int:
        return xxhash.xxh64_intdigest(t.encode("utf-8"))
except ImportError:
    import hashlib

    def _fast_hash(data: str) -> str:
        return hashlib.md5(data.encode("utf-8")).hexdigest()[:12]

    def _token_hash(t: str) -> int:
        return int(hashlib.md5(t.encode("utf-8")).hexdigest(), 16) & 0xFFFFFFFFFFFFFFFF


try:
    import omem_rust
except ImportError:
    omem_rust = None


from ...types import Memory, MemoryType
from .updater import merge_memories

logger = logging.getLogger(__name__)

# Pre-compiled tokenizer
_TOKENIZER = re.compile(r"\w+")

# Default cosine similarity threshold for grouping
_CLUSTER_THRESHOLD = 0.75


def cluster_memories(
    memories: List[Memory],
    threshold: float = _CLUSTER_THRESHOLD,
) -> List[List[Memory]]:
    """Group memories into clusters by cosine similarity."""
    if not memories:
        return []

    active = [m for m in memories if m.active]
    if len(active) < 2:
        return []

    if omem_rust and hasattr(omem_rust, "cognition_cluster_batch"):
        # Use Rust-accelerated parallel clustering
        V = np.array([m.vector for m in active], dtype=np.float32)
        # Assuming vectors are already normalized (standard for OMem)
        indices_list = omem_rust.cognition_cluster_batch(V, float(threshold))

        clusters = []
        for indices in indices_list:
            clusters.append([active[i] for i in indices])
        return clusters

    # Fallback to NumPy-accelerated Python loop
    V = np.array([m.vector for m in active], dtype=np.float32)
    sim_matrix = V @ V.T

    n = len(active)
    used = [False] * n
    clusters: List[List[Memory]] = []

    for i in range(n):
        if used[i]:
            continue
        cluster = [active[i]]
        used[i] = True
        for j in range(i + 1, n):
            if not used[j] and sim_matrix[i, j] >= threshold:
                cluster.append(active[j])
                used[j] = True
        if len(cluster) >= 2:
            clusters.append(cluster)

    return clusters


def compress_cluster(
    cluster: List[Memory],
    summarizer: Optional[Callable[[List[str]], str]] = None,
) -> Memory:
    """Compress a cluster of similar memories into one.

    Args:
        cluster: Memories to compress.
        summarizer: Optional LLM function ``f(texts) -> summary``.
                    If None, uses sentence-dedup merge.
    """
    if len(cluster) == 1:
        return cluster[0]

    contents = [m.content for m in cluster]

    if summarizer:
        compressed_text = summarizer(contents)
    else:
        compressed_text = merge_memories(cluster)

    # Average the vectors
    avg_vector = np.mean([m.vector for m in cluster], axis=0).astype(np.float32)
    norm = np.linalg.norm(avg_vector)
    if norm > 0:
        avg_vector = avg_vector / norm

    # Take max importance, latest timestamp
    max_importance = max(m.importance for m in cluster)
    latest_ts = max(m.timestamp for m in cluster)
    total_access = sum(m.access_count for m in cluster)
    namespace = cluster[0].namespace

    new_id = _fast_hash(compressed_text)

    tokens = set(_TOKENIZER.findall(compressed_text.lower()))
    tokens_list = sorted(tokens)
    token_hashes = np.array([_token_hash(t) for t in tokens_list], dtype=np.uint64)

    return Memory(
        id=new_id,
        type=MemoryType.SEMANTIC,
        content=compressed_text,
        vector=avg_vector,
        timestamp=latest_ts,
        importance=min(max_importance + 0.1, 1.0),  # compression boosts importance
        access_count=total_access,
        namespace=namespace,
        source="compression",
        tokens=tokens,
        token_hashes=token_hashes,
        metadata={
            "compressed_from": [m.id for m in cluster],
            "original_count": len(cluster),
        },
    )


def run_compression(
    memories: List[Memory],
    threshold: float = _CLUSTER_THRESHOLD,
    min_cluster_size: int = 2,
    summarizer: Optional[Callable[[List[str]], str]] = None,
) -> Tuple[List[Memory], List[str]]:
    """Run full compression pipeline.

    Returns:
        - List of new compressed memories
        - List of IDs that were deactivated (originals in clusters)
    """
    active = [m for m in memories if m.active]
    clusters = cluster_memories(active, threshold)

    # Filter to clusters meeting min size
    clusters = [c for c in clusters if len(c) >= min_cluster_size]

    compressed: List[Memory] = []
    deactivated_ids: List[str] = []

    for cluster in clusters:
        new_mem = compress_cluster(cluster, summarizer)
        compressed.append(new_mem)

        # Mark originals as superseded
        for mem in cluster:
            mem.active = False
            mem.superseded_by = new_mem.id
            deactivated_ids.append(mem.id)

    logger.info(
        "Compressed %d clusters into %d new memories (%d deactivated)",
        len(clusters),
        len(compressed),
        len(deactivated_ids),
    )

    return compressed, deactivated_ids
