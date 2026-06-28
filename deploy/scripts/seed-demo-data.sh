#!/usr/bin/env bash
# seed-demo-data.sh — Full 8-step Akamai leadership demo
#
# Seeds a live OMem Cloud instance with a realistic agent scenario:
#   1–3.  Coding agent runs a 10-step auth refactor with auto-checkpoints
#   4–5.  Fork + Plan A / Plan B (parallel branches)
#   6.    Merge winner, archive loser
#   7.    Context engine token savings demonstration
#   8.    Shared org memory (Agent A writes → Agent B recalls)
#   9.    Audit trail verification
#
# Usage:
#   export OMEM_ENDPOINT=http://localhost/   # or https://your-linode-ip
#   export OMEM_API_KEY=omem_sk_demo_...    # optional
#   ./deploy/scripts/seed-demo-data.sh
#
# Output: coloured step-by-step results with token savings % and audit counts.

set -eo pipefail

BASE="${OMEM_ENDPOINT:-http://localhost}"
BASE="${BASE%/}"   # strip trailing slash
SESSION="demo-refactor-$(date +%s)"
PLAN_A="${SESSION}-plan-a"
PLAN_B="${SESSION}-plan-b"
ORG_NS="org/akamai-demo"

AUTH_HDR=()
if [[ -n "${OMEM_API_KEY:-}" ]]; then
  AUTH_HDR=(-H "Authorization: Bearer $OMEM_API_KEY")
fi

