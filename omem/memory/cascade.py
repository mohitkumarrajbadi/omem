"""Focus → bridge → widen recall cascade.

Default mode keeps project isolation efficient: query the active namespace,
merge bridge (``personal`` / ``global``), and only widen to other namespaces
when focus+bridge is weak. Every returned memory keeps its ``namespace`` label.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Set

from ..namespace_resolve import (
    BRIDGE_NAMESPACES,
    active_namespace,
    is_bridge_namespace,
)
from ..types import Memory

# Widen only when focus+bridge has no usable hits (avoid cross-project pollution).
_WEAK_SCORE_FLOOR = 0.15
_WIDEN_CAP = 2

ScopeMode = str  # "focus" | "strict" | "all"


def _mem_score(mem: Memory) -> float:
    score = getattr(mem, "score", None)
    if score is not None:
        try:
            return float(score)
        except (TypeError, ValueError):
            pass
    return float(getattr(mem, "importance", 0.0) or 0.0)


def _dedupe_merge(*groups: Sequence[Memory]) -> List[Memory]:
    seen: Set[str] = set()
    out: List[Memory] = []
    for group in groups:
        for mem in group:
            mid = getattr(mem, "id", None) or id(mem)
            if mid in seen:
                continue
            seen.add(mid)
            out.append(mem)
    out.sort(key=_mem_score, reverse=True)
    return out


def _is_weak(results: Sequence[Memory], k: int) -> bool:
    """True only when focus+bridge produced nothing useful.

    A single on-namespace hit is enough to skip widen — otherwise high-importance
    memories from unrelated projects leak into context.
    """
    del k  # reserved for future soft thresholds
    if not results:
        return True
    return _mem_score(results[0]) < _WEAK_SCORE_FLOOR


def _lexical_ns(omem: Any, query: str, namespace: str, k: int) -> List[Memory]:
    """Fallback when the local hash embedder returns nothing useful."""
    needle = (query or "").lower().strip()
    if not needle or not hasattr(omem, "all"):
        return []
    tokens = [tok for tok in needle.split() if len(tok) > 3]
    scored: List[Memory] = []
    for mem in omem.all(namespace=namespace):
        hay = (mem.content or "").lower()
        if needle in hay or any(tok in hay for tok in tokens):
            scored.append(mem)
    scored.sort(key=_mem_score, reverse=True)
    return scored[:k]


def _recall_ns(
    omem: Any,
    query: str,
    namespace: str,
    *,
    k: int,
    context_type: Optional[str],
    mode: Optional[str],
    time_range: Optional[str],
    level: Optional[str],
    include_archive: bool,
) -> List[Memory]:
    hits = [
        m
        for m in omem.recall(
            query,
            k=k,
            namespace=namespace,
            context_type=context_type,
            mode=mode,
            time_range=time_range,
            level=level,
            include_archive=include_archive,
            project_only=True,
        )
        if getattr(m, "namespace", None) == namespace
    ]
    if hits:
        return hits
    return _lexical_ns(omem, query, namespace, k)


def cascade_recall(
    omem: Any,
    query: str,
    *,
    k: int = 5,
    namespace: Optional[str] = None,
    scope_mode: ScopeMode = "focus",
    context_type: Optional[str] = None,
    mode: Optional[str] = None,
    time_range: Optional[str] = None,
    level: Optional[str] = None,
    include_archive: bool = False,
) -> Dict[str, Any]:
    """Run scoped recall and return memories plus cascade stats.

    Returns:
        ``{"memories": [...], "stats": {...}}``
    """
    active = (namespace or "").strip() or active_namespace()
    mode_norm = (scope_mode or "focus").strip().lower()
    if mode_norm not in ("focus", "strict", "all"):
        mode_norm = "focus"

    stats: Dict[str, Any] = {
        "active_namespace": active,
        "mode": mode_norm,
        "widened": False,
        "bridge_namespaces": list(BRIDGE_NAMESPACES),
    }

    if mode_norm == "all":
        # Wide search then label — use project_only=False / namespace=None path.
        raw = list(
            omem.recall(
                query,
                k=max(k * 3, k),
                namespace=None,
                context_type=context_type,
                mode=mode,
                time_range=time_range,
                level=level,
                include_archive=include_archive,
                project_only=False,
            )
        )
        # If backend ignored namespace=None, fall back to per-ns.
        if not raw and hasattr(omem, "namespaces"):
            chunks: List[Memory] = []
            for ns in omem.namespaces() or []:
                chunks.extend(
                    _recall_ns(
                        omem,
                        query,
                        ns,
                        k=k,
                        context_type=context_type,
                        mode=mode,
                        time_range=time_range,
                        level=level,
                        include_archive=include_archive,
                    )
                )
            raw = _dedupe_merge(chunks)
        memories = _dedupe_merge(raw)[:k]
        stats["widened"] = True
        return {"memories": memories, "stats": stats}

    focus_hits = _recall_ns(
        omem,
        query,
        active,
        k=k,
        context_type=context_type,
        mode=mode,
        time_range=time_range,
        level=level,
        include_archive=include_archive,
    )

    if mode_norm == "strict":
        return {"memories": focus_hits[:k], "stats": stats}

    bridge_hits: List[Memory] = []
    for bridge_ns in BRIDGE_NAMESPACES:
        if bridge_ns == active:
            continue
        bridge_hits.extend(
            _recall_ns(
                omem,
                query,
                bridge_ns,
                k=k,
                context_type=context_type,
                mode=mode,
                time_range=time_range,
                level=level,
                include_archive=include_archive,
            )
        )

    merged = _dedupe_merge(focus_hits, bridge_hits)

    if not _is_weak(merged, k):
        return {"memories": merged[:k], "stats": stats}

    # Widen: other project namespaces only, capped.
    other_ns: List[str] = []
    if hasattr(omem, "namespaces"):
        for ns in omem.namespaces() or []:
            if ns == active or is_bridge_namespace(ns):
                continue
            other_ns.append(ns)

    widen_hits: List[Memory] = []
    for ns in other_ns:
        widen_hits.extend(
            _recall_ns(
                omem,
                query,
                ns,
                k=_WIDEN_CAP,
                context_type=context_type,
                mode=mode,
                time_range=time_range,
                level=level,
                include_archive=include_archive,
            )
        )

    widen_hits = _dedupe_merge(widen_hits)[:_WIDEN_CAP]
    if widen_hits:
        stats["widened"] = True
        stats["widen_namespaces"] = sorted({m.namespace for m in widen_hits})
        merged = _dedupe_merge(merged, widen_hits)

    return {"memories": merged[:k], "stats": stats}


__all__ = ["cascade_recall", "ScopeMode"]
