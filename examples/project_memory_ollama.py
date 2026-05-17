# examples/project_memory_ollama.py
#
# OMem Project Memory + Ollama — end-to-end working demo.
#
# What this does:
#   Indexes the OMem project itself using AST parsing, then uses Ollama
#   to answer natural language questions about the codebase — with exact
#   file paths, line numbers, and dependency graphs as grounding context.
#
# Setup:
#   pip install omem-os requests
#   ollama pull llama3             # or: codellama, gemma3:4b, qwen2.5-coder
#   python examples/project_memory_ollama.py
#
# Run it twice:
#   First run  → full index (AST parses all Python files, ~5-10 seconds)
#   Second run → instant sync via git diff (milliseconds)

import os
import sys

import requests

from omem import OMem

# ── Configuration ─────────────────────────────────────────────────────────────

OLLAMA_URL = "http://localhost:11434"
MODEL = "llama3"            # change to any model you have pulled (ollama list)
DB_PATH = "~/.omem/project_memory_demo.db"
NAMESPACE = "project"

# Root of the OMem project (one level up from this examples/ file)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── Ollama helpers ─────────────────────────────────────────────────────────────

def check_ollama() -> bool:
    """Return True if Ollama is reachable."""
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        return resp.status_code == 200
    except requests.exceptions.ConnectionError:
        return False


def ollama_chat(question: str, code_context: str) -> str:
    """Ask Ollama a question about code, grounded in retrieved symbol context."""
    system = (
        "You are an expert Python code assistant. "
        "You are given precise code symbol references retrieved from a real codebase — "
        "including file paths, line numbers, function signatures, docstrings, and "
        "dependency/caller relationships.\n\n"
        "Rules:\n"
        "- Answer based only on the context provided.\n"
        "- Always cite the exact file and line number when referring to code.\n"
        "- If something is not in the context, say so clearly.\n"
        "- Be concise and technical.\n\n"
        f"Retrieved codebase context:\n{'-' * 60}\n{code_context}\n{'-' * 60}"
    )

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": question},
        ],
        "stream": False,
        "options": {"temperature": 0.2},  # low temp for factual code answers
    }

    try:
        resp = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json()["message"]["content"]
    except requests.exceptions.ConnectionError:
        return f"[Ollama not reachable at {OLLAMA_URL}. Is it running?]"
    except requests.exceptions.HTTPError as e:
        return f"[Ollama HTTP error: {e}. Is model '{MODEL}' pulled? Try: ollama pull {MODEL}]"
    except Exception as e:
        return f"[Ollama error: {e}]"


# ── Formatting helpers ─────────────────────────────────────────────────────────

def rel_path(abs_path: str) -> str:
    """Return path relative to PROJECT_ROOT for clean display."""
    try:
        return os.path.relpath(abs_path, PROJECT_ROOT)
    except ValueError:
        return abs_path


def format_context_for_ollama(results: list) -> str:
    """Convert query_code results into a structured context string for Ollama."""
    if not results:
        return "No matching symbols found."

    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"[{i}] {r.get('symbol_id', 'unknown')}  ({r.get('type', '?')})")
        lines.append(f"    File:    {rel_path(r.get('file_path', ''))}")
        lines.append(f"    Lines:   {r.get('start_line', '?')}–{r.get('end_line', '?')}")
        content = r.get("content", "").strip()
        if content:
            # Indent content block
            for cline in content.splitlines()[:6]:
                lines.append(f"    {cline}")
        related = r.get("related", [])
        if related:
            lines.append(f"    Related ({len(related)}):")
            for rel in related[:4]:
                rel_id = rel.get("symbol_id", "?")
                rel_file = rel_path(rel.get("file_path", ""))
                rel_line = rel.get("start_line", "?")
                rel_type = rel.get("relationship", rel.get("type", "?"))
                lines.append(f"      [{rel_type}] {rel_id}  {rel_file}:{rel_line}")
        lines.append("")

    return "\n".join(lines)


def print_symbol_table(results: list) -> None:
    """Print a compact table of retrieved symbols."""
    if not results:
        print("  (no results)")
        return
    for r in results:
        score = r.get("score", 0.0)
        n_related = len(r.get("related", []))
        sid = r.get("symbol_id", "?")
        fpath = rel_path(r.get("file_path", ""))
        line = r.get("start_line", "?")
        sym_type = r.get("type", "?")
        print(f"  {score:.2f}  {sid[:52]:52s}  {fpath}:{line}  [{sym_type}]  {n_related} related")


def section(title: str) -> None:
    bar = "═" * 68
    print(f"\n{bar}\n  {title}\n{bar}")


