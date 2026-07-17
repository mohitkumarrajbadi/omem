"""Multi-tenant hierarchy: organization → workspace → agent → user.

Hard isolation units. Cloud API should bind tenants from server-side key
claims — never trust client-supplied org/workspace headers alone.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class TenantScope:
    """Canonical tenant coordinates for memory + state isolation."""

    org_id: str
    workspace_id: str = "default"
    agent_id: str = "default"
    user_id: str = "default"

    def namespace(self) -> str:
        """Stable namespace path used by OMem engines."""
        return f"{self.org_id}/{self.workspace_id}/{self.agent_id}/{self.user_id}"

    def org_namespace(self) -> str:
        return self.org_id

    def workspace_namespace(self) -> str:
        return f"{self.org_id}/{self.workspace_id}"

    def as_dict(self) -> Dict[str, str]:
        return {
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
            "agent_id": self.agent_id,
            "user_id": self.user_id,
            "namespace": self.namespace(),
        }


@dataclass
class TenantBinding:
    """Server-side binding attached after API key verification."""

    scope: TenantScope
    role: str = "writer"
    key_id: str = ""
    claims: Dict[str, Any] = field(default_factory=dict)


def resolve_tenant_from_binding(
    *,
    org_id: str,
    workspace_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    user_id: Optional[str] = None,
    role: str = "writer",
    key_id: str = "",
) -> TenantBinding:
    """Build a binding from verified server-side claims only."""
    if not org_id or not str(org_id).strip():
        raise ValueError("org_id is required for tenant isolation")
    scope = TenantScope(
        org_id=str(org_id).strip(),
        workspace_id=(workspace_id or "default").strip() or "default",
        agent_id=(agent_id or "default").strip() or "default",
        user_id=(user_id or "default").strip() or "default",
    )
    return TenantBinding(scope=scope, role=role, key_id=key_id)


def assert_same_org(a: TenantScope, b: TenantScope) -> None:
    if not hmac.compare_digest(a.org_id, b.org_id):
        raise PermissionError("cross-org tenant access denied")


def namespaces_isolated(a: TenantScope, b: TenantScope) -> bool:
    """True when scopes must not share memory (different org or workspace)."""
    return a.org_id != b.org_id or a.workspace_id != b.workspace_id


def harden_namespace(
    client_namespace: Optional[str],
    binding: TenantBinding,
    *,
    trust_client_suffix: bool = False,
) -> str:
    """Return the authoritative namespace.

    By default the client namespace is ignored for the org/workspace prefix.
    If ``trust_client_suffix`` is True, a relative agent/user suffix may be
    appended under the binding's workspace (still never overrides org).
    """
    base = binding.scope.workspace_namespace()
    if not trust_client_suffix or not client_namespace:
        return binding.scope.namespace()
    # Allow only a suffix under the binding workspace
    suffix = client_namespace.strip().lstrip("/")
    if suffix.startswith(binding.scope.org_id):
        # Client tried to set full path — force binding namespace
        return binding.scope.namespace()
    return f"{base}/{suffix}"
