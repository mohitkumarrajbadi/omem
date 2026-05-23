"""Automatic reflection engine.

After a batch of memories is accumulated, the reflection engine
generates higher-order insights by summarizing clusters of related
memories into structured reflection memories.

Works without an LLM via template-based summarization.
When an LLM function is provided, produces much richer reflections.
"""

import logging
import re
import time
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


from ...types import Memory, MemoryStatus, MemoryType
from .compression import cluster_memories

logger = logging.getLogger(__name__)

# Pre-compiled tokenizer
_TOKENIZER = re.compile(r"\w+")

# Minimum memories needed to trigger reflection
_MIN_MEMORIES_FOR_REFLECTION = 2
_REFLECTION_CLUSTER_THRESHOLD = 0.65  # looser than compression


def _template_reflect(memories: List[Memory]) -> str:
    """Generate a reflection from memories using templates (no LLM needed)."""
    if not memories:
        return ""

    # Group by type
    by_type: Dict[str, List[str]] = {}
    for m in memories:
        by_type.setdefault(m.type.name, []).append(m.content)

    parts = []

    # Summarize each type group
    if "DECISION" in by_type:
        decisions = by_type["DECISION"]
        parts.append(f"Key decisions: {'; '.join(d[:80] for d in decisions[:3])}")

    if "EPISODIC" in by_type:
        events = by_type["EPISODIC"]
        parts.append(f"Recent events: {'; '.join(e[:80] for e in events[:3])}")

    if "SEMANTIC" in by_type:
        facts = by_type["SEMANTIC"]
        parts.append(f"Known facts: {'; '.join(f[:80] for f in facts[:3])}")

    if "CAUSAL" in by_type:
        causes = by_type["CAUSAL"]
        parts.append(f"Cause-effect patterns: {'; '.join(c[:80] for c in causes[:3])}")

    if "PROCEDURAL" in by_type:
        procs = by_type["PROCEDURAL"]
        parts.append(f"Known procedures: {'; '.join(p[:80] for p in procs[:3])}")

    if "REFLECTION" in by_type:
        prev = by_type["REFLECTION"]
        parts.append(f"Meta-insights: {'; '.join(r[:80] for r in prev[:3])}")

    if "WORKING" in by_type or "ACTIVE" in by_type:
        current = by_type.get("WORKING", []) + by_type.get("ACTIVE", [])
        parts.append(f"Current focus: {'; '.join(c[:80] for c in current[:3])}")

    if not parts:
        contents = [m.content[:80] for m in memories[:5]]
        parts.append(
            f"Summary of {len(memories)} related memories: {'; '.join(contents)}"
        )

    return ". ".join(parts)


_ABSTRACTION_PROMPT = """Analyze the following related memories and extract higher-level insights, patterns, or user preferences.
Do not just summarize the facts; identify the 'why' or the 'style' behind them.
Example: 'User likes blue' + 'User likes neon' -> 'User prefers vibrant, high-contrast aesthetics.'

Memories:
{memories}

Insight:"""


def reflect_on_memories(
    memories: List[Memory],
    embedder=None,
    summarizer: Optional[Callable[[List[str]], str]] = None,
    threshold: float = _REFLECTION_CLUSTER_THRESHOLD,
    include_reflections: bool = True,
    mode: str = "summary",  # "summary" or "abstraction"
) -> List[Memory]:
    """Generate reflection memories from a set of memories.

    Args:
        memories: Source memories to reflect on.
        embedder: Embedder instance for creating vectors.
        summarizer: Optional LLM function ``f(texts) -> summary``.
        threshold: Clustering threshold.
        include_reflections: If True, allows reflecting on existing reflections (hierarchical).
        mode: "summary" for basic grouping, "abstraction" for pattern extraction.

    Returns:
        List of new REFLECTION-type memories.
    """
    if include_reflections:
        active = [m for m in memories if m.active]
    else:
        active = [m for m in memories if m.active and m.type != MemoryType.REFLECTION]

    if len(active) < _MIN_MEMORIES_FOR_REFLECTION:
        return []

    # Cluster related memories
    clusters = cluster_memories(active, threshold)

    reflections: List[Memory] = []

    for cluster in clusters:
        if len(cluster) < _MIN_MEMORIES_FOR_REFLECTION:
            continue

        contents = [m.content for m in cluster]

        if summarizer:
            if mode == "abstraction":
                prompt = _ABSTRACTION_PROMPT.format(
                    memories="\n".join(f"- {c}" for c in contents)
                )
                reflection_text = summarizer([prompt])
            else:
                reflection_text = summarizer(contents)
        else:
            reflection_text = _template_reflect(cluster)

        if not reflection_text.strip():
            continue

        # Create embedding for reflection
        if embedder:
            vector = embedder.encode(reflection_text)
        else:
            # Average cluster vectors
            avg = np.mean([m.vector for m in cluster], axis=0).astype(np.float32)
            norm = np.linalg.norm(avg)
            vector = avg / norm if norm > 0 else avg

        ref_id = _fast_hash(reflection_text)
        tokens = set(_TOKENIZER.findall(reflection_text.lower()))
        tokens_list = sorted(tokens)
        token_hashes = np.array([_token_hash(t) for t in tokens_list], dtype=np.uint64)

        reflection = Memory(
            id=ref_id,
            type=MemoryType.REFLECTION,
            content=reflection_text,
            vector=vector,
            timestamp=time.time(),
            importance=0.85 if mode == "abstraction" else 0.8,
            namespace=cluster[0].namespace,
            source="reflection_abstraction" if mode == "abstraction" else "reflection",
            tokens=tokens,
            token_hashes=token_hashes,
            metadata={
                "source_count": len(cluster),
                "mode": mode,
                "hierarchical": any(m.type == MemoryType.REFLECTION for m in cluster),
            },
        )
        reflections.append(reflection)

    logger.info(
        "Reflection (%s): generated %d insights from %d memories",
        mode,
        len(reflections),
        len(active),
    )
    return reflections


