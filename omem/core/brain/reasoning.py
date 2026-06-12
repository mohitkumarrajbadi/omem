"""Graph reasoning helpers for multi-hop memory inference."""

from typing import Dict, List, Optional, Set

from ..graph.knowledge import EdgeType, KnowledgeGraph


def infer_related_entities(
    graph: KnowledgeGraph,
    seed_entities: List[str],
    depth: int = 2,
) -> List[str]:
    """Return entity names reachable from seed entities within depth hops."""
    seen: Set[str] = set()
    ordered: List[str] = []
    for name in seed_entities:
        for neighbour in graph.traverse(name, depth=depth):
            key = neighbour.lower()
            if key not in seen:
                seen.add(key)
                ordered.append(neighbour)
    return ordered


def explain_relation_path(
    graph: KnowledgeGraph,
    source: str,
    target: str,
    max_depth: int = 3,
) -> List[Dict[str, str]]:
    """Return a simple BFS path of relations between two entities."""
    src = source.lower()
    tgt = target.lower()
    if src == tgt:
        return [{"source": source, "target": target, "type": "self"}]

    queue: List[tuple] = [(src, [])]
    visited: Set[str] = {src}

    while queue:
        current, path = queue.pop(0)
        if len(path) >= max_depth:
            continue
        for edge in graph.get_edges(current):
            nxt = edge.target if edge.source == current else edge.source
            step = {
                "source": edge.source,
                "target": edge.target,
                "type": edge.edge_type.value,
            }
            new_path = path + [step]
            if nxt == tgt:
                return new_path
            if nxt not in visited:
                visited.add(nxt)
                queue.append((nxt, new_path))
    return []


def query_graph_substrate(
    graph: KnowledgeGraph,
    entity_name: str,
    depth: int = 2,
    edge_type: Optional[EdgeType] = None,
) -> Dict:
    """Structured graph query for API consumers."""
    entity = graph.get_entity(entity_name)
    if entity is None:
        return {"entity": entity_name, "found": False, "nodes": [], "edges": []}

    node = graph.get_node_by_label(entity.name)
    edges = graph.get_edges(entity.name)
    if edge_type is not None:
        edges = [e for e in edges if e.edge_type == edge_type]

    related = graph.traverse(entity.name, depth=depth)
    return {
        "entity": entity.name,
        "found": True,
        "node_id": node.id if node else "",
        "nodes": related,
        "edges": [
            {
                "id": e.id,
                "source": e.source,
                "target": e.target,
                "type": e.edge_type.value,
                "weight": e.weight,
                "confidence": e.confidence,
            }
            for e in edges
        ],
        "memory_ids": graph.get_related_memory_ids(entity.name, depth=depth),
    }
