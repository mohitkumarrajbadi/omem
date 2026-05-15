"""Pluggable storage backends for OMem."""

from .sqlite import SQLiteBackend

# PostgresBackend is imported lazily; psycopg2 is an optional dependency.
# Use: from omem.backends.postgres import PostgresBackend
# Or install the extra: pip install omem-os[postgres]
try:
    from .postgres import PostgresBackend
except ImportError:
    PostgresBackend = None  # type: ignore[assignment,misc]

__all__ = ["SQLiteBackend", "PostgresBackend"]
