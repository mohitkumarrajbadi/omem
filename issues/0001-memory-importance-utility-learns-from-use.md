# Issue 0001: Move memory importance from heuristic to usage-based utility

## Summary

Current importance is bootstrapped from content heuristics, which is fine for MVP but incorrect for production. Instead, importance should evolve from observed memory utility over time.

## Problem

The current pipeline stores importance as:

- `importance = estimate_importance(content)`

This means heuristic keyword matches determine retention, which is brittle and context-agnostic. For example, `"My favorite color is blue"` may score higher than `"Our production database is PostgreSQL"` even though the latter is far more important for engineering agents.

## Why it matters

- Importance should represent expected future utility, not content labels.
- Future utility is unknown at ingestion time, so the system must learn from usage.
- Heuristic importance is useful only as an initial prior.

## Proposed change

1. Keep the current heuristic as an initial or default importance prior.
2. Add utility signals that update importance after ingest:
   - `retrieved_count`
   - `used_in_answer_count`
   - `successful_task_count`
   - `citation_count`
3. Recompute importance periodically or on relevant events:
   - promote frequently useful memories
   - demote memories that are never used
4. Treat importance as a dynamic score, not a static classification.

## Acceptance criteria

- `estimate_importance()` becomes `initial_importance()` or similar.
- Memory records collect usage/utility metrics.
- Importance is updated from utility signals.
- Retention decisions use the evolving importance score.
- Existing health formula remains unchanged.

## Notes

This is the right direction for moving from a rule-based memory manager toward a true memory operating system.
