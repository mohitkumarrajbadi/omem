"""LangGraph-compatible checkpointer and store — no LangGraph import required.

Uses StateOS for thread checkpoints and OMem recall/remember for the
long-term store. When ``langgraph`` is installed, ``OMemCheckpointSaver``
can be passed to ``graph.compile(checkpointer=...)``.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple, Union

from ..api import OMem
from ..state.layer import StateOS
from ..state.exceptions import SessionNotFoundError
from ..types import StatePayload


def _thread_id(config: Dict[str, Any]) -> str:
    conf = (config or {}).get("configurable") or config or {}
    tid = conf.get("thread_id") or conf.get("thread") or "default"
    return str(tid)


def _checkpoint_ns(config: Dict[str, Any]) -> str:
    conf = (config or {}).get("configurable") or {}
    return str(conf.get("checkpoint_ns") or "")


class OMemCheckpointSaver:
    """Persist LangGraph checkpoints in OMem StateOS.

    Checkpoints are JSON blobs on ``StatePayload.workflow_state['_lg']``.
    Works without installing langgraph (duck-typed ``put`` / ``get`` / ``list``).

    Optional ``run_os`` dual-writes durable ``checkpoint`` RunEvents when
    ``run_id`` is set (or an active run exists on the thread). This does not
    change LangGraph's drop-in ``graph.compile(checkpointer=...)`` contract.
    """

    def __init__(
        self,
        state: Optional[StateOS] = None,
        namespace: str = "default",
        run_os: Optional[Any] = None,
        run_id: Optional[str] = None,
    ) -> None:
        self._state = state or StateOS()
        self.namespace = namespace
        self._run_os = run_os
        self.run_id = run_id

    def get(self, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        tup = self.get_tuple(config)
        if tup is None:
            return None
        return tup.get("checkpoint")

    def get_tuple(self, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        thread = _thread_id(config)
        ns = _checkpoint_ns(config)
        payload = self._load(thread)
        store = (payload.workflow_state or {}).get("_lg") or {}
        bucket = store.get(ns) or {}
        latest_id = bucket.get("latest")
        wanted = ((config.get("configurable") or {}).get("checkpoint_id")) or latest_id
        if not wanted:
            return None
        blob = (bucket.get("checkpoints") or {}).get(wanted)
        if not blob:
            return None
        return {
            "config": {
                "configurable": {
                    "thread_id": thread,
                    "checkpoint_ns": ns,
                    "checkpoint_id": wanted,
                }
            },
            "checkpoint": blob.get("checkpoint"),
            "metadata": blob.get("metadata") or {},
            "parent_config": blob.get("parent_config"),
        }

    def put(
        self,
        config: Dict[str, Any],
        checkpoint: Any,
        metadata: Optional[Dict[str, Any]] = None,
        new_versions: Optional[Any] = None,
    ) -> Dict[str, Any]:
        thread = _thread_id(config)
        ns = _checkpoint_ns(config)
        payload = self._load(thread)
        store = dict(payload.workflow_state or {})
        lg = dict(store.get("_lg") or {})
        bucket = dict(lg.get(ns) or {})
        checkpoints = dict(bucket.get("checkpoints") or {})
        cid = None
        if isinstance(checkpoint, dict):
            cid = checkpoint.get("id")
        cid = cid or f"chk_{int(time.time() * 1000)}"
        parent = None
        if bucket.get("latest"):
            parent = {
                "configurable": {
                    "thread_id": thread,
                    "checkpoint_ns": ns,
                    "checkpoint_id": bucket["latest"],
                }
            }
        checkpoints[cid] = {
            "checkpoint": checkpoint,
            "metadata": metadata or {},
            "parent_config": parent,
            "saved_at": time.time(),
        }
        bucket["checkpoints"] = checkpoints
        bucket["latest"] = cid
        lg[ns] = bucket
        store["_lg"] = lg
        payload.workflow_state = store
        payload.session_id = thread
        payload.namespace = self.namespace
        self._state.save(thread, payload)
        self._emit_run_checkpoint(thread, cid)
        return {
            "configurable": {
                "thread_id": thread,
                "checkpoint_ns": ns,
                "checkpoint_id": cid,
            }
        }

    def _emit_run_checkpoint(self, thread: str, checkpoint_id: str) -> None:
        """Best-effort durable RunEvent when a RunOS is bound (OMem v1)."""
        if self._run_os is None:
            return
        rid = self.run_id
        if not rid:
            try:
                active = self._run_os.get_active_run(thread)
                rid = active.run_id if active else None
            except Exception:
                rid = None
        if not rid:
            return
        try:
            self._run_os.record_event(
                rid,
                "checkpoint",
                {
                    "checkpoint_id": checkpoint_id,
                    "source": "langgraph",
                    "thread_id": thread,
                },
                actor="system",
            )
        except Exception:
            # Never break LangGraph put path for audit dual-write failures
            pass

    def put_writes(
        self,
        config: Dict[str, Any],
        writes: Sequence[Tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Record pending writes on the latest checkpoint metadata."""
        tup = self.get_tuple(config)
        if tup is None:
            return
        meta = dict(tup.get("metadata") or {})
        pending = list(meta.get("writes") or [])
        pending.append({"task_id": task_id, "writes": list(writes), "task_path": task_path})
        meta["writes"] = pending
        ckpt = tup.get("checkpoint")
        self.put(config, ckpt, metadata=meta)

    def list(
        self,
        config: Optional[Dict[str, Any]] = None,
        *,
        filter: Optional[Dict[str, Any]] = None,
        before: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
    ) -> Iterator[Dict[str, Any]]:
        thread = _thread_id(config or {})
        ns = _checkpoint_ns(config or {})
        payload = self._load(thread)
        store = (payload.workflow_state or {}).get("_lg") or {}
        bucket = store.get(ns) or {}
        items = list((bucket.get("checkpoints") or {}).items())
        items.sort(key=lambda kv: kv[1].get("saved_at") or 0, reverse=True)
        n = 0
        for cid, blob in items:
            yield {
                "config": {
                    "configurable": {
                        "thread_id": thread,
                        "checkpoint_ns": ns,
                        "checkpoint_id": cid,
                    }
                },
                "checkpoint": blob.get("checkpoint"),
                "metadata": blob.get("metadata") or {},
                "parent_config": blob.get("parent_config"),
            }
            n += 1
            if limit is not None and n >= limit:
                break

    def _load(self, thread: str) -> StatePayload:
        try:
            existing = self._state.load(thread)
            if existing is not None:
                return existing
        except SessionNotFoundError:
            pass
        return self._state.get_or_create(thread, namespace=self.namespace)


