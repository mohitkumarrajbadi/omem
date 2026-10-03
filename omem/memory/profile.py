"""Compiled user/agent profile — SuperMemory-style 50ms briefing, no LLM.

A profile is a *view* over active TMS facts, recent episodes, and session
goal/plan. Hosts inject ``Profile.text`` as a small always-on block.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ..types import Memory, MemoryStatus, MemoryType

if TYPE_CHECKING:
    from ..state.layer import StateOS
    from .layer import MemoryOS


@dataclass
class ProfileFact:
    """One current belief extracted from an active memory."""

    subject: str
    attribute: str
    value: str
    memory_id: str
    valid_from: Optional[float] = None
    valid_to: Optional[float] = None
    importance: float = 0.5

    def as_line(self) -> str:
        return f"{self.subject} {self.attribute} {self.value}".strip()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subject": self.subject,
            "attribute": self.attribute,
            "value": self.value,
            "memory_id": self.memory_id,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "importance": self.importance,
        }


@dataclass
class Profile:
    """Token-cheap briefing: stable facts + recent activity + open goal."""

    namespace: str = "default"
    user_id: str = ""
    facts: List[ProfileFact] = field(default_factory=list)
    recent: List[Memory] = field(default_factory=list)
    goal: Optional[str] = None
    plan: List[str] = field(default_factory=list)
    step: int = 0
    text: str = ""
    fact_count: int = 0
    assembled_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "namespace": self.namespace,
            "user_id": self.user_id,
            "facts": [f.to_dict() for f in self.facts],
            "recent": [m.content for m in self.recent],
            "goal": self.goal,
            "plan": self.plan,
            "step": self.step,
            "text": self.text,
            "fact_count": self.fact_count,
            "assembled_at": self.assembled_at,
        }


def _triplet_from_memory(mem: Memory) -> Optional[tuple]:
    trip = (mem.metadata or {}).get("triplet")
    if trip and len(trip) == 3:
        return tuple(trip)
    facts = (mem.metadata or {}).get("facts") or []
    if facts and isinstance(facts[0], (list, tuple)) and len(facts[0]) == 3:
        return tuple(facts[0])
    if facts and isinstance(facts[0], dict):
        s = facts[0].get("subject") or facts[0].get("entity")
        a = facts[0].get("predicate") or facts[0].get("attribute")
        o = facts[0].get("object") or facts[0].get("value")
        if s and a and o:
            return (s, a, o)
    return None


def build_profile(
    memories: List[Memory],
    *,
    namespace: str = "default",
    user_id: str = "",
    goal: Optional[str] = None,
    plan: Optional[List[str]] = None,
    step: int = 0,
    max_facts: int = 20,
    max_recent: int = 8,
    now: Optional[float] = None,
) -> Profile:
    """Compile a profile from in-memory records. Deterministic, no LLM."""
    now = now if now is not None else time.time()
    active = [
        m
        for m in memories
        if m.active
        and m.status == MemoryStatus.ACTIVE
        and getattr(m, "is_current", lambda n=None: True)(now)
        and (not namespace or m.namespace == namespace)
    ]

    facts: List[ProfileFact] = []
    seen_keys = set()
    for mem in sorted(active, key=lambda m: (-m.importance, -m.timestamp)):
        trip = _triplet_from_memory(mem)
        if not trip:
            continue
        key = (str(trip[0]).lower(), str(trip[1]).lower())
        if key in seen_keys:
            continue
        seen_keys.add(key)
        facts.append(
            ProfileFact(
                subject=str(trip[0]),
                attribute=str(trip[1]),
                value=str(trip[2]),
                memory_id=mem.id,
                valid_from=getattr(mem, "valid_from", None),
                valid_to=getattr(mem, "valid_to", None),
                importance=float(mem.importance),
            )
        )
        if len(facts) >= max_facts:
            break

    recent_pool = [
        m
        for m in active
        if m.type in (MemoryType.EPISODIC, MemoryType.WORKING, MemoryType.DECISION)
        or not _triplet_from_memory(m)
    ]
    recent_pool.sort(key=lambda m: m.timestamp, reverse=True)
    recent = recent_pool[:max_recent]

    lines = ["## Profile"]
    if user_id:
        lines.append(f"- user: {user_id}")
    if goal:
        lines.append(f"- goal: {goal}")
        if plan:
            lines.append(f"- plan step {step + 1}/{len(plan)}: {plan[min(step, len(plan) - 1)]}")
    if facts:
        lines.append("### Current facts")
        for f in facts:
            lines.append(f"- {f.as_line()}")
    if recent:
        lines.append("### Recent")
        for m in recent:
            preview = m.content.strip().replace("\n", " ")
            if len(preview) > 160:
                preview = preview[:157] + "..."
            lines.append(f"- {preview}")
    text = "\n".join(lines)

    return Profile(
        namespace=namespace,
        user_id=user_id,
        facts=facts,
        recent=recent,
        goal=goal,
        plan=list(plan or []),
        step=step,
        text=text,
        fact_count=len(facts),
        assembled_at=now,
    )


def profile_from_layers(
    memory: "MemoryOS",
    state: Optional["StateOS"] = None,
    *,
    namespace: str = "default",
    user_id: str = "",
    session_id: Optional[str] = None,
    max_facts: int = 20,
    max_recent: int = 8,
) -> Profile:
    mems = memory.list(namespace=namespace, include_inactive=False)
    goal = None
    plan: List[str] = []
    step = 0
    if state is not None and session_id:
        try:
            payload = state.load(session_id)
            goal = payload.goal
            plan = list(payload.plan or [])
            step = int(payload.step or 0)
        except Exception:
            pass
    return build_profile(
        mems,
        namespace=namespace,
        user_id=user_id,
        goal=goal,
        plan=plan,
        step=step,
        max_facts=max_facts,
        max_recent=max_recent,
    )
