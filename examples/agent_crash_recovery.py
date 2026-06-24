"""Example: Agent Crash Recovery with OMem StateOS

This script demonstrates the complete Phase 2 state lifecycle:

  1. Agent starts a session and sets a goal + plan
  2. Agent executes tools, checkpointing after each one
  3. Agent "crashes" mid-execution (simulated)
  4. Agent restarts and recovers from the last checkpoint
  5. Agent forks from a snapshot to explore an alternative approach
  6. Winning branch is merged back to the base session

Run:
    python examples/agent_crash_recovery.py

No external services needed — uses in-memory backend.
"""

import time

from omem.state import InMemoryStateBackend, StateOS, StatePayload, ToolResult
from omem.state.exceptions import CheckpointNotFoundError

# ── Helpers ──────────────────────────────────────────────────────────────────

BOLD = "\033[1m"
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"


def header(text: str) -> None:
    print(f"\n{BOLD}{CYAN}{'─' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{BOLD}{CYAN}{'─' * 60}{RESET}")


def step(text: str) -> None:
    print(f"  {GREEN}▶{RESET}  {text}")


def warn(text: str) -> None:
    print(f"  {YELLOW}⚠{RESET}  {text}")


def info(text: str) -> None:
    print(f"  {CYAN}ℹ{RESET}  {text}")


# ── Simulated tool functions ──────────────────────────────────────────────────

def tool_fetch_data() -> dict:
    """Simulates a data fetch tool."""
    time.sleep(0.05)
    return {"rows": 1_200, "source": "s3://omem-datasets/train.parquet"}


def tool_clean_data(rows: int) -> dict:
    """Simulates a data cleaning tool."""
    time.sleep(0.05)
    dropped = int(rows * 0.02)
    return {"rows_clean": rows - dropped, "dropped": dropped}


def tool_train_model(rows: int) -> dict:
    """Simulates model training — the expensive step."""
    time.sleep(0.1)
    return {"accuracy": 0.924, "epochs": 10, "rows_used": rows}


def tool_evaluate(accuracy: float) -> dict:
    return {"pass": accuracy >= 0.90, "score": accuracy, "threshold": 0.90}


# ── Main demo ─────────────────────────────────────────────────────────────────

def main() -> None:
    backend = InMemoryStateBackend()
    state = StateOS(backend=backend)
    SESSION = "ml-pipeline-agent"

    # ──────────────────────────────────────────────────────────────────────
    header("Phase 1 — Agent Boot: Create session, set goal and plan")
    # ──────────────────────────────────────────────────────────────────────

    state.save(SESSION, StatePayload(session_id=SESSION))
    state.set_goal(SESSION, "Train and evaluate a sentiment classifier")
    state.set_plan(SESSION, [
        "Fetch training data",
        "Clean and validate data",
        "Train model",
        "Evaluate and gate",
    ])
    step(f"Session '{SESSION}' created")
    step(f"Goal: {state.load(SESSION).goal}")
    step(f"Plan: {state.load(SESSION).plan}")

    # ──────────────────────────────────────────────────────────────────────
    header("Phase 2 — Execution: tools + checkpoint after each step")
    # ──────────────────────────────────────────────────────────────────────

    # Step 0: Fetch data
    step("Running tool: fetch_data ...")
    fetch_result = tool_fetch_data()
    state.record_tool(SESSION, ToolResult(
        tool="fetch_data",
        input={"source": "s3://omem-datasets/"},
        output=fetch_result,
    ))
    state.advance(SESSION)
    chk1 = state.checkpoint(SESSION)
    info(f"Checkpoint after fetch: {chk1}")

    # Step 1: Clean data
    step("Running tool: clean_data ...")
    clean_result = tool_clean_data(fetch_result["rows"])
    state.record_tool(SESSION, ToolResult(
        tool="clean_data",
        input={"rows": fetch_result["rows"]},
        output=clean_result,
    ))
    state.advance(SESSION)
    chk2 = state.checkpoint(SESSION)
    info(f"Checkpoint after clean:  {chk2}")

    # Create a named snapshot before the expensive training step
    snap = state.snapshot(SESSION, label="pre-train")
    step(f"Snapshot '{snap.label}' created: {snap.id}")

    # ──────────────────────────────────────────────────────────────────────
    header("Phase 3 — Simulated crash mid-training")
    # ──────────────────────────────────────────────────────────────────────

    step("Running tool: train_model ... (this will crash!)")
    # Simulate partial work before crash — no checkpoint written
    state.set_workflow(SESSION, "_training_started", True)

    warn("💥  Agent process crashed! (simulated)")
    warn("    Restarting with a fresh StateOS instance ...")

    # Simulate restart: new StateOS pointing at the same backend
    restarted_state = StateOS(backend=backend)

    # ──────────────────────────────────────────────────────────────────────
    header("Phase 4 — Crash recovery from checkpoint")
    # ──────────────────────────────────────────────────────────────────────

    recovered = restarted_state.resume_latest(SESSION)
    step(f"Recovered! Step={recovered.step}, status={recovered.status}")
    step(f"  tool_outputs so far: {[t.tool for t in recovered.tool_outputs]}")

    # Verify the partial work from after the last checkpoint is gone
    assert "_training_started" not in recovered.workflow_state, \
        "Partial state from the crash should not be present after recovery!"
    step("✓  No partial crash state leaked into recovered payload")

    # ──────────────────────────────────────────────────────────────────────
    header("Phase 5 — Fork: try two different training strategies in parallel")
    # ──────────────────────────────────────────────────────────────────────

    branch_a = restarted_state.fork(snap.id, new_session_id="train-strategy-A")
    branch_b = restarted_state.fork(snap.id, new_session_id="train-strategy-B")
    step(f"Branch A: {branch_a} (default hyperparams)")
    step(f"Branch B: {branch_b} (higher learning rate)")

    # Run training on both branches
    for branch_id, label in [(branch_a, "default"), (branch_b, "aggressive")]:
        result = tool_train_model(clean_result["rows_clean"])
        restarted_state.record_tool(
            branch_id,
            ToolResult(
                tool="train_model",
                input={"strategy": label},
                output=result,
            ),
        )
        restarted_state.advance(branch_id)
        eval_result = tool_evaluate(result["accuracy"])
        restarted_state.record_tool(
            branch_id,
            ToolResult(tool="evaluate", input={}, output=eval_result),
        )
        step(f"  {branch_id}: accuracy={result['accuracy']:.3f}, pass={eval_result['pass']}")

    # ──────────────────────────────────────────────────────────────────────
    header("Phase 6 — Merge the winning branch back to base")
    # ──────────────────────────────────────────────────────────────────────

    # Pick the winner (branch A has better lineage traceability here — same result)
    merged = restarted_state.merge(
        winning_session_id=branch_a,
        losing_session_id=branch_b,
    )
    step(f"Merged! Session '{branch_a}' is now the canonical result")
    step(f"  version={merged.version}, tool_calls={len(merged.tool_outputs)}")

    # ──────────────────────────────────────────────────────────────────────
    header("Final session summary")
    # ──────────────────────────────────────────────────────────────────────

    summary = restarted_state.summary(branch_a)
    for key, val in summary.items():
        if key == "updated_at":
            val = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(val)))
        print(f"  {key:<22} {val}")

    print(f"\n{GREEN}{BOLD}All done!{RESET} The agent recovered, forked, and merged successfully.\n")


if __name__ == "__main__":
    main()
