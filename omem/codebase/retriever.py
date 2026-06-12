"""Hybrid retrieval for Project Memory.
This module implements a simple two‑stage retrieval:
1. Vector recall via OMem.recall to get a candidate set.
2. Re‑ranking using graph distance, recency, and a configurable weight
   vector (semantic_sim, graph_hops, recency, importance).
The current implementation keeps the graph‑distance calculation lightweight
by using the OMem knowledge‑graph adjacency list (if available). If the
graph API changes, this module can be swapped out without touching the rest
of the system.
"""

import time
from typing import Any, Dict, List

from ..api import OMem
from ..core.retrieval.fusion import fuse_score
from ..core.retrieval.ranker import weights_for_mode

DEFAULT_WEIGHTS = weights_for_mode("coding").as_dict()

class CodeRetriever:
    """Retrieve code symbols for a natural‑language query.

    Parameters
    ----------
    omem: OMem
        Core OMem instance.
    namespace: str, optional
        Namespace where project symbols live (default ``"project"``).
    weights: dict, optional
        Weighting factors for the ranking formula.
    """

    def __init__(self, omem: OMem, namespace: str = "project", weights: Dict[str, float] | None = None):
        self.omem = omem
        self.namespace = namespace
        self.weights = weights if weights is not None else DEFAULT_WEIGHTS

    # ---------------------------------------------------------------------
    # Helper: graph distance (hop count) between two symbols
    # ---------------------------------------------------------------------
    def _graph_hops(self, src_id: str, dst_id: str) -> int:
        """Return the shortest‑path hop count between two symbol IDs.
        If the graph library raises or the nodes are missing, fall back to a
        large penalty (e.g., 100).
        """
        try:
            # OMem exposes its internal KnowledgeGraph via ``brain.graph``
            graph = self.omem.brain.graph
            # ``shortest_path`` returns a list of node IDs; length-1 = hops
            path = graph.shortest_path(src_id, dst_id)
            return max(len(path) - 1, 0)
        except Exception:
            return 100

    # ---------------------------------------------------------------------
    # Main retrieval entry point
    # ---------------------------------------------------------------------
    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        include_dependencies: bool = True,
        include_callers: bool = True,
        context_depth: int = 2,
    ) -> List[Dict[str, Any]]:
        """Return a list of enriched code‑symbol results.
        Each result contains the primary symbol and an optional ``related`` list
        with dependencies / callers up to ``context_depth``.
        """
        # 1️⃣ Vector recall – get candidates from project namespace
        candidates = self.omem.recall(
            query,
            k=top_k * 10,  # oversample heavily to find code symbols in large stores
            namespace=self.namespace,
        )
        # Filter to only code symbols
        code_candidates = [c for c in candidates if c.metadata.get("is_code_symbol")]

        # 2️⃣ Compute ranking scores
        scored = []
        now = time.time()
        for mem in code_candidates:
            # Semantic similarity is already stored as ``score`` on the memory
            semantic_score = getattr(mem, "score", 0.0)
            # Recency – newer timestamps get higher value (seconds since epoch)
            recency_score = 1.0 / (1.0 + (now - mem.timestamp))
            # Importance – already a float 0‑1
            importance_score = getattr(mem, "importance", 0.0)
            # Graph distance – we compare to the top semantic result later
            graph_score = 0.0  # placeholder; will be filled after we pick primary
            scored.append({
                "mem": mem,
                "semantic": semantic_score,
                "recency": recency_score,
                "importance": importance_score,
                "graph": graph_score,
            })

        # Pick the primary result (highest combined weight without graph yet)
        def combined(s):
            w = self.weights
            return fuse_score(
                semantic=s["semantic"],
                keyword=0.0,
                recency=s["recency"],
                importance=s["importance"],
                graph=s["graph"],
                weights=weights_for_mode("coding"),
            )

        scored.sort(key=combined, reverse=True)
        primary = scored[:top_k]

        # Now compute graph distances from the primary symbol to all others
        if primary:
            primary_id = primary[0]["mem"].id
            for entry in primary:
                entry["graph"] = 1.0 / (1 + self._graph_hops(primary_id, entry["mem"].id))
            # Re‑rank with graph component
            primary.sort(
                key=lambda s: fuse_score(
                    semantic=s["semantic"],
                    keyword=0.0,
                    recency=s["recency"],
                    importance=s["importance"],
                    graph=s["graph"],
                    weights=weights_for_mode("coding"),
                ),
                reverse=True,
            )

        # 3️⃣ Build the final output structure
        results: List[Dict[str, Any]] = []
        for entry in primary:
            mem = entry["mem"]
            base = {
                "symbol_id": mem.metadata.get("symbol_id"),
                "file_path": mem.metadata.get("file_path"),
                "start_line": mem.metadata.get("start_line"),
                "end_line": mem.metadata.get("end_line"),
                "type": mem.metadata.get("symbol_type"),
                "summary": mem.metadata.get("summary"),
                "content": mem.content,
                "score": mem.score,
                "importance": getattr(mem, "importance", 0.0),
                "timestamp": mem.timestamp,
            }
            # Gather related context if requested
            related: List[Dict[str, Any]] = []
            if include_dependencies or include_callers:
                # Use the knowledge graph to fetch direct neighbours
                try:
                    graph = self.omem.brain.graph
                    neighbours = graph.neighbours(mem.id)
                except Exception:
                    neighbours = []
                for nb_id in neighbours:
                    nb_mem = self.omem.get(nb_id)
                    if not nb_mem:
                        continue
                    rel_type = graph.edge_label(mem.id, nb_id)  # may be None
                    if rel_type in {"depends_on", "called_by", "contains", "belongs_to"}:
                        if (rel_type == "depends_on" and not include_dependencies) or (
                            rel_type == "called_by" and not include_callers
                        ):
                            continue
                        related.append(
                            {
                                "symbol_id": nb_mem.metadata.get("symbol_id"),
                                "type": rel_type,
                                "file_path": nb_mem.metadata.get("file_path"),
                                "summary": nb_mem.metadata.get("summary"),
                            }
                        )
                # Depth‑limited expansion (simple BFS up to depth)
                # For brevity we only include first‑level neighbours.
            if related:
                base["related"] = related
            results.append(base)
        return results
