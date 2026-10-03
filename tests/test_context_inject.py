"""Unit tests for host-side OMem KV-cache injection helpers."""

from omem.context.inject import (
    OMEM_CONTEXT_END,
    OMEM_CONTEXT_START,
    apply_omem_context,
    apply_omem_to_messages,
    wrap_omem_pack,
)


def test_apply_omem_context_appends_marked_slot():
    base = "You are a coding agent.\nStable tools follow."
    out = apply_omem_context(base, "## OMem Context\nfact-1")
    assert OMEM_CONTEXT_START in out
    assert OMEM_CONTEXT_END in out
    assert out.startswith(base)
    assert out.index(base) < out.index(OMEM_CONTEXT_START)


def test_apply_omem_context_replaces_slot_only():
    prefix = "SYSTEM PREFIX — never rewrite"
    first = apply_omem_context(prefix, "pack-v1")
    second = apply_omem_context(first, "pack-v2")
    assert second.count(OMEM_CONTEXT_START) == 1
    assert "pack-v2" in second
    assert "pack-v1" not in second
    # Prefix before the slot is byte-identical (KV-cache invariant).
    assert second.startswith(prefix)
    assert second[: len(prefix)] == first[: len(prefix)]


def test_apply_omem_to_messages_leaves_history_untouched():
    msgs = [
        {"role": "system", "content": "stable system"},
        {"role": "user", "content": "turn-1"},
        {"role": "assistant", "content": "reply-1"},
    ]
    out = apply_omem_to_messages(msgs, "pack-a")
    assert out[1]["content"] == "turn-1"
    assert out[2]["content"] == "reply-1"
    assert OMEM_CONTEXT_START in out[0]["content"]
    out2 = apply_omem_to_messages(out, "pack-b")
    assert out2[1] == out[1]
    assert out2[2] == out[2]
    assert "pack-b" in out2[0]["content"]
    assert "pack-a" not in out2[0]["content"]


def test_wrap_omem_pack_idempotent():
    wrapped = wrap_omem_pack("hello")
    assert wrapped.startswith(OMEM_CONTEXT_START)
    assert wrap_omem_pack(wrapped) == wrapped
