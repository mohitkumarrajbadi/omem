"""Kill-the-Agent demo — Mode A resume + fork + context + audit timeline.

Simulates a multi-step incident agent that dies mid-run. A second
``AgentState`` instance (new process boundary) resumes from the last
checkpoint, forks an alternate branch, packs context, and prints the
durable event audit.

Offline: uses ``OMEM_EMBEDDER=hash``. No paid model APIs.

See: yc-w27-materials/OMEM_V1_ENGINEERING_SPEC.md §12 Demo A
"""

from __future__ import annotations

import os
import tempfile
from typing import Any, Dict, List, Optional

from ..agent_state import AgentState

STEPS = [
    "Read logs",
    "Query metrics",
    "Inspect deployment",
    "Check Git history",
    "Generate hypothesis",
    "Run verification test",  # kill after this checkpoint
    "Request approval",
    "Apply fix",
    "Verify recovery",
    "Write report",
]

KILL_AFTER_STEP = 6  # 1-indexed step number completed before "crash"


def run_kill_resume(*, db_path: Optional[str] = None) -> Dict[str, Any]:
    """Run the kill-resume walkthrough; return a machine-readable report."""
    os.environ.setdefault("OMEM_EMBEDDER", "hash")

    lines: List[str] = []
    cleanup_path: Optional[str] = None

    if db_path:
        resolved_db = db_path
    else:
        fd, resolved_db = tempfile.mkstemp(suffix=".omem-kill.db")
        os.close(fd)
        cleanup_path = resolved_db

    kwargs: Dict[str, Any] = {
        "session_id": "incident-agent",
        "backend": "sqlite",
        "db_path": resolved_db,
    }

    try:
        return _run(kwargs, lines)
    finally:
        if cleanup_path and os.path.exists(cleanup_path):
            try:
                os.unlink(cleanup_path)
                for suffix in ("-wal", "-shm"):
                    side = cleanup_path + suffix
                    if os.path.exists(side):
                        os.unlink(side)
            except OSError:
                pass


