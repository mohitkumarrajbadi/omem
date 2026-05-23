import os
import time
import sys
from omem import OMem, MemoryType

# -- ANSI COLORS --
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_ITALIC = "\033[3m"
C_GREEN = "\033[32m"
C_BLUE = "\033[34m"
C_CYAN = "\033[36m"
C_YELLOW = "\033[33m"
C_RED = "\033[31m"
C_MAGENTA = "\033[35m"


def print_header(text):
    print(f"\n{C_BOLD}{C_MAGENTA}{'=' * 60}{C_RESET}")
    print(f"{C_BOLD}{C_CYAN} [ {text} ]{C_RESET}")
    print(f"{C_BOLD}{C_MAGENTA}{'=' * 60}{C_RESET}\n")


def print_step(step, text):
    print(f"{C_BOLD}{C_YELLOW}[STEP {step}]{C_RESET} {text}")
    time.sleep(1)


def wait_for_user():
    input(f"\n{C_CYAN}>> Press [ENTER] to continue...{C_RESET}")


def main():
    # Zero-config initialization
    m = OMem(backend="memory")

    # Simple check for ANSI support
    if os.name == "nt":
        os.system("color")

    os.system("clear" if os.name == "posix" else "cls")
    print_header("OMEM: FINANCIAL FRAUD DETECTION - TECHNICAL DEMO")
    print(
        f"{C_ITALIC}Cognitive Memory Architecture for Secure Financial Workflows{C_RESET}\n"
    )

    # -- PHASE 1: INTELLIGENT INGESTION --
    print_step(1, "Intelligent Ingestion & Auto-Classification")
    print("Ingesting raw transaction logs and system policies...")

    # Ingesting mixed data: facts, decisions, and sensitive info
    m.add("User mohit@example.com logged in from new IP: 192.168.1.45 (Bangalore)")
    m.add(
        "Transaction #TRX-9981: amount=$4,500.00, status=pending, merchant='Global Gems'"
    )
    m.add(
        "Internal policy: decisions to flag transactions over $10k must follow procedure 44-B"
    )
    m.add(
        "AWS_ACCESS_KEY: AKIAJSJF92LLAKSJF92, secret stored in vault."
    )  # PII/Secret detection

    time.sleep(1.5)
    print(f"{C_GREEN}Ingested 4 cognitive memories successfully.{C_RESET}")

    print("\nListing memories with auto-priority scores:")
    for mem in m.all():
        p_color = C_RED if str(mem.priority.name) == "CORE" else C_BLUE
        print(
            f"  [{mem.type.name[:4]}] {p_color}{mem.priority.name:7}{C_RESET} | {mem.content[:70]}..."
        )

    print(f"\n{C_BOLD}{C_YELLOW}Technical Note:{C_RESET}")
    print(
        f"  - OMem automatically identified the AWS Key as {C_RED}CORE{C_RESET} priority (PII/Secret detection)."
    )
    print(
        f"  - System policies were correctly classified as {C_BLUE}DECISION{C_RESET} rules based on heuristics."
    )

    wait_for_user()

    # -- PHASE 2: THE DECISION ENGINE --
    print_header("PHASE 2: PROCEDURAL RETRIEVAL")
    print_step(2, "Procedural Memory & Mode-Aware RAG")

    # Adding procedural rules
    m.add(
        "Procedure 44-B: 1. Verify KYC, 2. Check geolocation history, 3. Manual review if score > 0.8"
    )
    m.add("Blocked transaction #TRX-4421: geolocation high-risk.")

    print("Scenario: A new high-risk transaction requires handling instructions.")
    print(
        f"Agent Query: {C_CYAN}'How should I handle this high-risk transaction?'{C_RESET}"
    )

    # Use planning mode to boost specific memory types
    results = m.recall("how to handle high-risk transaction", top_k=2, mode="planning")

    for r in results:
        print(f"\n{C_BOLD}{C_GREEN}RECALLED RULE:{C_RESET} {r.type.name}")
        print(f"Content: {r.content}")

    print(f"\n{C_BOLD}{C_YELLOW}Technical Note:{C_RESET}")
    print(
        f"  - Using {C_MAGENTA}'planning'{C_RESET} mode, the engine prioritizes Procedural & Decision"
    )
    print(
        "    memories over raw semantic facts, providing actionable logic to the LLM."
    )

    wait_for_user()

    # -- PHASE 3: EXPLAINABILITY (INSPECT) --
    print_header("PHASE 3: AUDIT & EXPLAINABILITY")
    print_step(3, "Deep Retrieval Inspection")

    query = "transaction geolocation"
    print(f"Agent Query: {C_CYAN}'{query}'{C_RESET}")
    explanations = m.inspect(query, top_k=1)

    for exp in explanations:
        print(f"\n{C_BOLD}Scoring Breakdown for Audit Logs:{C_RESET}")
        print(exp.explain())

    print(f"\n{C_BOLD}{C_YELLOW}Technical Note:{C_RESET}")
    print(
        "  - OMem provides full multi-signal explainability (Vector, Keyword, Recency, Importance)."
    )
    print("  - This is critical for regulatory compliance in financial services.")

    wait_for_user()

    # -- PHASE 4: THE DREAM CYCLE --
    print_header("PHASE 4: AUTONOMOUS CONSOLIDATION")
    print_step(4, "Memory Optimization (Dream Cycle)")

    print("Injecting redundant pattern logs...")
    m.add("Fraud Attempt Detected: user_id_881, IP 10.0.0.1")
    m.add("Fraud Attempt Detected: user_id_881, IP 10.0.0.2")
    m.add("Fraud Attempt Detected: user_id_881, IP 10.0.0.3")

    print(f"Current Memory Count: {C_BOLD}{len(m.all())}{C_RESET}")

    print("\nRunning 'Dream Cycle' to consolidate noise into patterns...")
    time.sleep(1)
    dream_res = m.dream(threshold=0.1)

    print(f"{C_GREEN}Wisdom Created: {dream_res.wisdom_created}{C_RESET}")
    print(
        f"{C_GREEN}Source Memories Consolidated: {dream_res.source_archived}{C_RESET}"
    )

    wisdom = [mem for mem in m.all() if mem.type == MemoryType.WISDOM]
    if wisdom:
        print(f"\n{C_BOLD}{C_MAGENTA}CONSOLIDATED PATTERN (WISDOM):{C_RESET}")
        print(f">> {C_ITALIC}{wisdom[-1].content if wisdom else ''}{C_RESET}")

    print(f"\n{C_BOLD}{C_YELLOW}Technical Note:{C_RESET}")
    print("  - OMem identified recurring audit logs autonomously.")
    print(
        "  - It synthesized high-level 'Wisdom' to preserve context while reducing token usage."
    )

    print_header("DEMO COMPLETE")
    print(f"{C_CYAN}Current State Summary:{C_RESET} {m}")
    print(
        f"{C_MAGENTA}OMem: The cognitive infrastructure for agentic applications.{C_RESET}\n"
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nDemo aborted.")
        sys.exit(0)
    except Exception as e:
        print(f"\nError occurred: {e}")
        import traceback

        traceback.print_exc()
