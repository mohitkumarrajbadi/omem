"""Shared active-namespace resolution for CLI and MCP.

Precedence:
  1. Sticky override — ``OMEM_NS`` / ``OMEM_NAMESPACE`` / ``~/.omem/active_namespace``
  2. Git root basename under ``OMEM_PROJECT_ROOT`` or ``cwd``
  3. Basename of cwd, else ``default``

Bridge namespaces (``personal`` + legacy ``global``) hold cross-project prefs.
Namespaces are create-on-write string partitions — no separate create step.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

BRIDGE_PRIMARY = "personal"
BRIDGE_LEGACY = "global"
BRIDGE_NAMESPACES: Tuple[str, ...] = (BRIDGE_PRIMARY, BRIDGE_LEGACY)

_STICKY_FILENAME = "active_namespace"


def omem_home() -> str:
    """Return ``~/.omem``, creating it when missing."""
    home = os.path.expanduser("~/.omem")
    os.makedirs(home, mode=0o700, exist_ok=True)
    return home


def sticky_path() -> str:
    return os.path.join(omem_home(), _STICKY_FILENAME)


def bridge_namespaces() -> List[str]:
    """Logical bridge tier: user-facing ``personal`` plus legacy ``global``."""
    return list(BRIDGE_NAMESPACES)


def is_bridge_namespace(name: str) -> bool:
    return (name or "").strip() in BRIDGE_NAMESPACES


def read_sticky() -> Optional[str]:
    """Read sticky namespace from disk (``omem use``)."""
    path = sticky_path()
    try:
        with open(path, encoding="utf-8") as fh:
            value = fh.read().strip()
            return value or None
    except OSError:
        return None


def write_sticky(namespace: str) -> str:
    """Persist sticky override. Returns normalized namespace."""
    ns = (namespace or "").strip()
    if not ns:
        raise ValueError("namespace must be non-empty")
    path = sticky_path()
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(ns + "\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return ns


def clear_sticky() -> bool:
    """Remove sticky override (``omem use --auto``). Returns True if a file was removed."""
    path = sticky_path()
    try:
        os.remove(path)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def _env_sticky() -> Optional[str]:
    for key in ("OMEM_NS", "OMEM_NAMESPACE"):
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    return None


def find_git_root(start: str) -> Optional[str]:
    """Walk up from ``start`` looking for a ``.git`` directory."""
    curr = os.path.abspath(os.path.expanduser(start))
    if not os.path.isdir(curr):
        curr = os.path.dirname(curr)
    while True:
        if os.path.exists(os.path.join(curr, ".git")):
            return curr
        parent = os.path.dirname(curr)
        if parent == curr:
            return None
        curr = parent


@dataclass(frozen=True)
class NamespaceResolution:
    """Resolved active namespace plus how it was chosen."""

    namespace: str
    source: str  # env | sticky | git | cwd | default
    project_root: Optional[str] = None
    git_root: Optional[str] = None
    bypassed_bridge_pin: Optional[str] = None  # personal/global pin ignored for project work


def _resolution_start(
    project_root: Optional[str] = None,
    cwd: Optional[str] = None,
) -> str:
    root_env = (os.environ.get("OMEM_PROJECT_ROOT") or "").strip()
    if project_root:
        return os.path.abspath(os.path.expanduser(project_root))
    if root_env:
        return os.path.abspath(os.path.expanduser(root_env))
    return os.path.abspath(cwd or os.getcwd())


def _force_namespace_pin() -> bool:
    """When true, honor personal/global pins even inside a git repo."""
    return (os.environ.get("OMEM_FORCE_NAMESPACE") or "").strip() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _is_weak_pin(ns: str) -> bool:
    """Pins that should not override a real git project namespace."""
    return is_bridge_namespace(ns) or (ns or "").strip() in {"default", ""}


def resolve_active_namespace(
    project_root: Optional[str] = None,
    *,
    cwd: Optional[str] = None,
    honor_sticky_file: bool = True,
    smart_project: bool = True,
) -> NamespaceResolution:
    """Resolve the active project namespace and its source.

    Smart project mode (default): if env/sticky is only the bridge name
    ``personal`` / ``global`` but you are inside a git repo, prefer the git
    folder namespace so coding recall stays lean and project-scoped. Prefs
    still live in the bridge via ``scope=personal`` / ``--personal``.
    Set ``OMEM_FORCE_NAMESPACE=1`` to keep a bridge pin.
    """
    start = _resolution_start(project_root, cwd)
    git_root = find_git_root(start)
    bypassed: Optional[str] = None

    env_ns = _env_sticky()
    if env_ns:
        if (
            smart_project
            and not _force_namespace_pin()
            and _is_weak_pin(env_ns)
            and git_root
        ):
            bypassed = env_ns
        else:
            return NamespaceResolution(
                namespace=env_ns,
                source="env",
                project_root=start,
                git_root=git_root,
            )

    if honor_sticky_file and bypassed is None:
        file_ns = read_sticky()
        if file_ns:
            if (
                smart_project
                and not _force_namespace_pin()
                and _is_weak_pin(file_ns)
                and git_root
            ):
                bypassed = file_ns
            else:
                return NamespaceResolution(
                    namespace=file_ns,
                    source="sticky",
                    project_root=start,
                    git_root=git_root,
                )

    if git_root:
        return NamespaceResolution(
            namespace=os.path.basename(git_root) or "default",
            source="git",
            project_root=start,
            git_root=git_root,
            bypassed_bridge_pin=bypassed,
        )

    base = os.path.basename(start.rstrip(os.sep)) or "default"
    if base in (".", ""):
        base = "default"
    return NamespaceResolution(
        namespace=base,
        source="cwd" if base != "default" else "default",
        project_root=start,
        bypassed_bridge_pin=bypassed,
    )


def active_namespace(project_root: Optional[str] = None) -> str:
    """Convenience: just the namespace string."""
    return resolve_active_namespace(project_root).namespace


def normalize_scope_target(
    *,
    scope: Optional[str] = None,
    is_global: bool = False,
    explicit_namespace: Optional[str] = None,
    project_root: Optional[str] = None,
) -> str:
    """Pick write target namespace for remember.

    ``scope=personal`` / ``is_global`` → bridge primary ``personal``.
    Explicit namespace wins over scope.
    """
    if explicit_namespace and explicit_namespace.strip():
        return explicit_namespace.strip()
    scope_norm = (scope or "").strip().lower()
    if is_global or scope_norm in ("personal", "global", "bridge"):
        return BRIDGE_PRIMARY
    return active_namespace(project_root)


__all__ = [
    "BRIDGE_LEGACY",
    "BRIDGE_NAMESPACES",
    "BRIDGE_PRIMARY",
    "NamespaceResolution",
    "active_namespace",
    "bridge_namespaces",
    "clear_sticky",
    "find_git_root",
    "is_bridge_namespace",
    "normalize_scope_target",
    "omem_home",
    "read_sticky",
    "resolve_active_namespace",
    "sticky_path",
    "write_sticky",
]
