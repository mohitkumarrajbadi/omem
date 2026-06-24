"""OMem CLI — professional-grade command line interface for OMem."""

import json
import os
import sys
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional

import click

from . import __version__
from .api import OMem
from .types import MemoryType

# Omem CLI Banner with stylized output for enhanced user experience and branding consistency.
CLI_BANNER = click.style(
    r"""
 ██████╗ ███╗   ███╗███████╗███╗   ███╗
██╔═══██╗████╗ ████║██╔════╝████╗ ████║
██║   ██║██╔████╔██║█████╗  ██╔████╔██║
██║   ██║██║╚██╔╝██║██╔══╝  ██║╚██╔╝██║
╚██████╔╝██║ ╚═╝ ██║███████╗██║ ╚═╝ ██║
 ╚═════╝ ╚═╝     ╚═╝╚══════╝╚═╝     ╚═╝

OMem — AI Memory Operating System
────────────────────────────────────────────────────────────
Unified memory • Retrieval • Reflection • Knowledge Graphs
""",
    fg="cyan",
    bold=True,
)

COMMAND_GROUPS = OrderedDict(
    [
        (
            "Core Memory Operations",
            [
                "init",
                "remember",
                "recall",
                "sleep",
                "add",
                "search",
                "list",
                "clear",
                "stats",
                "inspect",
                "maintain",
            ],
        ),
        # v2 command groups — registered when each phase is implemented
        ("Agent State", ["state"]),
        ("Context Engine", ["context"]),
        ("Knowledge Graph", ["knowledge"]),
        ("Observability", ["observe"]),
        ("Project Memory & Codebase", ["ingest", "sync", "codebase", "namespaces"]),
        ("Integration & Monitoring", ["serve", "dashboard", "demo"]),
        ("Data Lifecycle", ["export", "import", "version", "completion"]),
        ("Diagnostics & Benchmarks", ["health", "benchmark"]),
    ]
)

class OMemGroup(click.Group):
    """Custom Click Group to provide polished categorized help output."""

    def format_help(self, ctx, formatter):
        formatter.write(CLI_BANNER)
        formatter.write("\n\n")
        self.format_usage(ctx, formatter)
        self.format_options(ctx, formatter)
        self.format_commands(ctx, formatter)

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
            with formatter.section("Other Commands"):
                rows = []
                for name in orphan_cmds:
                    cmd = self.get_command(ctx, name)
                    rows.append((name, cmd.get_short_help_str() if cmd else ""))
                formatter.write_dl(rows)

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
    click.echo(click.style(f"Recalled {len(results)} memories:", fg="green", bold=True))
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
    help="Custom SQLite database path or backend connection string.",
)
@click.option(
    "--backend",
    default="sqlite",
    type=click.Choice(["sqlite", "memory", "postgres"]),
    help="Select the storage backend.",
)
@click.option(
    "--embedding-provider",
    default="local",
    type=click.Choice(["local", "openai", "sentence-transformers"]),
    help="Embedding provider used for memory vectorization.",
)
@click.option("--quiet", is_flag=True, help="Suppress non-essential output.")
@click.pass_context
def cli(ctx: click.Context, db_path: Optional[str], backend: str, embedding_provider: str, quiet: bool):
    """Persistent Memory OS for agent-grade memory, retrieval, and reasoning."""
    ctx.ensure_object(dict)
    ctx.obj["db_path"] = db_path
    ctx.obj["backend"] = backend
    ctx.obj["embedding_provider"] = embedding_provider
    ctx.obj["quiet"] = quiet

    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


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

    click.echo(click.style("OMem subsystem successfully initialized.", fg="green", bold=True))
    click.echo(f"  Target Ledger: {db_path}")
    click.echo(f"  Active Records: {m.stats().get('total', 0)} memories")
    click.echo("\nQuickstart:")
    click.echo('  omem add "Context to retain"')
    click.echo('  omem search "Query term"')


