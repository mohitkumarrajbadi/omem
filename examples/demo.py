#!/usr/bin/env python3
"""
OMem Cognitive Memory OS - Technical Demonstration

This demo showcases the core architectural features of OMem including
priority-weighted retrieval, mode-aware RAG, and autonomous lifecycle management.
"""

import os

# Prevent Numba/FAISS threading issues
os.environ["NUMBA_DISABLE_JIT"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"

import time
import sys

# Ensure the project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from omem import OMem, MemoryType, MemoryPriority

# -- Formatting Helpers --
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def header(title):
    print(f"\n{BOLD}{CYAN}{'=' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'=' * 60}{RESET}\n")


def step(msg):
    print(f"  [+] {msg}")


def result(msg):
    print(f"    - {msg}")


def mem_fmt(m):
    pri = f"{MAGENTA}{m.priority.name}{RESET}"
    typ = f"{CYAN}{m.type.name}{RESET}"
    score = f"{GREEN}{m.score:.4f}{RESET}"
    preview = m.content[:65] + "..." if len(m.content) > 65 else m.content
    return f'[{pri}] [{typ}] score={score}  "{preview}"'


# ==============================================================
print(f"""
{BOLD}OMem Cognitive Memory OS{RESET}
{DIM}Technical Infrastructure for Agentic Applications
Version 0.6.0+
{RESET}""")

input(f"{DIM}Press Enter to initialize the demo...{RESET}")

# ==============================================================
# DEMO 1: PRIORITIZATION LAYER
# ==============================================================

header("DEMO 1: Priority-Based Tiering")
print(
    f"  {DIM}OMem auto-classifies memories into priority tiers based on content features.{RESET}"
)
print(f"  {DIM}Tiering: Identity > Goals > Preferences > Facts > Casual{RESET}\n")

mem = OMem()

memories = [
    ("My name is Mohit and I'm a backend engineer", "identity"),
    ("My goal is to build a startup by 2027", "goal"),
    ("I prefer Python over JavaScript", "preference"),
    ("Python was created by Guido van Rossum in 1991", "fact"),
    ("The weather is nice today", "casual"),
    ("okay sure got it thanks", "filler"),
    ("My API key is sk-abc123secret456", "secret"),
]

for content, _ in memories:
    mid = mem.add(content)
    m = mem.get(mid)
    pri_color = {
        MemoryPriority.CORE: RED,
        MemoryPriority.HIGH: YELLOW,
        MemoryPriority.NORMAL: GREEN,
        MemoryPriority.LOW: DIM,
    }[m.priority]
    step(f'{pri_color}{m.priority.name:6s}{RESET} | "{content[:55]}"')

print(
    f"\n  {BOLD}Analysis:{RESET} CORE memories receive a significant scoring boost during retrieval."
)
print("            LOW priority memories are penalized to reduce noise.")

# ==============================================================
# DEMO 2: COMPOSITE SCORING
# ==============================================================

header("DEMO 2: Multi-Signal Retrieval")
print(f'  {DIM}Query: "Who am I and what do I like?"{RESET}\n')

results = mem.recall("Who am I and what do I like?", top_k=5)
for i, r in enumerate(results, 1):
    print(f"  {BOLD}#{i}{RESET} {mem_fmt(r)}")

print(
    f"\n  {BOLD}Note:{RESET} Identity and preference memories rank higher than generic facts."
)

# ==============================================================
# DEMO 3: MODE-AWARE RAG
# ==============================================================

header("DEMO 3: Mode-Aware Retrieval Strategies")
print(f"  {DIM}OMem optimizes retrieval across specific context-aware modes.{RESET}\n")

mem.add("System deployment: run docker-compose up -d", mem_type=MemoryType.PROCEDURAL)
mem.add("Decided to use FastAPI for the backend", mem_type=MemoryType.DECISION)

query = "How to handle deployment?"
modes = ["default", "coding", "planning"]

for mode in modes:
    mode_colors = {"default": RESET, "coding": CYAN, "planning": YELLOW}
    results = mem.recall(query, top_k=2, mode=mode)
    print(f'  {BOLD}{mode_colors[mode]}mode="{mode}"{RESET}')
    for r in results:
        print(f"    {mem_fmt(r)}")
    print()

# ==============================================================
# DEMO 4: LIFECYCLE MANAGEMENT
# ==============================================================

header("DEMO 4: Autonomous Lifecycle Management")
print(
    f"  {DIM}Intelligent forgetting and archival based on importance and recency.{RESET}\n"
)

mem2 = OMem()
now = time.time()

mem2.add("My name is Mohit")
step("Added Identity (CORE Tier - Immune)")

mid_fact = mem2.add("Meeting scheduled for 3pm tomorrow")
step("Added Fact (ACTIVE Tier)")

mid_filler = mem2.add("okay sure thanks")
step("Added Filler (ACTIVE Tier - Low Importance)")

# Simulate aging
fact_mem = mem2.get(mid_fact)
filler_mem = mem2.get(mid_filler)
if fact_mem:
    fact_mem.timestamp = now - (35 * 24 * 3600)  # 35 days old
if filler_mem:
    filler_mem.timestamp = now - (40 * 24 * 3600)  # 40 days old
    filler_mem.importance = 0.2

print(f"\n  {DIM}[Simulation: 35 days have passed]{RESET}\n")

forget_result = mem2.forget()
step("Sweep Summary:")
result(f"Kept: {forget_result.kept}")
result(f"Archived: {len(forget_result.archived)} (Stale Data)")
result(f"Deleted: {len(forget_result.deleted)} (Trivial Noise)")
result(f"Immune: {forget_result.core_immune}")

# ==============================================================
# DEMO 5: EXPLAINABILITY
# ==============================================================

header("DEMO 5: Retrieval Audit & Explainability")
print(f"  {DIM}Scoring breakdown for technical auditing.{RESET}\n")

explanations = mem.inspect("programming language", top_k=2)
for exp in explanations:
    print(f"  {BOLD}Memory ID:{RESET} {exp.memory_id}")
    print(f"    Vector:     {CYAN}{exp.vector_score:.4f}{RESET}")
    print(f"    Keyword:    {CYAN}{exp.keyword_score:.4f}{RESET}")
    print(f"    Importance: {CYAN}{exp.importance_score:.4f}{RESET}")
    print(f"    Recency:    {CYAN}{exp.recency_score:.4f}{RESET}")
    print(f"    {BOLD}Final Score: {GREEN}{exp.final_score:.4f}{RESET}")
    print()

# ==============================================================
# DEMO 6: CONSOLIDATION
# ==============================================================

header("DEMO 6: Pattern Consolidation")

mem3 = OMem()
mem3.add("Prefer Python for services")
mem3.add("Always use Python for services")
step("Added redundant preference logs")

compress_result = mem3.compress(threshold=0.6)
result(
    f"Consolidated {compress_result.get('merged', 0)} groups into synthesized memories"
)

insights = mem3.reflect()
step(f"Generated {len(insights)} insight reflections based on accumulated knowledge")

# ==============================================================
# SUMMARY
# ==============================================================

header("Technical Feature Summary")

summary = [
    ("Priority Tiering", "Multi-signal auto-classification", "[COMPLETED]"),
    ("Lifecycle Management", "Intelligent forgetting and archival", "[COMPLETED]"),
    ("Mode-Aware RAG", "Contextual retrieval strategies", "[COMPLETED]"),
    ("Hybrid Scoring", "Vector + Keyword + Importance + Recency", "[COMPLETED]"),
    ("Auditability", "Native explainability logs", "[COMPLETED]"),
    ("Consolidation", "Pattern synthesis via Dream Cycle", "[COMPLETED]"),
    ("Rust Performance", "SIMD-accelerated retrieval core", "[COMPLETED]"),
]

for name, desc, status in summary:
    print(f"  {status} {BOLD}{name:20s}{RESET} {DIM}{desc}{RESET}")

print(f"\n{BOLD}OMem - Cognitive Infrastructure for Agentic Systems{RESET}\n")
