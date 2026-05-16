# Run this twice — the second run remembers the first.
#
# pip install omem-os langchain langchain-community
#
# What this shows:
#   Run 1: stores user preferences, sets a "session complete" flag
#   Run 2: recalls preferences and prints them — no re-entry needed

from omem import OMem
from omem.types import MemoryType

try:
    from omem.integrations.langchain import OMemRetriever
except ImportError:
    print("LangChain integration not available. Install with: pip install omem-os langchain")
    raise


def main() -> None:
    # Uses a persistent path so data survives between runs
    brain = OMem(
        db_path="~/.omem/langchain_demo.db",
        namespace="langchain_demo",
    )

    # Check if this is the first run
    existing = brain.recall("session_1_complete", k=1)
    is_first_run = not existing

    if is_first_run:
        print("=== First run: storing preferences ===\n")

        brain.add(
            "User prefers dark mode in all applications",
            mem_type=MemoryType.DECISION,
            importance=0.7,
        )
        brain.add(
            "User's primary language is Python; avoids JavaScript when possible",
            mem_type=MemoryType.DECISION,
            importance=0.8,
        )
        brain.add(
            "User works in Pacific timezone (UTC-8) and prefers morning standups",
            mem_type=MemoryType.SEMANTIC,
            importance=0.6,
        )

        # Set the sentinel so second run knows preferences are stored
        brain.add("session_1_complete", mem_type=MemoryType.WORKING, importance=0.1)

        print("Stored 3 user preferences.")
        print("Run this script again to see them recalled.")

    else:
        print("=== Second run: recalling from memory ===\n")

        # Wrap OMem in the LangChain retriever interface
        retriever = OMemRetriever(omem_instance=brain)

        # Retrieve relevant documents using the LangChain interface
        docs = retriever.get_relevant_documents("user interface and language preferences")

        print("Remembered from last session:")
        for doc in docs:
            if "session_1_complete" not in doc.page_content:
                print(f"  • {doc.page_content}")

        total = len([m for m in brain.all() if "session_1_complete" not in m.content])
        print(f"\nTotal stored preferences: {total}")


if __name__ == "__main__":
    main()