def demo_query(
    brain: OMem,
    question: str,
    search_terms: str,
    top_k: int = 5,
) -> None:
    """Retrieve code symbols for search_terms, then ask Ollama the question."""
    print(f"\n  Question:   {question}")
    print(f"  Searching:  \"{search_terms}\"")

    results = brain.query_code(
        search_terms,
        top_k=top_k,
        include_dependencies=True,
        include_callers=True,
        context_depth=2,
        namespace=NAMESPACE,
    )

    if not results:
        print("  No matching symbols found for this query.")
        return

    print(f"\n  Retrieved {len(results)} symbol(s):")
    print_symbol_table(results)

    context = format_context_for_ollama(results)
    answer = ollama_chat(question, context)

    print(f"\n  Ollama ({MODEL}):")
    # Print answer with indentation, truncate very long responses
    for line in answer.splitlines()[:30]:
        print(f"    {line}")
    if len(answer.splitlines()) > 30:
        print("    [... truncated — run interactively for full answer]")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    print("\n" + "━" * 68)
    print("  OMem Project Memory + Ollama")
    print("  Indexes the OMem codebase, then answers questions about it.")
    print("━" * 68)

    # ── Preflight ────────────────────────────────────────────────────
    if not check_ollama():
        print(f"\n  Error: Ollama is not running at {OLLAMA_URL}")
        print("  Start it with:   ollama serve")
        print(f"  Pull the model:  ollama pull {MODEL}")
        sys.exit(1)

    print(f"\n  Ollama:   connected  (model = {MODEL})")
    print(f"  Project:  {PROJECT_ROOT}")

    # ── Initialize OMem ──────────────────────────────────────────────
    brain = OMem(db_path=os.path.expanduser(DB_PATH))
    stats = brain.stats()
    existing = stats.get("total", 0)
    print(f"  OMem:     initialized  ({existing} memories in {os.path.expanduser(DB_PATH)})")

    # ── Index or sync ────────────────────────────────────────────────
    section("Step 1 — Index the Project")

    if existing == 0:
        print(f"  First run — performing full AST ingest of: {PROJECT_ROOT}")
        print("  Parses every .py file: modules, classes, functions, methods,")
        print("  docstrings, signatures, dependencies, and call graphs.")
        print("  (This takes 5-15 seconds. All subsequent runs use git diff.)\n")

        count = brain.ingest_project(PROJECT_ROOT, namespace=NAMESPACE)

        print(f"  Done. {count} symbols indexed.\n")
        fresh_stats = brain.stats()
        type_counts = fresh_stats.get("types", {})
        if type_counts:
            print("  Memory types stored:")
            for t, n in sorted(type_counts.items(), key=lambda x: -x[1]):
                print(f"    {t:20s}  {n:4d}")
    else:
        print(f"  Already indexed ({existing} memories). Running incremental sync...")
        print("  OMem calls 'git diff --name-status HEAD' to find changed files")
        print("  and re-parses only those. The rest of the index is untouched.\n")

        updated = brain.sync_project(PROJECT_ROOT, namespace=NAMESPACE)
        print(f"  Sync complete. {updated} symbols refreshed.")

    # ── Canned demo queries ──────────────────────────────────────────
    section("Step 2 — Natural Language Queries About the Codebase")
    print("  Each query retrieves exact symbols + relationships, then asks Ollama.")
    print("  No grep. No file reading. No token waste re-discovering the codebase.")

    DEMO_QUERIES = [
        (
            "How does OMem decide when a memory is unhealthy enough to archive?",
            "forget sweep health score archive threshold",
        ),
        (
            "How does the truth maintenance system detect conflicting facts?",
            "truth maintenance conflict triplet hash extract",
        ),
        (
            "Where is the hybrid RAG scoring done and what are the signal weights?",
            "hybrid scoring vector keyword recency importance weights recall",
        ),
        (
            "What does the sleep cycle do — walk me through compress, forget, reflect.",
            "sleep cycle compress forget reflect brain maintenance",
        ),
        (
            "How does the codebase indexer extract function signatures from Python files?",
            "AST visitor function signature ingester parse file",
        ),
    ]

    for question, search_terms in DEMO_QUERIES:
        demo_query(brain, question, search_terms)

    # ── Show the sync story ──────────────────────────────────────────
    section("Step 3 — Incremental Sync After Code Changes")
    print(
        "  After editing any Python file in this project, run:\n\n"
        "      brain.sync_project('.')          # Python API\n"
        "      omem sync .                      # CLI\n\n"
        "  OMem calls git diff, re-parses only changed files, updates the\n"
        "  knowledge graph edges, and removes stale symbols from deleted files.\n"
        "  The full index is preserved — only the delta is touched.\n\n"
        "  This is the key difference vs. re-indexing on every session:\n"
        "  Claude Code / Cursor always has a current, complete picture of\n"
        "  your codebase at near-zero cost after the first ingest."
    )

    # ── Interactive loop ─────────────────────────────────────────────
    section("Step 4 — Ask Your Own Questions")
    print("  Type any question about the OMem codebase.")
    print("  OMem retrieves the relevant symbols; Ollama answers.")
    print("  Press Ctrl+C or type 'quit' to exit.\n")

    while True:
        try:
            user_input = input("  Your question: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n  Done.")
            break

        if not user_input or user_input.lower() in {"quit", "exit", "q"}:
            print("  Done.")
            break

        results = brain.query_code(user_input, top_k=5, namespace=NAMESPACE)

        if not results:
            print("  No matching symbols found. Try different keywords.\n")
            continue

        print(f"\n  Retrieved {len(results)} symbol(s):")
        print_symbol_table(results)

        context = format_context_for_ollama(results)
        answer = ollama_chat(user_input, context)
        print(f"\n  Ollama ({MODEL}):")
        for line in answer.splitlines():
            print(f"    {line}")
        print()


if __name__ == "__main__":
    main()
