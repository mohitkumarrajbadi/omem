"""Memory Corruption Guard — validates memory integrity before storage.

Catches silent failures: bad embeddings, empty types, NaN scores,
invalid tiers, corrupted vectors.

v0.6.0 Production hardening (E).
"""

import logging
from typing import Tuple

import numpy as np

from ...types import Memory, MemoryPriority, MemoryTier, MemoryType

logger = logging.getLogger(__name__)


def validate_memory(memory: Memory) -> Tuple[bool, str]:
    """Validate memory integrity. Returns (valid, reason).

    Checks:
    1. Vector must be L2-normalized (norm ≈ 1.0)
    2. Vector must not contain NaN/Inf
    3. Content must be non-empty
    4. ID must be non-empty
    5. Importance must be in [0, 1]
    6. Type must be valid enum
    7. Tier must be valid enum
    """
    # 1. ID check
    if not memory.id:
        return False, "empty_id"

    # 2. Content check
    if not memory.content or not memory.content.strip():
        return False, "empty_content"

    # 3. Vector checks
    if memory.vector is None or len(memory.vector) == 0:
        return False, "empty_vector"

    if np.any(np.isnan(memory.vector)):
        return False, "nan_in_vector"

    if np.any(np.isinf(memory.vector)):
        return False, "inf_in_vector"

    norm = float(np.linalg.norm(memory.vector))
    if abs(norm - 1.0) > 0.01:
        return False, f"vector_not_normalized: norm={norm:.4f}"

    # 4. Importance range
    if not (0.0 <= memory.importance <= 1.0):
        return False, f"importance_out_of_range: {memory.importance}"

    # 5. Type check
    if not isinstance(memory.type, MemoryType):
        return False, f"invalid_type: {memory.type}"

    # 6. Tier check
    if not isinstance(memory.tier, MemoryTier):
        return False, f"invalid_tier: {memory.tier}"

    # 7. Priority check
    if not isinstance(memory.priority, MemoryPriority):
        return False, f"invalid_priority: {memory.priority}"

    return True, "ok"


def sanitize_memory(memory: Memory) -> Memory:
    """Auto-fix common corruption issues in-place.

    Fixes:
    - Re-normalizes vector if drift detected
    - Clamps importance to [0, 1]
    - Ensures access_count >= 0
    """
    # Re-normalize vector
    if memory.vector is not None and len(memory.vector) > 0:
        norm = float(np.linalg.norm(memory.vector))
        if norm > 0 and abs(norm - 1.0) > 0.001:
            memory.vector = memory.vector / norm
            logger.debug("Sanitized vector norm for %s: %.4f → 1.0", memory.id, norm)

    # Clamp importance
    if memory.importance < 0.0:
        memory.importance = 0.0
    elif memory.importance > 1.0:
        memory.importance = 1.0

    # Fix negative access count
    if memory.access_count < 0:
        memory.access_count = 0

    return memory
