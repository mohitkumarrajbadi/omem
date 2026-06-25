# Contributing to OMem

Thank you for your interest in contributing. This document covers everything you need to get started.

---

## Start Here

OMem is moving toward v2 as AI state infrastructure. Before starting larger work, read:

- [docs/architecture/ARCHITECTURE.md](./docs/architecture/ARCHITECTURE.md) for the canonical layout
- [docs/architecture/PROJECT_STRUCTURE.md](./docs/architecture/PROJECT_STRUCTURE.md) for the contributor map
- [docs/roadmap/ROADMAP.md](./docs/roadmap/ROADMAP.md) for roadmap lanes
- [GOVERNANCE.md](./GOVERNANCE.md) for review and release standards
- [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md) for community expectations

Small docs, tests, examples, and CLI improvements are welcome without a design discussion. Public API changes, persistence changes, retrieval scoring changes, security changes, and new backends should start with an issue or discussion.

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

Done. The full test suite should pass locally.

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
| `main` | Stable OSS releases (PyPI tags). |
| `cloud` | **Akamai/Linode demo** — merge from `staging`, deploy to Linode. |

**Daily workflow:**

```bash
git checkout dev
git pull origin dev
git checkout -b feat/your-feature-name
# ... make changes ...
git push origin feat/your-feature-name
# Open a PR targeting dev
```

**Promote to live demo (`cloud` branch):**

```bash
git checkout staging && git merge dev && git push origin staging
git checkout cloud && git merge staging && git push origin cloud
./deploy/scripts/cloud-proof-deploy.sh --host "$OMEM_LINODE_IP"
```

Full playbook: [docs/guides/CLOUD_PROOF.md](./docs/guides/CLOUD_PROOF.md)

---

## V2 Contributor Lanes

| Lane | Good For | First Files |
|---|---|---|
| Memory core | Add, recall, lifecycle, scoring | `omem/core/engine/`, `omem/core/brain/` |
| Knowledge graph | Entity extraction, relations, reasoning | `omem/core/graph/`, `omem/core/brain/reasoning.py` |
| State infrastructure | Snapshots, restore, rollback, workflow state | `omem/state/` |
| Observability | Metrics, traces, replay, context savings | `omem/observe/` |
| Evaluation | Benchmarks, scenarios, quality metrics | `benchmarks/eval/`, `benchmarks/` |
| Governance | Audit, retention, deletion, RBAC | `omem/governance/` |
| Integrations | MCP, LangChain, LlamaIndex, CrewAI, agent SDKs | `omem/integrations/`, `examples/` |
| Docs and examples | Onboarding, recipes, launch materials | `README.md`, `docs/`, `examples/` |

For v2 roadmap tasks, use the `V2 roadmap task` issue template and include acceptance criteria.

---

## Testing Requirements

- The full test suite must pass before a PR can merge: `pytest tests/ -v`
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

## Pull Request Quality Bar

Every PR should answer:

- What problem does this solve?
- What files changed and why?
- How was it tested?
- Does it change public API or persisted data?
- Does it need docs, examples, or benchmark notes?

Prefer smaller PRs. A focused PR is easier to review, merge, and release.

---

## Issue Templates & Labels

To make contributions production-ready, we use issue templates and labels that help maintainers prioritize, triage, and ship work faster.

### Use the right template
- Open a new issue and choose either **Bug report** or **Feature request**.
- Include a short title and provide enough context so maintainers can reproduce or evaluate the request quickly.
- For bug reports, include reproduction steps, expected behavior, actual behavior, and environment details.
- For feature requests, describe the problem, why it matters, and an example of the desired behavior.

### Issue labels
Use the labels below when filing issues or PRs; maintainers will also apply them during triage.

| Label | When to use | Example / meaning |
|---|---|---|
| `bug` | Defect, regression, crash, incorrect results | Core memory retrieval returns wrong result |
| `enhancement` | New capability, connector, integration, or UX improvement | Add LangGraph memory adapter |
| `good first issue` | Simple, easy-to-start contributions | Add CLI flag, write a small unit test |
| `documentation` | Docs, examples, usage guides, README improvements | Add integration docs for LangChain |
| `performance` | Speed, latency, benchmarking, optimization | Improve RAG throughput or memory add latency |
| `security` | Vulnerability, data safety, encryption, secrets handling | Review encryption or input sanitization |
| `testing` | Test coverage, new tests, CI improvements | Add regression tests for recall() |
| `question` | Clarification, ask for design guidance, contribution help | Ask how to extend storage backends |

### Issue title format
Use a clear prefix to make issues easier to scan:
- `[BUG]` for defects
- `[FEATURE]` for new features or integrations
- `[DOCS]` for documentation requests
- `[PERF]` for performance work

Example: `[FEATURE] add LangGraph connector for OMem memory`

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
6. Document the new backend in `docs/guides/DEVELOPER.md` under "Storage Backends"

See `omem/backends/sqlite.py` as the reference implementation.

---

## Questions

Open a discussion at https://github.com/mohitkumarrajbadi/omem/discussions or file an issue. PRs targeting `main` directly will be redirected to `dev`.
