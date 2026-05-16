# Run this twice — the second run shares memory across agents.
#
# pip install omem-os crewai
#
# What this shows:
#   - Two agents (researcher, writer) share a namespace
#   - Researcher stores a fact; writer recalls it
#   - A third "finance" agent in a different namespace cannot see their memory

try:
    from crewai import Agent, Task, Crew
except ImportError:
    print("CrewAI not installed. Run: pip install crewai")
    raise

from omem import OMem
from omem.types import MemoryType


def make_omem_tool(brain: OMem):
    """Minimal tool adapter: gives a CrewAI agent add/recall access to OMem."""

    def remember(content: str) -> str:
        mid = brain.add(content, mem_type=MemoryType.SEMANTIC, importance=0.7)
        return f"Stored memory {mid}: {content}"

    def recall(query: str) -> str:
        results = brain.recall(query, k=3)
        if not results:
            return "No relevant memories found."
        return "\n".join(f"- {m.content}" for m in results)

    return remember, recall


def main() -> None:
    # Shared namespace: researcher and writer can both read/write
    shared_brain = OMem(
        db_path="~/.omem/crewai_demo.db",
        namespace="research_project",
    )

    # Isolated namespace: finance agent cannot see research_project memories
    finance_brain = OMem(
        db_path="~/.omem/crewai_demo.db",
        namespace="finance_team",
    )

    researcher_remember, researcher_recall = make_omem_tool(shared_brain)
    writer_remember, writer_recall = make_omem_tool(shared_brain)
    finance_remember, finance_recall = make_omem_tool(finance_brain)

    # --- Researcher stores a fact ---
    print("=== Researcher stores a finding ===")
    finding = "Study shows 40% retention improvement with personalized onboarding flows"
    result = researcher_remember(finding)
    print(result)

    # --- Writer recalls from the same namespace ---
    print("\n=== Writer recalls research findings ===")
    recalled = writer_recall("retention improvement onboarding")
    print(f"Writer sees:\n{recalled}")

    # --- Finance agent cannot see the research namespace ---
    print("\n=== Finance agent tries to recall (different namespace) ===")
    finance_recalled = finance_recall("retention improvement onboarding")
    print(f"Finance agent sees:\n{finance_recalled}")
    assert "retention" not in finance_recalled.lower(), (
        "Namespace isolation failed: finance agent saw research memory"
    )
    print("Namespace isolation confirmed: finance agent has no access to research memory.")

    # --- Memory persists across runs ---
    total = len(shared_brain.all())
    print(f"\nTotal memories in research_project namespace: {total}")
    print("Run again to see the count grow as more facts are stored.")


if __name__ == "__main__":
    main()
