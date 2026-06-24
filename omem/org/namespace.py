"""Namespace resolver for Phase 10 organizational memory.

Implements the namespace hierarchy from the implementation plan::

    personal/{user_id}/*              → private
    team/{team_id}/*                  → team-shared
    org/{org_id}/*                    → org-wide
    org/{org_id}/team/{team_id}/*     → team within org
    global                            → system-wide (read-only)

Scope resolution (what gets searched for a given scope):

    scope="personal"  → [personal/{user_id}]
    scope="team"      → [team/{team_id}, org/{org_id}, global]  (if ids known)
    scope="org"       → [org/{org_id}, global]
    scope="global"    → [global]
    scope="all"       → all of the above + personal
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


# ──────────────────────────────────────────────────────────────────────────────
# Data types
# ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NamespaceNode:
    """Parsed representation of a namespace string.

    Attributes:
        kind:    ``"personal"`` | ``"team"`` | ``"org"`` | ``"global"`` | ``"other"``
        user_id:  Set for ``kind="personal"``.
        team_id:  Set for ``kind="team"``.
        org_id:   Set for ``kind="org"`` or embedded org prefix.
        raw:      The original namespace string.
    """

    kind: str
    raw: str
    user_id: Optional[str] = None
    team_id: Optional[str] = None
    org_id: Optional[str] = None

    @property
    def display(self) -> str:
        return self.raw


# ──────────────────────────────────────────────────────────────────────────────
# NamespaceResolver
# ──────────────────────────────────────────────────────────────────────────────


class NamespaceResolver:
    """Resolves namespace strings into hierarchy-aware search sets.

    Usage::

        ns_list = NamespaceResolver.scoped(
            scope="team",
            user_id="alice",
            team_id="eng",
            org_id="acme",
        )
        # → ["team/eng", "org/acme", "global"]
    """

    # ------------------------------------------------------------------
    # Parse
    # ------------------------------------------------------------------

    @classmethod
    def parse(cls, namespace: str) -> NamespaceNode:
        """Parse a raw namespace string into a ``NamespaceNode``.

        Args:
            namespace: A namespace string (e.g. ``"team/eng"``).

        Returns:
            Parsed ``NamespaceNode``.
        """
        ns = namespace.strip("/")

        if ns == "global":
            return NamespaceNode(kind="global", raw=ns)

        parts = ns.split("/", 2)
        kind = parts[0]

        if kind == "personal" and len(parts) >= 2:
            return NamespaceNode(kind="personal", raw=ns, user_id=parts[1])

        if kind == "team" and len(parts) >= 2:
            return NamespaceNode(kind="team", raw=ns, team_id=parts[1])

        if kind == "org" and len(parts) >= 2:
            # org/{org_id}  or  org/{org_id}/team/{team_id}
            org_id = parts[1]
            team_id: Optional[str] = None
            if len(parts) == 3:
                sub = parts[2].split("/", 1)
                if sub[0] == "team" and len(sub) == 2:
                    team_id = sub[1]
            return NamespaceNode(
                kind="org",
                raw=ns,
                org_id=org_id,
                team_id=team_id,
            )

        return NamespaceNode(kind="other", raw=ns)

    # ------------------------------------------------------------------
    # Parents
    # ------------------------------------------------------------------

    @classmethod
    def parents(cls, namespace: str) -> List[str]:
        """Return the parent namespace chain for a given namespace.

        The list is ordered closest-parent first, ending with ``"global"``.

        Examples::

            parents("personal/alice")             → ["global"]
            parents("team/eng")                   → ["global"]
            parents("org/acme")                   → ["global"]
            parents("org/acme/team/eng")          → ["org/acme", "global"]

        Args:
            namespace: The namespace to get parents for.

        Returns:
            List of parent namespace strings, closest first.
        """
        node = cls.parse(namespace)
        result: List[str] = []

        if node.kind == "org" and node.team_id:
            result.append(f"org/{node.org_id}")

        if node.kind not in ("global",):
            result.append("global")

        return result

    # ------------------------------------------------------------------
    # Scope resolution
    # ------------------------------------------------------------------

    @classmethod
    def scoped(
        cls,
        scope: str,
        user_id: Optional[str] = None,
        team_id: Optional[str] = None,
        org_id: Optional[str] = None,
    ) -> List[str]:
        """Return the ordered list of namespaces to search for a given scope.

        The list is ordered from most-specific (highest priority) to
        least-specific. Deduplication is preserved.

        Scopes:

        - ``"personal"`` — only the user's private namespace.
        - ``"team"``     — team + org + global (if IDs are known).
        - ``"org"``      — org + global.
        - ``"global"``   — system-wide only.
        - ``"all"``      — personal + team + org + global.

        Args:
            scope:   The search scope.
            user_id: The user's ID (required for personal-scope namespaces).
            team_id: The team's ID.
            org_id:  The org's ID.

        Returns:
            Ordered, deduplicated list of namespace strings.
        """
        namespaces: List[str] = []

        def add(ns: str) -> None:
            if ns not in namespaces:
                namespaces.append(ns)

        if scope == "personal":
            if user_id:
                add(f"personal/{user_id}")

        elif scope == "team":
            if team_id:
                add(f"team/{team_id}")
            if org_id:
                add(f"org/{org_id}")
            add("global")

        elif scope == "org":
            if org_id:
                add(f"org/{org_id}")
            add("global")

        elif scope == "global":
            add("global")

        elif scope == "all":
            if user_id:
                add(f"personal/{user_id}")
            if team_id:
                add(f"team/{team_id}")
            if org_id:
                add(f"org/{org_id}")
            add("global")

        else:
            # Treat scope as a literal namespace string
            add(scope)

        return namespaces

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @classmethod
    def build(
        cls,
        kind: str,
        user_id: Optional[str] = None,
        team_id: Optional[str] = None,
        org_id: Optional[str] = None,
    ) -> str:
        """Build a canonical namespace string from parts.

        Args:
            kind:    ``"personal"`` | ``"team"`` | ``"org"`` | ``"global"``.
            user_id: Required for ``kind="personal"``.
            team_id: Required for ``kind="team"``.
            org_id:  Required for ``kind="org"``.

        Returns:
            Canonical namespace string.

        Raises:
            ValueError: If required IDs are missing.
        """
        if kind == "personal":
            if not user_id:
                raise ValueError("user_id required for personal namespace")
            return f"personal/{user_id}"
        if kind == "team":
            if not team_id:
                raise ValueError("team_id required for team namespace")
            return f"team/{team_id}"
        if kind == "org":
            if not org_id:
                raise ValueError("org_id required for org namespace")
            return f"org/{org_id}"
        if kind == "global":
            return "global"
        return kind
