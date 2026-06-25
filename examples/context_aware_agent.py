"""Example: Context-Aware Agent with OMem Phase 3

This script demonstrates the complete Phase 3 context engine:

  1. Agent accumulates memories across a coding task
  2. Agent builds optimized LLM context from memory + session state
  3. Context respects a token budget (6,000 tokens default)
  4. Savings vs naive "dump all memories" are measured
  5. Different modes (planning, coding) produce different context shapes

Run:
    python examples/context_aware_agent.py

Requires: omem installed (pip install -e .)
Uses in-memory backends — no disk I/O, no external services.
"""

import time

from omem import AgentState, ContextEngine, ContextRequest

# ── Helpers ──────────────────────────────────────────────────────────────────

BOLD = "\033[1m"
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def header(text: str) -> None:
    print(f"\n{BOLD}{CYAN}{'─' * 64}{RESET}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{BOLD}{CYAN}{'─' * 64}{RESET}")


def step(text: str) -> None:
    print(f"  {GREEN}▶{RESET}  {text}")


def info(text: str) -> None:
    print(f"  {CYAN}ℹ{RESET}  {text}")


# ── Demo corpus ───────────────────────────────────────────────────────────────


AUTH_MEMORIES = [
    "JWT is used for stateless auth — no DB lookup needed per request",
    "The auth service OOM-crashed last Tuesday due to unbounded token cache",
    "Decision: migrate to OAuth2 PKCE — better security for public clients",
    "Legacy session store uses MD5 — flagged for removal, creates security debt",
    "Password hashing uses bcrypt cost=12 — do NOT lower below 10",
    "Rate limiting: 100 req/min per IP via Redis sliding window",
    "Auth tokens expire in 15 minutes; refresh tokens valid for 7 days",
    "CORS whitelist: api.company.com, app.company.com, localhost:3000 only",
    "Step-by-step PKCE migration: 1) Add verifier 2) Update /authorize 3) Test 4) Rollout",
    "Last quarter: OAuth2 reduced login latency from 800ms → 200ms at Company X",
    "The /api/me endpoint is called on every page load — optimize with CDN edge caching",
    "PII is AES-256-GCM encrypted at rest; key rotation every 90 days via KMS",
    "Prefer server-side sessions for admin panel — simpler audit trail",
    "API contract: all endpoints return RFC 7807 Problem Details on errors",
    "The refresh token rotation policy prevents token replay attacks",
    "Frontend auth state lives in a secure HttpOnly cookie, NOT localStorage",
    "A/B test shows 12% higher conversion with the new OAuth flow vs old form",
    "The internal SSO gateway authenticates all internal service-to-service calls",
    "Known issue: Safari blocks third-party cookies — affects embedded widgets",
    "Compliance requirement: GDPR article 17 — user data deleted within 72h of request",
]


# ── Main demo ─────────────────────────────────────────────────────────────────


def main() -> None:
    # ──────────────────────────────────────────────────────────────────────
    header("Setup — Build a memory-rich OMem instance (in-memory backend)")
    # ──────────────────────────────────────────────────────────────────────

    agent = AgentState(
        session_id="auth-agent",
        backend="memory",         # in-memory OMem + in-memory StateOS
    )

    step(f"Agent created: {agent}")
    step("Loading 20 auth-domain memories into the store ...")

    for content in AUTH_MEMORIES:
        agent.memory.remember(content, namespace="auth")

    mem_count = len(agent.memory.list(namespace="auth"))
    step(f"Memory store: {mem_count} memories in namespace 'auth'")

    # ──────────────────────────────────────────────────────────────────────
    header("Session State — Set goal, plan, tool history")
    # ──────────────────────────────────────────────────────────────────────

    agent.set_goal("Migrate auth module to OAuth2 PKCE — secure and fast")
    agent.set_plan([
        "Audit current auth endpoints",
        "Implement PKCE backend",
        "Update frontend login flow",
        "Load test under 10k concurrent users",
        "Gradual rollout: 10% → 50% → 100%",
    ])

    agent.record_tool("audit_auth", output={"endpoints": 14, "insecure": 3})
    agent.advance()  # Step 0 → 1 (audit done)

    agent.record_tool("read_file", output={"file": "auth/pkce.py", "lines": 312})
    agent.checkpoint()

    state_summary = agent.summary()
    step(f"Session state: goal set, step {state_summary['step']} of "
         f"{state_summary['plan_length']}, {state_summary['tool_calls']} tool calls")

    # ──────────────────────────────────────────────────────────────────────
    header("Phase 3 — Build context for the LLM (planning mode, 3000 token budget)")
    # ──────────────────────────────────────────────────────────────────────

    ctx = agent.build_context(
        task="Continue the PKCE backend implementation",
        budget_tokens=3000,
        mode="planning",
    )

    step("Context assembled in planning mode")
    info(f"Token count:    {ctx.token_count:,} of 3,000")
    info(f"Memories used:  {len(ctx.memories_used)} of {mem_count}")
    info(f"State included: {ctx.state_included}")
    info(f"Savings:        {ctx.savings_vs_naive:.0%} vs full dump")
    print()
    print(ctx.text)

    # ──────────────────────────────────────────────────────────────────────
    header("Estimate savings before committing to a build")
    # ──────────────────────────────────────────────────────────────────────

    savings_stats = agent.estimate_context_savings(
        task="What are the security risks in the current auth module?",
        budget_tokens=2000,
    )
    step("Token efficiency preview:")
    for key, val in savings_stats.items():
        if key == "savings_pct":
            val = f"{val}%"
        info(f"  {key:<25} {val}")

    # ──────────────────────────────────────────────────────────────────────
    header("Mode comparison — coding vs planning mode")
    # ──────────────────────────────────────────────────────────────────────

    for mode in ["planning", "coding", "chat"]:
        ctx_m = agent.build_context(
            task="Implement the PKCE code challenge in Python",
            budget_tokens=2000,
            mode=mode,
        )
        step(
            f"  mode={mode:<10} tokens={ctx_m.token_count:>4,}  "
            f"memories={len(ctx_m.memories_used):>2}  "
            f"savings={ctx_m.savings_vs_naive:.0%}"
        )

    # ──────────────────────────────────────────────────────────────────────
    header("Standalone ContextEngine (without AgentState)")
    # ──────────────────────────────────────────────────────────────────────


    engine = ContextEngine(
        memory=agent.memory,
        state=agent.state,
        cache_ttl=60.0,
    )

    for _ in range(3):
        req = ContextRequest(
            task="Review PKCE implementation for security issues",
            budget_tokens=4000,
            session_id="auth-agent",
        )
        t0 = time.perf_counter()
        ctx2 = engine.build(req)
        elapsed = (time.perf_counter() - t0) * 1000

    step("First call: fresh build | Subsequent calls: cached")
    info(f"Last build latency: {elapsed:.2f}ms | cached: {ctx2.assembled_at == engine.build(req).assembled_at}")
    step("Cache hit confirmed — same assembled_at timestamp")

    print(f"\n{GREEN}{BOLD}Phase 3 complete!{RESET} "
          f"The context engine delivered {ctx.savings_vs_naive:.0%} token savings "
          f"on the auth-domain task.\n")


if __name__ == "__main__":
    main()
