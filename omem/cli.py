"""OMem CLI — a clean, fast command line for agent memory and state."""

import json
import os
import sys
import time
from collections import OrderedDict
from difflib import get_close_matches
from typing import Any, Dict, List, Optional

import click

from . import __version__
from .api import OMem
from .types import MemoryType

# ──────────────────────────────────────────────────────────────────────────────
# Visual system — one consistent look across every command.
#
# Principles: clear language, calm color, helpful next steps. Color is disabled
# automatically when piped/redirected or when NO_COLOR / OMEM_NO_COLOR is set,
# so output stays clean in scripts, logs, and CI.
# ──────────────────────────────────────────────────────────────────────────────

GLYPH_OK = "✓"
GLYPH_ERR = "✗"
GLYPH_WARN = "!"
GLYPH_INFO = "•"
GLYPH_ARROW = "→"


def _color_enabled() -> bool:
    """Honor NO_COLOR (https://no-color.org) and our own opt-out."""
    if os.environ.get("NO_COLOR") or os.environ.get("OMEM_NO_COLOR"):
        return False
    return True


def _c(text: str, **style) -> str:
    """Style text, but quietly no-op when color is disabled."""
    if not _color_enabled():
        return text
    return click.style(text, **style)


def success(message: str) -> None:
    """A completed action."""
    click.echo(f"{_c(GLYPH_OK, fg='green', bold=True)} {message}")


def failure(message: str) -> None:
    """A failed action (written to stderr)."""
    click.echo(f"{_c(GLYPH_ERR, fg='red', bold=True)} {message}", err=True)


def warn(message: str) -> None:
    """A non-fatal warning."""
    click.echo(f"{_c(GLYPH_WARN, fg='yellow', bold=True)} {message}")


def note(message: str) -> None:
    """A neutral status line."""
    click.echo(f"{_c(GLYPH_INFO, fg='cyan')} {message}")


def hint(message: str) -> None:
    """A dimmed 'try this next' suggestion."""
    click.echo(f"  {_c(GLYPH_ARROW + ' ' + message, fg='bright_black')}")


def field(label: str, value: Any, width: int = 11) -> None:
    """A left-aligned key/value detail line, consistent everywhere."""
    click.echo(f"  {_c(f'{label:<{width}}', fg='bright_black')}  {value}")


def rule(width: int = 52) -> None:
    click.echo(_c("  " + "─" * width, fg="bright_black"))


_BANNER_ART = r"""
 ██████╗ ███╗   ███╗███████╗███╗   ███╗
██╔═══██╗████╗ ████║██╔════╝████╗ ████║
██║   ██║██╔████╔██║█████╗  ██╔████╔██║
██║   ██║██║╚██╔╝██║██╔══╝  ██║╚██╔╝██║
╚██████╔╝██║ ╚═╝ ██║███████╗██║ ╚═╝ ██║
 ╚═════╝ ╚═╝     ╚═╝╚══════╝╚═╝     ╚═╝
"""

CLI_BANNER = (
    _c(_BANNER_ART, fg="cyan", bold=True)
    + _c("  Agent State Infrastructure SDK", fg="white", bold=True)
    + "\n"
    + _c(
        "  Memory · State · Context · Knowledge · Governance\n",
        fg="bright_black",
    )
)

# Commands grouped by what you're trying to do, not by internal architecture.
# Canonical commands come first; thin legacy aliases are kept but de-emphasized
# at the bottom so the common path stays obvious.
COMMAND_GROUPS = OrderedDict(
    [
        ("Start here", ["agent", "status", "init", "demo"]),
        ("Memory", ["remember", "recall", "list", "inspect", "stats", "sleep", "clear"]),
        ("State & context", ["state", "context", "knowledge"]),
        ("Enterprise", ["observe", "provenance", "governance", "runtime", "org"]),
        ("Codebase", ["ingest", "sync", "codebase", "namespaces"]),
        ("Server & tools", ["serve", "dashboard", "bench", "health", "export", "import", "completion", "version"]),
        ("Aliases", ["add", "search", "maintain", "benchmark"]),
    ]
)


class OMemGroup(click.Group):
    """Click group with a categorized help screen and typo suggestions."""

    def format_help(self, ctx, formatter):
        formatter.write(CLI_BANNER)
        formatter.write("\n\n")
        self.format_usage(ctx, formatter)
        self.format_options(ctx, formatter)
        # Note: click.MultiCommand.format_options already calls format_commands
        # internally, so we do NOT call it again here to avoid duplication.

    def format_commands(self, ctx, formatter):
        commands = self.list_commands(ctx)
        mapped_commands = set()

        for category, cmd_list in COMMAND_GROUPS.items():
            available_cmds = [c for c in cmd_list if c in commands]
            if not available_cmds:
                continue
            with formatter.section(category):
                rows = []
                for name in available_cmds:
                    cmd = self.get_command(ctx, name)
                    if cmd is None:
                        continue
                    rows.append((name, cmd.get_short_help_str()))
                    mapped_commands.add(name)
                formatter.write_dl(rows)

        orphan_cmds = [c for c in commands if c not in mapped_commands]
        if orphan_cmds:
            with formatter.section("More"):
                rows = []
                for name in orphan_cmds:
                    cmd = self.get_command(ctx, name)
                    rows.append((name, cmd.get_short_help_str() if cmd else ""))
                formatter.write_dl(rows)

    def resolve_command(self, ctx, args):
        """Resolve a command, with a friendly 'did you mean' on a typo."""
        try:
            return super().resolve_command(ctx, args)
        except click.UsageError:
            cmd_name = args[0] if args else ""
            matches = get_close_matches(cmd_name, self.list_commands(ctx), n=3, cutoff=0.6)
            lines = [f"Unknown command {cmd_name!r}."]
            if matches:
                suggestion = matches[0] if len(matches) == 1 else ", ".join(matches)
                lines.append(f"Did you mean: {suggestion}?")
            lines.append("Run 'omem --help' to see all commands.")
            raise click.UsageError("\n".join(lines)) from None

CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"], max_content_width=100)


def _get_omem(ctx: click.Context) -> OMem:
    config = ctx.obj or {}
    return OMem(
        backend=config.get("backend", "sqlite"),
        db_path=config.get("db_path"),
        embedding_provider=config.get("embedding_provider", "local"),
    )


def _format_duration(delta_seconds: float) -> str:
    if delta_seconds < 1:
        return f"{delta_seconds * 1000:.1f}ms"
    return f"{delta_seconds:.3f}s"


def _json_or_table(output: str, payload: Any, fmt: str):
    if fmt == "json":
        click.echo(json.dumps(payload, indent=2, sort_keys=True, default=str))
    else:
        click.echo(output)


def _resolve_memory_type(value: Optional[str]) -> Optional[MemoryType]:
    if not value:
        return None
    type_enum = getattr(MemoryType, value.upper(), None)
    if type_enum is None:
        valid = ", ".join(t.name for t in MemoryType)
        raise click.BadParameter(f"Unknown memory type '{value}'. Valid: {valid}")
    return type_enum


def _time_ago(timestamp: float) -> str:
    seconds = time.time() - timestamp
    if seconds < 60:
        return "now"
    elif seconds < 3600:
        return f"{int(seconds / 60)}m ago"
    elif seconds < 86400:
        return f"{int(seconds / 3600)}h ago"
    else:
        return f"{int(seconds / 86400)}d ago"


def _memory_to_payload(mem) -> Dict[str, Any]:
    return {
        "id": mem.id,
        "type": mem.type.name,
        "namespace": mem.namespace,
        "importance": mem.importance,
        "score": getattr(mem, "score", None),
        "confidence": getattr(mem, "confidence_score", None),
        "tier": getattr(mem.tier, "name", str(mem.tier)),
        "level": getattr(mem, "level", ""),
        "active": mem.active,
        "content": mem.content,
        "timestamp": mem.timestamp,
    }


def _print_memory_results(results, show_scores: bool = False) -> None:
    click.echo(_c(f"{len(results)} memories", fg="green", bold=True))
    click.echo("")
    for i, mem in enumerate(results, 1):
        score_text = ""
        if show_scores and getattr(mem, "score", None) is not None:
            score_text = f" score={mem.score:.3f}"
        confidence = getattr(mem, "confidence_score", 1.0)
        click.echo(
            f"{i}. [{mem.type.name}] importance={mem.importance:.2f} "
            f"confidence={confidence:.2f}{score_text}"
        )
        click.echo(f"   {mem.content[:100]}")
        click.echo(
            f"   id={mem.id[:12]} namespace={mem.namespace} level={getattr(mem, 'level', '')} {_time_ago(mem.timestamp)}\n"
        )


@click.group(
    cls=OMemGroup,
    context_settings=CONTEXT_SETTINGS,
    invoke_without_command=True,
)
@click.version_option(__version__, package_name="omem-os")
@click.option(
    "--db-path",
    default=None,
    help="Database path or connection string. Default: ~/.omem/brain.db",
)
@click.option(
    "--backend",
    default="sqlite",
    type=click.Choice(["sqlite", "memory", "postgres"]),
    help="Where to store data.",
)
@click.option(
    "--embedding-provider",
    default="local",
    type=click.Choice(["local", "openai", "sentence-transformers"]),
    help="How to turn text into embeddings.",
)
@click.option("--quiet", is_flag=True, help="Print less.")
@click.pass_context
def cli(ctx: click.Context, db_path: Optional[str], backend: str, embedding_provider: str, quiet: bool):
    """OMem — Agent State Infrastructure SDK.

    Persistent memory, session state, context assembly, knowledge graphs,
    observability, governance, and multi-agent coordination — all from one CLI.

    \b
    New here? Try:
        omem demo                              # see it work in 30 seconds
        omem remember "FastAPI uses Pydantic"  # store a memory
        omem recall "Pydantic"                 # search for it
        omem status                            # one-glance health dashboard

    \b
    Tip: set these once and skip the flags everywhere:
        OMEM_SESSION   default session ID
        OMEM_DB        database path
        OMEM_NS        default namespace
        OMEM_USER_ID / OMEM_TEAM_ID / OMEM_ORG_ID   org namespace identity

    \b
    Set NO_COLOR=1 for plain output, or OMEM_DEBUG=1 to see full tracebacks.
    """
    ctx.ensure_object(dict)
    ctx.obj["db_path"] = db_path
    ctx.obj["backend"] = backend
    ctx.obj["embedding_provider"] = embedding_provider
    ctx.obj["quiet"] = quiet

    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# ──────────────────────────────────────────────────────────────────────────────
# omem status  — top-level dashboard shortcut
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("status")
@click.option("--session", "-s", default=None, envvar="OMEM_SESSION",
              help="Session ID. Reads OMEM_SESSION if not set.")
