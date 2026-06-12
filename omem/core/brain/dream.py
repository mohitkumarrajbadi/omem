"""Background memory consolidation engine.

Clusters related memories and synthesizes them into summarized insights.
Reduces data noise and retrieval costs.
"""

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

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


from ...types import Memory, MemoryPriority, MemoryTier, MemoryType
from .compression import cluster_memories

try:
    import omem_rust
except ImportError:
    omem_rust = None


logger = logging.getLogger(__name__)

_TOKENIZER = re.compile(r"\w+")

# Minimum cluster size to trigger consolidation
_MIN_CLUSTER_SIZE = 3
# Clustering similarity threshold (looser = more consolidation)
_DREAM_CLUSTER_THRESHOLD = 0.60


@dataclass
class DreamResult:
    """Results from a consolidation cycle."""

    insight_created: int = 0
    source_archived: int = 0
    clusters_found: int = 0
    clusters_consolidated: int = 0
    insight_ids: List[str] = field(default_factory=list)
    elapsed_ms: float = 0.0

    def __repr__(self) -> str:
        return (
            f"DreamResult(insights={self.insight_created}, "
            f"archived={self.source_archived}, "
            f"clusters={self.clusters_consolidated}, "
            f"time={self.elapsed_ms:.0f}ms)"
        )


def _template_synthesize(memories: List[Memory]) -> str:
    """Synthesize a summary from a cluster using templates."""
    if not memories:
        return ""

    # Group by type for structured synthesis
    by_type: Dict[str, List[str]] = {}
    for m in memories:
        by_type.setdefault(m.type.name, []).append(m.content)

    # Count unique themes via word frequency
    word_freq: Dict[str, int] = {}
    for m in memories:
        for word in _TOKENIZER.findall(m.content.lower()):
            if len(word) > 3:
                word_freq[word] = word_freq.get(word, 0) + 1

    top_themes = sorted(word_freq.items(), key=lambda x: -x[1])[:5]
    theme_str = ", ".join(w for w, _ in top_themes)

    parts = []

    # Consolidated insight header
    parts.append(f"Consolidated insight from {len(memories)} related memories")
    if theme_str:
        parts.append(f"Core themes: {theme_str}")

    # Type-specific synthesis
    if "DECISION" in by_type:
        decisions = by_type["DECISION"]
        parts.append(
            f"Pattern of decisions: {'; '.join(d[:60] for d in decisions[:3])}"
        )

    if "CAUSAL" in by_type:
        causes = by_type["CAUSAL"]
        parts.append(f"Cause-effect patterns: {'; '.join(c[:60] for c in causes[:3])}")

    if "PROCEDURAL" in by_type:
        procs = by_type["PROCEDURAL"]
        parts.append(f"Common procedures: {'; '.join(p[:60] for p in procs[:3])}")

    if "EPISODIC" in by_type:
        events = by_type["EPISODIC"]
        parts.append(f"Recurring experiences: {'; '.join(e[:60] for e in events[:3])}")

    if "SEMANTIC" in by_type:
        facts = by_type["SEMANTIC"]
        parts.append(f"Key facts: {'; '.join(f[:60] for f in facts[:3])}")

    return ". ".join(parts)


def _llm_synthesize(
    memories: List[Memory],
    llm_fn: Callable[[str], str],
    conflicts: Optional[List[tuple]] = None,
) -> str:
    """Use an LLM to summarize a cluster of memories."""
    contents = "\n".join(f"- {m.content}" for m in memories)
    types = set(m.type.name for m in memories)

    conflict_clause = ""
    if conflicts:
        conflict_details = []
        for i, j in conflicts:
            conflict_details.append(
                f"'{memories[i].content}' VS '{memories[j].content}'"
            )
        conflict_clause = "\n\nConflicts detected:\n" + "\n".join(conflict_details)

    prompt = f"""Summarize these {len(memories)} related memories ({", ".join(types)}):

{contents}{conflict_clause}

Synthesize into ONE concise insight statement:"""

    try:
        result = llm_fn(prompt)
        return result.strip()
    except Exception as e:
        logger.warning("LLM synthesis failed: %s, falling back to template", e)
        return _template_synthesize(memories)


