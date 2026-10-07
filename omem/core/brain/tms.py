"""Truth Maintenance System (TMS) for OMem.

Responsible for extracting logical triplets, detecting contradictions,
and managing memory status (ACTIVE, DEPRECATED, CONFLICTED).

Temporal Resolution Policy (v1.0):
  When two memories share the same logical_hash (same entity-attribute pair)
  but have different values, the NEWER one wins. The older one is immediately
  set to DEPRECATED + inactive so the retrieval pipeline skips it without
  any further configuration. The new memory is always kept ACTIVE.
"""

import hashlib
import logging
import re
import time
from typing import List, Optional, Tuple

from ...types import Memory, MemoryStatus

logger = logging.getLogger(__name__)

# Basic patterns for entity-attribute extraction (the 'plumbing' for v1.0.0)
# No LLM: regex + optional structured metadata["triplet"] / metadata["facts"].
_EXTRACTION_PATTERNS = [
    # "User's favorite color is blue" -> (user, favorite color, blue)
    re.compile(r"([^']+)'s\s+(.+?)\s+is\s+(.+)"),
    # "The server is in Mumbai", "The server moved to Delhi"
    re.compile(r"(?:the\s+)?([^\s]+)\s+(?:is|moved\s+to|located\s+in|at)\s+(.+)"),
    # "My name is Mohit", "I want the dashboard to be neon green"
    re.compile(r"(?:my\s+)?([^\s]+)\s+(?:is|want|wants|favors)\s+(?:the\s+)?(.+)"),
    # Multi-term attributes
    re.compile(r"([^\s]+)\s+depends\s+on\s+(.+)"),
]

# Location / residence — same logical key so "lives in NYC" vs "moved to SF" conflict.
_LOCATION_PATTERNS = [
    re.compile(r"^(?:i|user|we)\s+live\s+in\s+(.+)$"),
    re.compile(r"^(?:i|user|we)\s+moved\s+to\s+(.+)$"),
    re.compile(r"^(?:i|user|we)\s+relocated\s+to\s+(.+)$"),
    re.compile(r"^(.+?)\s+lives\s+in\s+(.+)$"),
    re.compile(r"^(.+?)\s+moved\s+to\s+(.+)$"),
    re.compile(r"^(.+?)\s+relocated\s+to\s+(.+)$"),
    re.compile(r"^(?:my|the)\s+city\s+is\s+(.+)$"),
    re.compile(r"^user\s+lives\s+in\s+(.+)$"),
]


# Dialogue / haystack turns must not enter belief revision. The greedy
# "X is Y" extractors otherwise collapse unrelated chat (Shell gas, shift
# sheets) onto one logical_hash and delete evidence LongMemEval still needs.
_DIALOGUE_PREFIX = re.compile(
    r"^\s*(?:\[[^\]]{1,32}\]\s+|[A-Za-z][\w .'-]{0,40}:\s+\S)",
)


def is_dialogue_turn(content: str) -> bool:
    """True for ``[user] …``, ``[assistant] …``, or ``Speaker: …`` lines."""
    return bool(content and _DIALOGUE_PREFIX.match(content))


def extract_triplet(content: str) -> Optional[Tuple[str, str, str]]:
    """Extract (Entity, Attribute, Value) from text using heuristics."""
    text = content.strip().lower().rstrip(".")
    for pattern in _LOCATION_PATTERNS:
        match = pattern.search(text)
        if match:
            if len(match.groups()) == 1:
                return ("user", "location", match.group(1).strip())
            entity = match.group(1).strip()
            if entity in ("i", "my", "user", "we"):
                entity = "user"
            return (entity, "location", match.group(2).strip())
    for pattern in _EXTRACTION_PATTERNS:
        match = pattern.search(text)
        if match:
            # Normalize terms
            if len(match.groups()) >= 3:
                entity = match.group(1).strip()
                attr = match.group(2).strip()
                value = match.group(3).strip()
            else:
                entity = match.group(1).strip()
                attr = "fact"  # Default attribute for 2-group patterns
                value = match.group(2).strip()

            # Common normalization
            if entity in ("i", "my", "user"):
                entity = "user"
            return (entity, attr, value)
    return None


def compute_logical_hash(entity: str, attribute: str) -> str:
    """Generate a unique ID for an Entity-Attribute pair."""
    key = f"{entity.lower()}|{attribute.lower()}"
    return hashlib.md5(key.encode()).hexdigest()[:16]


_DEPENDENCY_PATTERNS = [
    # "Fact A depends on Fact B"
    re.compile(r"(.+?)\s+depends\s+on\s+(.+)"),
    # "Fact A is caused by Fact B"
    re.compile(r"(.+?)\s+is\s+caused\s+by\s+(.+)"),
]


