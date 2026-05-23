#!/usr/bin/env python3
"""OMem Killer Demo - AI Assistant That Remembers Everything.

This demo simulates a personal AI assistant that:
1. Learns about the user through conversation
2. Auto-classifies and scores importance
3. Compresses redundant memories
4. Generates reflections (insights)
5. Handles memory updates and contradictions
6. Supports multi-agent collaboration
7. Shows full retrieval explanations

Run: python examples/memory_assistant.py
"""

from omem import OMem


def divider(title: str = ""):
    print(f"\n{'=' * 70}")
    if title:
        print(f"  {title}")
        print(f"{'=' * 70}")


def show_memories(m: OMem, label: str = "Memories"):
    mems = m.all()
    print(f"\n  {label}: {len(mems)} active")
    for mem in mems[:8]:
        print(
            f"    [{mem.type.name:11s}] imp={mem.importance:.2f} ax={mem.access_count} | {mem.content[:65]}"
        )


def main():
    print("""
    ==================================================================
    OMem - AI Memory Operating System Demo
    "The assistant that truly remembers you"
    ==================================================================
    """)

    m = OMem()

    # -- SCENE 1: Learning About the User --
    divider("SCENE 1: Learning About The User")
    print("  User has a conversation with the AI assistant...")
    print()

    conversations = [
        ("My name is Mohit and I'm a software engineer", 0.95),
        ("I live in Bangalore, India", 0.85),
        ("I prefer Python over JavaScript for backend work", 0.8),
        ("I'm building an AI memory system called OMem", 0.9),
        ("I like working late at night, usually 10pm to 2am", 0.7),
        ("My favorite food is biryani", 0.6),
        ("I'm interested in IndiaAI grants for my projects", 0.75),
        ("I use VS Code as my primary editor", 0.5),
    ]

    for content, expected_imp in conversations:
        mid = m.add(content)
        mem = m.get(mid)
        print(f'  "{content}"')
        print(f"     -> Type: {mem.type.name}, Importance: {mem.importance:.2f}")

    show_memories(m, "After Learning")

    # -- SCENE 2: Intelligent Retrieval --
    divider("SCENE 2: Intelligent Retrieval (Importance-Weighted RAG)")

    queries = [
        "What does the user do?",
        "programming language preferences",
        "Where does the user live?",
        "What is the user working on?",
    ]

    for query in queries:
        print(f'\n  Query: "{query}"')
        results = m.recall(query, top_k=3)
        for i, r in enumerate(results):
            print(f"     {i + 1}. [{r.score:.3f}] {r.content[:70]}")

    # -- SCENE 3: Memory Compression --
    divider("SCENE 3: Memory Compression")
    print("  Adding redundant memories to simulate real usage...\n")

    m.add("I really like Python a lot")
    m.add("Python is my go-to language for everything")
    m.add("I always choose Python when starting a new project")
    m.add("Biryani is the best food ever")
    m.add("I love eating biryani on weekends")

    s1 = m.stats()
    print(f"  Before compression: {s1['total']} active memories")

    result = m.compress(threshold=0.7)
    s2 = m.stats()
    print(
        f"  After compression:  {s2['total']} active, {result['compressed']} new, {result['deactivated']} deactivated"
    )
    print(f"  Memory reduction: {s1['total']} -> {s2['total']}")

    # -- SCENE 4: Reflection Engine --
    divider("SCENE 4: Automatic Reflection")
    print("  Generating insights from accumulated memories...\n")

    reflections = m.reflect()
    if reflections:
        for ref in reflections:
            print(f"  Reflection: {ref.content[:100]}")
    else:
        print("  (Not enough clustered data for reflection in this demo)")

    # -- SCENE 5: Memory Updates --
    divider("SCENE 5: Memory Updates & Conflict Resolution")

    editor_id = m.add("I use VS Code as my primary editor")
    print('  Original: "I use VS Code as my primary editor"')

    new_id = m.update(editor_id, "I switched from VS Code to Cursor AI editor")
    if new_id:
        new_mem = m.get(new_id)
        print(f'  Updated:  "{new_mem.content}"')
        old_mem = m.get(editor_id)
        print(f"  Old memory active: {old_mem.active if old_mem else 'N/A'}")

    # -- SCENE 6: Multi-Agent Shared Memory --
    divider("SCENE 6: Multi-Agent Collaboration")
    print("  Simulating three agents sharing memory...\n")

    from omem.integrations.crewai import OMemSharedMemory

    shared = OMemSharedMemory(workspace="project-omem", omem=m)

    shared.store(
        "researcher", "Found that AI memory market is $2.3B and growing 40% YoY"
    )
    shared.store("researcher", "Top competitors: Mem0, ChromaDB, Pinecone")
    shared.store(
        "planner", "Strategy: target developer-first approach with zero-config setup"
    )
    shared.store("planner", "Set milestone: 1000 GitHub stars by Q3")
    shared.store("executor", "Published OMem v0.2.0 to PyPI")
    shared.store("executor", "Completed benchmark suite with 6 test modules")

    print("  Planner searches for market data:")
    results = shared.recall("market size competitors", agent=None)
    for r in results[:3]:
        print(f"     [{r.score:.3f}] {r.content[:70]}")

    print(f"\n  Workspace stats: {shared.stats()}")

    # -- SCENE 7: Observability --
    divider("SCENE 7: Retrieval Observability (Inspect)")
    print("  Explaining why memories are retrieved...\n")

    explanations = m.inspect("What programming language does the user prefer?", top_k=3)
    for exp in explanations:
        print(exp.explain())
        print()

    # -- SCENE 8: Conversation Reflection --
    divider("SCENE 8: Conversation Reflection")
    print("  Reflecting on a full conversation...\n")

    conversation = [
        "I've been thinking about open source strategy",
        "Maybe we should focus on the developer experience first",
        "The CLI needs to be really polished",
        "Documentation is key for adoption",
        "Let's target the LangChain community",
        "We need compelling benchmarks against competitors",
    ]

    for msg in conversation:
        print(f'  "{msg}"')

    insight = m.reflect_conversation(conversation)
    if insight:
        print(f'\n  Reflection: "{insight.content}"')
        print(f"     Type: {insight.type.name}, Importance: {insight.importance:.2f}")

    # -- Final Stats --
    divider("FINAL: Memory Operating System Status")
    stats = m.stats()
    print(f"""
  OMem Memory OS v0.2.0
  -----------------------------
  Active memories:   {stats["total"]}
  Inactive memories: {stats["inactive"]}
  Namespaces:        {stats["namespaces"]}
  Avg importance:    {stats["avg_importance"]:.2f}
  Graph edges:       {stats["graph_edges"]}
  Memory types:      {stats["types"]}
    """)

    divider()
    print("  OMem is not just a vector DB.")
    print("  It's the OPERATING SYSTEM for AI memory.")
    print("  github.com/your-username/omem")
    print()


if __name__ == "__main__":
    main()
