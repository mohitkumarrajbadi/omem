"""Postgres RLS session variables — transaction-scoped via SET LOCAL.

Request handlers set context via ``set_request_pg_context()`` (from cloud middleware).
Background writers (write_buffer flush thread) derive namespace from each Memory row.
"""

from __future__ import annotations

import contextvars
import os
from dataclasses import dataclass
from typing import Optional

_REQUEST_CTX: contextvars.ContextVar[Optional["PgSessionContext"]] = contextvars.ContextVar(
    "omem_pg_session", default=None
)


@dataclass(frozen=True)
class PgSessionContext:
    namespace: str
    org_id: str = ""
    user_id: str = ""


def set_request_pg_context(
    *,
    namespace: str,
    org_id: str = "",
    user_id: str = "",
) -> None:
    """Bind tenant context for the current async request / thread."""
    _REQUEST_CTX.set(
        PgSessionContext(
            namespace=namespace or "default",
            org_id=org_id or "",
            user_id=user_id or "",
        )
    )


def clear_request_pg_context() -> None:
    _REQUEST_CTX.set(None)


def _default_org_id() -> str:
    return os.getenv("OMEM_ORG_ID", "")


def _default_user_id() -> str:
    return os.getenv("OMEM_USER_ID", "")


def resolve_pg_session(*, fallback_namespace: str = "default") -> PgSessionContext:
    """Session for reads — prefer request context, else explicit fallback."""
    ctx = _REQUEST_CTX.get()
    if ctx is not None:
        return ctx
    return PgSessionContext(
        namespace=fallback_namespace or "default",
        org_id=_default_org_id(),
        user_id=_default_user_id(),
    )


def resolve_pg_session_for_write(memory) -> PgSessionContext:
    """Session for writes — memory.namespace wins (safe for write_buffer thread)."""
    req = _REQUEST_CTX.get()
    ns = getattr(memory, "namespace", None) or (req.namespace if req else "default")
    org_id = req.org_id if req else _default_org_id()
    user_id = req.user_id if req else _default_user_id()
    return PgSessionContext(namespace=ns or "default", org_id=org_id, user_id=user_id)


def apply_pg_session(cur, session: PgSessionContext) -> None:
    """SET LOCAL — transaction-scoped; safe with connection pooling."""
    cur.execute("SET LOCAL app.current_namespace = %s", (session.namespace,))
    cur.execute("SET LOCAL omem.org_id = %s", (session.org_id,))
    cur.execute("SET LOCAL omem.user_id = %s", (session.user_id,))
