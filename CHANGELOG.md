# Changelog

All notable changes to OMem will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Version note:** the latest published release is **0.0.1 on PyPI** and
> **v0.0.2 on GitHub**. Everything under *Unreleased* below — including the
> architecture work previously labeled "v3.0" internally — has **not** been
> released. The next release will be **0.0.3**.

## [Unreleased] — targeting 0.0.3

This section consolidates the internal "v2"/"v3.0" architecture milestones
(June 2026). These version labels were used in commit messages and design docs
but were never published to PyPI or tagged on GitHub; they ship for the first
time in the next release.

### Added

- **Six-layer product architecture** — `memory`, `state`, `context`, `knowledge`, `observe`, `governance`
- **`AgentState`** — unified product facade composing all layers
- Cross-cutting packages: `provenance`, `runtime`
- Layer extensions: `memory/org/`, `knowledge/codebase/`, `observe/dashboard/`
- Governance modules consolidated: `governance/audit.py`, `governance/encryption.py`
- Memory OS charter work: BM25 fusion, per-type retrieval strategies, lifecycle
  FSM, L0–L4 hierarchy conveyor, batch ingest pipeline, cold archive spill,
  tenant namespace hardening
- Architecture docs: `docs/architecture/ARCHITECTURE.md`, ADR-002, ADR-003
- Eval harness relocated to `benchmarks/eval/`

### Changed

- **Breaking:** Removed v2 compatibility shims — update imports before upgrading:
  - `omem.org` → `omem.memory.org`
  - `omem.security` → `omem.governance`
  - `omem.codebase` → `omem.knowledge.codebase`
  - `omem.viz` → `omem.observe.dashboard`
  - `omem.classify` → `omem.core.brain.classify`
- Docker: root `Dockerfile` / `docker-compose.yml` removed; use `deploy/docker/`
- Design notes moved from `issues/` to `docs/ideas/`

### Removed

- `omem/org/`, `omem/security/`, `omem/codebase/`, `omem/viz/` packages (directories deleted)
- Legacy imports now raise `ImportError` with migration hints via guard modules (`org.py`, `security.py`, …)
- `omem/eval/` (use `benchmarks/eval/` for dev benchmarks)
- Commercial cloud layer (`omem/cloud/`) detached from the open-source package;
  it now lives in the separate `omem-cloud` repository

---

## [0.0.2] - 2026-05-23

GitHub release only (tag `v0.0.2`); not published to PyPI.

### Fixed

- Python 3.13 wheel compilation via PyO3 forward-compatibility flag
- `setuptools-rust` added to `build-system.requires` (fixes cibuildwheel)
- Seamless `pip install`: auto-configured env vars, `mcp` included in core deps
- Deterministic audit-log tests; ruff lint cleanup

### Changed

- Standardized and alphabetized module imports across the codebase
- Test suite overhauled for correctness and coverage

[0.0.2]: https://github.com/mohitkumarrajbadi/omem/releases/tag/v0.0.2

---

## [0.0.1] - 2026-05-06

First public release on PyPI (`pip install omem-os`). Pre-alpha.

### Added

- `OMem.add()` — embedding, auto-classification, dedup, entity-graph sync, async persist
- `OMem.recall()` — hybrid RAG (vector + keyword + recency + importance) with Graph-RAG expansion
- `OMem.sleep()` — maintenance cycle: compress, forget, reflect, dream
- `OMem.inspect()` — per-memory score breakdown for retrieval debugging
- `OMem.reflect()`, `OMem.resolve_conflict()` (TMS), `OMem.entities()`, `OMem.stats()`
- SQLite backend (thread-safe WAL mode, zero configuration); PostgreSQL backend (beta)
- MCP server (`omem serve`) for Claude Desktop and Cursor
- CLI, web dashboard, Rust-accelerated scoring (PyO3 + Rayon)

[0.0.1]: https://pypi.org/project/omem-os/0.0.1/

---

## [1.0.0] - 2026-04-25 [YANKED]

Published to PyPI with an incorrect version number and yanked shortly after
(yank reason: "incorrect version, use 0.0.1"). No code from this upload is
current; it predates the 0.0.1 release. Listed here so the version history
has no silent gaps.

---

## Pre-release history (never published)

Earlier drafts of this changelog listed `0.1.0`, `0.7.0`, and `0.8.0`
milestones (February–May 2026, partly under the project's previous name,
`memx-ai`). Those version numbers were internal development milestones only —
none were tagged on GitHub or published to PyPI. Their features (Rust core,
hybrid scoring, MCP integration, truth maintenance, knowledge graph, namespace
isolation) shipped publicly in 0.0.1 and 0.0.2 above.
