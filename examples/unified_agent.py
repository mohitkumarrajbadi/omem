"""Unified Agent — Phase 5 demonstration.

Shows how ``AgentState`` acts as the single import, single object entry
point for building memory-native AI agents. Every capability from Phase 1
through Phase 4 is accessible through this one interface.

Sections demonstrated:
    1. Three construction patterns (kwargs, AgentConfig, factory methods)
    2. Memory shortcuts (remember, recall, forget, consolidate)
    3. Session state (goal, plan, advance, tools, workflow)
    4. Knowledge graph (learn, know_about, reason)
    5. Context assembly for LLM prompts
    6. Snapshot + rollback workflow
    7. Checkpoint + crash-recovery
    8. Clone — fork the session into a parallel experiment
    9. Export / import for agent handoff
   10. Context manager — checkpoint on clean exit
   11. Status dashboard

Run:
    python examples/unified_agent.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from omem import AgentConfig, AgentState


def section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)


def sub(title: str) -> None:
    print(f"\n  ── {title}")


def main() -> None:
    print("OMem — Phase 5: Unified AgentState Demo")
    print("One import. One object. All layers.\n")

    # ══════════════════════════════════════════════════════════════════
    section("1. Construction Patterns")
    # ══════════════════════════════════════════════════════════════════

    sub("Option A: keyword args (backward compatible)")
    a1 = AgentState(session_id="agent-kwarg", backend="memory")
    print(f"  {repr(a1)}")

    sub("Option B: AgentConfig (explicit, validated, env-loadable)")
    cfg = AgentConfig(
        session_id="agent-config",
        namespace="demo",
        backend="memory",
        context_budget_tokens=8000,
        context_default_mode="planning",
        auto_checkpoint=False,
    )
    a2 = AgentState.from_config(cfg)
    print(f"  {repr(a2)}")
    print(f"  config.is_cloud = {a2.config.is_cloud}")

    sub("Option C: ephemeral() — no persistence, no disk I/O")
    a3 = AgentState.ephemeral(session_id="agent-eph")
    print(f"  {repr(a3)}")
    print(f"  db_path = {a3.db_path!r}")  # None

    # Use the ephemeral agent for the rest of the demo
    agent = a3

    # ══════════════════════════════════════════════════════════════════
    section("2. Memory Shortcuts")
    # ══════════════════════════════════════════════════════════════════

    memories_to_add = [
        ("We're building an AI memory OS called OMem", 0.9),
        ("FastAPI is used for the REST API layer", 0.8),
        ("Python is the primary implementation language", 0.7),
        ("Rust handles performance-critical operations like SIMD scoring", 0.8),
        ("SQLite is used for local persistence with WAL mode", 0.6),
        ("The project targets Akamai Linode for managed cloud deployment", 0.9),
        ("AgentState is the unified facade composing all v2 layers", 0.9),
    ]

    print()
    for content, importance in memories_to_add:
        mid = agent.remember(content, importance=importance)
        print(f"  [{mid[:8]}] {content[:60]}…")

    sub("recall()")
    results = agent.recall("OMem architecture layers", k=3)
    print(f"  Query: 'OMem architecture layers' → {len(results)} results")
    for mem in results:
        score = getattr(mem, "score", mem.importance)
        print(f"    [{score:.2f}] {mem.content[:70]}")

    sub("consolidate()")
    result = agent.consolidate(speed="fast")
    print(f"  Consolidation: {result}")

    # ══════════════════════════════════════════════════════════════════
    section("3. Session State")
    # ══════════════════════════════════════════════════════════════════

    agent.set_goal("Ship Phase 5 of OMem")
    agent.set_plan([
        "Finalize AgentState facade",
        "Write comprehensive tests",
        "Create unified example",
        "Run full test suite",
        "Tag v0.5.0 release",
    ])

    print()
    payload = agent.current_state()
    print(f"  Goal    : {payload.goal}")
    print(f"  Plan    : {payload.plan}")
    print(f"  Status  : {payload.status}")

    sub("Recording tool outputs")
    agent.record_tool("test_runner", {"tests": 559, "passed": 559, "failed": 0})
    agent.record_tool("linter", {"files": 7, "errors": 0})

    sub("Advancing through plan steps")
    agent.advance()
    agent.advance()
    p = agent.current_state()
    print(f"  Progress: step {p.step + 1} of {len(p.plan)}")

    agent.set_workflow("release_tag", "v0.5.0")
    agent.set_workflow("build_system", "maturin")

    # ══════════════════════════════════════════════════════════════════
    section("4. Knowledge Graph Shortcuts")
    # ══════════════════════════════════════════════════════════════════

    facts = [
        ("OMem", "uses", "FastAPI", 1.0),
        ("OMem", "uses", "Python", 1.0),
        ("OMem", "uses", "Rust", 0.95),
        ("OMem", "uses", "SQLite", 1.0),
        ("FastAPI", "depends_on", "Python", 1.0),
        ("OMem", "deployed_on", "Akamai Linode", 0.9),
        ("AgentState", "composes", "MemoryOS", 1.0),
        ("AgentState", "composes", "StateOS", 1.0),
        ("AgentState", "composes", "ContextEngine", 1.0),
        ("AgentState", "composes", "KnowledgeOS", 1.0),
    ]

    print()
    for s, p, o, conf in facts:
        agent.learn(s, p, o, confidence=conf)

    print(f"  Asserted {len(facts)} knowledge graph relations")

    sub("know_about()")
    sg = agent.know_about("OMem", depth=2)
    print(f"  Subgraph(OMem, depth=2): {sg.entity_count} entities, {sg.edge_count} edges")
    for edge in sg.edges[:5]:
        print(f"    {edge.source} —[{edge.predicate}]→ {edge.target}")

    sub("reason()")
    results = agent.reason("What does AgentState compose?")
    print("  Q: 'What does AgentState compose?'")
    for r in results[:4]:
        tag = "⬥" if r.inference_type == "direct" else "◇"
        print(f"    {tag} [{r.confidence:.2f}] {r.statement}")

    sub("knowledge_stats()")
    ks = agent.knowledge_stats()
    print(f"  Entities: {ks.total_entities}  Edges: {ks.total_edges}  "
          f"Avg centrality: {ks.avg_centrality:.3f}")

    # ══════════════════════════════════════════════════════════════════
    section("5. Context Assembly for LLM")
    # ══════════════════════════════════════════════════════════════════

    ctx = agent.build_context(
        task="finalize AgentState documentation",
        budget_tokens=4000,
        mode="planning",
    )
    print(f"\n  Token budget : {ctx.budget_tokens:,}")
    print(f"  Tokens used  : {ctx.token_count:,}")
    print(f"  Savings      : {ctx.savings_vs_naive:.0%} vs naive dump")
    print(f"  Memories used: {len(ctx.memories_used)}")
    print(f"  State incl.  : {ctx.state_included}")
    print("\n  --- Context bundle preview (first 300 chars) ---")
    print(f"  {ctx.text[:300]}...")

    sub("estimate_context_savings()")
    est = agent.estimate_context_savings("write release notes", budget_tokens=5000)
    for k, v in est.items():
        print(f"    {k:<25} {v}")

    # ══════════════════════════════════════════════════════════════════
    section("6. Snapshot + Rollback")
    # ══════════════════════════════════════════════════════════════════

    snap = agent.snapshot(label="before-final-step")
    print(f"\n  Snapshot created: {snap.id[:12]}…  label={snap.label!r}")

    # Simulate an incorrect advancement
    agent.advance()
    agent.advance()  # now on step 4 (too far)
    print(f"  After two advances: step={agent.current_state().step}")

    agent.rollback(snap.id)
    print(f"  After rollback:     step={agent.current_state().step}")

    snaps = agent.list_snapshots()
    print(f"  Total snapshots: {len(snaps)}")

    # ══════════════════════════════════════════════════════════════════
    section("7. Checkpoint + Crash Recovery")
    # ══════════════════════════════════════════════════════════════════

    agent.set_goal("Deploy OMem v0.5.0 to Linode")
    chk_id = agent.checkpoint()
    print(f"\n  Checkpoint: {chk_id[:12]}…")

    # Simulate destructive change
    agent.set_goal("CORRUPTED GOAL — do not deploy")

    # Recovery
    recovered = agent.resume()
    print(f"  Goal after crash recovery: {recovered.goal!r}")

    chks = agent.list_checkpoints()
    print(f"  Total checkpoints: {len(chks)}")

    # ══════════════════════════════════════════════════════════════════
    section("8. Clone — Parallel Experiments")
    # ══════════════════════════════════════════════════════════════════

    agent.set_goal("Main branch: standard deployment")
    experiment = agent.clone(new_session_id="experiment-linode-k8s", label="pre-experiment")

    # Run the experiment independently
    experiment.set_goal("Experimental: Kubernetes deployment on Linode LKE")
    experiment.learn("OMem", "deployed_on", "Linode LKE", confidence=0.7)
    experiment.record_tool("helm", {"chart": "omem", "namespace": "ai"})

    print()
    print(f"  Main     goal: {agent.current_state().goal!r}")
    print(f"  Experiment:    {experiment.current_state().goal!r}")
    print(f"  Shared memory: {experiment._memory is agent._memory}")
    print(f"  Shared graph:  {experiment._knowledge is agent._knowledge}")

    # ══════════════════════════════════════════════════════════════════
    section("9. Export / Import — Agent Handoff")
    # ══════════════════════════════════════════════════════════════════

    agent.set_goal("Handoff: review and sign-off before release")
    export_data = agent.export_state()

    print()
    print(f"  Exported session : {export_data['session_id']!r}")
    print(f"  Snapshots saved  : {len(export_data['snapshots'])}")
    print(f"  Checkpoints saved: {len(export_data['checkpoints'])}")
    print(f"  JSON size        : ~{len(json.dumps(export_data)) // 1024}KB")

    # Restore into a fresh session (simulates handoff to another process)
    fresh = AgentState.ephemeral(session_id="reviewer-agent")
    restored = fresh.restore_state(export_data)
    print(f"\n  Restored goal : {restored.goal!r}")
    print(f"  Restored step : {restored.step}")

    # ══════════════════════════════════════════════════════════════════
    section("10. Context Manager — Auto-Checkpoint on Exit")
    # ══════════════════════════════════════════════════════════════════

    print()
    managed_cfg = AgentConfig(
        session_id="managed-agent",
        backend="memory",
        auto_checkpoint=True,
    )
    with AgentState(config=managed_cfg) as a:
        a.set_goal("Context-managed task")
        a.remember("managed agent memory")
        print(f"  Inside context: goal={a.current_state().goal!r}")
    # __exit__ wrote a checkpoint automatically
    chks = a.list_checkpoints()
    print(f"  After exit: {len(chks)} auto-checkpoint(s) written")

    # ══════════════════════════════════════════════════════════════════
    section("11. Status Dashboard")
    # ══════════════════════════════════════════════════════════════════

    status = agent.status()
    print()
    print(f"  session   : {status['session_id']}")
    print(f"  namespace : {status['namespace']}")
    print(f"  backend   : {status['backend']}")
    print(f"  is_cloud  : {status['is_cloud']}")
    print()
    if "memory" in status and "error" not in status["memory"]:
        print(f"  Memory    : {status['memory'].get('total_memories', '?')} memories")
    if "state" in status and "error" not in status["state"]:
        print(f"  Goal      : {status['state'].get('goal', '?')!r}")
    if "knowledge" in status and "error" not in status["knowledge"]:
        k = status["knowledge"]
        print(f"  Knowledge : {k['entities']} entities, {k['edges']} edges")
    if "context" in status:
        print(f"  Context   : budget={status['context']['budget_tokens']} "
              f"mode={status['context']['default_mode']!r}")

    # Full __str__ representation
    print()
    print("  agent.__str__():")
    for line in str(agent).split("\n"):
        print(f"    {line}")

    print()
    print("─" * 60)
    print("  Phase 5 demo complete.")
    print("  AgentState: One import. One object. All layers.")
    print("─" * 60)
    print()


if __name__ == "__main__":
    main()
