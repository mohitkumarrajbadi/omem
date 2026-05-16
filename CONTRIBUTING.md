# Contributing to OMem

Thank you for your interest in contributing. This document covers everything you need to get started.

---

## Two Contributor Paths

Choose the path that fits your goal:

### Path A — Python only (no Rust required)

Everything in `omem/`, `tests/`, `examples/`, `benchmarks/`, and docs. This covers the vast majority of contributions.

Setup in three commands:

```bash
git clone https://github.com/mohitkumarrajbadi/omem
cd omem
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```

Done. All 133 tests should pass.

---

### Path B — Full setup with Rust

Required only if you are modifying `rust/` (SIMD scoring, FAISS bindings, the `omem_rust` native extension).

```bash
# Install Rust toolchain
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source ~/.cargo/env

# Clone and install
git clone https://github.com/mohitkumarrajbadi/omem
cd omem
python3 -m venv .venv && source .venv/bin/activate
SETUPTOOLS_USE_DISTUTILS=stdlib pip install -e ".[dev]"
pytest tests/ -v
```

---

## Branch Workflow

| Branch | Purpose |
|---|---|
| `dev` | All active development. PRs target `dev`. |
| `staging` | Pre-release integration testing. |
| `main` | Stable releases only. |

**Workflow:**

```bash
git checkout dev
git pull origin dev
git checkout -b feat/your-feature-name
# ... make changes ...
git push origin feat/your-feature-name
# Open a PR targeting dev
```

---

## Testing Requirements

- All 133 tests must pass before a PR can merge: `pytest tests/ -v`
- New logic in `omem/core/` must have unit tests in `tests/` matching the module path (e.g., `tests/test_tms.py`)
- Tests must not make external API calls — mock any LLM or embedding calls
- If you modify `rust/`, `omem/core/retrieval/`, or `omem/core/engine/add.py`, run the benchmark to confirm no regression:

```bash
python benchmarks/competitor.py
```

Target thresholds: `add()` < 5 ms, RAG latency < 30 ms.

---

## Good First Issues

These are well-scoped tasks that require no deep knowledge of the codebase:

| Issue | Label | What to do |
|---|---|---|
| Add `omem export --format csv` | `good first issue` | Add CSV format to `omem/cli.py` export command |
| Add `--quiet` flag to CLI | `good first issue` | Suppress non-error output when `--quiet` is passed |
| Write test for `reflect()` | `good first issue` | Add `tests/test_reflect.py` with 3 scenarios |
| Write test for namespace isolation | `good first issue` | Confirm memories don't leak across namespaces |
| Add `OMem.count()` method | `good first issue` | Return total active memory count for a namespace |
| Improve error message for missing DB | `good first issue` | Surface a cleaner message when `db_path` dir doesn't exist |
| Add type stub for `MemoryResult` | `good first issue` | Create `omem/py.typed` and verify mypy passes |
| Document all `OMem()` constructor args | `docs` | Add docstring examples to `omem/api.py` |

Browse open issues at: https://github.com/mohitkumarrajbadi/omem/issues

---

## Code Style

**Linting:** Run `ruff check .` before committing. CI will fail if ruff reports errors.

**Formatting:** `ruff format .`

**Type hints:** Strict throughout. Every public function must have fully-typed signatures:

```python
def recall(self, query: str, k: int = 5, context_type: Optional[str] = None) -> list[MemoryResult]:
```

**Comments:** In `omem/core/brain/`, explain *why* the heuristic exists, not just what it does. The logic is non-obvious and the reasoning matters for future changes.

**No backwards-compat shims:** If you rename a function, update all call sites. Don't add a deprecated alias.

---

## Adding a New Storage Backend

1. Create `omem/backends/<name>.py`
2. Subclass `omem.backends.base.StorageBackend`
3. Implement the required interface: `save`, `load`, `delete`, `query`
4. Register it in `omem/api.py` inside `_initialize_backend()`
5. Add tests in `tests/test_backend_<name>.py`
6. Document the new backend in `DEVELOPER.md` under "Storage Backends"

See `omem/backends/sqlite.py` as the reference implementation.

---

## Questions

Open a discussion at https://github.com/mohitkumarrajbadi/omem/discussions or file an issue. PRs targeting `main` directly will be redirected to `dev`.