def _run(kwargs: Dict[str, Any], lines: List[str]) -> Dict[str, Any]:
    # ── Process 1: run until kill point ────────────────────────────────
    agent = AgentState(**kwargs)
    run = agent.start_run(
        goal="Investigate production incident and prepare remediation",
        agent_id="incident-agent",
        worker_id="worker_proc1",
        label="kill-demo",
    )
    agent.set_plan(STEPS)
    run.record("user_message", {"text": "Investigate this production incident."})

    killed_at = 0
    for i, step_name in enumerate(STEPS, start=1):
        agent.advance()
        call = run.record(
            "tool_call",
            {"tool": f"step.{i}", "name": step_name},
            idempotency_key=f"step:{i}:call",
        )
        run.record(
            "tool_result",
            {"ok": True, "summary": f"completed: {step_name}"},
            causation_id=call.event_id,
            idempotency_key=f"step:{i}:result",
        )
        agent.remember(
            f"Step {i} done: {step_name}",
            force=True,
            importance=0.7,
        )
        ck = run.checkpoint()
        lines.append(f"[step {i}/{len(STEPS)}] {step_name}  checkpoint={ck}")
        if i == KILL_AFTER_STEP:
            killed_at = i
            lines.append("")
            lines.append(f"PROCESS KILLED after step {i} (worker_proc1 gone)")
            lines.append(
                "  (Dead process cannot write run_crashed — resume will infer it.)"
            )
            break

    run_id = run.run_id
    session_id = agent.session_id
    step_before_death = agent.current_state().step

    # Release SQLite handles before the "new process" reopen (required on Windows).
    agent.close()
    del run
    del agent

    agent2: Optional[AgentState] = None
    try:
        # ── Process 2: resume ──────────────────────────────────────────
        lines.append("")
        lines.append("-- New process starting --")
        agent2 = AgentState(
            session_id=session_id,
            backend=kwargs["backend"],
            db_path=kwargs["db_path"],
        )
        r = agent2.runs.get_run(run_id)
        r.lease_until = 0.0
        agent2.runs._store.save_run(r)

        resumed = agent2.resume_run(run_id, worker_id="worker_proc2")
        payload = agent2.current_state()
        lines.append(
            f"[resume] run={run_id}  status={resumed.run.status}  "
            f"step={payload.step} (expected {killed_at})"
        )
        if payload.step != killed_at:
            return {
                "ok": False,
                "error": f"Mode A resume failed: step={payload.step}, expected {killed_at}",
                "lines": lines,
                "run_id": run_id,
            }

        for i, step_name in enumerate(STEPS[killed_at:], start=killed_at + 1):
            agent2.advance()
            call = resumed.record(
                "tool_call",
                {"tool": f"step.{i}", "name": step_name},
                idempotency_key=f"step:{i}:call",
            )
            resumed.record(
                "tool_result",
                {"ok": True, "summary": f"completed: {step_name}"},
                causation_id=call.event_id,
                idempotency_key=f"step:{i}:result",
            )
            resumed.checkpoint()
            lines.append(f"[step {i}/{len(STEPS)}] {step_name}  (after resume)")

        resumed.complete({"ok": True})

        # ── Fork from kill-point checkpoint ────────────────────────────
        chks = agent2.list_checkpoints()
        if len(chks) >= KILL_AFTER_STEP:
            kill_ck = chks[KILL_AFTER_STEP - 1].id
        elif chks:
            kill_ck = chks[0].id
        else:
            return {
                "ok": False,
                "error": "No checkpoint available to fork",
                "lines": lines,
                "run_id": run_id,
            }

        branch = agent2.fork_run(checkpoint_id=kill_ck, run_id=run_id, label="alt-model")
        lines.append("")
        lines.append(
            f"[fork] child_run={branch.run_id}  parent={run_id}  "
            f"from_checkpoint={kill_ck}  label=alt-model"
        )

        # ── Context pack ──────────────────────────────────────────────
        ctx = agent2.build_context(
            "Summarize incident remediation status",
            budget_tokens=800,
        )
        selected = int(getattr(ctx, "token_count", 0) or 0)
        budget = int(getattr(ctx, "budget_tokens", 0) or 0)
        # ContextBundle.savings_vs_naive = fraction saved vs dumping all memories
        savings = float(getattr(ctx, "savings_vs_naive", 0.0) or 0.0)
        discarded = None
        raw_est = None
        if selected and 0.0 < savings < 1.0:
            denom = 1.0 - savings
            raw_est = int(round(selected / denom))
            discarded = max(0, raw_est - selected)

        lines.append("")
        lines.append("[context]")
        lines.append(f"  selected_tokens  {selected}")
        lines.append(f"  budget_tokens    {budget}")
        if raw_est is not None:
            lines.append(f"  raw_tokens       {raw_est}")
        if discarded is not None:
            lines.append(f"  discarded_tokens {discarded}")
        lines.append(f"  savings_vs_naive {savings}")
        preview = (ctx.text or "")[:160]
        lines.append(f"  preview: {preview!r}...")

        # ── Audit timeline ─────────────────────────────────────────────
        lines.append("")
        lines.append("[audit] durable run_events (Mode B timeline — not tool re-exec)")
        all_events = agent2.inspect_events(run_id=run_id)
        for e in all_events[:40]:
            lines.append(f"  seq={e.sequence:03d}  {e.type:18s}  actor={e.actor}")
        n_events = len(all_events)
        if n_events > 40:
            lines.append(f"  ... ({n_events - 40} more)")

        lines.append("")
        lines.append("Kill-the-Agent demo complete.")
        lines.append(
            f"  killed_at={killed_at}  resumed_step={step_before_death}  "
            f"events={n_events}  fork={branch.run_id}"
        )

        return {
            "ok": True,
            "lines": lines,
            "run_id": run_id,
            "fork_run_id": branch.run_id,
            "killed_at_step": killed_at,
            "resumed_step": payload.step,
            "event_count": n_events,
            "context_selected_tokens": selected,
            "context_raw_tokens": raw_est,
            "db_path": kwargs["db_path"],
            "omem_schema": "omem_v1",
        }
    finally:
        if agent2 is not None:
            try:
                agent2.close()
            except Exception:
                pass
