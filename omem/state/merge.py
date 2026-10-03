"""True 3-way merge for StatePayload — not winner-takes-all.

Given a common ancestor (the fork snapshot) plus two diverged sessions,
each field is merged independently. Conflicts are recorded on
``workflow_state['_omem_merge']``; the target session's value is kept.
No LLM.
"""

from __future__ import annotations

import copy
import time
from typing import Any, Dict, List, Optional, Tuple

from ..types import StatePayload, ToolResult

_CONFLICT_KEY = "_omem_merge"
_STATUS_RANK = {
    "idle": 0,
    "running": 1,
    "paused": 2,
    "failed": 3,
    "done": 4,
}


def merge_scalar(base: Any, ours: Any, theirs: Any, field: str, conflicts: List[Dict]) -> Any:
    if ours == theirs:
        return ours
    if ours == base:
        return theirs
    if theirs == base:
        return ours
    conflicts.append({"field": field, "ours": ours, "theirs": theirs, "base": base})
    return ours


def merge_plan(base: List[str], ours: List[str], theirs: List[str]) -> List[str]:
    if ours == theirs:
        return list(ours)
    if ours == base:
        return list(theirs)
    if theirs == base:
        return list(ours)
    seen = set()
    out: List[str] = []
    for step in list(ours) + list(theirs):
        if step not in seen:
            seen.add(step)
            out.append(step)
    return out


def merge_dicts(
    base: Dict[str, Any],
    ours: Dict[str, Any],
    theirs: Dict[str, Any],
    prefix: str,
    conflicts: List[Dict],
) -> Dict[str, Any]:
    keys = set(base) | set(ours) | set(theirs)
    keys.discard(_CONFLICT_KEY)
    out: Dict[str, Any] = {}
    for key in keys:
        b = base.get(key)
        o = ours.get(key)
        t = theirs.get(key)
        in_o = key in ours
        in_t = key in theirs
        in_b = key in base
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(b, dict) or isinstance(o, dict) or isinstance(t, dict):
            out[key] = merge_dicts(
                b if isinstance(b, dict) else {},
                o if isinstance(o, dict) else {},
                t if isinstance(t, dict) else {},
                path,
                conflicts,
            )
            continue
        if o == t:
            if in_o or in_t:
                out[key] = copy.deepcopy(o)
            elif in_b:
                out[key] = copy.deepcopy(b)
            continue
        if not in_o or o == b:
            if in_t:
                out[key] = copy.deepcopy(t)
            elif in_b and not in_t:
                pass  # deleted on theirs
            continue
        if not in_t or t == b:
            if in_o:
                out[key] = copy.deepcopy(o)
            continue
        conflicts.append({"field": path, "ours": o, "theirs": t, "base": b})
        if in_o:
            out[key] = copy.deepcopy(o)
    return out


def _tool_key(tr: ToolResult) -> Tuple:
    return (tr.tool, round(float(tr.timestamp), 6), str(tr.error or ""), repr(tr.output))


def merge_tools(
    base: List[ToolResult],
    ours: List[ToolResult],
    theirs: List[ToolResult],
) -> List[ToolResult]:
    seen = set()
    out: List[ToolResult] = []
    for tr in list(ours) + list(theirs):
        key = _tool_key(tr)
        if key in seen:
            continue
        seen.add(key)
        out.append(tr)
    out.sort(key=lambda t: t.timestamp)
    return out


def three_way_merge(
    base: Optional[StatePayload],
    ours: StatePayload,
    theirs: StatePayload,
    *,
    target_session_id: str,
    now: Optional[float] = None,
) -> StatePayload:
    """Merge ``theirs`` into ``ours`` against common ancestor ``base``.

    ``ours`` is the target session (the one receiving the merge).
    """
    now = now if now is not None else time.time()
    ancestor = base or StatePayload(session_id=target_session_id)
    conflicts: List[Dict[str, Any]] = []

    goal = merge_scalar(ancestor.goal, ours.goal, theirs.goal, "goal", conflicts)
    plan = merge_plan(list(ancestor.plan or []), list(ours.plan or []), list(theirs.plan or []))
    step = merge_scalar(ancestor.step, ours.step, theirs.step, "step", conflicts)
    if isinstance(step, int) and ours.step != theirs.step:
        # Progress is monotonic: take the further step when no conflict was filed
        # because one side still matches the ancestor.
        if ours.step == ancestor.step or theirs.step == ancestor.step:
            step = max(ours.step, theirs.step)
        else:
            step = max(int(ours.step), int(theirs.step))

    status = merge_scalar(ancestor.status, ours.status, theirs.status, "status", conflicts)
    if ours.status != theirs.status:
        if ours.status == ancestor.status:
            status = theirs.status
        elif theirs.status == ancestor.status:
            status = ours.status
        else:
            # Both moved: prefer the more advanced status, keep the conflict note.
            if _STATUS_RANK.get(str(theirs.status), 0) > _STATUS_RANK.get(str(ours.status), 0):
                status = theirs.status

    workflow = merge_dicts(
        dict(ancestor.workflow_state or {}),
        dict(ours.workflow_state or {}),
        dict(theirs.workflow_state or {}),
        "workflow_state",
        conflicts,
    )
    metadata = merge_dicts(
        dict(ancestor.agent_metadata or {}),
        dict(ours.agent_metadata or {}),
        dict(theirs.agent_metadata or {}),
        "agent_metadata",
        conflicts,
    )
    tools = merge_tools(
        list(ancestor.tool_outputs or []),
        list(ours.tool_outputs or []),
        list(theirs.tool_outputs or []),
    )

    if conflicts:
        workflow[_CONFLICT_KEY] = {
            "conflicts": conflicts,
            "merged_at": now,
            "source_session": theirs.session_id,
            "target_session": target_session_id,
        }

    return StatePayload(
        session_id=target_session_id,
        goal=goal,
        plan=plan,
        step=int(step or 0),
        status=str(status or "idle"),
        workflow_state=workflow,
        tool_outputs=tools,
        agent_metadata=metadata,
        namespace=ours.namespace or ancestor.namespace,
        updated_at=now,
        version=max(ours.version, theirs.version) + 1,
    )
