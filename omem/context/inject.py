"""Host-side injection helpers — keep LLM KV-cache warm.

OMem returns a discrete context pack. The *host* (OpenCode, Cursor, your
agent loop) must splice it without rewriting earlier conversation turns.

Correct pattern
---------------
1. Keep a stable system / tool prefix (never rewrite it mid-session).
2. Maintain one replaceable slot marked by ``OMEM_CONTEXT_START/END``.
3. On each turn, call ``build_context`` and ``apply_omem_context`` so only
   that slot changes. Tokens *before* the slot stay prefix-cacheable.

Wrong pattern
-------------
Rebuilding the full prompt from scratch, reordering history, or inlining
memories into earlier user/assistant messages every turn.
"""

from __future__ import annotations

import re
from typing import List, Optional, Sequence, Union

OMEM_CONTEXT_START = "<!-- OMEM_CONTEXT_START -->"
OMEM_CONTEXT_END = "<!-- OMEM_CONTEXT_END -->"

_SLOT_RE = re.compile(
    re.escape(OMEM_CONTEXT_START) + r".*?" + re.escape(OMEM_CONTEXT_END),
    re.DOTALL,
)

HOST_INSTRUCTIONS = (
    "Append or replace ONLY the block between "
    f"{OMEM_CONTEXT_START} and {OMEM_CONTEXT_END}. "
    "Do not rewrite earlier conversation turns — that invalidates the "
    "model prefix KV-cache and spikes input-token cost."
)


def wrap_omem_pack(pack_text: str) -> str:
    """Ensure pack is wrapped in stable replace markers."""
    text = (pack_text or "").strip()
    if OMEM_CONTEXT_START in text and OMEM_CONTEXT_END in text:
        return text
    return f"{OMEM_CONTEXT_START}\n{text}\n{OMEM_CONTEXT_END}"


def apply_omem_context(prompt: str, pack_text: str) -> str:
    """Splice / replace the OMem slot in a system (or preamble) string.

    - If markers already exist → replace the slot only.
    - Else → append a new marked slot at the end.
    """
    block = wrap_omem_pack(pack_text)
    if _SLOT_RE.search(prompt or ""):
        return _SLOT_RE.sub(block, prompt, count=1)
    base = (prompt or "").rstrip()
    if not base:
        return block
    return f"{base}\n\n{block}"


def apply_omem_to_messages(
    messages: Sequence[dict],
    pack_text: str,
    *,
    system_role: str = "system",
) -> List[dict]:
    """Apply pack to the first system message (or create one).

    Leaves user/assistant/tool turns untouched — required for KV-cache.
    """
    out: List[dict] = [dict(m) for m in messages]
    block = wrap_omem_pack(pack_text)
    for m in out:
        if m.get("role") == system_role:
            m["content"] = apply_omem_context(str(m.get("content") or ""), block)
            return out
    out.insert(0, {"role": system_role, "content": block})
    return out


def injection_metadata(pack_text: str) -> dict:
    """Fields to return alongside MCP/API ``build_context`` results."""
    wrapped = wrap_omem_pack(pack_text)
    return {
        "slot": "system_tail",
        "replace_start": OMEM_CONTEXT_START,
        "replace_end": OMEM_CONTEXT_END,
        "instructions": HOST_INSTRUCTIONS,
        "text_marked": wrapped,
    }