@cli.command()
@click.argument("content")
@click.option("--importance", "-i", type=float, help="Explicit importance weight [0.0-1.0].")
@click.option("--namespace", "-n", default="default", help="Isolate memory partition.")
@click.option("--type", "-t", "mem_type", help="Target schema memory classification type.")
@click.pass_context
def add(ctx: click.Context, content: str, importance: Optional[float], namespace: str, mem_type: Optional[str]):
    """Write an individual text memory vector."""
    m = _get_omem(ctx)

    kwargs: Dict[str, Any] = {"namespace": namespace}
    if importance is not None:
        kwargs["importance"] = importance
    if mem_type:
        kwargs["mem_type"] = _resolve_memory_type(mem_type)

    mem_id = m.add(content, **kwargs)
    mem = m.get(mem_id)

    click.echo(click.style("Memory committed.", fg="green", bold=True))
    click.echo(f"  UID:        {mem_id[:12]}")
    click.echo(f"  Type:       {mem.type.name}")
    click.echo(f"  Weight:     {mem.importance:.2f}")
    click.echo(f"  Namespace:  {mem.namespace}")


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
    """V2: store graph-backed memory."""
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

    click.echo(click.style("Remembered.", fg="green", bold=True))
    click.echo(f"  id:         {mem.id[:12]}")
    click.echo(f"  type:       {mem.type.name}")
    click.echo(f"  namespace:  {mem.namespace}")
    click.echo(f"  importance: {mem.importance:.2f}")
    click.echo(f"  confidence: {mem.confidence_score:.2f}")


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
    """Query current memory states via hybrid retrieval."""
    m = _get_omem(ctx)

    results = m.recall(
        query,
        k=k,
        namespace=namespace,
        context_type=context_type,
        time_range=time_range,
    )

    if not results:
        click.echo(click.style("No memories found for the given query.", fg="yellow"))
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
    """V2: recall memories with multi-objective retrieval."""
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
        click.echo(click.style("No memories matched this query.", fg="yellow"))
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
def list(ctx: click.Context, namespace: Optional[str], mem_type: Optional[str], limit: int, inactive: bool, output_format: str):
    """Scan and list a segment of linear memory blocks."""
    m = _get_omem(ctx)
    memories = m.all(namespace=namespace, include_inactive=inactive)

    if mem_type:
        type_enum = getattr(MemoryType, mem_type.upper(), None)
        if type_enum:
            memories = [mem for mem in memories if mem.type == type_enum]

    memories = memories[:limit]

    if not memories:
        click.echo(click.style("No available records matched specifications.", fg="yellow"))
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

    click.echo(click.style(f"Displaying top {len(memories)} elements:", fg="green", bold=True))
    click.echo("")
    for i, mem in enumerate(memories, 1):
        status = "●" if mem.active else "○"
        click.echo(
            f"  {status} {i:02d} [{mem.type.name:11s}] w={mem.importance:.2f} | {mem.content[:65]}"
        )


@cli.command()
@click.argument("query")
@click.option("--k", default=5, help="Inspection target vector pool depth.")
@click.pass_context
def inspect(ctx: click.Context, query: str, k: int):
    """Verify raw algorithm score matrix distribution details."""
    m = _get_omem(ctx)
    exps = m.inspect(query, top_k=k)

    if not exps:
        click.echo(click.style("Inspection requires at least one indexed memory entry.", fg="yellow"))
        return

    click.echo(click.style(f"Scoring Analysis Matrix for: '{query}'", fg="green", bold=True))
    click.echo("─" * 60)
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
    """Display volumetric health data metrics overview."""
    m = _get_omem(ctx)
    s = m.stats()

    if output_format == "json":
        click.echo(json.dumps(s, indent=2, default=str, sort_keys=True))
        return

    click.echo("\nOMem Volumetric Index Summary")
    click.echo("─" * 45)
    click.echo(f"  Total Index Nodes:    {s['total']}")
    click.echo(f"  Active Contexts:      {s['total'] - s['inactive']}")
    click.echo(f"  Pruned/Inactive:      {s['inactive']}")
    click.echo(f"  Mean Importance Node: {s['avg_importance']:.2f}")
    click.echo(f"  Knowledge Graph Links: {s.get('graph_edges', 0)} edges")

    ns_str = ", ".join(s.get('namespaces', [])) if s.get('namespaces') else "default"
    click.echo(f"  Allocated Namespaces: {ns_str}")
    click.echo("\nNode Type Weight Distributions:")
    for mtype, count in s.get("types", {}).items():
        click.echo(f"    {mtype:15s} {count:>5d}")
    click.echo()


