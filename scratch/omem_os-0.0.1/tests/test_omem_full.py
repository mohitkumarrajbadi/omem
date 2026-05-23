#!/usr/bin/env python3
"""
Comprehensive OMem Test Script
Tests all functionality with realistic conversation dataset
"""

import json
import time
from omem import OMem


def print_section(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def main():
    print_section("OMem Comprehensive Test")

    # Initialize
    print("\n1. Initializing OMem...")
    m = OMem()
    print(f"OK Initialized: {m}")

    # Clear existing
    print("\n2. Clearing existing memories...")
    m.clear()
    print("OK Cleared")

    # Add individual memories
    print("\n3. Adding individual memories...")
    m.add("Testing OMem with comprehensive dataset", importance=0.9)
    m.add("User prefers dark mode theme", importance=0.8)
    m.add("Critical security vulnerability in auth", importance=1.0)
    print("OK Added 3 memories")

    # Load conversation dataset
    print("\n4. Loading conversation dataset...")
    with open("test_conversations.json") as f:
        conversations = json.load(f)

    for conv in conversations:
        m.add(conv["content"], importance=conv["importance"])
    print(f"OK Loaded {len(conversations)} conversations")

    # Stats
    print("\n5. Memory Statistics:")
    stats = m.stats()
    print(f"   Total memories: {stats['total']}")
    print(f"   Active: {stats['total'] - stats['inactive']}")
    print(f"   Inactive: {stats['inactive']}")
    print(f"   Avg importance: {stats['avg_importance']:.2f}")
    print(f"   Namespaces: {stats['namespaces']}")
    print("   Memory types:")
    for mtype, count in sorted(stats["types"].items()):
        print(f"     {mtype:15s} {count:>4d}")

    # Search tests
    print_section("Search & Retrieval Tests")

    queries = [
        ("security vulnerability", 3),
        ("dark mode", 3),
        ("performance optimization", 3),
        ("user preferences", 5),
        ("database", 3),
    ]

    for query, k in queries:
        print(f"\nQuery: '{query}'")
        results = m.recall(query, k=k)
        for i, mem in enumerate(results[:3], 1):
            print(
                f"   {i}. [{mem.type.name:11s}] score={mem.score:.3f} imp={mem.importance:.2f}"
            )
            print(f"      {mem.content[:70]}")

    # Context-type filtering
    print("\n\nSearching with context-type filter (bugs):")
    bug_results = m.recall("error", k=5, context_type="bugs")
    for i, mem in enumerate(bug_results[:3], 1):
        print(f"   {i}. {mem.content[:70]}")

    # Time-range filtering
    print("\nSearching with time-range filter (recent):")
    recent_results = m.recall("user", k=5, time_range="recent")
    print(f"   Found {len(recent_results)} recent memories")

    # List memories
    print_section("Memory Listing")

    print("\nAll memories (first 10):")
    all_mems = m.all()
    for i, mem in enumerate(all_mems[:10], 1):
        status = "OK" if mem.active else "INACTIVE"
        print(f"   {i}. {status} [{mem.type.name:11s}] imp={mem.importance:.2f}")
        print(f"      {mem.content[:65]}")

    # Inspection
    print_section("Retrieval Inspection")

    print("\nInspecting 'authentication' query:")
    explanations = m.inspect("authentication", top_k=2)
    for i, exp in enumerate(explanations, 1):
        print(f"\n{i}. Memory: {exp.memory_id[:12]}...")
        print(f"   Final score: {exp.final_score:.4f}")
        print(f"   Vector sim:  {exp.vector_score:.4f}")
        print(f"   Keywords:    {exp.keyword_score:.4f}")
        print(f"   Recency:     {exp.recency_score:.4f}")
        print(f"   Importance:  {exp.importance_score:.4f}")

    # Namespaces
    print_section("Namespace Tests")

    print("\nAdding memories to different namespaces...")
    m.add("Test memory in testing namespace", namespace="testing", importance=0.8)
    m.add("Another test in testing", namespace="testing", importance=0.7)
    m.add("Production memory", namespace="production", importance=0.9)
    print("OK Added to 3 namespaces")

    print("\nActive namespaces:")
    namespaces = m.namespaces()
    for ns in namespaces:
        ns_stats = m.namespace_stats(ns)
        print(f"   * {ns:20s} {ns_stats.get('total', 0):>4d} memories")

    # Export
    print_section("Export & Data Management")

    print("\nExporting memories to JSON...")
    memories_export = {
        "memories": [mem.to_dict() for mem in m.all()],
        "stats": m.stats(),
        "exported_at": time.time(),
    }
    with open("test_export_full.json", "w") as f:
        json.dump(memories_export, f, indent=2)
    print(f"OK Exported {len(memories_export['memories'])} memories")

    # Maintenance
    print_section("Maintenance Operations")

    print("\n1. Compression...")
    comp_result = m.compress(threshold=0.8)
    print(f"   OK Compressed: {comp_result['compressed']} groups")
    print(f"   OK Deactivated: {comp_result['deactivated']} memories")

    print("\n2. Reflection...")
    reflections = m.reflect(threshold=0.7)
    print(f"   OK Generated {len(reflections)} reflection insights")
    if reflections:
        print("\n   Sample reflections:")
        for i, ref in enumerate(reflections[:2], 1):
            print(f"   {i}. {ref.content[:70]}...")

    print("\n3. Forgetting cycle...")
    forget_result = m.forget()
    forgotten_count = (
        len(getattr(forget_result, "forgotten_ids", [])) if forget_result else 0
    )
    print(f"   OK Forgot {forgotten_count} low-value memories")

    # Final stats
    print_section("Final Statistics")

    final_stats = m.stats()
    print(f"\n   Total memories:     {final_stats['total']}")
    print(f"   Active:             {final_stats['total'] - final_stats['inactive']}")
    print(f"   Inactive:           {final_stats['inactive']}")
    print(f"   Avg importance:     {final_stats['avg_importance']:.2f}")
    print(f"   Graph edges:        {final_stats['graph_edges']}")
    print(f"   Namespaces:         {len(final_stats['namespaces'])}")

    print_section("Test Complete!")
    print("\nAll operations tested successfully")
    print("Generated files:")
    print("  - test_export_full.json")
    print()


if __name__ == "__main__":
    main()
