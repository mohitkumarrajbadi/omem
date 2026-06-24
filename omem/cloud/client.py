"""Remote HTTP client for OMem Cloud — Cloud Phase C1.

``OMemCloudClient`` wraps every v1 REST endpoint so the SDK can route
calls to the Akamai/Linode managed service when ``OMEM_ENDPOINT`` is set.

``CloudBackend`` implements the same ``Backend`` interface as SQLite and
Postgres, so ``AgentState`` can swap backends transparently.

Implementation target: docs/roadmap/FULL_IMPLEMENTATION_PLAN.md Cloud Phase C1.
See also: docs/roadmap/AKAMAI_LINODE_DEPLOYMENT.md
"""

import os
from typing import Any, Dict, List, Optional


class OMemCloudClient:
    """Low-level REST client for the OMem Cloud API.

    This class is a stub. All methods raise ``NotImplementedError``
    until Cloud Phase C1 is implemented.

    Environment variables (auto-read when endpoint/api_key are not passed):
        OMEM_ENDPOINT — https://state.akamai.ai
        OMEM_API_KEY  — omem_sk_...
        OMEM_ORG      — org name / ID

    Example (after Cloud Phase C1)::

        client = OMemCloudClient()   # reads env vars
        client.remember("User prefers dark mode", namespace="org/acme")
        sessions = client.state_load("agent-1")
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        org_id: Optional[str] = None,
    ) -> None:
        self.endpoint = endpoint or os.environ.get("OMEM_ENDPOINT", "")
        self.api_key = api_key or os.environ.get("OMEM_API_KEY", "")
        self.org_id = org_id or os.environ.get("OMEM_ORG", "")

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def remember(self, content: str, **kwargs: Any) -> str:
        """POST /v1/memory/remember"""
        raise NotImplementedError("Cloud Phase C1 — see FULL_IMPLEMENTATION_PLAN.md")

    def recall(self, query: str, **kwargs: Any) -> List[Dict[str, Any]]:
        """POST /v1/memory/recall"""
        raise NotImplementedError("Cloud Phase C1 — see FULL_IMPLEMENTATION_PLAN.md")

    def state_save(self, session_id: str, payload: Dict[str, Any]) -> None:
        """POST /v1/state/save"""
        raise NotImplementedError("Cloud Phase C1 — see FULL_IMPLEMENTATION_PLAN.md")

    def state_load(self, session_id: str) -> Dict[str, Any]:
        """GET /v1/state/{session_id}"""
        raise NotImplementedError("Cloud Phase C1 — see FULL_IMPLEMENTATION_PLAN.md")

    def state_snapshot(self, session_id: str, label: Optional[str] = None) -> Dict[str, Any]:
        """POST /v1/state/snapshot"""
        raise NotImplementedError("Cloud Phase C1 — see FULL_IMPLEMENTATION_PLAN.md")

    def state_rollback(self, snapshot_id: str) -> Dict[str, Any]:
        """POST /v1/state/rollback"""
        raise NotImplementedError("Cloud Phase C1 — see FULL_IMPLEMENTATION_PLAN.md")

    def state_fork(self, snapshot_id: str, new_session_id: Optional[str] = None) -> str:
        """POST /v1/state/fork"""
        raise NotImplementedError("Cloud Phase C1 — see FULL_IMPLEMENTATION_PLAN.md")

    def state_checkpoint(self, session_id: str) -> str:
        """POST /v1/state/checkpoint"""
        raise NotImplementedError("Cloud Phase C1 — see FULL_IMPLEMENTATION_PLAN.md")

    def state_resume(self, checkpoint_id: str) -> Dict[str, Any]:
        """POST /v1/state/resume"""
        raise NotImplementedError("Cloud Phase C1 — see FULL_IMPLEMENTATION_PLAN.md")

    def context_build(self, task: str, budget_tokens: int, **kwargs: Any) -> Dict[str, Any]:
        """POST /v1/context/build"""
        raise NotImplementedError("Cloud Phase C1 — see FULL_IMPLEMENTATION_PLAN.md")

    def observe_metrics(self, namespace: Optional[str] = None) -> Dict[str, Any]:
        """GET /v1/observe/metrics"""
        raise NotImplementedError("Cloud Phase C1 — see FULL_IMPLEMENTATION_PLAN.md")

    def health(self) -> Dict[str, Any]:
        """GET /v1/health"""
        raise NotImplementedError("Cloud Phase C1 — see FULL_IMPLEMENTATION_PLAN.md")