class OMemStore:
    """LangGraph-style namespaced KV + search over OMem memories."""

    def __init__(self, omem: Optional[OMem] = None, namespace: str = "store") -> None:
        self.omem = omem or OMem(backend="memory")
        self.namespace = namespace

    def _ns(self, namespace: Union[str, Tuple[str, ...], List[str], None]) -> str:
        if namespace is None:
            return self.namespace
        if isinstance(namespace, str):
            return namespace or self.namespace
        return "/".join(str(p) for p in namespace) or self.namespace

    def put(
        self,
        namespace: Union[str, Tuple[str, ...], List[str]],
        key: str,
        value: Any,
    ) -> str:
        ns = self._ns(namespace)
        if isinstance(value, str):
            content = value
            payload = value
        else:
            payload = json.dumps(value, default=str)
            content = payload
        return self.omem.add(
            content,
            namespace=ns,
            metadata={"kind": "store", "store_key": key, "payload": payload},
            force=True,
        )

    def get(
        self,
        namespace: Union[str, Tuple[str, ...], List[str]],
        key: str,
    ) -> Optional[Any]:
        ns = self._ns(namespace)
        for mem in self.omem.all(namespace=ns):
            if (mem.metadata or {}).get("store_key") == key:
                raw = (mem.metadata or {}).get("payload", mem.content)
                try:
                    return json.loads(raw)
                except Exception:
                    return raw
        return None

    def search(
        self,
        namespace: Union[str, Tuple[str, ...], List[str]],
        query: str,
        *,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        ns = self._ns(namespace)
        hits = self.omem.recall(query, k=limit, namespace=ns, project_only=True)
        out = []
        for m in hits:
            raw = (m.metadata or {}).get("payload", m.content)
            try:
                value = json.loads(raw)
            except Exception:
                value = raw
            out.append(
                {
                    "key": (m.metadata or {}).get("store_key"),
                    "value": value,
                    "score": m.score,
                    "namespace": m.namespace,
                }
            )
        return out
