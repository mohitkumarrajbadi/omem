"""Memory Quotas + Backpressure — prevents unbounded memory growth.

When memory count exceeds limits, triggers automatic forget/compress.

v0.5.0 Production hardening (E).
"""

import logging
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class MemoryQuota:
    """Memory system limits."""

    max_active: int = 50_000  # Max ACTIVE-tier memories
    max_per_namespace: int = 10_000  # Max memories per namespace
    max_total: int = 100_000  # Max total (including ARCHIVE)
    warning_ratio: float = 0.80  # Warn at 80% of limit


@dataclass
class QuotaStatus:
    """Quota check result."""

    within_limits: bool = True
    active_count: int = 0
    total_count: int = 0
    active_pct: float = 0.0
    namespace_counts: Dict[str, int] = None  # type: ignore
    exceeded: str = ""  # Which limit was exceeded
    action: str = ""  # Recommended action

    def __post_init__(self):
        if self.namespace_counts is None:
            self.namespace_counts = {}


def check_quota(
    all_memories: list,
    quota: Optional[MemoryQuota] = None,
    namespace: str = "default",
) -> QuotaStatus:
    """Check if current memory count is within quota.

    Args:
        all_memories: List of all Memory objects.
        quota: MemoryQuota limits (uses defaults if None).
        namespace: Namespace to check per-namespace quota.

    Returns:
        QuotaStatus with limits info and recommended action.
    """
    quota = quota or MemoryQuota()
    status = QuotaStatus()

    # Count by tier and namespace
    active_count = 0
    ns_counts: Dict[str, int] = {}
    total = len(all_memories)

    for mem in all_memories:
        if mem.active:
            active_count += 1
        ns = getattr(mem, "namespace", "default")
        ns_counts[ns] = ns_counts.get(ns, 0) + 1

    status.active_count = active_count
    status.total_count = total
    status.active_pct = active_count / max(quota.max_active, 1)
    status.namespace_counts = ns_counts

    # Check limits
    if total >= quota.max_total:
        status.within_limits = False
        status.exceeded = "max_total"
        status.action = "compress"
        logger.warning("QUOTA: total %d >= max %d → compress", total, quota.max_total)
        return status

    if active_count >= quota.max_active:
        status.within_limits = False
        status.exceeded = "max_active"
        status.action = "forget"
        logger.warning(
            "QUOTA: active %d >= max %d → forget", active_count, quota.max_active
        )
        return status

    ns_count = ns_counts.get(namespace, 0)
    if ns_count >= quota.max_per_namespace:
        status.within_limits = False
        status.exceeded = "max_per_namespace"
        status.action = "forget"
        logger.warning(
            "QUOTA: ns '%s' has %d >= max %d → forget",
            namespace,
            ns_count,
            quota.max_per_namespace,
        )
        return status

    # Warning level
    if status.active_pct >= quota.warning_ratio:
        logger.info("QUOTA warning: active at %.0f%% of limit", status.active_pct * 100)

    return status
