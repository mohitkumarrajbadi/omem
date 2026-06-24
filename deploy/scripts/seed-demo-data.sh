#!/usr/bin/env bash
# seed-demo-data.sh — populate a demo org with sample state for the leadership demo.
#
# Seeds the 8-step leadership demo described in FULL_IMPLEMENTATION_PLAN.md:
#   1-3.  Coding agent runs a 10-step refactor with checkpoints
#   4-5.  Fork + plan B
#   6.    Context engine token savings
#   7.    Shared org memory
#   8.    Audit trail
#
# Usage:
#   export OMEM_ENDPOINT=https://state-preview.akamai.ai
#   export OMEM_API_KEY=omem_sk_demo_...
#   ./deploy/scripts/seed-demo-data.sh

set -euo pipefail

: "${OMEM_ENDPOINT:?Set OMEM_ENDPOINT first}"
: "${OMEM_API_KEY:?Set OMEM_API_KEY first}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR/../.."

echo "==> Seeding demo data at $OMEM_ENDPOINT"
echo ""

python3 - << 'PYTHON'
import os, sys
sys.path.insert(0, os.environ.get("REPO_ROOT", "."))

# Once AgentState + CloudBackend are implemented (Cloud Phase C1),
# this script will drive the full 8-step leadership demo.
# For now it prints the demo script structure.

steps = [
    "Agent starts 10-step auth refactor; checkpoints every 3 steps",
    "Kill process at step 7",
    "state.resume(checkpoint) — agent continues at step 7",
    "state.fork(snap) — create Plan B branch",
    "Run Plan A and Plan B in parallel",
    "state.merge(winner) — rollback loser, keep winner",
    "context.build(budget=6000) — show token savings vs naive",
    "Agent A writes org memory; Agent B recalls it",
]

print("Leadership demo steps (to be automated after Cloud Phase C1):")
for i, step in enumerate(steps, 1):
    print(f"  {i}. {step}")

print()
print("Seed script complete. Wire up AgentState + CloudBackend in Cloud Phase C1.")
PYTHON
