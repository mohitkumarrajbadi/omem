"""Knowledge Graph Agent — Phase 4 demonstration.

Shows the full KnowledgeOS API in a realistic agent scenario:

1. Build a technology knowledge graph through manual assertions
2. Auto-extract entities from free-form text
3. BFS subgraph queries
4. Heuristic inference / reasoning
5. Path finding between entities
6. Track causal relationships between memories
7. Belief revision via dependency invalidation
8. Token-efficient context assembly with knowledge enrichment
9. Graph statistics

Run:
    python examples/knowledge_graph_agent.py
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from omem.knowledge import KnowledgeOS


def section(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)


def sub(title: str):
    print(f"\n  ── {title}")


def main():
    print("KnowledgeOS — Phase 4 Demo")
    print("OMem: Persistent State Infrastructure for AI Systems\n")

    # ── Initialize ───────────────────────────────────────────────────────
    knowledge = KnowledgeOS()   # standalone (no OMem instance needed)

    # ══════════════════════════════════════════════════════════════════════
    section("1. Manual Knowledge Assertions")
    # ══════════════════════════════════════════════════════════════════════

    sub("Technology stack relationships")

    # Tech stack for an AI product
    edges = [
        ("OMem", "uses", "FastAPI", "REST API layer"),
        ("OMem", "uses", "Python", "core language"),
        ("OMem", "uses", "Rust", "performance-critical engine"),
        ("OMem", "uses", "SQLite", "persistence backend"),
        ("OMem", "uses", "FAISS", "vector search index"),
        ("FastAPI", "uses", "Pydantic", "validation & serialization"),
        ("FastAPI", "uses", "Starlette", "ASGI foundation"),
        ("FastAPI", "depends_on", "Python", ""),
        ("Pydantic", "depends_on", "Python", ""),
        ("FAISS", "uses", "NumPy", "array operations"),
        ("OMem", "depends_on", "sentence-transformers", "embedding model"),
        ("sentence-transformers", "depends_on", "PyTorch", ""),
        ("PyTorch", "uses", "NumPy", ""),
    ]

    for subject, predicate, obj, _ in edges:
        edge_id = knowledge.link(subject, predicate, obj)

    print(f"  Asserted {len(edges)} relationships")

    sub("High-confidence fact assertion")
    edge_id = knowledge.assert_fact(
        "OMem", "uses", "Akamai Linode",
        memory_id="mem-architecture-001",
        confidence=0.98,
        source="architecture-doc",
    )
    print(f"  Fact asserted (edge_id={edge_id[:8]}...)")

    # ══════════════════════════════════════════════════════════════════════
    section("2. Auto-Extraction from Free Text")
    # ══════════════════════════════════════════════════════════════════════

    texts = [
        ("mem-001", "Alice is the lead engineer working on OMem at Akamai Technologies."),
        ("mem-002", "The team decided to use PostgreSQL for the managed cloud service."),
        ("mem-003", "Bob prefers Rust for systems-level code over C++."),
        ("mem-004", "We are building the OMem agent runtime using Python and Rust."),
    ]

    print()
    for mem_id, text in texts:
        result = knowledge.ingest(text, memory_id=mem_id, confidence=0.85)
        entities = result.get("entities", [])
        relations = result.get("relation_types", [])
        print(f"  [{mem_id}] entities={entities[:3]}  relations={relations[:2]}")

    # ══════════════════════════════════════════════════════════════════════
    section("3. Subgraph Query")
    # ══════════════════════════════════════════════════════════════════════

    for entity, depth in [("OMem", 1), ("FastAPI", 2)]:
        sg = knowledge.query(entity, depth=depth)
        print(
            f"\n  query({entity!r}, depth={depth})"
            f"  → entities={sg.entity_count}  edges={sg.edge_count}"
            f"  memories={len(sg.related_memory_ids)}"
        )
        if sg.edges:
            print(f"  Sample edges:")
            for edge in sg.edges[:5]:
                print(f"    {edge.source} —[{edge.predicate}]→ {edge.target}")

    # ══════════════════════════════════════════════════════════════════════
    section("4. Heuristic Reasoning")
    # ══════════════════════════════════════════════════════════════════════

    questions = [
        "What does OMem use?",
        "What does FastAPI depend on?",
        "What is Python related to?",
    ]

    for q in questions:
        results = knowledge.reason(q, max_results=5)
        print(f"\n  Q: {q!r}")
        if results:
            for r in results[:3]:
                tag = "⬥" if r.inference_type == "direct" else "◇"
                print(f"    {tag} [{r.confidence:.2f}] {r.statement}")
        else:
            print("    (no inferences found)")

    # ══════════════════════════════════════════════════════════════════════
    section("5. Path Finding")
    # ══════════════════════════════════════════════════════════════════════

    path_queries = [
        ("omem", "pydantic", 3),
        ("omem", "pytorch", 4),
        ("omem", "numpy", 4),
    ]

    print()
    for src, tgt, depth in path_queries:
        paths = knowledge.paths(src, tgt, max_depth=depth)
        if paths:
            print(f"  {src} → {tgt}  ({len(paths)} path(s)):")
            for p in paths[:2]:
                print(f"    {' → '.join(p)}")
        else:
            print(f"  {src} → {tgt}:  no path within {depth} hops")

    # ══════════════════════════════════════════════════════════════════════
    section("6. Causal Graph — Memory Cause-Effect Links")
    # ══════════════════════════════════════════════════════════════════════

    sub("Recording causal chains")
    knowledge.causes("mem-001", "mem-004",
                     label="Alice's decision triggered the build plan")
    knowledge.causes("mem-003", "mem-004",
                     label="Rust preference influenced the runtime architecture")

    print()
    for mem_id in ("mem-001", "mem-003"):
        effects = knowledge.get_effects(mem_id)
        print(f"  get_effects({mem_id!r})  → {effects}")

    causes_of_004 = knowledge.get_causes("mem-004")
    print(f"  get_causes('mem-004')  → {causes_of_004}")

    # ══════════════════════════════════════════════════════════════════════
    section("7. Dependency Graph — Belief Revision")
    # ══════════════════════════════════════════════════════════════════════

    sub("Registering logical dependencies")
    knowledge.depends_on("mem-004", "mem-003")   # build plan depends on Rust preference
    knowledge.depends_on("mem-002", "mem-001")   # PostgreSQL decision depends on Alice's role

    print()
    print("  If mem-001 (Alice's role) becomes invalid:")
    affected = knowledge.invalidate("mem-001")
    print(f"    → Affected memories: {affected}")

    print()
    print("  If mem-003 (Rust preference) changes:")
    affected = knowledge.invalidate("mem-003")
    print(f"    → Affected memories: {affected}")

    # ══════════════════════════════════════════════════════════════════════
    section("8. Entity Listing and Centrality")
    # ══════════════════════════════════════════════════════════════════════

    print()
    print("  Top 8 entities by mention count:")
    nodes = knowledge.entities()
    for node in nodes[:8]:
        centrality = knowledge.entity_centrality(node.label)
        print(
            f"    [{node.entity_type:12}] {node.label:<28} "
            f"mentions={node.mention_count}  centrality={centrality:.3f}"
        )

    # ══════════════════════════════════════════════════════════════════════
    section("9. Knowledge Graph Statistics")
    # ══════════════════════════════════════════════════════════════════════

    stats = knowledge.stats()
    d = stats.to_dict()
    print()
    print(f"  Total entities   : {stats.total_entities}")
    print(f"  Total nodes      : {stats.total_nodes}")
    print(f"  Total edges      : {stats.total_edges}")
    print(f"  Avg centrality   : {stats.avg_centrality:.4f}")
    print(f"  Causal links     : {stats.causal_links}")
    print(f"  Dependency links : {stats.dependency_links}")
    print()
    print("  Edge type distribution:")
    for etype, count in sorted(d["edge_type_distribution"].items(),
                               key=lambda x: x[1], reverse=True):
        bar = "█" * min(count, 20)
        print(f"    {etype:<15} {count:3}  {bar}")
    print()
    print("  Top entities (degree centrality):")
    for rec in d["top_entities"][:5]:
        print(f"    {rec['name']:<28} {rec['centrality']:.4f}")

    # ══════════════════════════════════════════════════════════════════════
    section("10. Export")
    # ══════════════════════════════════════════════════════════════════════

    graph_data = knowledge.export()
    print()
    print(f"  Exported {len(graph_data['entities'])} entities, "
          f"{len(graph_data['edges'])} edges")
    print(f"  JSON size: ~{len(json.dumps(graph_data)) // 1024}KB")

    print()
    print("─" * 60)
    print("  Phase 4 demo complete.")
    print("  KnowledgeOS is fully operational.")
    print("─" * 60)
    print()


if __name__ == "__main__":
    main()
