"""GovernedMem0 — wrap Mem0 with OMem audit / provenance / erasure logging.

Install::

    pip install "omem-os[mem0]"

Usage::

    from mem0 import Memory
    from omem import AgentState
    from omem.adapters import GovernedMem0

    agent = AgentState(session_id="payments-agent", backend="memory")
    store = GovernedMem0(Memory(), agent=agent)
    store.add(
        "Wire beneficiary is acct-100",
        user_id="u1",
        provenance={"source": "verified_erp", "actor": "cfo"},
    )
    store.search("beneficiary", user_id="u1")
    print(store.export_audit())
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Union

_MISSING_MEM0 = (
    'Install omem-os[mem0] to use this adapter '
    '(pip install "omem-os[mem0]").'
)


def _require_mem0() -> None:
    try:
        import mem0  # noqa: F401
    except ImportError as exc:
        raise ImportError(_MISSING_MEM0) from exc


def _normalize_provenance(
    provenance: Optional[Dict[str, Any]],
    metadata: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Merge provenance into Mem0 metadata without inventing a Mem0 API."""
    out = dict(metadata or {})
    prov = dict(provenance or {})
    if "source" in prov and "source" not in out:
        out["source"] = prov["source"]
    if "actor" in prov and "actor" not in out:
        out["actor"] = prov["actor"]
    out.setdefault("validity_ts", prov.get("validity_ts", time.time()))
    if "sensitivity" in prov:
        out.setdefault("sensitivity", prov["sensitivity"])
    elif "sensitivity_level" in prov:
        out.setdefault("sensitivity", prov["sensitivity_level"])
    out["omem_provenance"] = prov
    return out


def _result_ids(result: Any) -> List[str]:
    if result is None:
        return []
    rows = result
    if isinstance(result, dict):
        rows = result.get("results") or result.get("memories") or []
    ids: List[str] = []
    for row in rows or []:
        if isinstance(row, dict):
            mid = row.get("id") or row.get("memory_id")
            if mid:
                ids.append(str(mid))
        elif hasattr(row, "id"):
            ids.append(str(getattr(row, "id")))
    return ids


def _audit_extras(**kwargs: Any) -> Dict[str, Any]:
    return {k: v for k, v in kwargs.items() if v is not None}


class GovernedMem0:
    """Mem0 client wrapped with OMem governance audit.

    Semantic recall stays in Mem0. Provenance, access, and erasure events
    are recorded in the OMem audit ledger attached to ``agent``.
    """

    def __init__(
        self,
        memory: Optional[Any] = None,
        *,
        agent: Optional[Any] = None,
        session_id: str = "governed-mem0",
        namespace: Optional[str] = None,
        **mem0_kwargs: Any,
    ) -> None:
        _require_mem0()
        from omem import AgentState

        if memory is None:
            from mem0 import Memory

            memory = Memory(**mem0_kwargs)
        elif mem0_kwargs:
            raise TypeError(
                "Pass either an existing Mem0 instance or initialization "
                "kwargs, not both."
            )

        self._mem0 = memory
        self._agent = agent or AgentState(
            session_id=session_id,
            backend="memory",
        )
        self._namespace = (
            namespace or getattr(self._agent, "namespace", None) or "default"
        )

    @property
    def mem0(self) -> Any:
        return self._mem0

    @property
    def agent(self) -> Any:
        return self._agent

    def _audit(
        self,
        operation: str,
        *,
        memory_id: str = "",
        source: str = "governed-mem0",
        **extra: Any,
    ) -> None:
        gov = self._agent.governance
        # Same AuditLogger instance used by export_audit / flush_audit.
        logger = getattr(gov, "_audit", None)
        if logger is None:
            return
        logger.log(
            operation,
            memory_id=memory_id,
            namespace=self._namespace,
            source=source,
            **_audit_extras(
                session_id=getattr(self._agent, "session_id", "") or "",
                **extra,
            ),
        )

    def add(
        self,
        messages: Union[str, List[Any], Dict[str, Any]],
        *,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        provenance: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        """Audit, then delegate write to Mem0."""
        meta = _normalize_provenance(provenance, metadata)
        actor = meta.get("actor") or (provenance or {}).get("actor") or "unknown"
        source = meta.get("source") or (provenance or {}).get("source") or "mem0"
        self._audit(
            "memory_write",
            source=source,
            actor=actor,
            user_id=user_id,
            sensitivity=meta.get("sensitivity"),
            validity_ts=meta.get("validity_ts"),
            content_preview=str(messages)[:160],
        )
        call: Dict[str, Any] = {"metadata": meta, **kwargs}
        if user_id is not None:
            call["user_id"] = user_id
        result = self._mem0.add(messages, **call)
        for mid in _result_ids(result):
            self._audit(
                "memory_write_ack",
                memory_id=mid,
                source=source,
                actor=actor,
                user_id=user_id,
            )
            try:
                self._agent.provenance.record(
                    entity_id=mid,
                    entity_type="memory",
                    operation="create",
                    source=source,
                    session_id=getattr(self._agent, "session_id", "") or "",
                    namespace=self._namespace,
                    actor=actor,
                    user_id=user_id,
                )
            except Exception:
                pass
        return result

    def search(
        self,
        query: str,
        *,
        user_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        """Delegate search to Mem0, then log memory_accessed for each hit."""
        call: Dict[str, Any] = dict(kwargs)
        if user_id is not None:
            call["user_id"] = user_id
        if filters is not None:
            call["filters"] = filters
        try:
            result = self._mem0.search(query, **call)
        except TypeError:
            call.pop("filters", None)
            if filters is not None:
                call["filter"] = filters
            result = self._mem0.search(query, **call)

        ids = _result_ids(result)
        self._audit(
            "memory_accessed",
            source="governed-mem0",
            user_id=user_id,
            query=query[:200],
            result_count=len(ids),
            memory_ids=ids,
        )
        for mid in ids:
            self._audit(
                "memory_accessed",
                memory_id=mid,
                source="governed-mem0",
                user_id=user_id,
                query=query[:200],
            )
        return result

    def delete(self, memory_id: str, **kwargs: Any) -> Any:
        """Log erasure, then delegate delete to Mem0."""
        self._audit(
            "memory_erasure",
            memory_id=str(memory_id),
            source="governed-mem0",
            reason="right_to_erasure",
            **_audit_extras(
                **{k: kwargs[k] for k in ("user_id", "agent_id") if k in kwargs}
            ),
        )
        try:
            self._agent.provenance.record(
                entity_id=str(memory_id),
                entity_type="memory",
                operation="erasure",
                source="governed-mem0",
                session_id=getattr(self._agent, "session_id", "") or "",
                namespace=self._namespace,
                reason="right_to_erasure",
            )
        except Exception:
            pass
        return self._mem0.delete(memory_id, **kwargs)

    def delete_all(self, **kwargs: Any) -> Any:
        """Log bulk erasure, then delegate delete_all to Mem0."""
        self._audit(
            "memory_erasure_all",
            source="governed-mem0",
            reason="right_to_erasure",
            **_audit_extras(
                **{
                    k: kwargs[k]
                    for k in ("user_id", "agent_id", "run_id")
                    if k in kwargs
                }
            ),
        )
        return self._mem0.delete_all(**kwargs)

    def export_audit(self, **kwargs: Any) -> str:
        """Dump the OMem governance audit trail (JSON by default)."""
        kwargs.setdefault("format", "json")
        return self._agent.governance.export_audit(**kwargs)
