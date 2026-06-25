# Issue 0002: Treat `MemoryType` as a probabilistic hint, not an authoritative label

## Summary

MemoryType should be kept, but its role must change from "truth" to "hint." In production, types should influence ranking and extraction, not define final memory schema or retention decisions.

## Problem

The current system effectively uses memory type as a hard label:

- `type = truth`

That leads to brittle, overfit behavior where type classification can override actual utility. Instead, the type should be:

- `type ≈ hint`

## Why it matters

- Keeps the classifier useful without making it decisive.
- Prevents rule-based labels from locking in stale or irrelevant memory semantics.
- Supports structured knowledge extraction and schema selection.

## Proposed change

1. Continue storing `MemoryType` and `type_mask`.
2. Add `type_confidence` to capture classification uncertainty.
3. Use type as a relevance/ranking feature, not a retention gate.
4. Add structured knowledge fields to `Memory`:
   - `entities`
   - `relations`
   - `facts`
   - `temporal_state`
5. Keep `type` useful for downstream extraction hints:
   - `PROCEDURAL` → extract steps
   - `CAUSAL` → extract cause/effect
   - `DECISION` → extract choice/reason

## Acceptance criteria

- `MemoryType` remains in the data model.
- `type` is no longer treated as the final memory schema decision.
- New structured fields are added to the `Memory` model.
- Type confidence is captured and available.
- Classification is treated as a soft signal for recall and extraction.

## Notes

This change enables conflict-resolvable, queryable, and temporal memory behavior, rather than relying on brittle rule-based type labels.
