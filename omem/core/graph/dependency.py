"""Dependency Graph for OMem.

Tracks logical dependencies between memories to support Belief Revision.
If Fact A depends on Fact B, and B is updated or invalidated, Fact A
will be flagged for re-evaluation.
"""

import logging
from collections import defaultdict
from typing import Dict, List, Set

logger = logging.getLogger(__name__)


class DependencyGraph:
    """A directed graph of memory dependencies."""

    def __init__(self, backend=None):
        # child_id -> set(parent_ids)
        self._child_to_parents: Dict[str, Set[str]] = defaultdict(set)
        # parent_id -> set(child_ids)
        self._parent_to_children: Dict[str, Set[str]] = defaultdict(set)
        self.backend = backend

    def add_dependency(self, child_id: str, parent_id: str):
        """Mark that child_id depends on parent_id."""
        if child_id == parent_id:
            return

        self._child_to_parents[child_id].add(parent_id)
        self._parent_to_children[parent_id].add(child_id)
        logger.debug("Dependency added: %s -> %s", child_id, parent_id)

    def get_parents(self, child_id: str) -> List[str]:
        """Get all memories that child_id depends on."""
        return list(self._child_to_parents.get(child_id, set()))

    def get_children(self, parent_id: str) -> List[str]:
        """Get all memories that depend on parent_id."""
        return list(self._parent_to_children.get(parent_id, set()))

    def remove_memory(self, memory_id: str):
        """Clean up all links for a removed memory."""
        # Remove as child
        parents = self._child_to_parents.pop(memory_id, set())
        for p in parents:
            self._parent_to_children[p].discard(memory_id)

        # Remove as parent
        children = self._parent_to_children.pop(memory_id, set())
        for c in children:
            self._child_to_parents[c].discard(memory_id)

    def get_all_downstream(self, parent_id: str) -> Set[str]:
        """Get all memories that eventually depend on parent_id (recursive)."""
        visited = set()
        stack = [parent_id]

        while stack:
            curr = stack.pop()
            children = self._parent_to_children.get(curr, set())
            for child in children:
                if child not in visited:
                    visited.add(child)
                    stack.append(child)
        return visited

    def invalidate_branch(self, root_id: str) -> List[str]:
        """Propagate invalidation down the dependency tree.

        Returns a list of memory IDs that need re-evaluation.
        """
        downstream = self.get_all_downstream(root_id)
        affected = list(downstream)

        if affected:
            logger.info(
                "Belief Revision: Parent %s invalidated %d downstream memories",
                root_id,
                len(affected),
            )

        return affected
