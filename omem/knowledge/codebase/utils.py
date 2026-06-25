"""Utility helpers for the Project Memory layer.
* hash_file_content – SHA‑256 of a string (used for content_hash)
* stable_symbol_id – builds a hierarchical ID from the current namespace stack.
* file_relative_module – converts a file path to a dotted module name.
* is_python_file – quick extension check.
"""
import hashlib
import os
from typing import List


def hash_text(text: str) -> str:
    """Return SHA‑256 hex digest of *text*.
    Used for stable content hashing of a code snippet.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def file_to_module(root_dir: str, file_path: str) -> str:
    """Convert an absolute *file_path* to a dotted module name relative to *root_dir*.
    Example: ``/proj/src/auth/jwt.py`` → ``auth.jwt`` (assuming ``root_dir`` is ``/proj/src``).
    """
    rel_path = os.path.relpath(file_path, root_dir)
    if rel_path.endswith('.py'):
        rel_path = rel_path[:-3]
    return rel_path.replace(os.sep, '.')

def is_python_file(path: str) -> bool:
    return path.lower().endswith('.py')

def normalize_path(p: str) -> str:
    """Return an absolute, normalized path (resolve symlinks, remove trailing slashes)."""
    return os.path.abspath(os.path.realpath(p))

def default_ignore_dirs() -> List[str]:
    return {'.git', '.venv', 'venv', '__pycache__', 'node_modules', 'build', 'dist'}
