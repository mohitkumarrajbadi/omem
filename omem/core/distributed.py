"""
Distributed OMem Architecture — Scaling Beyond Single-Node.

This module documents and implements the sharding/replication strategy
for scaling OMem to 10M+ memories across multiple nodes.

Architecture tiers:
  Tier 1: Local (current)    — FAISS + SQLite, 1 node, up to ~1M memories
  Tier 2: Server             — FAISS + PostgreSQL, 1 beefy node, up to ~5M
  Tier 3: Distributed        — Sharded FAISS + PG, N nodes, 10M–100M+

This file implements the ShardManager abstraction that routes memories
to shards by namespace hash, distributing the FAISS index across workers.
"""

import hashlib
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ShardConfig:
    """Configuration for a distributed OMem deployment."""

    num_shards: int = 4
    replication_factor: int = 2
    shard_strategy: str = "namespace_hash"  # or "round_robin", "range"
    max_memories_per_shard: int = 2_500_000
    enable_query_routing: bool = True


class ShardRouter:
    """Routes memories and queries to the correct shard.

    Sharding strategies:
    - namespace_hash: Hash the namespace to determine shard (default)
    - round_robin: Distribute evenly across shards
    - range: Assign memory ID ranges to shards

    This is the foundation for distributed OMem. In production,
    each shard runs on a separate node with its own FAISS index.
    """

    def __init__(self, config: Optional[ShardConfig] = None):
        self.config = config or ShardConfig()
        self._shard_counts: Dict[int, int] = {
            i: 0 for i in range(self.config.num_shards)
        }
        self._rr_counter = 0

    def route_write(self, memory_id: str, namespace: str = "default") -> int:
        """Determine which shard a memory should be written to."""
        if self.config.shard_strategy == "namespace_hash":
            return self._hash_route(namespace)
        elif self.config.shard_strategy == "round_robin":
            shard = self._rr_counter % self.config.num_shards
            self._rr_counter += 1
            return shard
        elif self.config.shard_strategy == "range":
            return self._range_route(memory_id)
        else:
            return self._hash_route(namespace)

    def route_query(self, query: str, namespace: Optional[str] = None) -> List[int]:
        """Determine which shards to query.

        If namespace is given, route to the specific shard.
        If namespace is None, query all shards (scatter-gather).
        """
        if namespace and self.config.enable_query_routing:
            return [self._hash_route(namespace)]
        return list(range(self.config.num_shards))

    def replicas_for_shard(self, shard_id: int) -> List[int]:
        """Return replica IDs for a given shard (for read scaling)."""
        replicas = []
        for i in range(self.config.replication_factor):
            replica = (shard_id + i + 1) % self.config.num_shards
            if replica != shard_id:
                replicas.append(replica)
        return replicas[: self.config.replication_factor - 1]

    def _hash_route(self, key: str) -> int:
        h = int(hashlib.md5(key.encode()).hexdigest(), 16)
        return h % self.config.num_shards

    def _range_route(self, memory_id: str) -> int:
        h = int(hashlib.md5(memory_id.encode()).hexdigest()[:8], 16)
        return h % self.config.num_shards

    def stats(self) -> Dict[str, Any]:
        return {
            "num_shards": self.config.num_shards,
            "replication_factor": self.config.replication_factor,
            "strategy": self.config.shard_strategy,
            "max_per_shard": self.config.max_memories_per_shard,
        }


# ── Capacity Planning ──


def estimate_resources(
    total_memories: int,
    dim: int = 384,
    num_shards: int = 4,
) -> Dict[str, Any]:
    """Estimate resource requirements for a distributed deployment."""
    per_shard = total_memories // num_shards

    # FAISS IndexFlatIP: 4 bytes per float * dim dimensions
    faiss_per_shard_mb = (per_shard * dim * 4) / (1024 * 1024)
    faiss_total_mb = faiss_per_shard_mb * num_shards

    # SQLite/PG overhead: ~500 bytes per memory (content + metadata)
    db_per_shard_mb = (per_shard * 500) / (1024 * 1024)

    # RAM estimate: FAISS + overhead
    ram_per_shard_mb = faiss_per_shard_mb * 1.3 + db_per_shard_mb

    # Latency estimates based on benchmark data (FAISS IndexFlatIP, O(n) scan)
    # Empirical: ~0.03ms per 1K vectors at dim=384
    estimated_p50_ms = per_shard * 0.03 / 1000

    # Instance recommendations
    if ram_per_shard_mb < 2048:
        instance = "t3.small (2GB)"
    elif ram_per_shard_mb < 8192:
        instance = "t3.large (8GB)"
    elif ram_per_shard_mb < 16384:
        instance = "r6g.large (16GB)"
    elif ram_per_shard_mb < 32768:
        instance = "r6g.xlarge (32GB)"
    else:
        instance = "r6g.2xlarge (64GB) or GPU instance"

    return {
        "total_memories": total_memories,
        "num_shards": num_shards,
        "per_shard_memories": per_shard,
        "faiss_per_shard_mb": round(faiss_per_shard_mb, 1),
        "faiss_total_mb": round(faiss_total_mb, 1),
        "db_per_shard_mb": round(db_per_shard_mb, 1),
        "ram_per_shard_mb": round(ram_per_shard_mb, 1),
        "estimated_p50_ms": round(estimated_p50_ms, 2),
        "recommended_instance": instance,
        "architecture_notes": _arch_notes(total_memories, num_shards),
    }


def _arch_notes(total: int, shards: int) -> str:
    if total <= 1_000_000:
        return "Single-node FAISS + SQLite sufficient. No sharding needed."
    elif total <= 5_000_000:
        return "Single beefy node (32GB+) or 2-4 shards with PG backend."
    elif total <= 50_000_000:
        return f"{shards} shards recommended. Use PG + FAISS IVF index for sub-linear search."
    else:
        return f"{shards}+ shards with FAISS IVF or GPU. Consider Milvus/Qdrant for managed infrastructure."


def print_capacity_plan():
    """Print capacity planning table for common deployment sizes."""
    print("=" * 90)
    print("  OMem Distributed Capacity Planning")
    print("=" * 90)
    print(
        f"  {'Memories':>12} │ {'Shards':>6} │ {'Per Shard':>12} │ {'FAISS/Shard':>11} │ {'RAM/Shard':>10} │ {'Est p50':>8} │ Instance"
    )
    print("─" * 90)

    plans = [
        (100_000, 1),
        (500_000, 1),
        (1_000_000, 1),
        (1_000_000, 4),
        (5_000_000, 4),
        (10_000_000, 8),
        (50_000_000, 16),
        (100_000_000, 32),
    ]

    for total, shards in plans:
        r = estimate_resources(total, num_shards=shards)
        print(
            f"  {r['total_memories']:>12,} │ {r['num_shards']:>6} │ {r['per_shard_memories']:>12,} │"
            f" {r['faiss_per_shard_mb']:>9.1f}MB │ {r['ram_per_shard_mb']:>8.1f}MB │"
            f" {r['estimated_p50_ms']:>6.2f}ms │ {r['recommended_instance']}"
        )

    print("─" * 90)
    print("\n  Architecture notes:")
    for total, shards in [(1_000_000, 1), (10_000_000, 8), (100_000_000, 32)]:
        r = estimate_resources(total, num_shards=shards)
        print(f"    {total:>12,}: {r['architecture_notes']}")
    print()


if __name__ == "__main__":
    print_capacity_plan()
