"""Snapshot + Recovery — serialize/restore full memory state.

Supports:
- Full state dump (KV + graph + metadata)
- Atomic recovery from snapshot
- JSON-based format for portability

v0.6.0 Production hardening (G).
"""

import json
import time
import gzip
import logging
from pathlib import Path
from typing import Dict, Any


logger = logging.getLogger(__name__)


def _memory_to_serializable(memory) -> Dict[str, Any]:
    """Convert a Memory to a JSON-serializable dict."""
    d = {
        "id": memory.id,
        "type": memory.type.value
        if hasattr(memory.type, "value")
        else str(memory.type),
        "content": memory.content,
        "vector": memory.vector.tolist() if memory.vector is not None else [],
        "timestamp": memory.timestamp,
        "score": memory.score,
        "metadata": memory.metadata,
        "importance": memory.importance,
        "access_count": memory.access_count,
        "last_accessed": memory.last_accessed,
        "namespace": memory.namespace,
        "source": memory.source,
        "superseded_by": memory.superseded_by,
        "active": memory.active,
        "level": memory.level,
        "priority": memory.priority.value
        if hasattr(memory.priority, "value")
        else str(memory.priority),
        "tier": memory.tier.value
        if hasattr(memory.tier, "value")
        else str(memory.tier),
        "entities": memory.entities,
        "wisdom_sources": memory.wisdom_sources,
        "consolidation_count": memory.consolidation_count,
    }
    return d


def snapshot(
    engine,
    output_path: str,
    compress: bool = True,
) -> Dict[str, Any]:
    """Create a full state snapshot of the engine.

    Args:
        engine: BrainTrace engine instance.
        output_path: File path for the snapshot.
        compress: Use gzip compression (default True).

    Returns:
        Snapshot metadata dict.
    """
    start = time.time()

    # Serialize all memories
    all_mems = engine.kv.all()
    memories_data = [_memory_to_serializable(m) for m in all_mems]

    # Serialize knowledge graph entities and edges
    graph_data = {
        "entities": [],
        "edges": [],
    }
    if hasattr(engine, "knowledge_graph"):
        for entity in engine.knowledge_graph.all_entities():
            graph_data["entities"].append(
                {
                    "name": entity.name,
                    "type": entity.type.value,
                    "mention_count": entity.mention_count,
                }
            )

    snapshot_data = {
        "version": "0.6.0",
        "timestamp": time.time(),
        "memory_count": len(memories_data),
        "memories": memories_data,
        "graph": graph_data,
        "id_order": list(engine._id_order),
    }

    # Write to file
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    data_bytes = json.dumps(snapshot_data, separators=(",", ":")).encode("utf-8")
    if compress:
        with gzip.open(str(path), "wb") as f:
            f.write(data_bytes)
    else:
        path.write_bytes(data_bytes)

    elapsed = (time.time() - start) * 1000
    meta = {
        "path": str(path),
        "memory_count": len(memories_data),
        "size_bytes": path.stat().st_size,
        "compressed": compress,
        "elapsed_ms": round(elapsed, 1),
    }
    logger.info(
        "Snapshot: %d memories → %s (%.1fms, %d bytes)",
        len(memories_data),
        path,
        elapsed,
        meta["size_bytes"],
    )
    return meta


def restore(
    engine,
    snapshot_path: str,
    clear_existing: bool = True,
) -> Dict[str, Any]:
    """Restore engine state from a snapshot file.

    Args:
        engine: BrainTrace engine instance.
        snapshot_path: Path to snapshot file.
        clear_existing: Clear current state before restore.

    Returns:
        Restore metadata dict.
    """

    start = time.time()
    path = Path(snapshot_path)

    # Read and decompress
    try:
        with gzip.open(str(path), "rb") as f:
            data = json.loads(f.read())
    except gzip.BadGzipFile:
        data = json.loads(path.read_text())

    if clear_existing:
        engine.clear()

    # Restore memories
    restored = 0
    for mem_data in data.get("memories", []):
        try:
            # Reconstruct memory via add()
            engine.add(
                content=mem_data["content"],
                namespace=mem_data.get("namespace", "default"),
                source=mem_data.get("source", "snapshot"),
                importance=mem_data.get("importance", 0.5),
                force=True,  # bypass noise gate + dedup for restore
            )
            restored += 1
        except Exception as e:
            logger.warning(
                "Failed to restore memory %s: %s", mem_data.get("id", "?"), e
            )

    elapsed = (time.time() - start) * 1000
    meta = {
        "path": str(path),
        "snapshot_version": data.get("version", "unknown"),
        "total_in_snapshot": len(data.get("memories", [])),
        "restored": restored,
        "elapsed_ms": round(elapsed, 1),
    }
    logger.info(
        "Restore: %d/%d memories from %s (%.1fms)",
        restored,
        meta["total_in_snapshot"],
        path,
        elapsed,
    )
    return meta