_hdr() {
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  STEP $1 — $2"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

_api() {
  local method="$1"; local path="$2"; shift 2
  curl -sf -X "$method" "$BASE$path" \
    -H "Content-Type: application/json" \
    -H "X-OMem-Session: $SESSION" \
    "${AUTH_HDR[@]}" \
    "$@" | python3 -m json.tool
}

_api_ns() {
  local method="$1"; local path="$2"; local ns="$3"; shift 3
  curl -sf -X "$method" "$BASE$path" \
    -H "Content-Type: application/json" \
    -H "X-OMem-Session: $SESSION" \
    -H "X-OMem-Namespace: $ns" \
    "${AUTH_HDR[@]}" \
    "$@" | python3 -m json.tool
}

# ─────────────────────────────────────────────────────────────────────────────
# Preflight
# ─────────────────────────────────────────────────────────────────────────────
echo "==> Checking API health at $BASE"
curl -sf "$BASE/v1/health" | python3 -m json.tool
echo ""
echo "Session:   $SESSION"
echo "Plan A:    $PLAN_A"
echo "Plan B:    $PLAN_B"
echo "Org NS:    $ORG_NS"

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Set goal + populate memories from a 10-step refactor
# ─────────────────────────────────────────────────────────────────────────────
_hdr 1 "Agent starts 10-step auth refactor — sets goal and remembers each step"

_api POST /v1/goal -d "{\"goal\": \"Refactor auth module: migrate from JWT v1 to JWT v2 with PKCE flow\", \"session_id\": \"$SESSION\"}"

steps=(
  "Analysed existing auth/jwt.py — 3 deprecated API calls identified"
  "Added PKCE code_verifier generation in auth/pkce.py"
  "Replaced jwt.encode(legacy=True) with jwt.encode() in 12 files"
  "Updated token expiry from 3600s to 900s per security audit recommendation"
  "Added refresh token rotation logic in auth/refresh.py"
  "Migrated unit tests in tests/test_auth.py — 47 tests updated"
  "Updated API gateway middleware to validate PKCE challenge"
  "Added backwards-compat shim for clients still on JWT v1"
  "Performance test: PKCE adds 1.2ms p99 overhead — acceptable"
  "Documentation updated in docs/auth/README.md"
)

echo ""
echo "--- Storing 10 refactor step memories ---"
for i in "${!steps[@]}"; do
  step_num=$((i + 1))
  curl -sf -X POST "$BASE/v1/remember" \
    -H "Content-Type: application/json" \
    -H "X-OMem-Session: $SESSION" \
    "${AUTH_HDR[@]}" \
    -d "{\"content\": \"Step $step_num: ${steps[$i]}\", \"importance\": 0.9}" > /dev/null
  echo "  [✓] Step $step_num stored"
done

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Checkpoint every 3 steps (simulate crash recovery)
# ─────────────────────────────────────────────────────────────────────────────
_hdr 2 "Auto-checkpoint at step 3, 6, 9 — crash recovery proof"

echo "--- Checkpoint at step 3 ---"
CHK_3=$(curl -sf -X POST "$BASE/v1/state/$SESSION/checkpoint" \
  -H "Content-Type: application/json" \
  -H "X-OMem-Session: $SESSION" \
  "${AUTH_HDR[@]}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('checkpoint_id',''))")
echo "  Checkpoint ID (step 3): $CHK_3"

echo ""
echo "--- Snapshot at step 6 (label: post-test-migration) ---"
SNAP_6=$(curl -sf -X POST "$BASE/v1/state/$SESSION/snapshot" \
  -H "Content-Type: application/json" \
  -H "X-OMem-Session: $SESSION" \
  "${AUTH_HDR[@]}" \
  -d '{"label": "post-test-migration"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('snapshot_id',''))")
echo "  Snapshot ID (step 6): $SNAP_6"

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — Simulate crash at step 7, then resume
# ─────────────────────────────────────────────────────────────────────────────
_hdr 3 "Simulated crash at step 7 — agent resumes from checkpoint"

echo "--- (Crash simulated) --- Calling resume..."
_api POST "/v1/state/$SESSION/resume"

echo ""
echo "--- Recalling context after resume ---"
curl -sf -X POST "$BASE/v1/recall" \
  -H "Content-Type: application/json" \
  -H "X-OMem-Session: $SESSION" \
  "${AUTH_HDR[@]}" \
  -d '{"query": "PKCE auth refactor progress", "k": 3}' | python3 -m json.tool

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — Fork: create Plan A and Plan B branches
# ─────────────────────────────────────────────────────────────────────────────
_hdr 4 "Fork into Plan A (keep PKCE) and Plan B (use OAuth Device Flow)"

echo "--- Forking Plan A ---"
curl -sf -X POST "$BASE/v1/state/$SESSION/fork" \
  -H "Content-Type: application/json" \
  -H "X-OMem-Session: $SESSION" \
  "${AUTH_HDR[@]}" \
  -d "{\"snapshot_id\": \"$SNAP_6\", \"new_session_id\": \"$PLAN_A\"}" | python3 -m json.tool

echo ""
echo "--- Forking Plan B ---"
curl -sf -X POST "$BASE/v1/state/$SESSION/fork" \
  -H "Content-Type: application/json" \
  -H "X-OMem-Session: $SESSION" \
  "${AUTH_HDR[@]}" \
  -d "{\"snapshot_id\": \"$SNAP_6\", \"new_session_id\": \"$PLAN_B\"}" | python3 -m json.tool

# Add memories to each branch to differentiate
curl -sf -X POST "$BASE/v1/remember" \
  -H "Content-Type: application/json" \
  -H "X-OMem-Session: $PLAN_A" \
  "${AUTH_HDR[@]}" \
  -d '{"content": "Plan A: Complete PKCE implementation — 1.2ms overhead, fully spec compliant", "importance": 0.95}' > /dev/null
echo ""
echo "  [✓] Plan A memory stored"

curl -sf -X POST "$BASE/v1/remember" \
  -H "Content-Type: application/json" \
  -H "X-OMem-Session: $PLAN_B" \
  "${AUTH_HDR[@]}" \
  -d '{"content": "Plan B: OAuth Device Flow — better for CLI clients but adds 800ms round-trip", "importance": 0.95}' > /dev/null
echo "  [✓] Plan B memory stored"

# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — Merge winner (Plan A wins — lower latency, spec compliant)
# ─────────────────────────────────────────────────────────────────────────────
_hdr 5 "Plan A wins — merge back into main session, archive Plan B"

curl -sf -X POST "$BASE/v1/state/$SESSION/merge" \
  -H "Content-Type: application/json" \
  -H "X-OMem-Session: $SESSION" \
  "${AUTH_HDR[@]}" \
  -d "{\"winner_session_id\": \"$PLAN_A\", \"loser_session_id\": \"$PLAN_B\", \"label\": \"pkce-winner-merged\"}" | python3 -m json.tool

# ─────────────────────────────────────────────────────────────────────────────
# STEP 6 — Token savings demonstration
# ─────────────────────────────────────────────────────────────────────────────
_hdr 6 "Context engine token savings — budget=4096 vs naive full history"

echo "--- Building optimised context (budget: 4096 tokens) ---"
CONTEXT_RESULT=$(curl -sf -X POST "$BASE/v1/context/build" \
  -H "Content-Type: application/json" \
  -H "X-OMem-Session: $SESSION" \
  "${AUTH_HDR[@]}" \
  -d '{"task": "Summarise the auth refactor progress and next steps", "budget_tokens": 4096}')

echo "$CONTEXT_RESULT" | python3 -m json.tool

echo ""
echo "$CONTEXT_RESULT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
token_count = data.get('token_count', 0)
budget      = data.get('budget_tokens', 4096)
savings     = data.get('savings_vs_naive', 0)
memories    = data.get('memories_used', [])
mem_count   = len(memories) if isinstance(memories, list) else memories
print(f'  Token count (optimised): {token_count}')
print(f'  Token budget:            {budget}')
print(f'  Memories used:           {mem_count}')
if savings:
    pct = abs(savings / max(token_count, 1)) * 100
    print(f'  Tokens saved vs naive:   {savings:+.0f}  ({pct:.0f}% reduction)')
else:
    print('  Token budget not exceeded — all memories fit within budget')
"

# ─────────────────────────────────────────────────────────────────────────────
# STEP 7 — Shared org memory (Agent A writes, Agent B recalls)
# Agents share memory via a common org-scoped session pool.
# Both agents use the org session ID so memories are pooled in the namespace.
# ─────────────────────────────────────────────────────────────────────────────
_hdr 7 "Shared org memory — Agent A writes to org pool, Agent B reads the same pool"

ORG_SESSION="org-pool-${SESSION}"   # shared session for the org namespace pool

echo "--- Agent A writing shared knowledge to org pool ---"
for fact in \
  "PKCE flow approved by security team on 2026-06-27" \
  "JWT v1 deprecation deadline: 2026-09-01" \
  "Auth service SLA: 99.95% uptime, p99 < 50ms" \
  "PKCE overhead: 1.2ms p99 — within acceptable budget"; do
  curl -sf -X POST "$BASE/v1/remember" \
    -H "Content-Type: application/json" \
    -H "X-OMem-Session: $ORG_SESSION" \
    -H "X-OMem-Namespace: $ORG_NS" \
    "${AUTH_HDR[@]}" \
    -d "{\"content\": \"$fact\", \"importance\": 0.85}" > /dev/null
  echo "  [A] $fact"
done

echo ""
echo "--- Agent B recalling from org pool (same session, same namespace) ---"
curl -sf -X POST "$BASE/v1/recall" \
  -H "Content-Type: application/json" \
  -H "X-OMem-Session: $ORG_SESSION" \
  -H "X-OMem-Namespace: $ORG_NS" \
  "${AUTH_HDR[@]}" \
  -d '{"query": "auth security and PKCE deadline", "k": 4}' | python3 -m json.tool

# ─────────────────────────────────────────────────────────────────────────────
# STEP 8 — Audit trail
# ─────────────────────────────────────────────────────────────────────────────
_hdr 8 "Governance audit trail — every write, delete, and fork timestamped"

echo "--- Querying audit log (last 20 entries) ---"
curl -sf "$BASE/v1/governance/audit?limit=20" \
  "${AUTH_HDR[@]}" | python3 -m json.tool

echo ""
echo "--- Session status dashboard ---"
curl -sf "$BASE/v1/state/$SESSION/status" \
  -H "X-OMem-Session: $SESSION" \
  "${AUTH_HDR[@]}" | python3 -m json.tool

# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  DEMO COMPLETE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Session:        $SESSION"
echo "  Plan A (winner): $PLAN_A"
echo "  Plan B (loser):  $PLAN_B"
echo "  Org namespace:   $ORG_NS"
echo ""
echo "  Swagger UI:  $BASE/docs"
echo "  Metrics:     $BASE/v1/metrics"
echo "  Audit trail: $BASE/v1/governance/audit"
echo ""
echo "  Akamai pillars demonstrated:"
echo "  [✓] State       — checkpoint / resume / fork / merge"
echo "  [✓] Memory      — tiered storage, hybrid scoring, importance"
echo "  [✓] Token saving — context engine with budget"
echo "  [✓] Multi-agent — shared org namespace"
echo "  [✓] Governance  — retention policies + audit trail"
echo "  [✓] Trust       — API key auth + RBAC headers"
echo ""