@cli.command()
@click.option("--namespace", "-n", help="Export matching partition scope only.")
@click.option(
    "--format",
    "-f",
    "fmt",
    default="json",
    type=click.Choice(["json", "txt"]),
    help="Target extraction template structure.",
)
@click.option("--output", "-o", help="File disk path output destination.")
@click.pass_context
def export(ctx: click.Context, namespace: Optional[str], fmt: str, output: Optional[str]):
    """Serialize and export internal spaces out to standard formats."""
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
        click.echo(
            click.style(
                f"Export successful: {len(memories)} entries saved to {output}",
                fg="green",
            )
        )
    else:
        click.echo(content)


@cli.command(name="import")
@click.argument("file", type=click.Path(exists=True))
@click.option("--namespace", "-n", default="default", help="Import ingestion target partition namespace.")
@click.pass_context
def load(ctx: click.Context, file: str, namespace: str):
    """Incorporate records from standardized historical source files."""
    import builtins
    m = _get_omem(ctx)

    with open(file, "r") as f:
        data = json.load(f)

    if isinstance(data, dict) and "memories" in data:
        memories = data["memories"]
    elif isinstance(data, builtins.list):
        memories = data
    else:
        click.echo(click.style("Error: unsupported import format.", fg="red"))
        return

    click.echo(click.style(f"Hydrating {len(memories)} storage cells...", fg="blue"))
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

    click.echo(
        click.style(
            f"Hydration complete: {count} elements allocated inside partition '{namespace}'.",
            fg="green",
        )
    )