@click.option("--namespace", "-n", default="default", envvar="OMEM_NS", show_default=True)
@click.option("--db", default=None, envvar="OMEM_DB", help="Database path.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def top_status(session: Optional[str], namespace: str, db: Optional[str], as_json: bool):
    """Cross-layer health dashboard for a session.

    Shows memory count, state goal, knowledge graph size, active traces,
    and runtime agents — all in one glance.

    \b
    Example:
        omem status --session mybot
        export OMEM_SESSION=mybot && omem status
    """
    from .agent_state import AgentState
    agent = AgentState(session_id=session, namespace=namespace, db_path=db)
    s = agent.status()
    if as_json:
        click.echo(json.dumps(s, indent=2, default=str))
        return

    _print_status_dashboard(s)


def _print_status_dashboard(s: Dict[str, Any]) -> None:
    """Pretty-print a status() dict from AgentState."""
    W = _c
    click.echo(W("  OMem Agent Dashboard", fg="cyan", bold=True))
    click.echo(W("  " + "─" * 50, fg="bright_black"))

    sid = s.get("session_id") or W("(none — use --session to set)", fg="yellow")
    click.echo(f"  Session    : {W(str(sid), fg='white', bold=True)}")
    click.echo(f"  Namespace  : {s.get('namespace', 'default')}")
    click.echo(f"  Backend    : {s.get('backend', '?')}")

    # Memory
    m = s.get("memory", {})
    if "error" not in m:
        n = m.get("total_memories", m.get("total", 0))
        click.echo(f"  Memory     : {W(str(n), fg='green')} memories stored")
    else:
        click.echo(f"  Memory     : {W('unavailable', fg='red')}")

    # State
    st = s.get("state", {})
    if "error" not in st and st.get("session_id"):
        goal = st.get("goal") or W("(no goal set)", fg="bright_black")
        status_val = st.get("status", "active")
        status_col = "green" if status_val == "active" else "yellow" if status_val == "done" else "red"
        plan = st.get("plan", [])
        step = st.get("step", 0)
        progress = f"  [{step}/{len(plan)}]" if plan else ""
        click.echo(f"  State      : {W(status_val, fg=status_col)}{progress}  goal={goal}")

    # Knowledge
    kg = s.get("knowledge", {})
    if "error" not in kg:
        click.echo(
            f"  Knowledge  : {W(str(kg.get('entities', 0)), fg='blue')} entities, "
            f"{W(str(kg.get('edges', 0)), fg='blue')} edges"
        )

    # Context
    ctx_s = s.get("context", {})
    if ctx_s:
        click.echo(
            f"  Context    : budget={ctx_s.get('budget_tokens', '?')} tokens, "
            f"mode={ctx_s.get('default_mode', '?')}"
        )

    # Observability
    obs = s.get("observe", {})
    if "error" not in obs and obs.get("total_events", 0) > 0:
        recall_p50 = obs.get("recall_latency_p50_ms", 0)
        savings = obs.get("context_tokens_saved_pct", 0)
        click.echo(
            f"  Traces     : {W(str(obs['total_events']), fg='cyan')} events  "
            f"recall_p50={recall_p50:.0f}ms  ctx_savings={savings:.0f}%"
        )

    # Runtime
    rt = s.get("runtime", {})
    if "error" not in rt:
        active = rt.get("active_agents", 0)
        if active > 0:
            click.echo(f"  Runtime    : {W(str(active), fg='magenta')} agents active")

    click.echo(W("  " + "─" * 50, fg="bright_black"))


@cli.command()
@click.option("--db-path", default=None, help="Custom SQLite database target path.")
@click.pass_context
def init(ctx: click.Context, db_path: Optional[str]):
    """Initialize a new local memory space."""
    db_path = db_path or ctx.obj.get("db_path") or os.path.expanduser("~/.omem/brain.db")

    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    m = OMem(
        backend=ctx.obj.get("backend", "sqlite"),
        db_path=db_path,
        embedding_provider=ctx.obj.get("embedding_provider", "local"),
    )

    success("OMem initialized.")
    field("database", db_path)
    field("memories", m.stats().get("total", 0))
    click.echo("")
    hint('omem remember "FastAPI uses Pydantic v2"')
    hint('omem recall "Pydantic"')


@cli.command()
@click.argument("content")
@click.option("--importance", "-i", type=float, help="Importance from 0.0 to 1.0.")
@click.option("--namespace", "-n", default="default", help="Namespace to store it in.")
@click.option("--type", "-t", "mem_type", help="Memory type (e.g. fact, decision, event).")
@click.pass_context
def add(ctx: click.Context, content: str, importance: Optional[float], namespace: str, mem_type: Optional[str]):
    """Add a memory.  (alias of `remember`)"""
    m = _get_omem(ctx)

    kwargs: Dict[str, Any] = {"namespace": namespace}
    if importance is not None:
        kwargs["importance"] = importance
    if mem_type:
        kwargs["mem_type"] = _resolve_memory_type(mem_type)

    mem_id = m.add(content, **kwargs)
    mem = m.get(mem_id)

    success("Memory added.")
    field("id", mem_id[:12])
    field("type", mem.type.name)
    field("importance", f"{mem.importance:.2f}")
    field("namespace", mem.namespace)


@cli.command()
@click.argument("content")
@click.option("--importance", "-i", type=float, help="Explicit importance weight [0.0-1.0].")
@click.option("--namespace", "-n", default="default", help="Memory namespace.")
@click.option("--type", "-t", "mem_type", help="Optional legacy MemoryType label.")
@click.option("--confidence", "-c", default=1.0, type=float, help="Confidence score [0.0-1.0].")
@click.option("--source", "-s", default="cli", help="Memory source label.")
@click.option("--force", is_flag=True, help="Bypass deduplication.")
@click.option(
    "--format",
    "-f",
    "output_format",
    default="table",
    type=click.Choice(["table", "json"]),
    help="Render result as table or JSON.",
)
@click.pass_context
def remember(
    ctx: click.Context,
    content: str,
    importance: Optional[float],
    namespace: str,
    mem_type: Optional[str],
    confidence: float,
    source: str,
    force: bool,
    output_format: str,
):
    """Store a memory in the graph-backed memory engine."""
    from .memory import MemoryOS

    memory = MemoryOS(_get_omem(ctx))
    type_enum = _resolve_memory_type(mem_type)
    mem_id = memory.remember(
        content,
        namespace=namespace,
        memory_type=type_enum,
        importance=importance,
        confidence=confidence,
        source=source,
        force=force,
    )
    mem = memory.omem.get(mem_id)
    payload = _memory_to_payload(mem)

    if output_format == "json":
        click.echo(json.dumps(payload, indent=2, default=str, sort_keys=True))
        return

    success("Remembered.")
    field("id", mem.id[:12])
    field("type", mem.type.name)
    field("namespace", mem.namespace)
    field("importance", f"{mem.importance:.2f}")
    field("confidence", f"{mem.confidence_score:.2f}")


@cli.command()
@click.argument("query")
@click.option("--k", "-k", default=5, help="Limit maximum returned fragments.")
@click.option("--namespace", "-n", help="Filter matching by specific partition.")
@click.option("--context-type", "-c", help="Contextual intent tag filter match.")
@click.option("--time-range", "-t", help="Window constraints (today, recent, last_week).")
@click.option(
    "--format",
    "-f",
    "output_format",
    default="table",
    type=click.Choice(["table", "json"]),
    help="Render results as a table or JSON.",
)
@click.option("--show-scores", "-s", is_flag=True, help="Include relevance scores in output.")
@click.pass_context
def search(
    ctx: click.Context,
    query: str,
    k: int,
    namespace: Optional[str],
    context_type: Optional[str],
    time_range: Optional[str],
    output_format: str,
    show_scores: bool,
):
    """Search memories.  (alias of `recall`)"""
    m = _get_omem(ctx)

    results = m.recall(
        query,
        k=k,
        namespace=namespace,
        context_type=context_type,
        time_range=time_range,
    )

    if not results:
        warn("No memories matched your query.")
        hint('add one with: omem remember "your fact here"')
        return

    if output_format == "json":
        output = [_memory_to_payload(mem) for mem in results]
        click.echo(json.dumps(output, indent=2, default=str))
        return

    _print_memory_results(results, show_scores=show_scores)


@cli.command()
@click.argument("query")
@click.option("--k", "-k", default=5, help="Limit maximum returned memories.")
@click.option("--namespace", "-n", help="Filter by namespace.")
@click.option("--context-type", "-c", help="Intent tag such as bugs, decisions, architecture.")
@click.option("--mode", "-m", default="default", help="Retrieval profile: default, planning, coding, chat, recall.")
@click.option("--level", help="Memory hierarchy level: working, short_term, long_term, archive.")
@click.option("--include-archive", is_flag=True, help="Include archived memories.")
@click.option(
    "--format",
    "-f",
    "output_format",
    default="table",
    type=click.Choice(["table", "json"]),
    help="Render results as table or JSON.",
)
@click.option("--show-scores", "-s", is_flag=True, help="Include relevance scores.")
@click.pass_context
def recall(
    ctx: click.Context,
    query: str,
    k: int,
    namespace: Optional[str],
    context_type: Optional[str],
    mode: str,
    level: Optional[str],
    include_archive: bool,
    output_format: str,
    show_scores: bool,
):
    """Search memories with smart, multi-signal ranking."""
    from .memory import MemoryOS

    memory = MemoryOS(_get_omem(ctx))
    results = memory.recall(
        query,
        k=k,
        namespace=namespace,
        context_type=context_type,
        mode=mode,
        level=level,
        include_archive=include_archive,
    )

    if not results:
        warn("No memories matched your query.")
        hint('add one with: omem remember "your fact here"')
        return

    if output_format == "json":
        click.echo(json.dumps([_memory_to_payload(mem) for mem in results], indent=2, default=str))
        return

    _print_memory_results(results, show_scores=show_scores)


@cli.command(name="list")
@click.option("--namespace", "-n", help="Filter target storage partition.")
@click.option("--type", "-t", "mem_type", help="Filter by raw structure type.")
@click.option("--limit", "-l", default=20, help="Truncate visual log limit.")
@click.option("--inactive", is_flag=True, help="Include records marked down for historical pruning.")
@click.option(
    "--format",
    "-f",
    "output_format",
    default="table",
    type=click.Choice(["table", "json"]),
    help="Render results as a table or JSON.",
)
@click.pass_context
def list_memories(ctx: click.Context, namespace: Optional[str], mem_type: Optional[str], limit: int, inactive: bool, output_format: str):
    """List stored memories."""
    m = _get_omem(ctx)
    memories = m.all(namespace=namespace, include_inactive=inactive)

    if mem_type:
        type_enum = getattr(MemoryType, mem_type.upper(), None)
        if type_enum:
            memories = [mem for mem in memories if mem.type == type_enum]

    memories = memories[:limit]

    if not memories:
        warn("No memories found.")
        hint('add one with: omem remember "your fact here"')
        return

    if output_format == "json":
        payload = [
            {
                "id": mem.id,
                "type": mem.type.name,
                "namespace": mem.namespace,
                "importance": mem.importance,
                "active": mem.active,
                "content": mem.content,
            }
            for mem in memories
        ]
        click.echo(json.dumps(payload, indent=2, default=str))
        return

    click.echo(_c(f"{len(memories)} memories", fg="green", bold=True))
    click.echo("")
    for i, mem in enumerate(memories, 1):
        status = "●" if mem.active else "○"
        click.echo(
            f"  {status} {i:02d} [{mem.type.name:11s}] w={mem.importance:.2f} | {mem.content[:65]}"
        )


@cli.command()
@click.argument("query")
@click.option("--k", default=5, help="How many results to score.")
@click.pass_context
def inspect(ctx: click.Context, query: str, k: int):
    """Show why memories match a query (full score breakdown)."""
    m = _get_omem(ctx)
    exps = m.inspect(query, top_k=k)

    if not exps:
        warn("Nothing to inspect yet — add a memory first.")
        hint('omem remember "your fact here"')
        return

    click.echo(_c(f"Why these match: '{query}'", fg="green", bold=True))
    rule(60)
    for i, exp in enumerate(exps, 1):
        click.echo(f"\n{i:02d}. {exp.explain()}")


@cli.command()
@click.option(
    "--format",
    "-f",
    "output_format",
    default="table",
    type=click.Choice(["table", "json"]),
    help="Render stats as table or JSON.",
)
@click.pass_context
def stats(ctx: click.Context, output_format: str):
    """Show memory statistics."""
    m = _get_omem(ctx)
    s = m.stats()

    if output_format == "json":
        click.echo(json.dumps(s, indent=2, default=str, sort_keys=True))
        return

    click.echo("")
    click.echo(_c("  Memory statistics", fg="cyan", bold=True))
    rule(45)
    field("Total", s["total"], width=18)
    field("Active", s["total"] - s["inactive"], width=18)
    field("Inactive", s["inactive"], width=18)
    field("Avg importance", f"{s['avg_importance']:.2f}", width=18)
    field("Graph edges", s.get("graph_edges", 0), width=18)

    ns_str = ", ".join(s.get("namespaces", [])) if s.get("namespaces") else "default"
    field("Namespaces", ns_str, width=18)
    if s.get("types"):
        click.echo("")
        click.echo(_c("  By type", fg="bright_black"))
        for mtype, count in s.get("types", {}).items():
            click.echo(f"    {mtype:15s} {count:>5d}")
    click.echo()


@cli.command()
@click.option("--namespace", "-n", help="Export only this namespace.")
@click.option(
    "--format",
    "-f",
    "fmt",
    default="json",
    type=click.Choice(["json", "txt"]),
    help="Output format.",
)
@click.option("--output", "-o", help="Write to this file instead of stdout.")
@click.pass_context
def export(ctx: click.Context, namespace: Optional[str], fmt: str, output: Optional[str]):
    """Export memories to a file (or stdout)."""
    m = _get_omem(ctx)
    memories = m.all(namespace=namespace)

    if fmt == "json":
        data = {
            "memories": [mem.to_dict() for mem in memories],
            "stats": m.stats(),
            "exported_at": time.time(),
        }
        content = json.dumps(data, indent=2)
    else:
        content = "\n".join(
            [f"{mem.content} | {mem.type.name} | {mem.importance:.2f}" for mem in memories]
        )

    if output:
        with open(output, "w") as f:
            f.write(content)
        success(f"Exported {len(memories)} memories to {output}")
    else:
        click.echo(content)


@cli.command(name="import")
@click.argument("file", type=click.Path(exists=True))
@click.option("--namespace", "-n", default="default", help="Namespace to import into.")
@click.pass_context
def load(ctx: click.Context, file: str, namespace: str):
    """Import memories from a file."""
    import builtins
    m = _get_omem(ctx)

    with open(file, "r") as f:
        data = json.load(f)

    if isinstance(data, dict) and "memories" in data:
        memories = data["memories"]
    elif isinstance(data, builtins.list):
        memories = data
    else:
        failure("Unsupported import format — expected a list or a {\"memories\": [...]} object.")
        raise SystemExit(1)

    note(f"Importing {len(memories)} memories...")
    count = 0
    for mem_data in memories:
        if isinstance(mem_data, dict):
            content = mem_data.get("content", "")
            importance = mem_data.get("importance", 0.5)
            if content:
                m.add(content, importance=importance, namespace=namespace)
                count += 1
        elif isinstance(mem_data, str):
            m.add(mem_data, namespace=namespace)
            count += 1

    success(f"Imported {count} memories into namespace '{namespace}'.")


@cli.command()
@click.option("--compress", is_flag=True, help="Merge near-duplicate memories.")
@click.option("--reflect", is_flag=True, help="Derive higher-level insights.")
@click.option("--forget", is_flag=True, help="Prune low-importance memories.")
@click.option("--dream", is_flag=True, help="Cluster and consolidate across topics.")
@click.option(
    "--all", "all_ops", is_flag=True, help="Run the full maintenance cycle (default)."
)
@click.pass_context
def maintain(
    ctx: click.Context,
    compress: bool,
    reflect: bool,
    forget: bool,
    dream: bool,
    all_ops: bool,
):
    """Run maintenance: compress, reflect, forget, dream.  (alias of `sleep`)"""
    m = _get_omem(ctx)

    if all_ops or not any([compress, reflect, forget, dream]):
        note("Running full maintenance cycle...")
        result = m.sleep()
        success("Maintenance complete.")
        field("compressed", result.get("compressed", 0))
        field("insights", result.get("reflected", 0))
        field("forgotten", result.get("forgotten", 0))
        return

    if compress:
        note("Compressing near-duplicate memories...")
        result = m.compress()
        success(f"Compressed {result['compressed']}, deactivated {result['deactivated']}.")

    if reflect:
        note("Reflecting to derive insights...")
        refs = m.reflect()
        success(f"Added {len(refs)} insights.")

    if forget:
        note("Forgetting low-importance memories...")
        result = m.forget()
        success(f"Forgot {len(result.forgotten_ids)} memories.")

    if dream:
        note("Dreaming — clustering across topics...")
        result = m.dream()
        success(
            f"Formed {result.clusters_formed} clusters, added {result.insights_created} insights."
        )


@cli.command()
@click.option("--speed", default="normal", type=click.Choice(["fast", "normal", "deep"]), help="Sleep cycle depth.")
@click.option(
    "--format",
    "-f",
    "output_format",
    default="table",
    type=click.Choice(["table", "json"]),
    help="Render result as table or JSON.",
)
@click.pass_context
def sleep(ctx: click.Context, speed: str, output_format: str):
    """Consolidate memory while the agent is idle."""
    from .memory import MemoryOS

    memory = MemoryOS(_get_omem(ctx))
    result = memory.consolidate(speed=speed)

    if output_format == "json":
        click.echo(json.dumps(result, indent=2, default=str, sort_keys=True))
        return

    success("Sleep cycle complete.")
    for key in sorted(result):
        field(key, result[key])


@cli.command()
@click.option("--namespace", "-n", help="Only clear this namespace (default: everything).")
@click.confirmation_option(prompt="This permanently deletes memories and cannot be undone. Continue?")
@click.pass_context
def clear(ctx: click.Context, namespace: Optional[str]):
    """Delete memories — a single namespace, or everything."""
    m = _get_omem(ctx)
    if namespace:
        m.clear(namespace=namespace)
        success(f"Cleared namespace '{namespace}'.")
    else:
        m.clear()
        success("Cleared all memories.")


@cli.command()
@click.option(
    "--format",
    "-f",
    "output_format",
    default="table",
    type=click.Choice(["table", "json"]),
    help="Render namespaces as table or JSON.",
)
@click.pass_context
def namespaces(ctx: click.Context, output_format: str):
    """List namespaces and how many memories each holds."""
    m = _get_omem(ctx)
    ns_list = m.namespaces()

    if not ns_list:
        warn("No namespaces yet.")
        return

    if output_format == "json":
        mapping = {ns: m.namespace_stats(ns).get("total", 0) for ns in ns_list}
        click.echo(json.dumps(mapping, indent=2, sort_keys=True))
        return

    click.echo(_c("Namespaces", fg="cyan", bold=True) + "\n")
    for ns in ns_list:
        stats = m.namespace_stats(ns)
        click.echo(f"  {GLYPH_INFO} {ns:22s} {stats.get('total', 0):>6d} memories")


@cli.command()
@click.pass_context
def demo(ctx: click.Context):
    """Run a quick end-to-end demo of OMem."""
    m = _get_omem(ctx)
    click.echo("\n" + "═" * 50)
    click.echo(_c("  OMem — 30-second demo", fg="cyan", bold=True))
    click.echo("" + "═" * 50 + "\n")

    samples = [
        "My name is Mohit and I'm building OMem",
        "Decided to use FAISS for vector search",
        "Step 1: install omem, Step 2: import OMem",
        "Yesterday deployed v0.2.0 to production",
        "Rain caused server outage in Mumbai region",
        "Currently optimizing the hybrid RAG pipeline",
        "Urgent: security vulnerability in auth module",
        "Python is the most popular programming language",
    ]

    note("Adding a few sample memories...")
    for content in samples:
        mid = m.add(content)
        mem = m.get(mid)
        click.echo(f"  [{mem.type.name:11s}] w={mem.importance:.2f} | {content[:50]}")

    s = m.stats()
    click.echo(f"\n{s['total']} memories stored across {len(s['types'])} types.\n")

    note("Now let's recall a few things:")
    for q in ["Who am I?", "deployment production", "security urgent"]:
        results = m.recall(q, k=2)
        click.echo(f'  "{q}"')
        for r in results:
            click.echo(f"    {GLYPH_ARROW} [{r.score:.3f}] {r.content[:55]}")

    note("Consolidating duplicates...")
    result = m.compress()
    click.echo(f"  compressed {result['compressed']}, deactivated {result['deactivated']}")

    note("Reflecting to derive insights...")
    refs = m.reflect()
    click.echo(f"  added {len(refs)} insights.")
    click.echo("\n" + "═" * 50)
    success("Demo complete. Try: omem remember \"...\"  then  omem recall \"...\"")


@cli.command("bench")
@click.option(
    "--suite", "-s",
    multiple=True,
    type=click.Choice(["memory", "state", "context", "continuity", "explainability", "concurrency"]),
    help="Suite(s) to run. Repeat for multiple. Default: all suites.",
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON (CI-friendly).")
@click.option("--quiet", is_flag=True, help="Suppress per-metric details.")
@click.option("--out", default=None, help="Write JSON results to this file path.")
def bench_cmd(suite, as_json: bool, quiet: bool, out: Optional[str]):
    """Run STATE-Bench — the AI Agent State Infrastructure benchmark suite.

    STATE-Bench measures what memory frameworks actually need to prove:
    Recall quality, state integrity, context efficiency, agent continuity,
    explainability depth, and concurrency correctness.

    \b
    Suites:
        memory          Recall@K, MRR, latency
        state           Snapshot/rollback fidelity, fork independence
        context         Token savings, budget adherence, build latency
        continuity      Crash-recovery, workflow resume fidelity
        explainability  Score decomposition coverage, explain latency
        concurrency     Parallel agent throughput and error rate

    \b
    Example:
        omem bench                          # run all suites
        omem bench --suite memory --suite state
        omem bench --json > results.json   # CI export
        omem bench --json --out results/latest.json
    """
    from benchmarks.state_bench import run_bench
    selected = list(suite) or None
    report = run_bench(suites=selected, as_json=as_json, quiet=quiet)
    if out:
        import pathlib
        pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            json.dump(report, f, indent=2, default=str)
        if not as_json:
            success(f"Results written to {out}")


@cli.command()
@click.option("--n", default=10_000, help="Number of memories to write.")
@click.pass_context
def benchmark(ctx: click.Context, n: int):
    """Measure raw write/query throughput.  (see `bench` for STATE-Bench)"""
    m = _get_omem(ctx)
    note(f"Benchmarking with {n:,} memories...\n")

    t0 = time.perf_counter()
    for i in range(n):
        m.add(f"Benchmark transaction sequence {i}: tag {i % 100} vector block {i % 50}", importance=0.5)
    add_time = time.perf_counter() - t0

    click.echo(
        f"  Writes:   {_format_duration(add_time)} total | {(add_time / n) * 1000:.4f}ms/op | {n / add_time:,.0f} writes/sec"
    )

    queries = 1000
    t0 = time.perf_counter()
    for i in range(queries):
        m.recall(f"tag {i % 100} vector block {i % 50}", k=5)
    rag_time = time.perf_counter() - t0

    click.echo(
        f"  Queries:  {_format_duration(rag_time)} total | {(rag_time / queries) * 1000:.4f}ms/query | {queries / rag_time:,.0f} queries/sec"
    )


@cli.command()
@click.option("--port", default=7900, help="Port to serve the dashboard on.")
@click.pass_context
def dashboard(ctx: click.Context, port: int):
    """Open the web dashboard in your browser."""
    from .viz.server import serve as start_dashboard

    m = _get_omem(ctx)
    note(f"Dashboard running at http://localhost:{port}  (Ctrl+C to stop)")
    start_dashboard(omem=m, port=port)


@cli.command()
@click.pass_context
def health(ctx: click.Context):
    """Check that OMem is healthy."""
    try:
        m = _get_omem(ctx)
        stats = m.stats()
        success("OMem is healthy.")
        field("version", __version__)
        field("memories", stats["total"])
        sys.exit(0)
    except Exception as e:
        failure(f"OMem is not healthy: {e}")
        sys.exit(1)


@cli.command()
@click.argument('path', default='.', type=click.Path(exists=True))
@click.option('--namespace', '-n', default='project', help='Namespace to index into.')
@click.pass_context
def ingest(ctx: click.Context, path: str, namespace: str):
    """Index a codebase into memory."""
    m = _get_omem(ctx)
    count = m.ingest_project(path, namespace)
    success(f"Indexed {count} code symbols into '{namespace}'.")


@cli.command()
@click.argument('path', default='.', type=click.Path(exists=True))
@click.option('--namespace', '-n', default='project', help='Namespace to sync.')
@click.pass_context
def sync(ctx: click.Context, path: str, namespace: str):
    """Sync code changes since the last index."""
    m = _get_omem(ctx)
    processed = m.sync_project(path, namespace)
    success(f"Synced {processed} changed symbols into '{namespace}'.")


@cli.command()
@click.argument('query')
@click.option('--namespace', '-n', default='project', help='Namespace to search.')
@click.option('--depth', '-d', default=2, help='How many relationship hops to follow.')
@click.option('--top-k', default=5, help='Maximum results to return.')
@click.pass_context
def codebase(ctx: click.Context, query: str, namespace: str, depth: int, top_k: int):
    """Search an indexed codebase."""
    m = _get_omem(ctx)
    results = m.query_code(query, namespace=namespace, context_depth=depth, top_k=top_k)
    for i, r in enumerate(results, 1):
        click.echo(f"{i:02d}. {r.get('symbol_id', 'N/A')} ({r.get('type', '')})")
        click.echo(f"    {r.get('file_path', '')}:{r.get('start_line', '')}")
        if 'summary' in r:
            click.echo(f"    {r['summary']}")
        click.echo('')


@cli.command()
@click.option(
    "--transport",
    default="stdio",
    type=click.Choice(["stdio"]),
    help="Transport for the MCP server.",
)
@click.pass_context
def serve(ctx: click.Context, transport: str):
    """Start the MCP server (Claude Desktop, Cursor, agents)."""
    note(f"Starting OMem MCP server (transport: {transport})")
    note("Ready. Connect from Claude Desktop, Cursor, or any MCP client.\n")

    try:
        from .integrations.mcp_server import mcp
        mcp.run(transport=transport)
    except KeyboardInterrupt:
        click.echo("\nMCP server stopped.")
    except Exception as e:
        failure(f"MCP server failed to start: {e}")
        sys.exit(1)


@cli.command()
@click.argument("shell", default="bash", type=click.Choice(["bash", "zsh", "fish", "powershell"]))
def completion(shell: str):
    """Generate shell completion code for supported shells."""
    try:
        from click.shell_completion import get_completion_script

        click.echo(get_completion_script("omem", shell))
    except (ImportError, AttributeError):
        warn("Shell completion is not available with this Click version.")


@cli.command()
def version():
    """Show the currently installed OMem version."""
    click.echo(f"omem {__version__}")


# ---------------------------------------------------------------------------
# omem state — Agent State CLI (Phase 2)
# ---------------------------------------------------------------------------

@click.group("state")
def state_group():
    """Session state — Git-like snapshots, rollback, fork, and checkpoints.

    \b
    Examples:
        omem state save      --session mybot --goal "Build REST API"
        omem state snapshot  --session mybot --label before-refactor
        omem state rollback  --session mybot --snapshot snap_abc
        omem state fork      --session mybot --snapshot snap_abc --new-session experiment
        omem state checkpoint --session mybot
        omem state status    --session mybot
    """


def _get_state_os(db_path: Optional[str] = None):
    """Resolve a production-ready StateOS from an optional db_path."""
    from .state.layer import StateOS
    from .state.backend import SQLiteStateBackend
    resolved = db_path or os.path.expanduser("~/.omem/brain.db")
    return StateOS(backend=SQLiteStateBackend(resolved))


@state_group.command("save")
@click.argument("session_id")
@click.option("--goal", default=None, help="Goal for this session.")
@click.option("--plan", default=None, help="Comma-separated plan steps.")
@click.option("--namespace", default="default", help="Namespace.")
@click.option("--db", default=None, envvar="OMEM_DB", help="Path to brain.db.")
def state_save(session_id: str, goal: Optional[str], plan: Optional[str], namespace: str, db: Optional[str]):
    """Create or update a session's state."""
    from .types import StatePayload
    state = _get_state_os(db)
    payload = state.get_or_create(session_id, namespace=namespace)
    if goal:
        state.set_goal(session_id, goal)
    if plan:
        steps = [s.strip() for s in plan.split(",") if s.strip()]
        state.set_plan(session_id, steps)
    payload = state.load(session_id)
    click.echo(click.style(f"✓ Session '{session_id}' saved", fg="green"))
    click.echo(f"  goal: {payload.goal or '(none)'}")
    click.echo(f"  steps: {len(payload.plan)}, step: {payload.step}, status: {payload.status}")


@state_group.command("load")
@click.argument("session_id")
@click.option("--db", default=None, envvar="OMEM_DB", help="Path to brain.db.")
def state_load(session_id: str, db: Optional[str]):
    """Print the current state for a session."""
    from .state.exceptions import SessionNotFoundError
    state = _get_state_os(db)
    try:
        payload = state.load(session_id)
    except SessionNotFoundError as exc:
        click.echo(click.style(str(exc), fg="red"), err=True)
        sys.exit(1)
    data = payload.to_dict()
    click.echo(json.dumps(data, indent=2, default=str))


@state_group.command("snapshot")
@click.argument("session_id")
@click.option("--label", default=None, help="Human-readable snapshot label.")
@click.option("--db", default=None, envvar="OMEM_DB", help="Path to brain.db.")
def state_snapshot(session_id: str, label: Optional[str], db: Optional[str]):
    """Create an immutable named snapshot of a session."""
    from .state.exceptions import SessionNotFoundError
    state = _get_state_os(db)
    try:
        snap = state.snapshot(session_id, label=label)
    except SessionNotFoundError as exc:
        click.echo(click.style(str(exc), fg="red"), err=True)
        sys.exit(1)
    click.echo(click.style(f"✓ Snapshot created", fg="green"))
    click.echo(f"  id:    {snap.id}")
    click.echo(f"  label: {snap.label or '(none)'}")


@state_group.command("snapshots")
@click.argument("session_id")
@click.option("--db", default=None, envvar="OMEM_DB", help="Path to brain.db.")
def state_snapshots(session_id: str, db: Optional[str]):
    """List all snapshots for a session."""
    state = _get_state_os(db)
    snaps = state.list_snapshots(session_id)
    if not snaps:
        click.echo(f"No snapshots found for session '{session_id}'.")
        return
    click.echo(f"Snapshots for '{session_id}' ({len(snaps)} total):")
    for s in snaps:
        label = f"  [{s.label}]" if s.label else ""
        ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(s.created_at))
        click.echo(f"  {s.id}  {ts}{label}")


@state_group.command("rollback")
@click.argument("snapshot_id")
@click.option("--db", default=None, envvar="OMEM_DB", help="Path to brain.db.")
def state_rollback(snapshot_id: str, db: Optional[str]):
    """Restore a session to a prior snapshot (non-destructive)."""
    from .state.exceptions import SnapshotNotFoundError
    state = _get_state_os(db)
    try:
        payload = state.rollback(snapshot_id)
    except SnapshotNotFoundError as exc:
        click.echo(click.style(str(exc), fg="red"), err=True)
        sys.exit(1)
    click.echo(click.style(f"✓ Rolled back to snapshot {snapshot_id}", fg="green"))
    click.echo(f"  session: {payload.session_id}, step: {payload.step}, version: {payload.version}")


@state_group.command("fork")
@click.argument("snapshot_id")
@click.option("--session", default=None, help="ID for the new child session.")
@click.option("--db", default=None, envvar="OMEM_DB", help="Path to brain.db.")
def state_fork(snapshot_id: str, session: Optional[str], db: Optional[str]):
    """Branch a new session from a snapshot."""
    from .state.exceptions import SnapshotNotFoundError, ForkError
    state = _get_state_os(db)
    try:
        child_id = state.fork(snapshot_id, new_session_id=session)
    except (SnapshotNotFoundError, ForkError) as exc:
        click.echo(click.style(str(exc), fg="red"), err=True)
        sys.exit(1)
    click.echo(click.style(f"✓ Forked into new session", fg="green"))
    click.echo(f"  child session: {child_id}")
    click.echo(f"  parent snap:   {snapshot_id}")


@state_group.command("checkpoint")
@click.argument("session_id")
@click.option("--db", default=None, envvar="OMEM_DB", help="Path to brain.db.")
def state_checkpoint(session_id: str, db: Optional[str]):
    """Write a crash-recovery checkpoint for a session."""
    from .state.exceptions import SessionNotFoundError
    state = _get_state_os(db)
    try:
        chk_id = state.checkpoint(session_id)
    except SessionNotFoundError as exc:
        click.echo(click.style(str(exc), fg="red"), err=True)
        sys.exit(1)
    click.echo(click.style(f"✓ Checkpoint created", fg="green"))
    click.echo(f"  id: {chk_id}")


@state_group.command("resume")
@click.argument("checkpoint_id")
@click.option("--db", default=None, envvar="OMEM_DB", help="Path to brain.db.")
def state_resume(checkpoint_id: str, db: Optional[str]):
    """Restore a session from a checkpoint ID."""
    from .state.exceptions import CheckpointNotFoundError
    state = _get_state_os(db)
    try:
        payload = state.resume(checkpoint_id)
    except CheckpointNotFoundError as exc:
        click.echo(click.style(str(exc), fg="red"), err=True)
        sys.exit(1)
    click.echo(click.style(f"✓ Resumed from checkpoint {checkpoint_id}", fg="green"))
    click.echo(f"  session: {payload.session_id}, step: {payload.step}, status: {payload.status}")


@state_group.command("merge")
@click.option("--winner", required=True, help="Session ID whose state wins.")
@click.option("--loser", required=True, help="Session ID to mark as merged.")
@click.option("--db", default=None, envvar="OMEM_DB", help="Path to brain.db.")
def state_merge(winner: str, loser: str, db: Optional[str]):
    """Merge a winning branch back to base and retire the loser."""
    from .state.exceptions import SessionNotFoundError, MergeError
    state = _get_state_os(db)
    try:
        payload = state.merge(winner, loser)
    except (SessionNotFoundError, MergeError) as exc:
        click.echo(click.style(str(exc), fg="red"), err=True)
        sys.exit(1)
    click.echo(click.style(f"✓ Merged '{loser}' → '{winner}'", fg="green"))
    click.echo(f"  final version: {payload.version}")


@state_group.command("status")
@click.argument("session_id")
@click.option("--db", default=None, envvar="OMEM_DB", help="Path to brain.db.")
def state_status(session_id: str, db: Optional[str]):
    """Show a human-friendly summary of a session."""
    from .state.exceptions import SessionNotFoundError
    state = _get_state_os(db)
    try:
        info = state.summary(session_id)
    except SessionNotFoundError as exc:
        click.echo(click.style(str(exc), fg="red"), err=True)
        sys.exit(1)
    click.echo(click.style(f"Session: {session_id}", fg="cyan", bold=True))
    for key, val in info.items():
        if key == "session_id":
            continue
        if key == "updated_at":
            val = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(val)))
        click.echo(f"  {key:<20} {val}")


