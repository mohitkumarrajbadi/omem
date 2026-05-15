"""OMem Quickstart - 10 lines to AI memory."""

from omem import OMem

# 1-line setup
omem = OMem()

# Add memories (auto-classified)
omem.add("The capital of France is Paris")
omem.add("User visited Mumbai last week for a conference")
omem.add("To deploy: step 1 build Docker image, step 2 push to registry")
omem.add("Slow response times caused the team to add caching")
omem.add("User decided to migrate from MySQL to PostgreSQL")

print(f"Stored {omem.stats()['total']} memories\n")

# Query
for query in ["France capital", "deploy steps", "database decision"]:
    print(f"rag('{query}'):")
    for r in omem.recall(query, top_k=3):
        print(f"   [{r.type.name:<12}] score={r.score:.3f}  {r.content}")
    print()

print(f"Stats: {omem.stats()}")