def dream_consolidate(
    memories: List[Memory],
    embedder=None,
    llm_fn: Optional[Callable[[str], str]] = None,
    threshold: float = _DREAM_CLUSTER_THRESHOLD,
    min_cluster_size: int = _MIN_CLUSTER_SIZE,
) -> tuple:
    """Consolidate clusters into summarized insights."""
    t0 = time.time()
    result = DreamResult()

    # Only consider active, non-CORE memories
    candidates = [
        m
        for m in memories
        if m.active
        and m.tier
        not in (
            MemoryTier.CORE,
            MemoryTier.INSIGHT,
            MemoryTier.ARCHIVE,
            MemoryTier.FORGOTTEN,
        )
        and m.type != MemoryType.INSIGHT
        and m.priority != MemoryPriority.CORE
    ]

    if len(candidates) < min_cluster_size:
        result.elapsed_ms = (time.time() - t0) * 1000
        return [], [], result

    # Cluster related memories
    clusters = cluster_memories(candidates, threshold)
    result.clusters_found = len(clusters)

    # Truth Maintenance: Detect conflicts in batches using Rust if available
    cluster_conflicts = []
    if omem_rust and clusters:
        cluster_contents = []
        cluster_indices = []

        # Flatten clusters for Rust processing
        for c in clusters:
            start_idx = len(cluster_contents)
            cluster_contents.extend([m.content for m in c])
            cluster_indices.append(list(range(start_idx, start_idx + len(c))))

        # Returns a list of lists of (idx_in_cluster, idx_in_cluster)
        conflicts_from_rust = omem_rust.cognition_detect_conflicts(
            cluster_indices, cluster_contents
        )
        cluster_conflicts = conflicts_from_rust
    else:
        cluster_conflicts = [[] for _ in clusters]

    insight_memories: List[Memory] = []
    source_ids: List[str] = []

    for i, cluster in enumerate(clusters):
        if len(cluster) < min_cluster_size:
            continue

        result.clusters_consolidated += 1
        conflicts = cluster_conflicts[i] if i < len(cluster_conflicts) else []

        # Synthesize insight
        if llm_fn:
            insight_text = _llm_synthesize(cluster, llm_fn, conflicts=conflicts)
        else:
            insight_text = _template_synthesize(cluster)

        if not insight_text.strip():
            continue

        # Create INSIGHT memory
        if embedder:
            vector = embedder.encode(insight_text)
        else:
            avg = np.mean([m.vector for m in cluster], axis=0).astype(np.float32)
            norm = np.linalg.norm(avg)
            vector = avg / norm if norm > 0 else avg

        insight_id = _fast_hash(f"insight_{insight_text}_{time.time()}")
        tokens = set(_TOKENIZER.findall(insight_text.lower()))
        tokens_list = sorted(tokens)
        token_hashes = np.array([_token_hash(t) for t in tokens_list], dtype=np.uint64)

        cluster_source_ids = [m.id for m in cluster]

        insight = Memory(
            id=insight_id,
            type=MemoryType.INSIGHT,
            content=insight_text,
            vector=vector,
            timestamp=time.time(),
            importance=0.90,
            namespace=cluster[0].namespace,
            source="consolidation",
            tokens=tokens,
            token_hashes=token_hashes,
            tier=MemoryTier.INSIGHT,
            priority=MemoryPriority.HIGH,
            metadata={
                "source_count": len(cluster),
                "cluster_types": list(set(m.type.name for m in cluster)),
                "abstract": True,
            },
            insight_sources=cluster_source_ids,
            consolidation_count=len(cluster),
            confidence_score=min(0.6 + len(cluster) * 0.05, 0.95),
            evidence_count=len(cluster),
            level="long_term",
        )
        insight_memories.append(insight)
        result.insight_ids.append(insight_id)

        # Mark source memories for archival
        source_ids.extend(cluster_source_ids)

    result.insight_created = len(insight_memories)
    result.source_archived = len(source_ids)
    result.elapsed_ms = (time.time() - t0) * 1000

    logger.info("Maintenance Cycle: %s", result)
    return insight_memories, source_ids, result