def reflect_on_conflicts(
    memories: List[Memory],
    summarizer: Optional[Callable[[List[str]], str]] = None,
) -> List[Memory]:
    """Specifically reflect on memories marked as CONFLICTED to attempt resolution.

    This works best with an LLM summarizer.
    """
    conflicts = [m for m in memories if m.status == MemoryStatus.CONFLICTED]
    if not conflicts or not summarizer:
        return []

    # Group conflicts by logical hash
    by_hash: Dict[str, List[Memory]] = {}
    for m in conflicts:
        if m.logical_hash:
            by_hash.setdefault(m.logical_hash, []).append(m)

    resolutions = []
    for l_hash, cluster in by_hash.items():
        if len(cluster) < 2:
            continue

        # Ask LLM to resolve
        prompt = "The following memories are contradictory. Please provide a single, consistent summary or identify which is more likely to be true:\n"
        for m in cluster:
            prompt += f"- {m.content} (source: {m.source}, time: {m.timestamp})\n"

        # We reuse the summarizer function as the 'resolver'
        resolved_text = summarizer([prompt])

        # Create a special high-importance reflection
        res_mem = Memory(
            id=_fast_hash(resolved_text),
            type=MemoryType.REFLECTION,
            content=f"RESOLVED CONFLICT: {resolved_text}",
            vector=np.mean([m.vector for m in cluster], axis=0),
            importance=0.95,
            source="conflict_resolver",
            metadata={"resolved_ids": [m.id for m in cluster]},
        )
        resolutions.append(res_mem)

    return resolutions


def reflect_on_conversation(
    messages: List[str],
    embedder=None,
    summarizer: Optional[Callable[[List[str]], str]] = None,
) -> Optional[Memory]:
    """Reflect on a conversation (list of message strings) to produce a single insight.

    This is the key feature for production agents: after a conversation ends,
    call this to create a structured memory of what was discussed.
    """
    if not messages or len(messages) < 2:
        return None

    if summarizer:
        reflection_text = summarizer(messages)
    else:
        # Template-based: extract topics
        " ".join(messages)
        topics = set()
        for msg in messages:
            words = msg.lower().split()
            # Extract multi-word phrases (crude noun extraction)
            for i in range(len(words) - 1):
                if len(words[i]) > 3 and len(words[i + 1]) > 3:
                    topics.add(f"{words[i]} {words[i + 1]}")

        topic_list = list(topics)[:5]
        reflection_text = f"Conversation covered {len(messages)} messages about: {', '.join(topic_list) if topic_list else 'various topics'}"

    if embedder:
        vector = embedder.encode(reflection_text)
    else:
        vector = np.zeros(384, dtype=np.float32)

    ref_id = _fast_hash(reflection_text)
    tokens = set(_TOKENIZER.findall(reflection_text.lower()))
    tokens_list = sorted(tokens)
    token_hashes = np.array([_token_hash(t) for t in tokens_list], dtype=np.uint64)

    return Memory(
        id=ref_id,
        type=MemoryType.REFLECTION,
        content=reflection_text,
        vector=vector,
        timestamp=time.time(),
        importance=0.75,
        source="reflection",
        tokens=tokens,
        token_hashes=token_hashes,
        metadata={"message_count": len(messages)},
    )
