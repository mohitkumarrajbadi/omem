# Changelog

All notable changes to OMem will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
