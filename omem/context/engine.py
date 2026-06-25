"""Context Engine — Phase 3 of the v2 implementation plan.

The ``ContextEngine`` solves the single most expensive problem in AI agent
deployment: **what to actually send to the LLM**.

Naive approach: dump all memories → thousands of tokens every call.
OMem approach: assemble the optimal slice within a token budget.

Assembly pipeline
-----------------
1. Load current ``StatePayload`` — goal, plan, step, recent tool outputs.
2. ``memory.recall()`` — top-k memories ranked by multi-objective score.
3. Knowledge graph neighbors for recalled entity context.
4. Sort all candidate sections by priority score.
5. Greedy packing: fill the budget highest-priority first.
   High-priority sections (state) are truncated if too long.
   Memory sections are dropped entirely — no partial memories.
6. Format as a structured prompt block.
7. Return a ``ContextBundle`` with text, section map, token stats, and
   ``savings_vs_naive`` so you can measure the exact value delivered.

Typical savings: 40–80% vs a naive "dump all" approach.

Reuses (no duplication)
-----------------------
- ``omem.core.retrieval.ranker`` — mode-based fusion weights (planning / coding / chat)
- ``omem.state.layer.StateOS``   — session state load
- ``omem.memory.layer.MemoryOS`` — multi-objective recall

Usage::

    # Standalone (no session state)
    engine = ContextEngine(memory=agent.memory)
    ctx = engine.build(ContextRequest(task="continue oauth2 work", budget_tokens=6000))

    # With session state (recommended)
    engine = ContextEngine(memory=agent.memory, state=agent.state)
    ctx = engine.build(ContextRequest(
        task="continue oauth2 work",
        budget_tokens=6000,
        session_id="agent-1",
    ))
    llm.chat(ctx.text + user_message)
    print(f"Tokens saved: {ctx.savings_vs_naive:.0%}")

See: docs/roadmap/FULL_IMPLEMENTATION_PLAN.md — Phase 3
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..types import Memory, MemoryType
from .tokenizer import TokenCounter

logger = logging.getLogger(__name__)

# Priority tiers: state header is always packed first regardless of budget
_PRIORITY_STATE_HEADER = 1.0
_PRIORITY_STATE_TOOLS = 0.9
_PRIORITY_KNOWLEDGE = 0.3     # knowledge fills the tail of the budget
_MIN_SECTION_BUDGET = 20      # never attempt to pack a section with < 20 tokens left


# ---------------------------------------------------------------------------
# Public data contracts
# ---------------------------------------------------------------------------


@dataclass
class ContextRequest:
    """Parameters for a context assembly request.

    Attributes:
        task:          What the agent is doing right now.
        budget_tokens: Hard ceiling on output token count.
        session_id:    Include state from this session (optional).
        namespace:     Filter memories to this namespace (optional).
        mode:          Retrieval mode — reuses existing ranker profiles:
                       ``"planning"``, ``"coding"``, ``"chat"``, ``"recall"``.
        include:       Which sections to include. Any subset of
                       ``["state", "memory", "knowledge"]``.
        exclude_types: Memory types to skip (e.g. ``[MemoryType.WORKING]``).
        top_k_memories: Max number of memories to consider.
        token_model:   LLM model name for tiktoken (e.g. ``"gpt-4o"``).
                       When None, word-based approximation is used.
    """

    task: str
    budget_tokens: int = 6000
    session_id: Optional[str] = None
    namespace: Optional[str] = None
    mode: str = "planning"
    include: List[str] = field(default_factory=lambda: ["state", "memory", "knowledge"])
    exclude_types: List[MemoryType] = field(default_factory=list)
    top_k_memories: int = 15
    token_model: Optional[str] = None


@dataclass
class ContextBundle:
    """Assembled context ready to inject into an LLM prompt.

    Attributes:
        text:               The full prompt block (inject before user message).
        sections:           Per-section text (for fine-grained inspection).
        section_tokens:     Per-section token counts.
        token_count:        Total tokens in ``text``.
        budget_tokens:      The budget passed in the request.
        memories_used:      IDs of memories that made it into the bundle.
        state_included:     Whether a state section was included.
        knowledge_included: Whether a knowledge section was included.
        savings_vs_naive:   Fraction saved vs dumping all memories.
                            0.75 means 75% fewer tokens than naive.
        assembled_at:       Unix timestamp of assembly (for cache invalidation).
    """

    text: str
    sections: Dict[str, str] = field(default_factory=dict)
    section_tokens: Dict[str, int] = field(default_factory=dict)
    token_count: int = 0
    budget_tokens: int = 6000
    memories_used: List[str] = field(default_factory=list)
    state_included: bool = False
    knowledge_included: bool = False
    savings_vs_naive: float = 0.0
    assembled_at: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Internal section representation
# ---------------------------------------------------------------------------


@dataclass
class _ContextSection:
    """One candidate block for budget packing (internal only)."""

    name: str
    text: str
    priority: float
    token_count: int = 0
    memory_id: Optional[str] = None
    truncatable: bool = False  # only state sections are truncated; memory is dropped


# ---------------------------------------------------------------------------
# LRU+TTL cache
# ---------------------------------------------------------------------------


class _ContextCache:
    """Simple TTL-based cache for assembled bundles.

    Keyed by a SHA-256 of the serialized request. Entries expire after
    ``ttl`` seconds. No eviction limit — context bundles are small and
    most agents only have a handful of concurrent sessions.
    """

    def __init__(self, ttl: float = 30.0) -> None:
        self._ttl = ttl
        self._store: Dict[str, Tuple[float, ContextBundle]] = {}

    @staticmethod
    def _key(request: ContextRequest) -> str:
        data = {
            "task": request.task,
            "budget": request.budget_tokens,
            "session": request.session_id,
            "ns": request.namespace,
            "mode": request.mode,
            "include": sorted(request.include),
            "top_k": request.top_k_memories,
        }
        return hashlib.sha256(
            json.dumps(data, sort_keys=True).encode()
        ).hexdigest()[:16]

    def get(self, request: ContextRequest) -> Optional[ContextBundle]:
        key = self._key(request)
        entry = self._store.get(key)
        if entry is None:
            return None
        ts, bundle = entry
        if time.time() - ts > self._ttl:
            del self._store[key]
            return None
        return bundle

    def put(self, request: ContextRequest, bundle: ContextBundle) -> None:
        self._store[self._key(request)] = (time.time(), bundle)

    def invalidate(self, session_id: str) -> None:
        """Remove all cached bundles associated with a session."""
        to_delete = [
            k for k, (_, b) in self._store.items()
            if b.state_included
        ]
        for k in to_delete:
            self._store.pop(k, None)

    def clear(self) -> None:
        self._store.clear()


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _type_label(mtype: MemoryType) -> str:
    _LABELS = {
        MemoryType.EPISODIC: "EPISODIC",
        MemoryType.SEMANTIC: "SEMANTIC",
        MemoryType.CAUSAL: "CAUSAL",
        MemoryType.DECISION: "DECISION",
        MemoryType.PROCEDURAL: "PROCEDURAL",
        MemoryType.REFLECTION: "REFLECTION",
        MemoryType.INSIGHT: "INSIGHT",
        MemoryType.WORKING: "WORKING",
        MemoryType.ACTIVE: "ACTIVE",
        MemoryType.SENSORY: "SENSORY",
    }
    return _LABELS.get(mtype, mtype.name)


def _format_state_section(payload) -> str:
    """Render a StatePayload as a concise markdown block."""
    lines = []

    if payload.goal:
        lines.append(f"**Goal:** {payload.goal}")

    if payload.plan:
        plan_items = []
        for i, step in enumerate(payload.plan):
            if i < payload.step:
                plan_items.append(f"{step} ✓")
            elif i == payload.step:
                plan_items.append(f"**{step}** ←")
            else:
                plan_items.append(step)
        lines.append("**Plan:** " + " → ".join(plan_items))
        total = len(payload.plan)
        lines.append(
            f"**Progress:** step {payload.step + 1} of {total} "
            f"| status: `{payload.status}`"
        )

    if payload.workflow_state:
        wf_items = [
            f"  - `{k}`: {str(v)[:80]}"
            for k, v in payload.workflow_state.items()
            if not k.startswith("_") and v is not None
        ]
        if wf_items:
            lines.append("**Workflow state:**\n" + "\n".join(wf_items))

    return "\n".join(lines)


def _format_tools_section(payload, max_tools: int) -> str:
    """Render recent tool outputs as a compact bullet list."""
    if not payload.tool_outputs:
        return ""
    recent = payload.tool_outputs[-max_tools:]
    lines = ["**Recent tool outputs:**"]
    for t in recent:
        output_str = str(t.output)
        if len(output_str) > 120:
            output_str = output_str[:120] + "…"
        status = f" *(error: {t.error})*" if t.error else ""
        lines.append(f"- `{t.tool}` → {output_str}{status}")
    return "\n".join(lines)


def _format_memory_line(rank: int, mem: Memory) -> str:
    """Render a single memory as a ranked bullet."""
    score = getattr(mem, "score", mem.importance)
    type_tag = _type_label(mem.type)
    source = f" | src: {mem.source}" if getattr(mem, "source", "") else ""
    return (
        f"{rank}. **[{type_tag}]** {mem.content}\n"
        f"   *(score: {score:.2f} | imp: {mem.importance:.2f}{source})*"
    )


def _format_knowledge_section(memories: List[Memory], omem_instance) -> str:
    """Extract entity context from recalled memories via the knowledge graph."""
    kg = getattr(getattr(omem_instance, "brain", None), "knowledge_graph", None)
    if kg is None:
        return ""

    entity_lines: List[str] = []
    seen_pairs = set()

    for mem in memories[:5]:  # Only use top-5 to avoid noise
        try:
            entities = [e.name for e in kg.find_entities_in_query(mem.content)]
        except Exception:
            entities = []
        for entity in entities[:2]:
            try:
                # get_edges returns both forward and backward edges; filter to outgoing
                all_edges = kg.get_edges(entity)
                entity_key = entity.lower()
                outgoing = [e for e in all_edges if e.source == entity_key][:3]
            except Exception:
                outgoing = []
            for rel in outgoing:
                pair = (entity_key, rel.edge_type.value, rel.target)
                if pair not in seen_pairs:
                    entity_lines.append(
                        f"- {rel.source} —[{rel.edge_type.value}]→ {rel.target}"
                    )
                    seen_pairs.add(pair)
            if len(entity_lines) >= 8:
                break
        if len(entity_lines) >= 8:
            break

    if not entity_lines:
        return ""
    return "**Entity context:**\n" + "\n".join(entity_lines)


def _format_bundle_text(
    sections: Dict[str, str],
    session_id: Optional[str],
    task: str,
    token_count: int,
    budget_tokens: int,
    savings: float,
) -> str:
    """Compose the final prompt block from packed sections."""
    header_parts = ["## OMem Context"]
    if session_id:
        header_parts.append(f"session: `{session_id}`")
    header = " — ".join(header_parts)

    parts = [header, f"*Task: {task}*", ""]

    ordered_keys = ["state_header", "state_tools", "memory", "knowledge"]
    section_titles = {
        "state_header": "### Session State",
        "state_tools": "### Recent Tool Activity",
        "memory": "### Relevant Memory",
        "knowledge": "### Knowledge Context",
    }
    for key in ordered_keys:
        if key in sections and sections[key]:
            parts.append(section_titles[key])
            parts.append(sections[key])
            parts.append("")

    # Footer with token stats
    savings_pct = f"{savings:.0%}"
    parts.append(
        f"---\n*{token_count:,} of {budget_tokens:,} tokens | "
        f"{savings_pct} saved vs full memory dump*"
    )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Context Engine
# ---------------------------------------------------------------------------


class ContextEngine:
    """V2 context engine — fully implemented (Phase 3).

    Given a task and a token budget, assembles the most relevant slice of
    memory + agent state + knowledge and returns a ``ContextBundle`` ready
    to prepend to any LLM prompt.

    Args:
        memory:        ``MemoryOS`` instance (or compatible duck type).
                       If None, the memory section is skipped.
        state:         ``StateOS`` instance.
                       If None, the state section is skipped.
        cache_ttl:     Cache expiry in seconds (default 30s).
                       Set 0 to disable caching.
        default_mode:  Default retrieval mode (``"planning"``, ``"coding"``,
                       ``"chat"``, ``"recall"``).
        max_memories:  Upper bound on recalled memories per call.
        max_tool_outputs: Max tool output lines in the state section.
        token_model:   OpenAI model name for exact tiktoken counting
                       (e.g. ``"gpt-4o"``). Falls back to word-based.
    """

    def __init__(
        self,
        memory=None,
        state=None,
        cache_ttl: float = 30.0,
        default_mode: str = "planning",
        max_memories: int = 15,
        max_tool_outputs: int = 5,
        token_model: Optional[str] = None,
    ) -> None:
        self._memory = memory
        self._state = state
        self._cache = _ContextCache(ttl=cache_ttl) if cache_ttl > 0 else None
        self._default_mode = default_mode
        self._max_memories = max_memories
        self._max_tool_outputs = max_tool_outputs
        self._counter = TokenCounter.create(token_model)
        logger.debug(
            "ContextEngine initialized (memory=%s, state=%s, counter=%s)",
            memory is not None,
            state is not None,
            "tiktoken" if self._counter.is_exact else "word-based",
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self, request: ContextRequest) -> ContextBundle:
        """Assemble an optimal context bundle within the token budget.

        The pipeline is:
          1. Candidate sections are generated from state + memory + knowledge.
          2. Sections are sorted by priority (state > memory > knowledge).
          3. Greedy packing: highest-priority sections fill the budget first.
             State sections are truncated to fit; memory sections are dropped.
          4. The packed sections are formatted into a structured prompt block.
          5. Token savings are computed vs. dumping all memories naively.

        Returns:
            ``ContextBundle`` with ``text``, ``sections``, ``token_count``,
            ``memories_used``, and ``savings_vs_naive``.
        """
        if self._cache is not None:
            cached = self._cache.get(request)
            if cached is not None:
                logger.debug("context.build cache_hit session=%r", request.session_id)
                return cached

        t0 = time.time()
        mode = request.mode or self._default_mode

        # ── Step 1: Gather candidates ────────────────────────────────
        candidates: List[_ContextSection] = []

        if "state" in request.include and request.session_id and self._state:
            candidates.extend(self._make_state_sections(request.session_id))

        memories: List[Memory] = []
        if "memory" in request.include and self._memory:
            memories = self._recall_memories(request, mode)
            candidates.extend(self._make_memory_sections(memories, request))

        # ── Step 2: Compute token counts ────────────────────────────
        for sec in candidates:
            sec.token_count = self._counter.count(sec.text)

        # ── Step 3: Greedy packing ───────────────────────────────────
        packed, used_tokens = self._pack(candidates, request.budget_tokens)

        # ── Step 4: Knowledge neighbors (budget tail) ────────────────
        kg_text = ""
        if "knowledge" in request.include and memories and self._memory:
            omem = getattr(self._memory, "omem", None) or getattr(self._memory, "_omem", None)
            remaining = request.budget_tokens - used_tokens
            if omem and remaining > _MIN_SECTION_BUDGET:
                kg_text = _format_knowledge_section(memories, omem)
                kg_tokens = self._counter.count(kg_text)
                if kg_text and kg_tokens <= remaining:
                    packed.append(_ContextSection(
                        name="knowledge",
                        text=kg_text,
                        priority=_PRIORITY_KNOWLEDGE,
                        token_count=kg_tokens,
                    ))
                    used_tokens += kg_tokens

        # ── Step 5: Compute savings ──────────────────────────────────
        naive_tokens = self._naive_token_count(request)
        savings = max(0.0, 1.0 - used_tokens / naive_tokens) if naive_tokens > 0 else 0.0

        # ── Step 6: Format ───────────────────────────────────────────
        sections: Dict[str, str] = {}
        section_tokens: Dict[str, int] = {}
        memory_ids: List[str] = []
        state_included = False

        for sec in packed:
            key = sec.name if ":" not in sec.name else "memory"
            sections[key] = sections.get(key, "") + (
                "\n" + sec.text if key in sections else sec.text
            )
            section_tokens[key] = section_tokens.get(key, 0) + sec.token_count
            if sec.memory_id:
                memory_ids.append(sec.memory_id)
            if sec.name in ("state_header", "state_tools"):
                state_included = True

        text = _format_bundle_text(
            sections=sections,
            session_id=request.session_id,
            task=request.task,
            token_count=used_tokens,
            budget_tokens=request.budget_tokens,
            savings=savings,
        )
        # Recount with the full formatted text (header/footer add tokens)
        final_token_count = self._counter.count(text)

        bundle = ContextBundle(
            text=text,
            sections=sections,
            section_tokens=section_tokens,
            token_count=final_token_count,
            budget_tokens=request.budget_tokens,
            memories_used=memory_ids,
            state_included=state_included,
            knowledge_included=bool(kg_text),
            savings_vs_naive=savings,
            assembled_at=time.time(),
        )

        if self._cache is not None:
            self._cache.put(request, bundle)

        elapsed_ms = (time.time() - t0) * 1000
        logger.debug(
            "context.build done session=%r tokens=%d/%d memories=%d savings=%.0f%% %.1fms",
            request.session_id,
            final_token_count,
            request.budget_tokens,
            len(memory_ids),
            savings * 100,
            elapsed_ms,
        )
        return bundle

    def estimate_savings(self, request: ContextRequest) -> Dict[str, Any]:
        """Compute token statistics without modifying any state.

        Returns a dict with keys:
            naive_tokens:      total tokens if all namespace memories were dumped
            optimised_tokens:  tokens in the assembled bundle
            savings_pct:       percentage saved (0–100)
            memories_in_store: total memories available
            memories_used:     memories included in the bundle
            budget_tokens:     the budget from the request
        """
        bundle = self.build(request)
        naive_tokens = self._naive_token_count(request)
        mems_in_store = 0
        if self._memory:
            try:
                mems_in_store = len(self._memory.list(namespace=request.namespace))
            except Exception:
                pass
        return {
            "naive_tokens": naive_tokens,
            "optimised_tokens": bundle.token_count,
            "savings_pct": round(bundle.savings_vs_naive * 100, 1),
            "memories_in_store": mems_in_store,
            "memories_used": len(bundle.memories_used),
            "budget_tokens": request.budget_tokens,
        }

    def invalidate_cache(self, session_id: Optional[str] = None) -> None:
        """Flush the context cache (all entries, or entries for a session)."""
        if self._cache is None:
            return
        if session_id:
            self._cache.invalidate(session_id)
        else:
            self._cache.clear()

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------

    def _make_state_sections(self, session_id: str) -> List[_ContextSection]:
        """Load state and split into header + tools sections."""
        try:
            payload = self._state.load(session_id)
        except Exception:
            return []

        sections = []

        header_text = _format_state_section(payload)
        if header_text:
            sections.append(_ContextSection(
                name="state_header",
                text=header_text,
                priority=_PRIORITY_STATE_HEADER,
                truncatable=True,
            ))

        tools_text = _format_tools_section(payload, self._max_tool_outputs)
        if tools_text:
            sections.append(_ContextSection(
                name="state_tools",
                text=tools_text,
                priority=_PRIORITY_STATE_TOOLS,
                truncatable=True,
            ))

        return sections

    def _make_memory_sections(
        self,
        memories: List[Memory],
        request: ContextRequest,
    ) -> List[_ContextSection]:
        """Convert recalled memories into packed sections."""
        sections = []
        for rank, mem in enumerate(memories, start=1):
            if request.exclude_types and mem.type in request.exclude_types:
                continue
            score = getattr(mem, "score", mem.importance)
            sections.append(_ContextSection(
                name=f"memory:{mem.id}",
                text=_format_memory_line(rank, mem),
                priority=min(0.85, 0.5 + score * 0.35),  # 0.5–0.85 range
                memory_id=mem.id,
                truncatable=False,
            ))
        return sections

    # ------------------------------------------------------------------
    # Greedy packer
    # ------------------------------------------------------------------

    def _pack(
        self,
        candidates: List[_ContextSection],
        budget: int,
    ) -> Tuple[List[_ContextSection], int]:
        """Greedy packing: sort by priority, fill budget highest-first.

        State sections (``truncatable=True``) are shrunk to fit if the full
        text exceeds remaining budget. Memory sections are dropped entirely.

        Returns:
            (packed_sections, total_tokens_used)
        """
        ordered = sorted(candidates, key=lambda s: s.priority, reverse=True)
        packed: List[_ContextSection] = []
        used = 0

        for sec in ordered:
            remaining = budget - used
            if remaining < _MIN_SECTION_BUDGET:
                break

            if sec.token_count <= remaining:
                packed.append(sec)
                used += sec.token_count
            elif sec.truncatable and remaining > _MIN_SECTION_BUDGET:
                truncated_text = self._counter.truncate(sec.text, remaining - 5)
                truncated_tokens = self._counter.count(truncated_text)
                if truncated_tokens > 0:
                    sec.text = truncated_text
                    sec.token_count = truncated_tokens
                    packed.append(sec)
                    used += truncated_tokens
            # Memory sections that don't fit are silently dropped

        return packed, used

    # ------------------------------------------------------------------
    # Token helpers
    # ------------------------------------------------------------------

    def _recall_memories(
        self, request: ContextRequest, mode: str
    ) -> List[Memory]:
        try:
            return self._memory.recall(
                request.task,
                k=request.top_k_memories,
                namespace=request.namespace,
                mode=mode,
            )
        except Exception as exc:
            logger.warning("context: memory recall failed — %s", exc)
            return []

    def _naive_token_count(self, request: ContextRequest) -> int:
        """Total tokens in the full memory store — the naive baseline."""
        if self._memory is None:
            return 0
        try:
            all_mems = self._memory.list(namespace=request.namespace)
            return sum(self._counter.count(m.content) for m in all_mems)
        except Exception:
            return 0
