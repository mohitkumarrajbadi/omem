> **Technical documentation for extending, integrating, and contributing to OMem.**
>
> *Version: 0.1.0*

---

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Programmatic Usage (How to use the "bits")](#programmatic-usage-how-to-use-the-bits)
   - [Initialization & Backends](#initialization--backends)
   - [Adding Memories (Types & Importance)](#adding-memories-types--importance)
   - [Recalling Memories (Hybrid RAG)](#recalling-memories-hybrid-rag)
   - [Memory Maintenance (Sleep & TMS)](#memory-maintenance-sleep--tms)
   - [Graph-RAG Explained](#graph-rag-explained)
   - [Agent Integrations (MCP & LangChain)](#agent-integrations-mcp--langchain)
3. [Contributor Guide](#contributor-guide)
   - [Environment Setup](#environment-setup)
   - [Branching & PR Workflow](#branching--pr-workflow)
   - [Testing Standard](#testing-standard)
   - [Benchmarking](#benchmarking)
   - [Code Style & Linting](#code-style--linting)
   - [Adding New Backends](#adding-new-backends)
4. [CLI Reference](#cli-reference)
5. [Context FAQ](#memory-layer-faq--does-it-bloat-context)

---

## System Architecture

OMem is organized into highly optimized, modular components:

### 1. Interface Layer (`omem/api.py`)
Provides the unified entry point for application integration (`class OMem`). It handles request normalization, sensible defaults, and orchestrates interaction between the Brain and Engine layers.

### 2. Retrieval Layer (Rust Core)
Based in `omem/core/retrieval/` and utilizing the `omem_rust` native extension.
- **Hybrid Scoring**: SIMD-accelerated ranking combining vector similarity, keyword matching, recency, and importance in a single pass.
- **Optimized Retrieval**: Built on FAISS HNSW. Thread-safe management of embeddings.

### 3. Logic Layer (The "Brain")
Based in `omem/core/brain/`. Implementation of core cognitive functions:
- **Consolidation (`dream.py`)**: Clustering and summarization for memory synthesis.
- **Truth Maintenance (`tms.py`)**: Detects and resolves conflicting information.
- **Importance (`importance.py`)**: Heuristic scoring for memory prioritization.
- **Security (`secrets.py`)**: Automated sensitivity detection.

### 4. Engine Layer
Based in `omem/core/engine/`. Manages memory lifecycle and state:
- **Ingestion Pipeline (`add.py`)**: Validates, embeds, classifies, and indexes raw data.
- **Context Retrieval (`rag.py`)**: Executes complex, multi-signal retrieval strategies.
- **State Management (`lifecycle.py`)**: Handles archiving, pruning, and snapshotting.

---

## Programmatic Usage (How to use the "bits")

If you are building an AI application, you will interact primarily with the `OMem` class in Python.

### Initialization & Backends

OMem supports multiple storage backends depending on your deployment needs.

```python
from omem import OMem

# 1. Local SQLite (Default, best for most single-machine agents)
# Automatically creates ~/.omem/brain.db
brain = OMem()

# 2. In-Memory (Best for unit tests or highly ephemeral tasks)
test_brain = OMem(backend="memory")

# 3. PostgreSQL (Best for production, distributed multi-agent systems)
pg_brain = OMem(
    backend="postgres",
    db_path="postgresql://user:pass@localhost:5432/omem"
)
```

### Adding Memories (Types & Importance)

OMem automatically classifies what you input, but you can explicitly define importance and type to control how the agent remembers it.

```python
from omem.types import MemoryType

# Automatic (OMem detects this is a 'DECISION' and boosts importance based on keywords)
brain.add("We decided to migrate from REST to GraphQL due to over-fetching.")

# Explicit Control
brain.add(
    "Critical API key rotation policy: Must rotate every 30 days.",
    importance=0.95,                  # 0.0 to 1.0 (forces it to stay in memory longer)
    mem_type=MemoryType.DECISION      # Explicitly categorize the memory
)

# Procedural Tool Snippets (For MCP / Agent tool calling)
brain.add(
    "To deploy, run 'aws ecs update-service --cluster prod'",
    mem_type=MemoryType.PROCEDURAL
)
```

### Recalling Memories (Hybrid RAG)

Retrieval in OMem is not just vector search. It uses 4 signals (Vector + Keyword + Recency + Importance). 

```python
# Standard recall (Returns top 5 matches as a combined string)
context = brain.recall("What is our API rotation policy?")

# Advanced Recall (Returns raw Memory objects for custom formatting)
raw_memories = brain.recall(
    "deployment steps",
    k=3,                          # Limit to 3 results
    context_type="PROCEDURAL",    # Only look for procedural memories
    time_range="recent"           # Only look at recent memories
)

for mem in raw_memories:
    print(f"[{mem.type}] {mem.content} (Score: {mem.score})")
```

**Debugging Retrieval**: If you want to see *why* OMem picked a memory, use `inspect()`:
```python
for result in brain.inspect("GraphQL"):
    print(result.explain())
    # Output: vector=0.88, keyword=0.45, recency=0.99, importance=1.2x boost -> Final: 0.92
```

### Memory Maintenance (Sleep & TMS)

Agents, like humans, need to sleep to consolidate memories and remove garbage.

```python
# Run the full sleep cycle:
# 1. Deduplicates repetitive memories
# 2. Forgets low-importance, old memories
# 3. Reflects on recent events to create high-level insights
stats = brain.sleep()
print(f"Forgotten: {stats['forgotten']}, Consolidated: {stats['consolidated']}")

# Truth Maintenance System (TMS) - Resolving Conflicts
brain.add("Python version is 3.9")
brain.add("Python version is 3.11") # OMem detects this conflicts with 3.9

# Explicitly resolve the conflict (archives 3.9, keeps 3.11)
brain.resolve_conflict("Python version")
```

### Graph-RAG Explained

When you `add()` a memory, OMem runs a fast NER (Named Entity Recognition) pass to extract entities (e.g., "Python", "GraphQL", "AWS") and builds a graph edge between them.

During `recall()`, if `graph_boost=True` (which is default), OMem will:
1. Find the top vector matches.
2. Look at the entities in those matches.
3. Traverse the graph to find *connected* memories that might not share the exact semantic meaning but are highly relevant structurally.
4. Inject them into the result set.

### Agent Integrations (MCP & LangChain)

**Model Context Protocol (MCP)**
To expose OMem natively to Claude Desktop or Cursor, simply run the server:
```python
from omem.integrations.mcp_server import serve_mcp
serve_mcp() # Or use CLI: omem serve
```

**LangChain Wrapper**
```python
from omem.integrations.langchain import OMemRetriever
retriever = OMemRetriever(omem_instance=brain)
# Pass retriever to your LangChain agents
```

---

## Contributor Guide

We welcome contributions! OMem is built to be fast, typed, and fully tested. See [CONTRIBUTING.md](./CONTRIBUTING.md) for the full guide including a Python-only setup path that requires no Rust.

### Environment Setup

> **You do NOT need Rust to contribute.** Rust is only required for SIMD/performance work in the `rust/` directory. See [CONTRIBUTING.md](./CONTRIBUTING.md) for the Python-only setup path.

1. **Clone & Virtual Env**:
   ```bash
   git clone https://github.com/mohitkumarrajbadi/omem
   cd omem
   python3 -m venv .venv
   source .venv/bin/activate
   ```
2. **Install with Dev Dependencies & Rust Extensions**:
   ```bash
   # Note: Rust is only needed for SIMD acceleration.
   # For Python-only contribution: pip install -e ".[dev]"
   # For full setup with Rust: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   SETUPTOOLS_USE_DISTUTILS=stdlib pip install -e ".[dev]"
   ```
3. **Verify**:
   ```bash
   pytest tests/ -v
   ```

> **macOS / Anaconda users:** If you experience FAISS/OpenMP crashes, add this to your environment:
> `export KMP_DUPLICATE_LIB_OK=TRUE`
> To speed up local runs without network checks: `export HF_HUB_OFFLINE=1`

### Branching & PR Workflow

1. **`dev` (Default)**: All active development happens here. PRs target `dev`.
2. **`staging`**: Pre-release integration testing.
3. **`main`/`prod`**: Stable releases (`1.0.0`, etc.). Current line is pre-alpha (`0.0.x`).

**To contribute:**
1. Checkout `dev`: `git checkout dev`
2. Create feature branch: `git checkout -b feat/my-new-feature`
3. Commit your changes.
4. Open a Pull Request targeting the `dev` branch.

### Testing Standard

- **Coverage**: All new core logic in `omem/core/` must have unit tests.
- **Location**: Place tests in the `tests/` directory matching the module structure (e.g., `tests/test_tms.py`).
- **Command**: Run `pytest tests/` before submitting a PR.
- **No API Calls**: Tests should mock LLM or external API calls to remain fast and deterministic.

### Benchmarking

Because OMem competes directly with vector DBs on speed, performance regressions are strictly monitored.
If you modify the `rust/` core, `omem/core/retrieval/`, or `omem/core/engine/add.py`, you **must** run the benchmark:

```bash
python benchmarks/competitor.py
# Or using the CLI:
omem benchmark --n 10000
```
Ensure that `add()` operations remain under `5ms` and `RAG` latency remains under `30ms`.

### Code Style & Linting

- **Typing**: Strict type hinting is enforced (`def add(text: str, importance: float = 0.5) -> str:`).
- **Format**: We use standard Python formatting. In the future, we will enforce `ruff`.
- **Comments**: Explain *why* complex heuristic logic exists, especially in the `brain/` directory.

### Adding New Backends

To add a new storage backend (e.g., Redis, MongoDB):
1. Create `omem/backends/redis.py`.
2. Inherit from `omem.backends.base.StorageBackend`.
3. Implement the required interface (`save`, `load`, `delete`, `query`).
4. Register the backend in `omem/api.py` inside the `_initialize_backend()` factory.

---

## CLI Reference

The `omem` CLI is the primary interface for managing the memory system. Install it with `pip install omem-os`.

### Setup
| Command | Description |
|---|---|
| `omem init` | Initialize memory system at `~/.omem/brain.db` |
| `omem init --db-path ./custom.db` | Use a custom database path |
| `omem health` | Health check — exits `0` if OK, `1` if error |

### Writing & Reading
```bash
omem add "content" -i 0.9 -n myproject -t DECISION
omem search "query" -k 10 -n myproject -c architecture -t recent
omem list -n myproject -l 50
omem inspect "query" # Debug retrieval scoring
```

### Maintenance & Integrations
```bash
omem maintain              # full cycle: compress + reflect + forget + dream
omem export -f json -o dump.json
omem load dump.json
omem serve                 # start MCP stdio server
omem dashboard             # launch web memory dashboard (port 7900)
```

---

## Memory Layer FAQ — Does It Bloat Context?

A common concern when connecting OMem to AI agents is:
> *"Won't injecting memory into every prompt increase context size and add latency?"*

**No. OMem is a retrieval layer, not an injection layer.** 

### ❌ What people assume (wrong)
```
Every agent turn → dump ALL stored memories into context
256 memories × ~100 tokens = 25,600 tokens injected every request
→ Blown context window + high cost + slow responses
```

### ✅ What actually happens
```
Every agent turn → semantic search returns only TOP 3–5 relevant memories
256 memories stored, ~5 retrieved → ~200–500 tokens injected
→ Lean, precise, always relevant context
```

### Direct comparison
| | Without OMem | With OMem |
|---|---|---|
| Context per turn | Full conversation history (grows unboundedly) | 3–5 recalled memories (~300 tokens) |
| Cross-session memory | ❌ Starts from zero each session | ✅ Persistent across sessions, projects, restarts |
| Token cost | High — re-reads everything | Low — retrieves only what's relevant |
| Latency added | 0ms (no memory) | <1ms (FAISS search) + ~10ms (embedding) |

**Connecting OMem to an agent makes it smarter with *less* context, not slower with more.**