@cli.command()
@click.option("--compress", is_flag=True, help="Consolidate contextual overlap anomalies.")
@click.option("--reflect", is_flag=True, help="Trigger consolidation analytical reflections.")
@click.option("--forget", is_flag=True, help="Force execute decay logic prune intervals.")
@click.option("--dream", is_flag=True, help="Execute cross-cluster consolidation cycles.")
@click.option(
    "--all", "all_ops", is_flag=True, help="Run standard full-stack lifecycle maintenance optimizations."
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
    """Execute structural optimization and decay consolidation passes."""
    m = _get_omem(ctx)

    if all_ops or not any([compress, reflect, forget, dream]):
        click.echo(click.style("Initializing system optimizations pass...", fg="blue"))
        result = m.sleep()
        click.echo(click.style("Optimization routine complete.", fg="green"))
        click.echo(f"  Merged Units:      {result.get('compressed', 0)}")
        click.echo(f"  Derived Insights:  {result.get('reflected', 0)}")
        click.echo(f"  Pruned Nodes:      {result.get('forgotten', 0)}")
        return

    if compress:
        click.echo("Compressing high-overlap data nodes...")
        result = m.compress()
        click.echo(f"Compressed {result['compressed']} configurations; suspended {result['deactivated']} nodes.")

    if reflect:
        click.echo("Compiling system analytical patterns...")
        refs = m.reflect()
        click.echo(f"Injected {len(refs)} derived contextual optimization cells.")

    if forget:
        click.echo("Processing index structural weight decay evaluations...")
        result = m.forget()
        click.echo(f"Pruned {len(result.forgotten_ids)} sub-threshold memory blocks.")

    if dream:
        click.echo("Executing deep non-linear correlation graph consolidation...")
        result = m.dream()
        click.echo(
            f"Completed: {result.clusters_formed} topology clusters mapped, {result.insights_created} nodes injected."
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
    """V2: run memory consolidation and maintenance."""
    from .memory import MemoryOS

    memory = MemoryOS(_get_omem(ctx))
    result = memory.consolidate(speed=speed)

    if output_format == "json":
        click.echo(json.dumps(result, indent=2, default=str, sort_keys=True))
        return

    click.echo(click.style("Sleep cycle complete.", fg="green", bold=True))
    for key in sorted(result):
        click.echo(f"  {key}: {result[key]}")


@cli.command()
@click.option("--namespace", "-n", help="Target singular partition scope to dump.")
@click.confirmation_option(prompt="Confirm structural destruction command sequence? This action cannot be reversed.")
@click.pass_context
def clear(ctx: click.Context, namespace: Optional[str]):
    """Purge structural memory registers safely."""
    m = _get_omem(ctx)
    if namespace:
        m.clear(namespace=namespace)
        click.echo(click.style(f"Dropped storage partition namespace context: '{namespace}'", fg="green"))
    else:
        m.clear()
        click.echo(click.style("System wipe successful. All memory systems blank.", fg="green"))


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
    """List structural partitions and allocation distribution maps."""
    m = _get_omem(ctx)
    ns_list = m.namespaces()

    if not ns_list:
        click.echo(click.style("Zero namespace allocations logged.", fg="yellow"))
        return

    if output_format == "json":
        mapping = {ns: m.namespace_stats(ns).get("total", 0) for ns in ns_list}
        click.echo(json.dumps(mapping, indent=2, sort_keys=True))
        return

    click.echo("Active Namespace Allocation Map:\n")
    for ns in ns_list:
        stats = m.namespace_stats(ns)
        click.echo(f"  • {ns:22s} {stats.get('total', 0):>6d} elements allocated")


@cli.command()
@click.pass_context
def demo(ctx: click.Context):
    """Initiate an automated end-to-end features demo loop."""
    m = _get_omem(ctx)
    click.echo("\n" + "═" * 50)
    click.echo("  OMem Engine Framework Simulation Terminal")
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

    click.echo("Simulating active stream records additions...")
    for content in samples:
        mid = m.add(content)
        mem = m.get(mid)
        click.echo(f"  [{mem.type.name:11s}] w={mem.importance:.2f} | {content[:50]}")

    s = m.stats()
    click.echo(f"\nMatrix Status: {s['total']} logs running, {len(s['types'])} variants loaded.\n")

    click.echo("Testing similarity extraction recall heuristics:")
    for q in ["Who am I?", "deployment production", "security urgent"]:
        results = m.recall(q, k=2)
        click.echo(f'  Query target: "{q}"')
        for r in results:
            click.echo(f"    ↳ [{r.score:.3f}] {r.content[:55]}")

    click.echo("\nExecuting background structural convergence logic...")
    result = m.compress()
    click.echo(f"  Group targets consolidated: {result['compressed']}. Linear allocations dropped: {result['deactivated']}")

    click.echo("\nSimulating metadata insight calculations...")
    refs = m.reflect()
    click.echo(f"  Synthesized {len(refs)} cognitive patterns.")
    click.echo("\n" + "═" * 50)
    click.echo("  Verification phase pass complete.")


@cli.command()
@click.option("--n", default=10_000, help="Throughput load parameter size configuration.")
@click.pass_context
def benchmark(ctx: click.Context, n: int):
    """Run real-time performance ingestion calculations metrics logs."""
    m = _get_omem(ctx)
    click.echo(click.style(f"\nInitiating benchmark profile routines across {n:,} simulated items...\n", fg="blue"))

    t0 = time.perf_counter()
    for i in range(n):
        m.add(f"Benchmark transaction sequence {i}: tag {i % 100} vector block {i % 50}", importance=0.5)
    add_time = time.perf_counter() - t0

    click.echo(
        f"  Writes:   {_format_duration(add_time)} total | {(add_time / n) * 1000:.4f}ms/op | {n / add_time:,.0f} records/sec"
    )

    queries = 1000
    t0 = time.perf_counter()
    for i in range(queries):
        m.recall(f"tag {i % 100} vector block {i % 50}", k=5)
    rag_time = time.perf_counter() - t0

    click.echo(
        f"  Queries:  {_format_duration(rag_time)} total | {(rag_time / queries) * 1000:.4f}ms/query | {queries / rag_time:,.0f} find/sec"
    )


@cli.command()
@click.option("--port", default=7900, help="Interface telemetry bind server port address.")
@click.pass_context
def dashboard(ctx: click.Context, port: int):
    """Launch the localized diagnostic telemetry monitoring browser app."""
    from .viz.server import serve as start_dashboard

    m = _get_omem(ctx)
    start_dashboard(omem=m, port=port)


@cli.command()
@click.pass_context
def health(ctx: click.Context):
    """Verify standard structural process context errors status."""
    try:
        m = _get_omem(ctx)
        stats = m.stats()
        click.echo(click.style("SYSTEM STATUS: OPERATIONAL", fg="green", bold=True))
        click.echo(f"Core Engine  : v{__version__}")
        click.echo(f"Local Matrix : {stats['total']} cells mapped")
        sys.exit(0)
    except Exception as e:
        click.echo(click.style(f"SYSTEM STATUS: DEGRADED - CRITICAL FAULT: {e}", fg="red"), err=True)
        sys.exit(1)


@cli.command()
@click.argument('path', default='.', type=click.Path(exists=True))
@click.option('--namespace', '-n', default='project', help='Partition mapping label target.')
@click.pass_context
def ingest(ctx: click.Context, path: str, namespace: str):
    """Ingest clean static filesystem code symbol maps."""
    m = _get_omem(ctx)
    count = m.ingest_project(path, namespace)
    click.echo(
        click.style(
            f"Ingested {count} parsed symbol definitions into namespace '{namespace}'.",
            fg="green",
        )
    )


@cli.command()
@click.argument('path', default='.', type=click.Path(exists=True))
@click.option('--namespace', '-n', default='project', help='Partition mapping label target.')
@click.pass_context
def sync(ctx: click.Context, path: str, namespace: str):
    """Incrementally parse codebase differences tracking historical delta edits."""
    m = _get_omem(ctx)
    processed = m.sync_project(path, namespace)
    click.echo(
        click.style(
            f"Synchronization complete: processed {processed} symbol updates into '{namespace}'.",
            fg="green",
        )
    )


@cli.command()
@click.argument('query')
@click.option('--namespace', '-n', default='project', help='Target storage partition namespace scope.')
@click.option('--depth', '-d', default=2, help='Graph relational link traversal tracking query limits depth.')
@click.option('--top-k', default=5, help='Limit tracking results count returned metrics.')
@click.pass_context
def codebase(ctx: click.Context, query: str, namespace: str, depth: int, top_k: int):
    """Execute syntax graph semantic analysis searches across ingested codebase paths."""
    m = _get_omem(ctx)
    results = m.query_code(query, namespace=namespace, context_depth=depth, top_k=top_k)
    for i, r in enumerate(results, 1):
        click.echo(f"{i:02d}. {r.get('symbol_id', 'N/A')} ({r.get('type', '')})")
        click.echo(f"    Location: {r.get('file_path', '')}:{r.get('start_line', '')}")
        if 'summary' in r:
            click.echo(f"    Abstract: {r['summary']}")
        click.echo('')


@cli.command()
@click.option(
    "--transport",
    default="stdio",
    type=click.Choice(["stdio"]),
    help="Core communication channel transport paradigm.",
)
@click.pass_context
def serve(ctx: click.Context, transport: str):
    """Expose the interface context as an MCP compliant microservice system daemon."""
    click.echo("Initializing OMem Model Context Protocol Server process...")
    click.echo(f"Channel Pipeline Transport: {transport}")
    click.echo("Engine ready to service external agent context attachment sequences.\n")

    try:
        from .integrations.mcp_server import mcp
        mcp.run(transport=transport)
    except KeyboardInterrupt:
        click.echo("\nService intercept signal caught. OMem daemon down.")
    except Exception as e:
        click.echo(click.style(f"Fatal integration engine startup termination anomaly: {e}", fg="red"), err=True)
        sys.exit(1)


@cli.command()
@click.argument("shell", default="bash", type=click.Choice(["bash", "zsh", "fish", "powershell"]))
def completion(shell: str):
    """Generate shell completion code for supported shells."""
    try:
        from click.shell_completion import get_completion_script

        click.echo(get_completion_script("omem", shell))
    except (ImportError, AttributeError):
        click.echo(
            click.style(
                "Shell completion is not available with this Click version.",
                fg="yellow",
            )
        )


@cli.command()
def version():
    """Show the currently installed OMem version."""
    click.echo(f"omem {__version__}")


def main():
    cli()


if __name__ == "__main__":
    main()