@state_group.command("list")
@click.option("--namespace", default=None, help="Filter by namespace.")
@click.option("--db", default=None, envvar="OMEM_DB", help="Path to brain.db.")
def state_list(namespace: Optional[str], db: Optional[str]):
    """List all known sessions."""
    state = _get_state_os(db)
    sessions = state.list_sessions(namespace=namespace)
    if not sessions:
        click.echo("No sessions found.")
        return
    click.echo(f"Sessions ({len(sessions)}):")
    for sid in sessions:
        click.echo(f"  {sid}")


cli.add_command(state_group)


# ---------------------------------------------------------------------------
# omem context — Context Engine CLI (Phase 3)
# ---------------------------------------------------------------------------

@click.group("context")
def context_group():
    """Context engine — build token-efficient prompts for LLMs.

    Packs state, memories, and knowledge into a single context block that
    fits your token budget. Shows actual token savings vs. naive inclusion.

    \b
    Examples:
        omem context build --session mybot --task "implement auth" --budget 4000
        omem context estimate --session mybot --task "review PR"
        omem context clear-cache
    """


def _get_context_engine(db: Optional[str] = None, session_id: Optional[str] = None):
    """Resolve a fully-wired ContextEngine from on-disk OMem state."""
    from .state.layer import StateOS
    from .state.backend import SQLiteStateBackend
    from .memory.layer import MemoryOS

    resolved_db = db or os.path.expanduser("~/.omem/brain.db")

    # Memory layer — real OMem; skipped if db doesn't exist yet
    memory = None
    if os.path.exists(resolved_db):
        try:
            from .api import OMem
            memory = MemoryOS(OMem(backend="sqlite", db_path=resolved_db))
        except Exception:
            pass

    state = StateOS(backend=SQLiteStateBackend(resolved_db))

    from .context.engine import ContextEngine
    return ContextEngine(memory=memory, state=state)


