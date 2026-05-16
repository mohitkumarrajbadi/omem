# Changelog

All notable changes to OMem will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-05-16

### Stable

This release marks the first publicly stable version of OMem. The core API is locked for the v0.1.x series.

#### Core API (stable)
- `OMem.add()` — embedding, auto-classification, dedup, entity-graph sync, async persist
- `OMem.recall()` — hybrid RAG (vector + keyword + recency + importance) with Graph-RAG expansion
- `OMem.sleep()` — full maintenance cycle: compress, forget, reflect, dream
- `OMem.inspect()` — per-memory score breakdown for retrieval debugging
- `OMem.reflect()` — generate REFLECTION-type insights from episodic memories
- `OMem.resolve_conflict()` — TMS conflict detection and resolution
- `OMem.entities()` — knowledge graph entity listing
- `OMem.stats()` — memory system statistics

#### SQLite backend (stable)
- Handles 100 000+ memories; thread-safe WAL mode; zero configuration

#### PostgreSQL backend (beta)
- Multi-process / distributed deployments; connection-string config

#### MCP server (stable)
- `omem serve` — stdio MCP server for Claude Desktop and Cursor IDE
- Full tool set: `remember`, `recall`, `reflect`, `maintain`, `resolve_conflict`,
  `remember_action`, `recall_action`, `query_codebase`, `sync_codebase`, `ingest_codebase`
- Full resource set: `omem://recent`, `omem://top_insights`, `omem://status`, `omem://graph`

#### Tooling
- CLI (`omem health`, `omem demo`, `omem dashboard`, `omem benchmark`, …)
- Web dashboard (`omem dashboard`) with memory table and knowledge-graph visualization
- Published on PyPI as `omem-os`

[0.1.0]: https://github.com/mohitkumarrajbadi/omem/releases/tag/v0.1.0

---

## [0.8.0] - 2026-04-11

### Added
- Comprehensive test script for full functionality validation
- Context-type filtering in recall function (architecture, bugs, decisions, etc.)
- Time-range filtering in recall function (today, recent, last_week)
- Memory lifecycle maintenance system
- Truth maintenance system for conflict detection and resolution
- Enhanced memory metadata with quality-based retrieval filtering
- MCP server integration for Claude Desktop
- Rust-powered SIMD operations for vector similarity
- Hybrid scoring (vector + keyword + recency + importance)
- Memory consolidation via dream cycles
- Namespace isolation for multi-agent systems
- Secret detection to prevent credential leakage
- Knowledge graph support with entity linking
- Export and visualization tools

### Changed
- Improved README with centered layout and better documentation
- Updated import paths for cleaner API surface
- Enhanced retrieval scoring with quality metrics
- Optimized performance for sub-millisecond retrieval
- Refactored project structure for better modularity

### Fixed
- Memory lifecycle error handling
- Thread safety improvements in concurrent operations
- Import path inconsistencies

## [0.7.0] - 2026-03-15

### Added
- Rust core implementation for performance
- Benchmarking suite for latency and throughput testing
- Example applications (memory assistant, demo scripts)

### Changed
- Renamed project from memx-ai to omem-os
- Major v2 cognitive architecture upgrade

## [0.1.0] - 2026-02-01

### Added
- Initial release
- Basic memory add, recall, and delete operations
- SQLite backend for persistence
- Sentence-transformer embeddings
- FAISS vector indexing

[0.8.0]: https://github.com/mohitkumarrajbadi/omem/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/mohitkumarrajbadi/omem/compare/v0.1.0...v0.7.0
[0.1.0]: https://github.com/mohitkumarrajbadi/omem/releases/tag/v0.1.0
