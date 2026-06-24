"""KnowledgeOS — full production implementation of the v2 knowledge layer.

``KnowledgeOS`` is a clean, high-level facade over three internal graph
substrates that live inside ``omem.core.graph``:

    KnowledgeGraph   — entity-relation graph (entity extraction, BFS traversal)
    CausalGraph      — directed cause-effect links between memory IDs
    DependencyGraph  — logical dependencies for belief revision

The facade adds nothing to the underlying graph logic — it translates
developer-friendly string predicates to enum values, constructs rich
response objects (``GraphSubgraph``, ``InferenceResult``), and guards
callers from internal implementation details.

Usage::

    # Via AgentState (recommended)
    agent = AgentState()
    agent.knowledge.link("FastAPI", "uses", "Pydantic")
    subgraph = agent.knowledge.query("FastAPI", depth=2)

    # Standalone (e.g. tests, scripts)
    knowledge = KnowledgeOS()                         # fresh, empty graph
    knowledge = KnowledgeOS(omem=some_omem_instance)  # live engine

See: docs/roadmap/FULL_IMPLEMENTATION_PLAN.md — Phase 4
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from ..types import GraphNode
from .types import EdgeRecord, GraphSubgraph, InferenceResult, KnowledgeStats

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Predicate → EdgeType mapping
# ---------------------------------------------------------------------------

def _resolve_edge_type(predicate: str):
    """Map a human-readable predicate string to an ``EdgeType`` enum value.

    Falls back to ``EdgeType.RELATED_TO`` for unknown predicates, with a
    debug-level log so callers can discover unmapped predicates.
    """
    from ..core.graph.knowledge import EdgeType
    _MAP: Dict[str, EdgeType] = {
        "uses": EdgeType.USES,
        "use": EdgeType.USES,
        "used": EdgeType.USES,
        "works_on": EdgeType.WORKS_ON,
        "works on": EdgeType.WORKS_ON,
        "working_on": EdgeType.WORKS_ON,
        "works_at": EdgeType.WORKS_AT,
        "works at": EdgeType.WORKS_AT,
        "employed_at": EdgeType.WORKS_AT,
        "prefers": EdgeType.PREFERS,
        "prefer": EdgeType.PREFERS,
        "preferred": EdgeType.PREFERS,
        "likes": EdgeType.PREFERS,
        "decided": EdgeType.DECIDED,
        "chose": EdgeType.DECIDED,
        "chosen": EdgeType.DECIDED,
        "picked": EdgeType.DECIDED,
        "switched_to": EdgeType.DECIDED,
        "migrated_to": EdgeType.DECIDED,
        "knows": EdgeType.KNOWS,
        "know": EdgeType.KNOWS,
        "located_at": EdgeType.LOCATED_AT,
        "located at": EdgeType.LOCATED_AT,
        "in": EdgeType.LOCATED_AT,
        "at": EdgeType.LOCATED_AT,
        "related_to": EdgeType.RELATED_TO,
        "related to": EdgeType.RELATED_TO,
        "related": EdgeType.RELATED_TO,
        "created": EdgeType.CREATED,
        "built": EdgeType.CREATED,
        "made": EdgeType.CREATED,
        "wrote": EdgeType.CREATED,
        "developed": EdgeType.CREATED,
        "designed": EdgeType.CREATED,
        "depends_on": EdgeType.DEPENDS_ON,
        "depends on": EdgeType.DEPENDS_ON,
        "requires": EdgeType.DEPENDS_ON,
        "needs": EdgeType.DEPENDS_ON,
        "relies_on": EdgeType.DEPENDS_ON,
        "asserted": EdgeType.ASSERTED,
        "assert": EdgeType.ASSERTED,
    }
    normalized = predicate.strip().lower()
    if normalized in _MAP:
        return _MAP[normalized]
    # Try upper-case enum lookup (e.g. "USES" → EdgeType.USES)
    try:
        return EdgeType[normalized.upper()]
    except KeyError:
        pass
    logger.debug("knowledge.link: unknown predicate %r — using RELATED_TO", predicate)
    return EdgeType.RELATED_TO


# ---------------------------------------------------------------------------
# KnowledgeOS
# ---------------------------------------------------------------------------

class KnowledgeOS:
    """V2 knowledge layer — fully implemented (Phase 4).

    Exposes three complementary graph APIs:

    **Entity-relation graph** (``KnowledgeGraph``)
        link(), query(), reason(), entities(), assert_fact(),
        neighbors(), paths(), ingest(), stats(), export()

    **Causal graph** (``CausalGraph``)
        causes(), get_causes(), get_effects()

    **Dependency graph** (``DependencyGraph``)
        depends_on(), invalidate(), get_dependents()

    Constructor injection
    ~~~~~~~~~~~~~~~~~~~~~
    - ``KnowledgeOS(omem=agent.memory.omem)`` — share the live engine's graph
    - ``KnowledgeOS()``                        — isolated empty graph (tests)
    - ``KnowledgeOS(_kg=kg, _cg=cg, _dg=dg)`` — inject specific graph instances

    Thread safety: all writes delegate to the underlying graph objects;
    ``KnowledgeGraph`` is a pure-Python dict structure accessed single-
    threaded in the BrainTrace lock context.  For standalone usage (no
    BrainTrace lock) callers are responsible for their own serialization.
    """

    def __init__(
        self,
        omem=None,
        _kg=None,
        _cg=None,
        _dg=None,
    ) -> None:
        if omem is not None:
            self._kg = omem.brain.knowledge_graph
            self._cg = omem.brain.graph
            self._dg = omem.brain.dependency_graph
        else:
            from ..core.graph.knowledge import KnowledgeGraph
            from ..core.graph.causal import CausalGraph
            from ..core.graph.dependency import DependencyGraph
            self._kg = _kg if _kg is not None else KnowledgeGraph()
            self._cg = _cg if _cg is not None else CausalGraph()
            self._dg = _dg if _dg is not None else DependencyGraph()

    # ------------------------------------------------------------------
    # Entity-relation graph — write operations
    # ------------------------------------------------------------------

    def link(
        self,
        subject: str,
        predicate: str,
        obj: str,
        confidence: float = 1.0,
        memory_id: str = "",
        namespace: str = "default",
    ) -> str:
        """Assert a typed relation between two entities.

        The predicate string is mapped to the nearest known ``EdgeType``;
        unknown predicates fall back to ``"related_to"``.

        Args:
            subject:    Source entity name (e.g. ``"FastAPI"``).
            predicate:  Relation type string (e.g. ``"uses"``, ``"depends_on"``).
            obj:        Target entity name (e.g. ``"Pydantic"``).
            confidence: Edge confidence [0, 1].
            memory_id:  ID of the backing memory (optional).
            namespace:  Logical namespace (unused internally, stored as provenance).

        Returns:
            Edge ID string.
        """
        from ..core.graph.knowledge import Entity, EntityType
        from ..types import Provenance

        edge_type = _resolve_edge_type(predicate)

        # Ensure both nodes exist before adding the edge
        self._kg.add_entity(Entity(name=subject, type=EntityType.CONCEPT))
        self._kg.add_entity(Entity(name=obj, type=EntityType.CONCEPT))

        edge = self._kg.add_edge(
            subject,
            obj,
            edge_type,
            memory_id=memory_id,
            confidence=confidence,
            provenance=Provenance(
                source="knowledge.link", memory_id=memory_id, namespace=namespace
            ),
        )
        logger.debug(
            "knowledge.link %r -[%s]-> %r (conf=%.2f)",
            subject, edge_type.value, obj, confidence,
        )
        return edge.id

    def assert_fact(
        self,
        subject: str,
        relation: str,
        obj: str,
        memory_id: str = "",
        confidence: float = 0.9,
        source: str = "user",
    ) -> str:
        """Assert a high-confidence structured fact.

        Higher-weight than ``link()`` — use for explicit, verified facts.

        Returns:
            Edge ID string.
        """
        edge_type = _resolve_edge_type(relation)
        result = self._kg.assert_fact(
            subject, edge_type, obj,
            memory_id=memory_id,
            confidence=confidence,
            source=source,
        )
        logger.debug("knowledge.assert_fact %r -[%s]-> %r", subject, relation, obj)
        return result.get("edge_id", "")

    def ingest(
        self,
        content: str,
        memory_id: str = "",
        source: str = "user",
        confidence: float = 1.0,
        namespace: str = "default",
    ) -> Dict[str, Any]:
        """Auto-extract entities and relations from free text.

        Delegates to the existing ``ingest_experience`` pipeline which uses
        regex patterns for technology, organization, person, and location
        detection.

        Returns:
            Dict with keys: ``node_ids``, ``edge_ids``, ``entities``,
            ``relation_types``, ``evidence_count``.
        """
        return self._kg.ingest_experience(
            memory_id=memory_id,
            content=content,
            source=source,
            confidence=confidence,
            namespace=namespace,
        )

    # ------------------------------------------------------------------
    # Entity-relation graph — read operations
    # ------------------------------------------------------------------

    def query(
        self,
        entity: str,
        depth: int = 2,
        namespace: Optional[str] = None,
    ) -> GraphSubgraph:
        """Return the subgraph centred on an entity up to ``depth`` hops.

        Performs BFS traversal from ``entity`` and collects all reachable
        nodes and the edges that connect them within the subgraph boundary.

        Args:
            entity:    Root entity name.
            depth:     BFS hop limit (1 = direct neighbors only).
            namespace: Reserved for future multi-tenant filtering.

        Returns:
            ``GraphSubgraph`` with nodes, edges, and related memory IDs.
        """
        entity_key = entity.lower()
        reachable_keys = [entity_key] + [n.lower() for n in self._kg.traverse(entity, depth=depth)]
        reachable_set = set(reachable_keys)

        # Collect GraphNode objects
        nodes: List[GraphNode] = []
        seen_nodes: set = set()
        for name in reachable_keys:
            ent = self._kg.get_entity(name)
            if ent and ent.node_id and ent.node_id not in seen_nodes:
                node = self._kg.get_node(ent.node_id)
                if node:
                    nodes.append(node)
                    seen_nodes.add(ent.node_id)

        # Collect edges fully contained within the subgraph
        edges: List[EdgeRecord] = []
        seen_edges: set = set()
        for name in reachable_keys:
            for edge in self._kg.get_edges(name):
                if edge.id in seen_edges:
                    continue
                if edge.source in reachable_set and edge.target in reachable_set:
                    seen_edges.add(edge.id)
                    edges.append(EdgeRecord(
                        id=edge.id,
                        source=edge.source,
                        target=edge.target,
                        predicate=edge.edge_type.value,
                        confidence=edge.confidence,
                        weight=edge.weight,
                        memory_id=edge.memory_id,
                        evidence_count=edge.evidence_count,
                    ))

        related_memory_ids = self._kg.get_related_memory_ids(entity, depth=depth)

        return GraphSubgraph(
            root_entity=entity,
            depth=depth,
            nodes=nodes,
            edges=edges,
            entity_count=len(nodes),
            edge_count=len(edges),
            related_memory_ids=related_memory_ids,
        )

    def reason(
        self,
        question: str,
        namespace: Optional[str] = None,
        max_results: int = 20,
    ) -> List[InferenceResult]:
        """Apply heuristic inference over known facts to answer a question.

        Strategy:
        1. Extract entities from the question using regex patterns.
        2. Collect direct (1-hop) facts — high confidence.
        3. Collect transitive (2-hop) inferences — confidence discounted by 0.7.
        4. Sort by confidence descending, cap at ``max_results``.

        Works best when the question names entities the graph knows about.
        For example: "What does FastAPI use?" with FastAPI in the graph.

        Returns:
            List of ``InferenceResult`` sorted by confidence (highest first).
        """
        from ..core.graph.knowledge import extract_entities

        # Step 1: Extract entities from the question
        entities = extract_entities(question)

        # Fallback: scan known entities for any word in the question
        if not entities:
            words = set(question.lower().split())
            for ent in self._kg.all_entities():
                if ent.name.lower() in words:
                    entities.append(ent)

        results: List[InferenceResult] = []
        seen_statements: set = set()

        for ent in entities:
            name = ent.name
            name_key = name.lower()

            # Step 2: Direct facts (1-hop)
            for edge in self._kg.get_edges(name):
                stmt = (
                    f"{edge.source} {edge.edge_type.value.replace('_', ' ')} {edge.target}"
                )
                if stmt not in seen_statements:
                    seen_statements.add(stmt)
                    results.append(InferenceResult(
                        statement=stmt,
                        confidence=edge.confidence,
                        supporting_memory_ids=[edge.memory_id] if edge.memory_id else [],
                        reasoning_path=[edge.source, edge.target],
                        inference_type="direct",
                    ))

            # Step 3: Transitive inference (2-hop)
            for neighbor in self._kg.traverse(name, depth=1):
                for edge in self._kg.get_edges(neighbor):
                    # Only include edges that extend AWAY from the root entity
                    other = edge.target if edge.source == neighbor.lower() else edge.source
                    if other == name_key:
                        continue
                    stmt = (
                        f"{name} → {neighbor} "
                        f"{edge.edge_type.value.replace('_', ' ')} {other}"
                    )
                    if stmt not in seen_statements:
                        seen_statements.add(stmt)
                        results.append(InferenceResult(
                            statement=stmt,
                            confidence=round(edge.confidence * 0.7, 4),
                            supporting_memory_ids=[edge.memory_id] if edge.memory_id else [],
                            reasoning_path=[name, neighbor, other],
                            inference_type="transitive",
                        ))

        results.sort(key=lambda r: r.confidence, reverse=True)
        return results[:max_results]

    def entities(
        self,
        namespace: Optional[str] = None,
        entity_type: Optional[str] = None,
    ) -> List[GraphNode]:
        """List all known entities as ``GraphNode`` objects.

        Args:
            namespace:   Reserved for future filtering.
            entity_type: Filter by type string (e.g. ``"technology"``,
                         ``"person"``, ``"concept"``).

        Returns:
            List of ``GraphNode``, sorted by ``mention_count`` descending.
        """
        nodes = self._kg.all_nodes()
        if entity_type:
            nodes = [n for n in nodes if n.entity_type == entity_type]
        nodes.sort(key=lambda n: n.mention_count, reverse=True)
        return nodes

    def neighbors(self, entity: str, depth: int = 1) -> List[str]:
        """Return all entity names reachable within ``depth`` hops.

        Args:
            entity: Root entity name.
            depth:  BFS hop limit.

        Returns:
            List of entity names (strings), not including the root itself.
        """
        return self._kg.traverse(entity, depth=depth)

    def paths(
        self,
        source: str,
        target: str,
        max_depth: int = 4,
    ) -> List[List[str]]:
        """Find all simple paths between two entities.

        Uses BFS with path-tracking.  Cycles are avoided by not revisiting
        nodes already in the current path.  Results are capped at 10 paths
        to prevent combinatorial explosion on dense graphs.

        Args:
            source:    Start entity name.
            target:    End entity name.
            max_depth: Maximum path length (in hops).

        Returns:
            List of paths; each path is a list of entity name strings from
            ``source`` to ``target`` inclusive.
        """
        target_key = target.lower()
        found: List[List[str]] = []
        queue: List[Tuple[str, List[str]]] = [(source.lower(), [source.lower()])]

        while queue:
            current, path = queue.pop(0)
            if len(path) > max_depth + 1:
                continue
            if current == target_key:
                found.append(list(path))
                if len(found) >= 10:
                    break
                continue
            for neighbor in self._kg.neighbours(current):
                if neighbor not in path:
                    queue.append((neighbor, path + [neighbor]))

        return found

    def get_entity_node(self, entity: str) -> Optional[GraphNode]:
        """Return the ``GraphNode`` for a single entity, or None."""
        return self._kg.get_node_by_label(entity)

    def stats(self) -> KnowledgeStats:
        """Return aggregate statistics about the knowledge graph."""
        from ..core.graph.knowledge import extract_entities

        all_entities = self._kg.all_entities()
        all_edges = self._kg.all_edges()

        # Top-10 entities by degree centrality
        centralities: List[Tuple[str, float]] = [
            (e.name, self._kg.entity_centrality(e.name))
            for e in all_entities
        ]
        centralities.sort(key=lambda x: x[1], reverse=True)
        top_entities = centralities[:10]

        avg_centrality = (
            sum(c for _, c in centralities) / len(centralities)
            if centralities else 0.0
        )

        edge_type_dist: Dict[str, int] = {}
        for edge in all_edges:
            t = edge.edge_type.value
            edge_type_dist[t] = edge_type_dist.get(t, 0) + 1

        dep_links = sum(
            len(v) for v in getattr(self._dg, "_child_to_parents", {}).values()
        )

        return KnowledgeStats(
            total_entities=len(all_entities),
            total_nodes=len(self._kg.all_nodes()),
            total_edges=len(all_edges),
            top_entities=top_entities,
            edge_type_distribution=edge_type_dist,
            avg_centrality=round(avg_centrality, 4),
            causal_links=self._cg.num_edges,
            dependency_links=dep_links,
        )

    def export(self) -> Dict[str, Any]:
        """Return a fully serializable dict representation of the graph.

        Includes all entities, nodes, edges, and aggregate stats.
        Safe to JSON-serialise and persist.
        """
        return self._kg.to_dict()

    def entity_centrality(self, entity: str) -> float:
        """Normalized degree centrality for an entity [0, 1]."""
        return self._kg.entity_centrality(entity)

    def related_memories(self, entity: str, depth: int = 2) -> List[str]:
        """Return memory IDs linked to an entity and its neighbors."""
        return self._kg.get_related_memory_ids(entity, depth=depth)

    # ------------------------------------------------------------------
    # Causal graph — cause-effect links between memories
    # ------------------------------------------------------------------

    def causes(
        self,
        cause_memory_id: str,
        effect_memory_id: str,
        label: str = "",
        weight: float = 1.0,
    ) -> None:
        """Record that ``cause_memory_id`` causes ``effect_memory_id``.

        Args:
            cause_memory_id:  Memory that is the cause.
            effect_memory_id: Memory that is the effect.
            label:            Human-readable description of the causal link.
            weight:           Causal strength [0, ∞).
        """
        self._cg.add_link(cause_memory_id, effect_memory_id, weight=weight, label=label)
        logger.debug(
            "knowledge.causes %r → %r (w=%.2f)", cause_memory_id, effect_memory_id, weight
        )

    def get_effects(self, memory_id: str) -> List[str]:
        """Return memory IDs that are effects of ``memory_id``."""
        return [e.dst for e in self._cg.get_effects(memory_id)]

    def get_causes(self, memory_id: str) -> List[str]:
        """Return memory IDs that are causes of ``memory_id``."""
        return [e.src for e in self._cg.get_causes(memory_id)]

    # ------------------------------------------------------------------
    # Dependency graph — logical belief revision
    # ------------------------------------------------------------------

    def depends_on(self, child_memory_id: str, parent_memory_id: str) -> None:
        """Mark that the fact in ``child_memory_id`` depends on ``parent_memory_id``.

        When the parent is later updated or invalidated, the child will
        appear in the ``invalidate()`` response.
        """
        self._dg.add_dependency(child_memory_id, parent_memory_id)
        logger.debug(
            "knowledge.depends_on child=%r parent=%r",
            child_memory_id, parent_memory_id,
        )

    def invalidate(self, memory_id: str) -> List[str]:
        """Propagate invalidation from ``memory_id`` to all dependent memories.

        Returns:
            List of memory IDs that are transitively dependent on the
            invalidated memory and may need re-evaluation.
        """
        affected = self._dg.invalidate_branch(memory_id)
        if affected:
            logger.info(
                "knowledge.invalidate %r affected %d downstream memories",
                memory_id, len(affected),
            )
        return affected

    def get_dependents(self, memory_id: str) -> List[str]:
        """Return memory IDs that directly depend on ``memory_id``."""
        return self._dg.get_children(memory_id)

    def get_dependencies(self, memory_id: str) -> List[str]:
        """Return memory IDs that ``memory_id`` directly depends on."""
        return self._dg.get_parents(memory_id)