@context_group.command("build")
@click.option("--task", required=True, help="What the agent is doing right now.")
@click.option("--budget", default=6000, show_default=True, help="Token budget.")
@click.option("--session", default=None, help="Session ID to include state from.")
@click.option("--mode", default="planning", show_default=True,
              type=click.Choice(["planning", "coding", "chat", "recall"]),
              help="Retrieval mode.")
@click.option("--namespace", default=None, help="Filter memories to namespace.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@click.option("--db", default=None, envvar="OMEM_DB", help="Path to brain.db.")
def context_build(
    task: str,
    budget: int,
    session: Optional[str],
    mode: str,
    namespace: Optional[str],
    as_json: bool,
    db: Optional[str],
):
    """Assemble an optimal context bundle and print it."""
    from .context.engine import ContextRequest
    engine = _get_context_engine(db, session)
    request = ContextRequest(
        task=task,
        budget_tokens=budget,
        session_id=session,
        namespace=namespace,
        mode=mode,
    )
    bundle = engine.build(request)

    if as_json:
        out = {
            "token_count": bundle.token_count,
            "budget_tokens": bundle.budget_tokens,
            "savings_vs_naive": bundle.savings_vs_naive,
            "memories_used": bundle.memories_used,
            "state_included": bundle.state_included,
            "text": bundle.text,
        }
        click.echo(json.dumps(out, indent=2, default=str))
    else:
        click.echo(bundle.text)
        click.echo()
        savings_pct = f"{bundle.savings_vs_naive:.0%}"
        click.echo(click.style(
            f"✓  {bundle.token_count:,} of {budget:,} tokens | "
            f"savings: {savings_pct} | memories: {len(bundle.memories_used)}",
            fg="cyan",
        ))


@context_group.command("estimate")
@click.option("--task", required=True, help="What the agent is doing right now.")
@click.option("--budget", default=6000, show_default=True, help="Token budget.")
@click.option("--session", "-s", default=None, envvar="OMEM_SESSION", help="Session ID. Reads OMEM_SESSION if not set.")
@click.option("--namespace", default=None, help="Filter memories to namespace.")
@click.option("--db", default=None, envvar="OMEM_DB", help="Path to brain.db.")
def context_estimate(
    task: str,
    budget: int,
    session: Optional[str],
    namespace: Optional[str],
    db: Optional[str],
):
    """Preview token savings without assembling the full bundle."""
    from .context.engine import ContextRequest
    engine = _get_context_engine(db, session)
    request = ContextRequest(
        task=task,
        budget_tokens=budget,
        session_id=session,
        namespace=namespace,
    )
    stats = engine.estimate_savings(request)
    click.echo(click.style("Context efficiency estimate", fg="cyan", bold=True))
    for key, val in stats.items():
        if key == "savings_pct":
            val = f"{val}%"
        click.echo(f"  {key:<25} {val}")


@context_group.command("clear-cache")
def context_clear_cache():
    """Flush the in-process context cache (no-op for CLI invocations)."""
    click.echo(click.style(
        "Cache is per-process — nothing to flush for CLI invocations. "
        "In long-running agents, call engine.invalidate_cache().",
        fg="yellow",
    ))


cli.add_command(context_group)


# ──────────────────────────────────────────────────────────────────────────────
# omem knowledge  (Phase 4)
# ──────────────────────────────────────────────────────────────────────────────

def _get_knowledge_os(db: Optional[str]):
    """Instantiate a KnowledgeOS backed by the same OMem instance as the CLI."""
    from .api import OMem
    from .knowledge.layer import KnowledgeOS

    db_path = db or os.path.expanduser("~/.omem/brain.db")
    omem_instance = OMem(backend="sqlite" if os.path.exists(db_path) else "memory",
                         db_path=db_path if os.path.exists(db_path) else None)
    return KnowledgeOS(omem=omem_instance)


@click.group("knowledge")
def knowledge_group():
    """Knowledge graph — typed entity-relation graph for agent reasoning.

    Build, query, and reason over a graph that lives alongside memories.
    Supports manual assertions, auto-extraction, BFS traversal, path-finding,
    and heuristic multi-hop inference.

    \b
    Examples:
        omem knowledge link    FastAPI uses Pydantic
        omem knowledge link    FastAPI uses Starlette --confidence 0.95
        omem knowledge query   FastAPI --depth 2
        omem knowledge reason  --question "What does FastAPI depend on?"
        omem knowledge entities --type technology
        omem knowledge paths   FastAPI Pydantic
        omem knowledge stats
    """


@knowledge_group.command("link")
@click.argument("subject")
@click.argument("predicate")
@click.argument("object_entity", metavar="OBJECT")
@click.option("--confidence", default=1.0, show_default=True, type=float,
              help="Edge confidence [0, 1].")
@click.option("--memory-id", default="", help="Link to a backing memory ID.")
@click.option("--db", default=None, envvar="OMEM_DB", help="Path to brain.db.")
def knowledge_link(
    subject: str,
    predicate: str,
    object_entity: str,
    confidence: float,
    memory_id: str,
    db: Optional[str],
):
    """Assert a typed relation: SUBJECT PREDICATE OBJECT.

    \b
    Examples:
        omem knowledge link FastAPI uses Pydantic
        omem knowledge link Alice works_at "Akamai Technologies"
        omem knowledge link Python depends_on CPython --confidence 0.95
    """
    kg = _get_knowledge_os(db)
    edge_id = kg.link(subject, predicate, object_entity,
                      confidence=confidence, memory_id=memory_id)
    click.echo(click.style("✓ Edge asserted", fg="green", bold=True))
    click.echo(f"  {subject!r} —[{predicate}]→ {object_entity!r}")
    click.echo(f"  edge_id: {edge_id}")


@knowledge_group.command("assert-fact")
@click.argument("subject")
@click.argument("relation")
@click.argument("object_entity", metavar="OBJECT")
@click.option("--confidence", default=0.9, show_default=True, type=float)
@click.option("--memory-id", default="", help="Backing memory ID.")
@click.option("--source", default="user", show_default=True,
              help="Provenance source tag.")
@click.option("--db", default=None, envvar="OMEM_DB")
def knowledge_assert_fact(
    subject: str,
    relation: str,
    object_entity: str,
    confidence: float,
    memory_id: str,
    source: str,
    db: Optional[str],
):
    """Assert a high-confidence, high-weight fact (stronger than link)."""
    kg = _get_knowledge_os(db)
    edge_id = kg.assert_fact(subject, relation, object_entity,
                              memory_id=memory_id, confidence=confidence,
                              source=source)
    click.echo(click.style("✓ Fact asserted", fg="green", bold=True))
    click.echo(f"  {subject!r} —[{relation}]→ {object_entity!r}  (conf={confidence})")
    click.echo(f"  edge_id: {edge_id}")


@knowledge_group.command("ingest")
@click.argument("text")
@click.option("--memory-id", default="", help="Memory ID to associate with entities.")
@click.option("--confidence", default=1.0, type=float, show_default=True)
@click.option("--namespace", default="default", show_default=True)
@click.option("--db", default=None, envvar="OMEM_DB")
def knowledge_ingest(
    text: str,
    memory_id: str,
    confidence: float,
    namespace: str,
    db: Optional[str],
):
    """Auto-extract entities and relations from free text.

    \b
    Example:
        omem knowledge ingest "Alice is building OMem using Python and Rust"
    """
    kg = _get_knowledge_os(db)
    result = kg.ingest(text, memory_id=memory_id, confidence=confidence,
                       namespace=namespace)
    click.echo(click.style("✓ Text ingested", fg="green", bold=True))
    click.echo(f"  entities:       {result.get('entities', [])}")
    click.echo(f"  relation_types: {result.get('relation_types', [])}")
    click.echo(f"  nodes:          {len(result.get('node_ids', []))} created/merged")
    click.echo(f"  edges:          {len(result.get('edge_ids', []))} created/merged")


@knowledge_group.command("query")
@click.argument("entity")
@click.option("--depth", default=2, show_default=True, type=int,
              help="BFS hop depth.")
@click.option("--json", "as_json", is_flag=True, default=False,
              help="Output as JSON.")
@click.option("--db", default=None, envvar="OMEM_DB")
def knowledge_query(entity: str, depth: int, as_json: bool, db: Optional[str]):
    """Return the subgraph centred on ENTITY up to DEPTH hops.

    \b
    Example:
        omem knowledge query FastAPI --depth 2
    """
    kg = _get_knowledge_os(db)
    subgraph = kg.query(entity, depth=depth)

    if as_json:
        click.echo(json.dumps(subgraph.to_dict(), indent=2))
        return

    click.echo(click.style(f"Subgraph: {entity!r}  (depth={depth})", fg="cyan", bold=True))
    click.echo(f"  Entities : {subgraph.entity_count}")
    click.echo(f"  Edges    : {subgraph.edge_count}")
    click.echo(f"  Memories : {len(subgraph.related_memory_ids)}")
    if subgraph.nodes:
        click.echo()
        click.echo(click.style("  Nodes:", fg="yellow"))
        for node in subgraph.nodes[:20]:
            click.echo(f"    [{node.entity_type}] {node.label}  (mentions={node.mention_count})")
    if subgraph.edges:
        click.echo()
        click.echo(click.style("  Relations:", fg="yellow"))
        for edge in subgraph.edges[:20]:
            conf = f"conf={edge.confidence:.2f}" if edge.confidence < 1.0 else ""
            click.echo(f"    {edge.source} —[{edge.predicate}]→ {edge.target}  {conf}")


@knowledge_group.command("reason")
@click.option("--question", required=True, help="Question to reason about.")
@click.option("--max", "max_results", default=10, show_default=True, type=int,
              help="Max results to return.")
@click.option("--json", "as_json", is_flag=True, default=False)
@click.option("--db", default=None, envvar="OMEM_DB")
def knowledge_reason(
    question: str,
    max_results: int,
    as_json: bool,
    db: Optional[str],
):
    """Apply heuristic inference to answer a QUESTION about the graph.

    \b
    Example:
        omem knowledge reason --question "What does FastAPI use?"
    """
    kg = _get_knowledge_os(db)
    results = kg.reason(question, max_results=max_results)

    if as_json:
        click.echo(json.dumps([r.to_dict() for r in results], indent=2))
        return

    if not results:
        click.echo(click.style(
            "No relevant facts found. Try ingesting more memories or adding "
            "explicit links with `omem knowledge link`.",
            fg="yellow",
        ))
        return

    click.echo(click.style(f"Inference results for: {question!r}", fg="cyan", bold=True))
    for i, r in enumerate(results, 1):
        conf_col = "green" if r.confidence >= 0.8 else "yellow"
        type_tag = f"[{r.inference_type}]"
        click.echo(
            f"  {i:2}. {click.style(f'{r.confidence:.2f}', fg=conf_col)} "
            f"{type_tag}  {r.statement}"
        )


@knowledge_group.command("entities")
@click.option("--type", "entity_type", default=None,
              help="Filter by type: technology, person, organization, etc.")
@click.option("--limit", default=30, show_default=True, type=int,
              help="Max entities to show.")
@click.option("--json", "as_json", is_flag=True, default=False)
@click.option("--db", default=None, envvar="OMEM_DB")
def knowledge_entities(
    entity_type: Optional[str],
    limit: int,
    as_json: bool,
    db: Optional[str],
):
    """List all known entities, sorted by mention count."""
    kg = _get_knowledge_os(db)
    nodes = kg.entities(entity_type=entity_type)

    if as_json:
        click.echo(json.dumps([
            {"label": n.label, "type": n.entity_type,
             "mentions": n.mention_count, "confidence": n.confidence}
            for n in nodes[:limit]
        ], indent=2))
        return

    if not nodes:
        click.echo(click.style("No entities found.", fg="yellow"))
        return

    type_filter = f"  (type={entity_type!r})" if entity_type else ""
    click.echo(click.style(
        f"Entities in graph{type_filter}  ({len(nodes)} total)", fg="cyan", bold=True
    ))
    for node in nodes[:limit]:
        click.echo(
            f"  [{node.entity_type:12}] {node.label:<30} "
            f"mentions={node.mention_count}"
        )


@knowledge_group.command("paths")
@click.argument("source")
@click.argument("target")
@click.option("--max-depth", default=4, show_default=True, type=int,
              help="Maximum path length in hops.")
@click.option("--db", default=None, envvar="OMEM_DB")
def knowledge_paths(source: str, target: str, max_depth: int, db: Optional[str]):
    """Find all paths from SOURCE to TARGET in the graph.

    \b
    Example:
        omem knowledge paths Python FastAPI --max-depth 3
    """
    kg = _get_knowledge_os(db)
    paths = kg.paths(source, target, max_depth=max_depth)

    if not paths:
        click.echo(click.style(
            f"No path found between {source!r} and {target!r} "
            f"within {max_depth} hops.",
            fg="yellow",
        ))
        return

    click.echo(click.style(
        f"Paths from {source!r} to {target!r}", fg="cyan", bold=True
    ))
    for i, path in enumerate(paths, 1):
        click.echo(f"  {i}. {' → '.join(path)}")


@knowledge_group.command("stats")
@click.option("--json", "as_json", is_flag=True, default=False)
@click.option("--db", default=None, envvar="OMEM_DB")
def knowledge_stats(as_json: bool, db: Optional[str]):
    """Print aggregate statistics about the knowledge graph."""
    kg = _get_knowledge_os(db)
    stats = kg.stats()

    if as_json:
        click.echo(json.dumps(stats.to_dict(), indent=2))
        return

    click.echo(click.style("Knowledge Graph Statistics", fg="cyan", bold=True))
    click.echo(f"  Entities        : {stats.total_entities}")
    click.echo(f"  Nodes           : {stats.total_nodes}")
    click.echo(f"  Edges           : {stats.total_edges}")
    click.echo(f"  Causal links    : {stats.causal_links}")
    click.echo(f"  Dependency links: {stats.dependency_links}")
    click.echo(f"  Avg centrality  : {stats.avg_centrality:.4f}")

    if stats.edge_type_distribution:
        click.echo()
        click.echo(click.style("  Edge types:", fg="yellow"))
        for etype, count in sorted(stats.edge_type_distribution.items(),
                                   key=lambda x: x[1], reverse=True):
            click.echo(f"    {etype:<15} {count}")

    if stats.top_entities:
        click.echo()
        click.echo(click.style("  Top entities (by degree centrality):", fg="yellow"))
        for name, centrality in stats.top_entities[:5]:
            click.echo(f"    {name:<30} {centrality:.4f}")


@knowledge_group.command("export")
@click.option("--output", "-o", default="-", help="Output file (default: stdout).")
@click.option("--db", default=None, envvar="OMEM_DB")
def knowledge_export(output: str, db: Optional[str]):
    """Export the full knowledge graph as JSON."""
    kg = _get_knowledge_os(db)
    data = kg.export()
    out_str = json.dumps(data, indent=2)

    if output == "-":
        click.echo(out_str)
    else:
        with open(output, "w") as f:
            f.write(out_str)
        click.echo(click.style(f"✓ Exported to {output}", fg="green"))


cli.add_command(knowledge_group)


# ──────────────────────────────────────────────────────────────────────────────
# omem agent  (Phase 5)
# ──────────────────────────────────────────────────────────────────────────────

def _get_agent_state(
    session: Optional[str],
    namespace: str,
    db: Optional[str],
    backend: str = "sqlite",
) -> "AgentState":
    """Build a CLI-scoped AgentState."""
    from .agent_state import AgentState
    return AgentState(
        session_id=session,
        namespace=namespace,
        backend=backend,
        db_path=db or None,
    )


# Lazy type annotation — avoids import at module level
AgentState = None  # resolved inside each command


@click.group("agent", invoke_without_command=True)
@click.pass_context
def agent_group(ctx: click.Context):
    """Unified agent interface — memory, state, knowledge, context, governance.

    The primary way to interact with OMem. Combines all layers into one
    simple command surface. Set OMEM_SESSION once and skip --session everywhere.

    \b
    Quickstart:
        export OMEM_SESSION=my-agent
        omem agent remember "FastAPI uses Pydantic v2"
        omem agent recall "Pydantic"
        omem agent explain "Pydantic validation"
        omem agent learn FastAPI uses Pydantic
        omem agent context --task "implement auth endpoint"
        omem agent status
        omem agent snapshot --label before-refactor
        omem agent checkpoint
        omem agent clone --new-session my-agent-v2
        omem agent export > session.json

    \b
    Environment variables (set once, works for all subcommands):
        OMEM_SESSION  — default session ID
        OMEM_DB       — database path
        OMEM_NS       — default namespace
    """
    ctx.ensure_object(dict)
    if ctx.invoked_subcommand is None:
        # Show dashboard when invoked with no subcommand
        session = os.environ.get("OMEM_SESSION")
        namespace = os.environ.get("OMEM_NS", "default")
        db = os.environ.get("OMEM_DB")
        from .agent_state import AgentState
        agent = AgentState(session_id=session, namespace=namespace, db_path=db)
        s = agent.status()
        _print_status_dashboard(s)
        if not session:
            click.echo()
            click.echo(
                click.style("  Tip: ", fg="yellow", bold=True)
                + "set OMEM_SESSION=<name> to persist your session across commands.\n"
                + "       Then just run: omem agent status"
            )


@agent_group.command("status")
@click.option("--session", "-s", default=None, envvar="OMEM_SESSION", help="Session ID. Reads OMEM_SESSION if not set.")
@click.option("--namespace", default="default", show_default=True)
@click.option("--db", default=None, envvar="OMEM_DB")
@click.option("--json", "as_json", is_flag=True, default=False)
def agent_status(session: Optional[str], namespace: str, db: Optional[str], as_json: bool):
    """Show a full cross-layer health dashboard for a session.

    \b
    Example:
        omem agent status --session mybot
        export OMEM_SESSION=mybot && omem agent status
        omem agent status --session mybot --json | jq .memory
    """
    from .agent_state import AgentState
    agent = AgentState(session_id=session, namespace=namespace, db_path=db)
    status = agent.status()
    if as_json:
        click.echo(json.dumps(status, indent=2, default=str))
        return
    _print_status_dashboard(status)


@agent_group.command("remember")
@click.argument("content")
@click.option("--session", "-s", default=None, envvar="OMEM_SESSION", help="Session ID. Reads OMEM_SESSION if not set.")
@click.option("--namespace", default="default", show_default=True)
@click.option("--importance", default=0.5, type=float, show_default=True)
@click.option("--db", default=None, envvar="OMEM_DB")
def agent_remember(
    content: str,
    session: Optional[str],
    namespace: str,
    importance: float,
    db: Optional[str],
):
    """Store a memory via the unified facade.

    \b
    Example:
        omem agent remember "FastAPI is faster than Django for APIs" --importance 0.8
    """
    from .agent_state import AgentState
    agent = AgentState(session_id=session, namespace=namespace, db_path=db)
    mem_id = agent.remember(content, importance=importance, namespace=namespace)
    click.echo(click.style("✓ Remembered", fg="green", bold=True))
    click.echo(f"  memory_id : {mem_id}")


@agent_group.command("recall")
@click.argument("query")
@click.option("--session", "-s", default=None, envvar="OMEM_SESSION", help="Session ID. Reads OMEM_SESSION if not set.")
@click.option("--namespace", default=None)
@click.option("--k", "-k", default=5, type=int, show_default=True, help="Number of results to return.")
@click.option("--mode", default="recall", show_default=True,
              type=click.Choice(["recall", "planning", "coding", "chat"]))
@click.option("--db", default=None, envvar="OMEM_DB")
def agent_recall(
    query: str,
    session: Optional[str],
    namespace: Optional[str],
    k: int,
    mode: str,
    db: Optional[str],
):
    """Retrieve relevant memories for a query.

    \b
    Example:
        omem agent recall "database setup" --k 5
    """
    from .agent_state import AgentState
    agent = AgentState(session_id=session, db_path=db)
    memories = agent.recall(query, k=k, namespace=namespace, mode=mode)
    if not memories:
        click.echo(click.style("No memories found.", fg="yellow"))
        return
    click.echo(click.style(f"Recalled {len(memories)} memories:", fg="cyan", bold=True))
    for i, mem in enumerate(memories, 1):
        score = getattr(mem, "score", mem.importance)
        click.echo(
            f"  {i:2}. [{mem.type.value:10}] {mem.content[:90]}"
            f"  (score={score:.2f})"
        )


@agent_group.command("learn")
@click.argument("subject")
@click.argument("predicate")
@click.argument("object_entity", metavar="OBJECT")
@click.option("--session", "-s", default=None, envvar="OMEM_SESSION", help="Session ID. Reads OMEM_SESSION if not set.")
@click.option("--confidence", default=1.0, type=float, show_default=True)
@click.option("--db", default=None, envvar="OMEM_DB")
def agent_learn(
    subject: str,
    predicate: str,
    object_entity: str,
    session: Optional[str],
    confidence: float,
    db: Optional[str],
):
    """Assert a knowledge graph relation via the facade.

    \b
    Example:
        omem agent learn FastAPI uses Pydantic
    """
    from .agent_state import AgentState
    agent = AgentState(session_id=session, db_path=db)
    edge_id = agent.learn(subject, predicate, object_entity, confidence=confidence)
    click.echo(click.style("✓ Learned", fg="green", bold=True))
    click.echo(f"  {subject!r} —[{predicate}]→ {object_entity!r}")
    click.echo(f"  edge_id: {edge_id}")


@agent_group.command("context")
@click.option("--task", required=True, help="What the agent is doing right now.")
@click.option("--session", "-s", default=None, envvar="OMEM_SESSION", help="Session ID. Reads OMEM_SESSION if not set.")
@click.option("--budget", default=6000, show_default=True, type=int)
@click.option("--mode", default="planning", show_default=True,
              type=click.Choice(["planning", "coding", "chat", "recall"]))
@click.option("--namespace", default=None)
@click.option("--json", "as_json", is_flag=True, default=False)
@click.option("--db", default=None, envvar="OMEM_DB")
def agent_context(
    task: str,
    session: Optional[str],
    budget: int,
    mode: str,
    namespace: Optional[str],
    as_json: bool,
    db: Optional[str],
):
    """Build an optimized context bundle for an LLM prompt.

    \b
    Example:
        omem agent context --task "implement OAuth2" --session my-agent
    """
    from .agent_state import AgentState
    agent = AgentState(session_id=session, db_path=db)
    bundle = agent.build_context(task, budget_tokens=budget, mode=mode)

    if as_json:
        click.echo(json.dumps({
            "text": bundle.text,
            "token_count": bundle.token_count,
            "savings_vs_naive": bundle.savings_vs_naive,
            "memories_used": bundle.memories_used,
        }, indent=2))
        return

    click.echo(bundle.text)
    click.echo()
    click.echo(click.style(
        f"✓  {bundle.token_count:,} / {budget:,} tokens  |  "
        f"savings: {bundle.savings_vs_naive:.0%}  |  "
        f"memories: {len(bundle.memories_used)}",
        fg="cyan",
    ))


@agent_group.command("snapshot")
@click.option("--session", "-s", default=None, envvar="OMEM_SESSION", help="Session ID. Reads OMEM_SESSION if not set.")
@click.option("--label", default=None, help="Human-readable snapshot label.")
@click.option("--db", default=None, envvar="OMEM_DB")
def agent_snapshot(session: str, label: Optional[str], db: Optional[str]):
    """Create a named state snapshot for a session."""
    from .agent_state import AgentState
    agent = AgentState(session_id=session, db_path=db)
    snap = agent.snapshot(label=label)
    click.echo(click.style("✓ Snapshot created", fg="green", bold=True))
    click.echo(f"  snapshot_id : {snap.id}")
    click.echo(f"  label       : {snap.label or '(none)'}")
    click.echo(f"  created_at  : {snap.created_at:.0f}")


@agent_group.command("checkpoint")
@click.option("--session", "-s", default=None, envvar="OMEM_SESSION", help="Session ID. Reads OMEM_SESSION if not set.")
@click.option("--db", default=None, envvar="OMEM_DB")
def agent_checkpoint(session: str, db: Optional[str]):
    """Write a crash-recovery checkpoint for a session."""
    from .agent_state import AgentState
    agent = AgentState(session_id=session, db_path=db)
    chk_id = agent.checkpoint()
    click.echo(click.style("✓ Checkpoint written", fg="green", bold=True))
    click.echo(f"  checkpoint_id : {chk_id}")


@agent_group.command("resume")
@click.option("--session", "-s", default=None, envvar="OMEM_SESSION", help="Session ID. Reads OMEM_SESSION if not set.")
@click.option("--db", default=None, envvar="OMEM_DB")
def agent_resume(session: str, db: Optional[str]):
    """Resume from the latest checkpoint for a session."""
    from .agent_state import AgentState
    agent = AgentState(session_id=session, db_path=db)
    payload = agent.resume()
    click.echo(click.style("✓ Session resumed", fg="green", bold=True))
    click.echo(f"  session : {payload.session_id}")
    click.echo(f"  goal    : {payload.goal or '(none)'}")
    click.echo(f"  status  : {payload.status}")
    click.echo(f"  step    : {payload.step}")


@agent_group.command("clone")
@click.option("--session", required=True, help="Source session to clone.")
@click.option("--new-session", default=None, help="ID for the cloned session.")
@click.option("--label", default="pre-clone", show_default=True)
@click.option("--db", default=None, envvar="OMEM_DB")
def agent_clone(session: str, new_session: Optional[str], label: str, db: Optional[str]):
    """Clone a session — fork state into a new independent session."""
    from .agent_state import AgentState
    agent = AgentState(session_id=session, db_path=db)
    clone = agent.clone(new_session_id=new_session, label=label)
    click.echo(click.style("✓ Session cloned", fg="green", bold=True))
    click.echo(f"  parent  : {session}")
    click.echo(f"  clone   : {clone.session_id}")


@agent_group.command("export")
@click.option("--session", "-s", default=None, envvar="OMEM_SESSION", help="Session ID. Reads OMEM_SESSION if not set.")
@click.option("--output", "-o", default="-", help="Output file (default: stdout).")
@click.option("--db", default=None, envvar="OMEM_DB")
def agent_export(session: str, output: str, db: Optional[str]):
    """Export full session state to JSON for handoff."""
    from .agent_state import AgentState
    agent = AgentState(session_id=session, db_path=db)
    data = agent.export_state()
    out_str = json.dumps(data, indent=2, default=str)
    if output == "-":
        click.echo(out_str)
    else:
        with open(output, "w") as f:
            f.write(out_str)
        click.echo(click.style(f"✓ Exported to {output}", fg="green"))


@agent_group.command("import")
@click.option("--session", required=True, help="Target session ID.")
@click.option("--input", "-i", "input_file", required=True,
              help="JSON file from a prior export.")
@click.option("--db", default=None, envvar="OMEM_DB")
def agent_import(session: str, input_file: str, db: Optional[str]):
    """Restore session state from a prior export."""
    from .agent_state import AgentState
    with open(input_file) as f:
        data = json.load(f)
    agent = AgentState(session_id=session, db_path=db)
    payload = agent.restore_state(data)
    click.echo(click.style("✓ State restored", fg="green", bold=True))
    click.echo(f"  session : {payload.session_id}")
    click.echo(f"  goal    : {payload.goal or '(none)'}")
    click.echo(f"  status  : {payload.status}")


@agent_group.command("ping")
@click.option("--session", "-s", default=None, envvar="OMEM_SESSION", help="Session ID.")
@click.option("--db", default=None, envvar="OMEM_DB")
def agent_ping(session: Optional[str], db: Optional[str]):
    """Quick health check — verify all layers are accessible.

    \b
    Example:
        omem agent ping
        omem agent ping --session mybot
    """
    from .agent_state import AgentState
    agent = AgentState(session_id=session, db_path=db)
    ok = agent.ping()
    if ok:
        click.echo(click.style("✓ All layers healthy", fg="green", bold=True))
    else:
        click.echo(click.style("✗ Health check failed", fg="red", bold=True))
        raise SystemExit(1)


@agent_group.command("explain")
@click.argument("query")
@click.option("--session", "-s", default=None, envvar="OMEM_SESSION", help="Session ID. Reads OMEM_SESSION if not set.")
@click.option("--namespace", "-n", default=None, envvar="OMEM_NS")
@click.option("--k", "-k", default=5, type=int, show_default=True, help="Memories to explain.")
@click.option("--mode", default="recall", show_default=True,
              type=click.Choice(["recall", "planning", "coding", "chat"]))
@click.option("--db", default=None, envvar="OMEM_DB")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def agent_explain(
    query: str, session: Optional[str], namespace: Optional[str],
    k: int, mode: str, db: Optional[str], as_json: bool,
):
    """Explain exactly why memories would be recalled for a query.

    Shows the full score decomposition (vector, keyword, recency, importance,
    confidence, graph proximity), provenance lineage, knowledge graph
    connections, and alignment with the current session goal.

    \b
    Example:
        omem agent explain "What database should I use?" --session mybot
        omem agent explain "API design" -k 3 --mode planning --json
        export OMEM_SESSION=mybot && omem agent explain "auth strategy"
    """
    from .agent_state import AgentState
    ns = namespace or "default"
    agent = AgentState(session_id=session, namespace=ns, db_path=db)
    report = agent.explain(query, k=k, namespace=namespace, mode=mode)
    if as_json:
        click.echo(json.dumps(report.as_dict(), indent=2, default=str))
    else:
        click.echo(report.format())


@agent_group.command("goal")
@click.argument("goal_text")
@click.option("--session", "-s", required=True, envvar="OMEM_SESSION", help="Session ID.")
@click.option("--namespace", "-n", default="default", envvar="OMEM_NS", show_default=True)
@click.option("--db", default=None, envvar="OMEM_DB")
def agent_goal(goal_text: str, session: str, namespace: str, db: Optional[str]):
    """Set the current goal for a session.

    \b
    Example:
        omem agent goal "Build a REST API with FastAPI" --session mybot
        export OMEM_SESSION=mybot && omem agent goal "Implement auth middleware"
    """
    from .agent_state import AgentState
    agent = AgentState(session_id=session, namespace=namespace, db_path=db)
    agent.set_goal(goal_text)
    click.echo(click.style("✓ Goal set", fg="green", bold=True))
    click.echo(f"  session : {session}")
    click.echo(f"  goal    : {goal_text}")


@agent_group.command("plan")
@click.argument("steps", nargs=-1, required=True)
@click.option("--session", "-s", required=True, envvar="OMEM_SESSION", help="Session ID.")
@click.option("--namespace", "-n", default="default", envvar="OMEM_NS", show_default=True)
@click.option("--db", default=None, envvar="OMEM_DB")
def agent_plan(steps, session: str, namespace: str, db: Optional[str]):
    """Set an execution plan for a session (ordered steps).

    \b
    Example:
        omem agent plan "Design schema" "Write models" "Add tests" --session mybot
        export OMEM_SESSION=mybot && omem agent plan "step 1" "step 2"
    """
    from .agent_state import AgentState
    agent = AgentState(session_id=session, namespace=namespace, db_path=db)
    agent.set_plan(list(steps))
    click.echo(click.style(f"✓ Plan set ({len(steps)} steps)", fg="green", bold=True))
    for i, s in enumerate(steps, 1):
        click.echo(f"  {i:2}. {s}")


@agent_group.command("rollback")
@click.argument("snapshot_id")
@click.option("--session", "-s", envvar="OMEM_SESSION")
@click.option("--db", default=None, envvar="OMEM_DB")
def agent_rollback(snapshot_id: str, session: Optional[str], db: Optional[str]):
    """Roll the session back to a named snapshot.

    \b
    Example:
        omem agent rollback snap_abc123 --session mybot
    """
    from .agent_state import AgentState
    agent = AgentState(session_id=session, db_path=db)
    payload = agent.rollback(snapshot_id)
    click.echo(click.style("✓ Rolled back", fg="green", bold=True))
    click.echo(f"  session     : {payload.session_id}")
    click.echo(f"  goal        : {payload.goal or '(none)'}")
    click.echo(f"  status      : {payload.status}")


@agent_group.command("forget")
@click.option("--session", "-s", envvar="OMEM_SESSION")
@click.option("--namespace", "-n", default="default", envvar="OMEM_NS", show_default=True)
@click.option("--db", default=None, envvar="OMEM_DB")
def agent_forget(session: Optional[str], namespace: str, db: Optional[str]):
    """Run heuristic forgetting — prune low-importance memories.

    \b
    Example:
        omem agent forget --session mybot
    """
    from .agent_state import AgentState
    agent = AgentState(session_id=session, namespace=namespace, db_path=db)
    agent.forget()
    click.echo(click.style("✓ Forgetting sweep completed", fg="green"))


@agent_group.command("consolidate")
@click.option("--session", "-s", envvar="OMEM_SESSION")
@click.option("--namespace", "-n", default="default", envvar="OMEM_NS", show_default=True)
@click.option("--db", default=None, envvar="OMEM_DB")
@click.option("--speed", default="normal", type=click.Choice(["fast", "normal"]), show_default=True)
def agent_consolidate(session: Optional[str], namespace: str, db: Optional[str], speed: str):
    """Run memory consolidation — merge duplicates, promote key memories.

    \b
    Example:
        omem agent consolidate --session mybot
        omem agent consolidate --speed fast
    """
    from .agent_state import AgentState
    agent = AgentState(session_id=session, namespace=namespace, db_path=db)
    result = agent.consolidate(speed=speed)
    click.echo(click.style("✓ Consolidation complete", fg="green", bold=True))
    if isinstance(result, dict):
        for k, v in result.items():
            click.echo(f"  {k}: {v}")


@agent_group.command("share")
@click.argument("memory_id")
@click.argument("target_namespace")
@click.option("--session", "-s", envvar="OMEM_SESSION")
@click.option("--db", default=None, envvar="OMEM_DB")
def agent_share(memory_id: str, target_namespace: str, session: Optional[str], db: Optional[str]):
    """Promote a memory to a shared namespace (team/org).

    \b
    Example:
        omem agent share mem-abc123 team/eng --session mybot
        omem agent share mem-abc123 org/acme --session mybot
    """
    from .agent_state import AgentState
    agent = AgentState(session_id=session, db_path=db)
    result = agent.share(memory_id, target_namespace=target_namespace)
    click.echo(click.style("✓ Shared", fg="green", bold=True))
    click.echo(f"  from : {result['source_namespace']}")
    click.echo(f"  to   : {result['target_namespace']}")
    click.echo(f"  id   : {result['new_id']}")


cli.add_command(agent_group)


# ──────────────────────────────────────────────────────────────────────────────
# omem observe  — Phase 6
# ──────────────────────────────────────────────────────────────────────────────

@click.group("observe")
def observe_group():
    """Observability — every operation emits a trace you can query.

    \b
    Examples:
        omem observe metrics --session mybot
        omem observe traces  --session mybot
        omem observe replay  --session mybot
        omem observe export-otel --session mybot --out traces.json
    """


@observe_group.command("metrics")
@click.option("--session", default=None, help="Filter to a specific session.")
@click.option("--namespace", default=None, help="Filter to a specific namespace.")
@click.option("--db", default=None, envvar="OMEM_DB")
def observe_metrics(session: Optional[str], namespace: Optional[str], db: Optional[str]):
    """Print aggregated metrics for a session or namespace."""
    from .agent_state import AgentState
    import json as _json
    agent = AgentState(session_id=session, namespace=namespace or "default", db_path=db)
    m = agent.observe.metrics(session_id=session, namespace=namespace)
    click.echo(_json.dumps(m, indent=2, default=str))


@observe_group.command("traces")
@click.option("--session", required=True, help="Session ID to retrieve traces for.")
@click.option("--db", default=None, envvar="OMEM_DB")
@click.option("--limit", default=50, show_default=True, help="Max events to show.")
def observe_traces(session: str, db: Optional[str], limit: int):
    """List trace events for a session."""
    from .agent_state import AgentState
    agent = AgentState(session_id=session, db_path=db)
    events = agent.observe.traces(session)
    click.echo(f"Session: {session}  ({len(events)} events)")
    for ev in events[:limit]:
        click.echo(
            f"  [{ev.event_type:<18}] +{ev.duration_ms:6.1f}ms  {ev.payload}"
        )


@observe_group.command("replay")
@click.option("--session", required=True, help="Session ID to replay.")
@click.option("--db", default=None, envvar="OMEM_DB")
def observe_replay(session: str, db: Optional[str]):
    """Step-by-step replay of all events in a session."""
    from .agent_state import AgentState
    agent = AgentState(session_id=session, db_path=db)
    idx = 0
    for ev in agent.observe.replay(session):
        idx += 1
        click.echo(f"  {idx:4d}. [{ev.event_type}] {ev.payload}")
    if idx == 0:
        click.echo("No events recorded for this session.")


@observe_group.command("export-otel")
@click.option("--session", default=None, help="Session ID (None = all sessions).")
@click.option("--db", default=None, envvar="OMEM_DB")
@click.option("--out", default=None, help="Output file (default: stdout).")
def observe_export_otel(session: Optional[str], db: Optional[str], out: Optional[str]):
    """Export traces as OpenTelemetry-compatible OTLP JSON."""
    from .agent_state import AgentState
    import json as _json
    agent = AgentState(session_id=session, db_path=db)
    data = agent.observe.export_otel(session_id=session)
    payload = _json.dumps(data, indent=2, default=str)
    if out:
        with open(out, "w") as f:
            f.write(payload)
        click.echo(f"Written to {out}")
    else:
        click.echo(payload)


cli.add_command(observe_group)


# ──────────────────────────────────────────────────────────────────────────────
# omem provenance  — Phase 7
# ──────────────────────────────────────────────────────────────────────────────

@click.group("provenance")
def provenance_group():
    """Provenance — trace where every memory and state change came from.

    \b
    Examples:
        omem provenance trace  --entity mem-abc123
        omem provenance history --namespace team/platform
        omem provenance summary
    """


@provenance_group.command("trace")
@click.option("--entity", required=True, help="Entity ID (memory, snapshot, edge).")
@click.option("--session", default=None, envvar="OMEM_SESSION")
@click.option("--db", default=None, envvar="OMEM_DB")
def provenance_trace(entity: str, session: Optional[str], db: Optional[str]):
    """Print the full lineage chain for an entity."""
    from .agent_state import AgentState
    import json as _json
    agent = AgentState(session_id=session, db_path=db)
    chain = agent.provenance.trace(entity)
    click.echo(f"Entity: {chain.root_id}  ({len(chain.events)} events)")
    for ev in chain.events:
        click.echo(f"  {ev.operation:<12} {ev.source:<16} {ev.entity_type}")


@provenance_group.command("history")
@click.option("--namespace", default="default", show_default=True)
@click.option("--limit", default=20, show_default=True)
@click.option("--since", default=None, help="Unix timestamp (filter).")
@click.option("--session", default=None, envvar="OMEM_SESSION")
@click.option("--db", default=None, envvar="OMEM_DB")
def provenance_history(namespace: str, limit: int, since: Optional[str], session: Optional[str], db: Optional[str]):
    """Print recent provenance events for a namespace."""
    from .agent_state import AgentState
    since_ts = float(since) if since else None
    agent = AgentState(session_id=session, db_path=db)
    events = agent.provenance.history(namespace, limit=limit, since=since_ts)
    click.echo(f"Namespace: {namespace}  ({len(events)} events)")
    for ev in events:
        click.echo(f"  {ev.operation:<12} {ev.entity_type:<12} {ev.entity_id[:16]}")


@provenance_group.command("summary")
@click.option("--namespace", default=None)
@click.option("--session", default=None, envvar="OMEM_SESSION")
@click.option("--db", default=None, envvar="OMEM_DB")
def provenance_summary(namespace: Optional[str], session: Optional[str], db: Optional[str]):
    """Print aggregate provenance statistics."""
    from .agent_state import AgentState
    import json as _json
    agent = AgentState(session_id=session, db_path=db)
    s = agent.provenance.summary(namespace=namespace)
    click.echo(_json.dumps(s, indent=2, default=str))


cli.add_command(provenance_group)


# ──────────────────────────────────────────────────────────────────────────────
# omem governance  — Phase 8
# ──────────────────────────────────────────────────────────────────────────────

@click.group("governance")
def governance_group():
    """Governance — retention, audit trail, RBAC, and data deletion.

    \b
    Examples:
        omem governance policy-add --pattern "org/acme/*" --max-age-days 90
        omem governance enforce
        omem governance audit --namespace default --limit 50
        omem governance delete --scope namespace --id team/old-project
    """


@governance_group.command("policy-add")
@click.option("--pattern", required=True, help="Namespace glob pattern (e.g. 'org/acme/*').")
@click.option("--max-age-days", default=None, type=int, help="Delete memories older than N days.")
@click.option("--max-count", default=None, type=int, help="Keep only top N memories per namespace.")
@click.option("--tier", default=None, help="Restrict to tier: ACTIVE | ARCHIVE | DEEP.")
@click.option("--db", default=None, envvar="OMEM_DB")
def governance_policy_add(pattern: str, max_age_days: Optional[int], max_count: Optional[int], tier: Optional[str], db: Optional[str]):
    """Register a retention policy."""
    from .agent_state import AgentState
    from .governance import RetentionPolicy
    agent = AgentState(db_path=db)
    policy = RetentionPolicy(
        namespace_pattern=pattern,
        max_age_days=max_age_days,
        max_count=max_count,
        tier=tier,
    )
    agent.governance.set_policy(policy)
    click.echo(click.style(f"✓ Policy set for {pattern!r}", fg="green"))


@governance_group.command("enforce")
@click.option("--db", default=None, envvar="OMEM_DB")
def governance_enforce(db: Optional[str]):
    """Apply all active retention policies immediately."""
    from .agent_state import AgentState
    import json as _json
    agent = AgentState(db_path=db)
    report = agent.governance.enforce_retention()
    click.echo(click.style(
        f"✓ Retention enforced: {report.memories_evicted} memories evicted",
        fg="green" if not report.errors else "yellow",
    ))
    if report.errors:
        for e in report.errors:
            click.echo(f"  warning: {e}")


@governance_group.command("audit")
@click.option("--namespace", default=None, help="Filter by namespace.")
@click.option("--op", default=None, help="Filter by operation.")
@click.option("--limit", default=20, show_default=True)
@click.option("--db", default=None, envvar="OMEM_DB")
def governance_audit(namespace: Optional[str], op: Optional[str], limit: int, db: Optional[str]):
    """Query the audit log."""
    from .agent_state import AgentState
    agent = AgentState(db_path=db)
    entries = agent.governance.audit(namespace=namespace, operation=op, limit=limit)
    click.echo(f"Audit log ({len(entries)} entries)")
    for e in entries:
        import datetime
        ts = datetime.datetime.fromtimestamp(e["ts"]).strftime("%Y-%m-%d %H:%M:%S")
        click.echo(f"  {ts}  {e['operation']:<20}  {e['namespace']:<20}  {e.get('memory_id','')[:12]}")


@governance_group.command("delete")
@click.option("--scope", required=True, type=click.Choice(["memory_id", "namespace", "user", "org"]))
@click.option("--id", "id_", required=True, help="The ID to delete.")
@click.option("--no-cascade", is_flag=True, default=False, help="Skip cascade deletion of state.")
@click.option("--db", default=None, envvar="OMEM_DB")
def governance_delete(scope: str, id_: str, no_cascade: bool, db: Optional[str]):
    """Delete data at a given scope."""
    from .agent_state import AgentState
    agent = AgentState(db_path=db)
    report = agent.governance.delete_scope(scope, id_, cascade=not no_cascade)
    click.echo(click.style(
        f"✓ Deleted: {report.total_deleted} records "
        f"({report.deleted_memories} memories, {report.deleted_snapshots} snapshots)",
        fg="green" if not report.errors else "yellow",
    ))
    if report.errors:
        for e in report.errors:
            click.echo(f"  warning: {e}", err=True)


cli.add_command(governance_group)


# ──────────────────────────────────────────────────────────────────────────────
# omem runtime  — Phase 9
# ──────────────────────────────────────────────────────────────────────────────

@click.group("runtime")
def runtime_group():
    """Multi-agent runtime — register agents, sync state, recover from crashes.

    \b
    Examples:
        omem runtime register --agent researcher --session sess-1 --namespace prod
        omem runtime list     --namespace prod
        omem runtime recover  --agent researcher
        omem runtime summary  --namespace prod
    """


@runtime_group.command("register")
@click.option("--agent", "agent_id", required=True, help="Agent ID to register.")
@click.option("--session", required=True, help="Session ID this agent operates on.")
@click.option("--namespace", default="default", show_default=True)
@click.option("--capability", "capabilities", multiple=True, help="Agent capability flags.")
@click.option("--db", default=None, envvar="OMEM_DB")
def runtime_register(agent_id: str, session: str, namespace: str, capabilities, db: Optional[str]):
    """Register an agent in the namespace runtime registry."""
    from .agent_state import AgentState
    agent = AgentState(session_id=session, namespace=namespace, db_path=db)
    reg = agent.register_agent(agent_id, capabilities=list(capabilities))
    click.echo(click.style(f"✓ Registered {agent_id!r}", fg="green"))
    click.echo(f"  session   : {reg['session_id']}")
    click.echo(f"  namespace : {reg['namespace']}")
    click.echo(f"  status    : {reg['status']}")


@runtime_group.command("list")
@click.option("--namespace", default="default", show_default=True)
@click.option("--status", default=None, type=click.Choice(["active", "idle", "crashed", "done"]))
@click.option("--db", default=None, envvar="OMEM_DB")
def runtime_list(namespace: str, status: Optional[str], db: Optional[str]):
    """List agents registered in a namespace."""
    from .agent_state import AgentState
    agent = AgentState(namespace=namespace, db_path=db)
    agents = agent.runtime.list_agents(namespace, status=status)
    if not agents:
        click.echo(f"No agents in namespace {namespace!r} (filter: {status or 'all'})")
        return
    click.echo(f"Agents in {namespace!r}:")
    for a in agents:
        import datetime
        hb = datetime.datetime.fromtimestamp(a.last_heartbeat).strftime("%H:%M:%S")
        click.echo(f"  {a.agent_id:<24} {a.status:<10} session={a.session_id[:16]} hb={hb}")


@runtime_group.command("recover")
@click.option("--agent", "agent_id", required=True, help="Crashed agent ID to recover.")
@click.option("--db", default=None, envvar="OMEM_DB")
def runtime_recover(agent_id: str, db: Optional[str]):
    """Recover state for a crashed agent."""
    from .agent_state import AgentState
    import json as _json
    agent = AgentState(db_path=db)
    payload = agent.runtime.recover(agent_id)
    if payload is None:
        click.echo(f"No recovery data found for agent {agent_id!r}", err=True)
        raise SystemExit(1)
    click.echo(click.style(f"✓ Recovered state for {agent_id!r}", fg="green"))
    click.echo(_json.dumps(payload, indent=2, default=str))


@runtime_group.command("deregister")
@click.option("--agent", "agent_id", required=True)
@click.option("--db", default=None, envvar="OMEM_DB")
def runtime_deregister(agent_id: str, db: Optional[str]):
    """Remove an agent from the registry (mark as done)."""
    from .agent_state import AgentState
    agent = AgentState(db_path=db)
    ok = agent.runtime.deregister(agent_id)
    if ok:
        click.echo(click.style(f"✓ Deregistered {agent_id!r}", fg="green"))
    else:
        click.echo(f"Agent {agent_id!r} not found", err=True)


@runtime_group.command("summary")
@click.option("--namespace", default="default", show_default=True)
@click.option("--db", default=None, envvar="OMEM_DB")
def runtime_summary(namespace: str, db: Optional[str]):
    """Print a health summary for all agents in a namespace."""
    from .agent_state import AgentState
    import json as _json
    agent = AgentState(namespace=namespace, db_path=db)
    s = agent.runtime.namespace_summary(namespace)
    click.echo(_json.dumps(s, indent=2, default=str))


cli.add_command(runtime_group)


# ──────────────────────────────────────────────────────────────────────────────
# omem org  — Phase 10
# ──────────────────────────────────────────────────────────────────────────────

@click.group("org")
def org_group():
    """Organizational memory — team/org namespace hierarchy and memory promotion.

    Namespace hierarchy:  personal/{user}  →  team/{team}  →  org/{org}  →  global

    \b
    Examples:
        omem org remember "API rate limit is 100/min" --scope org --org-id acme
        omem org recall   "rate limits" --scope team  --team eng --org-id acme
        omem org share    --memory mem-abc --to team/eng
        omem org namespaces --user alice --team eng --org-id acme
    """


@org_group.command("remember")
@click.argument("content")
@click.option("--scope", default="personal", show_default=True,
              type=click.Choice(["personal", "team", "org", "global"]))
@click.option("--user", "user_id", default=None, envvar="OMEM_USER_ID")
@click.option("--team", "team_id", default=None, envvar="OMEM_TEAM_ID")
@click.option("--org-id", "org_id", default=None, envvar="OMEM_ORG_ID")
@click.option("--db", default=None, envvar="OMEM_DB")
def org_remember(content: str, scope: str, user_id: Optional[str], team_id: Optional[str], org_id: Optional[str], db: Optional[str]):
    """Store a memory in the resolved org namespace."""
    from .agent_state import AgentState
    agent = AgentState(db_path=db)
    agent.org._user_id = user_id or ""
    agent.org._team_id = team_id or ""
    agent.org._org_id = org_id or ""
    mid = agent.org.remember(content, scope=scope)
    click.echo(click.style(f"✓ Stored in {scope} namespace", fg="green"))
    click.echo(f"  memory_id: {mid}")


@org_group.command("recall")
@click.argument("query")
@click.option("--scope", default="team", show_default=True)
@click.option("--k", default=5, show_default=True)
@click.option("--user", "user_id", default=None, envvar="OMEM_USER_ID")
@click.option("--team", "team_id", default=None, envvar="OMEM_TEAM_ID")
@click.option("--org-id", "org_id", default=None, envvar="OMEM_ORG_ID")
@click.option("--db", default=None, envvar="OMEM_DB")
def org_recall(query: str, scope: str, k: int, user_id: Optional[str], team_id: Optional[str], org_id: Optional[str], db: Optional[str]):
    """Recall memories scoped to the org namespace hierarchy."""
    from .agent_state import AgentState
    agent = AgentState(db_path=db)
    agent.org._user_id = user_id or ""
    agent.org._team_id = team_id or ""
    agent.org._org_id = org_id or ""
    results = agent.org.recall_scoped(query, scope=scope, k=k)
    if not results:
        click.echo("No results.")
        return
    click.echo(f"Results ({len(results)}):")
    for i, m in enumerate(results, 1):
        ns = getattr(m, "namespace", "?")
        click.echo(f"  {i}. [{ns}] {getattr(m, 'content', str(m))[:80]}")


@org_group.command("share")
@click.option("--memory", "memory_id", required=True, help="Memory ID to share.")
@click.option("--to", "target", required=True, help="Target namespace (e.g. 'team/eng').")
@click.option("--db", default=None, envvar="OMEM_DB")
def org_share(memory_id: str, target: str, db: Optional[str]):
    """Promote a memory to a shared namespace tier."""
    from .agent_state import AgentState
    agent = AgentState(db_path=db)
    result = agent.share(memory_id, target_namespace=target)
    click.echo(click.style("✓ Memory shared", fg="green"))
    click.echo(f"  original : {result['original_id']}")
    click.echo(f"  new_id   : {result['new_id']}")
    click.echo(f"  from     : {result['source_namespace']}")
    click.echo(f"  to       : {result['target_namespace']}")


@org_group.command("namespaces")
@click.option("--user", "user_id", default=None, envvar="OMEM_USER_ID")
@click.option("--team", "team_id", default=None, envvar="OMEM_TEAM_ID")
@click.option("--org-id", "org_id", default=None, envvar="OMEM_ORG_ID")
@click.option("--db", default=None, envvar="OMEM_DB")
def org_namespaces(user_id: Optional[str], team_id: Optional[str], org_id: Optional[str], db: Optional[str]):
    """List all namespaces available to the current identity."""
    from .agent_state import AgentState
    agent = AgentState(db_path=db)
    agent.org._user_id = user_id or ""
    agent.org._team_id = team_id or ""
    agent.org._org_id = org_id or ""
    infos = agent.org.namespaces()
    click.echo(f"Available namespaces ({len(infos)}):")
    for ns_info in infos:
        rw = "rw" if ns_info.is_writable else "ro"
        click.echo(f"  [{rw}] {ns_info.namespace:<36} {ns_info.kind:<10} {ns_info.memory_count} memories")


cli.add_command(org_group)


def main():
    """Entry point with friendly, non-noisy error handling.

    Click already renders usage errors, ``--help``, and Ctrl-C cleanly (these
    raise ``SystemExit`` / ``Abort``, which we let through). We only wrap
    *unexpected* runtime errors so users get a clean one-line message instead of
    a raw traceback. Set ``OMEM_DEBUG=1`` to see the full traceback.
    """
    try:
        cli()
    except Exception as exc:  # noqa: BLE001 — top-level guard for a friendly CLI
        if os.environ.get("OMEM_DEBUG"):
            raise
        failure(str(exc) or exc.__class__.__name__)
        hint("re-run with OMEM_DEBUG=1 for the full traceback")
        sys.exit(1)


if __name__ == "__main__":
    main()