def extract_dependency(content: str) -> Optional[Tuple[str, str]]:
    """Extract (Subject, Dependency) from text."""
    text = content.strip().lower()
    for pattern in _DEPENDENCY_PATTERNS:
        match = pattern.search(text)
        if match:
            return (match.group(1).strip(), match.group(2).strip())
    return None


class ConflictResolver:
    """Detects and resolves logical inconsistencies and manages dependencies."""

    def __init__(self, backend, kv=None, dependency_graph=None):
        self.backend = backend
        self.kv = kv
        self.dependency_graph = dependency_graph

    def check_and_mark_conflicts(self, new_memory: Memory) -> List[str]:
        """Check if new memory contradicts existing memories or creates dependencies.

        Marks older conflicting memories as CONFLICTED.
        Propagates invalidation down the dependency tree.
        """
        affected_ids = []
        if is_dialogue_turn(new_memory.content):
            return affected_ids

        # 1. Dependency Extraction
        dep_pair = extract_dependency(new_memory.content)
        if dep_pair and self.dependency_graph:
            # For now, we search for the 'parent' memory by content similarity
            # In a more advanced version, we'd use the KnowledgeGraph directly
            parent_id = self._find_best_match(dep_pair[1])
            if parent_id:
                self.dependency_graph.add_dependency(new_memory.id, parent_id)
                new_memory.dependencies.append(parent_id)

        # 2. Conflict Detection (Triplets)
        # Structured facts first: metadata["triplet"] or metadata["facts"][0].
        pre_triplet = new_memory.metadata.get("triplet")
        if pre_triplet and len(pre_triplet) == 3:
            triplet = tuple(pre_triplet)
        else:
            facts = new_memory.metadata.get("facts") or []
            if facts and isinstance(facts[0], (list, tuple)) and len(facts[0]) == 3:
                triplet = tuple(facts[0])
            elif facts and isinstance(facts[0], dict):
                triplet = (
                    facts[0].get("subject") or facts[0].get("entity"),
                    facts[0].get("predicate") or facts[0].get("attribute"),
                    facts[0].get("object") or facts[0].get("value"),
                )
                if not all(triplet):
                    triplet = extract_triplet(new_memory.content)
            else:
                triplet = extract_triplet(new_memory.content)

        if not triplet:
            return affected_ids

        entity, attr, value = triplet
        l_hash = compute_logical_hash(entity, attr)
        new_memory.logical_hash = l_hash
        new_memory.metadata["triplet"] = triplet

        # Find existing memories with THIS logical hash
        existing = []
        if self.kv:
            existing.extend(self.kv.all())
        if self.backend:
            existing.extend(self.backend.all())

        unique_mems = {m.id: m for m in existing if m.id != new_memory.id}.values()
        conflicts = [m for m in unique_mems if m.logical_hash == l_hash and m.active]

        for old in conflicts:
            if is_dialogue_turn(old.content):
                continue
            old_triplet = old.metadata.get("triplet")
            if old_triplet and old_triplet[2] != value:
                logger.warning(
                    "Belief Revision: '%s' → superseded by '%s'",
                    old.content[:80],
                    new_memory.content[:80],
                )

                # ── Temporal Resolution (v1.0) ──
                # The newer memory is always the ground truth.
                # Mark the old one DEPRECATED + inactive so rag.py skips it
                # automatically (no penalty needed — it simply disappears).
                old.status = MemoryStatus.DEPRECATED
                old.active = False
                old.superseded_by = new_memory.id
                old.valid_to = new_memory.timestamp or time.time()
                if self.backend:
                    self.backend.save(old)
                if self.kv:
                    self.kv.set(old.id, old)
                affected_ids.append(old.id)

                # Propagate invalidation down the dependency tree
                if self.dependency_graph:
                    downstream = self.dependency_graph.invalidate_branch(old.id)
                    for d_id in downstream:
                        d_mem = self.kv.get(d_id) if self.kv else None
                        if (
                            d_mem is None
                            and self.backend
                            and hasattr(self.backend, "load")
                        ):
                            d_mem = self.backend.load(d_id)
                        if d_mem:
                            d_mem.status = MemoryStatus.CONFLICTED
                            d_mem.confidence_score = max(
                                d_mem.confidence_score * 0.5, 0.0
                            )
                            if self.backend:
                                self.backend.save(d_mem)
                            affected_ids.append(d_id)

        # The new memory is always ACTIVE — it is the current truth.
        new_memory.status = MemoryStatus.ACTIVE
        new_memory.active = True
        if new_memory.valid_from is None:
            new_memory.valid_from = new_memory.timestamp
        new_memory.valid_to = None
        return affected_ids

    def _find_best_match(self, topic: str) -> Optional[str]:
        """Search engine for finding a memory ID by content fragment."""
        if not self.kv:
            return None
        # Simple string match for demo, would be vector search in production
        for m in self.kv.all():
            if topic in m.content.lower():
                return m.id
        return None
