"""OMem CLI — command-line interface for OMem."""

# ── Runtime environment fixes ─────────────────────────────────────────────────
# Must be set BEFORE any import that loads FAISS, numpy, or sentence-transformers,
# as those trigger OpenMP initialisation which causes libomp.dylib conflicts on macOS.
import os

os.environ.setdefault(
    "KMP_DUPLICATE_LIB_OK", "TRUE"
)  # fix libomp conflict (conda + FAISS)
os.environ.setdefault("HF_HUB_OFFLINE", "1")  # no HuggingFace Hub network calls
os.environ.setdefault(
    "TOKENIZERS_PARALLELISM", "false"
)  # suppress tokenizer fork warnings
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")  # suppress model load noise
# ─────────────────────────────────────────────────────────────────────────────

import time
import json
import click

from .api import OMem
from .types import MemoryType
from . import __version__


@click.group(context_settings=dict(help_option_names=['-h', '-help', '--help']))
@click.version_option(__version__)
def cli():
    """OMem - Persistent Memory System for AI Agents."""
    pass


@cli.command()
@click.option("--db-path", default=None, help="Database path")
def init(db_path):
    """Initialize a OMem memory system."""
    import os

    if db_path is None:
        db_path = os.path.expanduser("~/.omem/brain.db")

    db_dir = os.path.dirname(db_path)
    if not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    m = OMem(db_path=db_path)

    click.echo("OMem memory system initialized successfully")
    click.echo(f"  Database: {db_path}")
    click.echo(f"  Status:   {m.stats()['total']} memories")
    click.echo("\nQuick start:")
    click.echo('  omem add "Your first memory"')
    click.echo('  omem search "memory"')
    click.echo("  omem stats")


@cli.command()
@click.argument("content")
@click.option("--importance", "-i", type=float, help="Importance score (0.0-1.0)")
@click.option("--namespace", "-n", default="default", help="Namespace")
@click.option("--type", "-t", "mem_type", help="Memory type")
def add(content, importance, namespace, mem_type):
    """Add a new memory to the system."""
    m = OMem()

    kwargs = {"namespace": namespace}
    if importance is not None:
        kwargs["importance"] = importance
    if mem_type:
        kwargs["mem_type"] = getattr(MemoryType, mem_type.upper(), None)

    mem_id = m.add(content, **kwargs)
    mem = m.get(mem_id)

    click.echo("Memory added successfully")
    click.echo(f"  ID:         {mem_id[:12]}...")
    click.echo(f"  Type:       {mem.type.name}")
    click.echo(f"  Importance: {mem.importance:.2f}")
    click.echo(f"  Namespace:  {mem.namespace}")


@cli.command()
@click.argument("query")
@click.option("--k", "-k", default=5, help="Number of results")
@click.option("--namespace", "-n", help="Filter by namespace")
@click.option(
    "--context-type", "-c", help="Context type (architecture, bugs, decisions)"
)
@click.option("--time-range", "-t", help="Time range (today, recent, last_week)")
def search(query, k, namespace, context_type, time_range):
    """Search memories with a query."""
    m = OMem()

    results = m.recall(
        query,
        k=k,
        namespace=namespace,
        context_type=context_type,
        time_range=time_range,
    )

    if not results:
        click.echo("No memories found.")
        return

    click.echo(f"Found {len(results)} memories:\n")
    for i, mem in enumerate(results, 1):
        click.echo(
            f"{i}. [{mem.type.name}] score={mem.score:.3f} imp={mem.importance:.2f}"
        )
        click.echo(f"   {mem.content[:80]}")
        click.echo(
            f"   ID: {mem.id[:12]}... | {mem.namespace} | {_time_ago(mem.timestamp)}"
        )
        click.echo()


@cli.command()
@click.option("--namespace", "-n", help="Filter by namespace")
@click.option("--type", "-t", "mem_type", help="Filter by type")
@click.option("--limit", "-l", default=20, help="Max results")
@click.option("--inactive", is_flag=True, help="Include inactive memories")
def list(namespace, mem_type, limit, inactive):
    """List all memories."""
    m = OMem()

    memories = m.all(namespace=namespace, include_inactive=inactive)

    if mem_type:
        type_enum = getattr(MemoryType, mem_type.upper(), None)
        if type_enum:
            memories = [mem for mem in memories if mem.type == type_enum]

    memories = memories[:limit]

    if not memories:
        click.echo("No memories found.")
        return

    click.echo(f"Showing {len(memories)} memories:\n")
    for i, mem in enumerate(memories, 1):
        status = "[active]" if mem.active else "[inactive]"
        click.echo(
            f"{i}. {status} [{mem.type.name:11s}] imp={mem.importance:.2f} | {mem.content[:60]}"
        )


@cli.command()
@click.argument("query")
@click.option("--k", default=5, help="Number of results")
def inspect(query, k):
    """Inspect retrieval scoring for a query."""
    m = OMem()
    exps = m.inspect(query, top_k=k)

    if not exps:
        click.echo("No memories to inspect. Add some first!")
        return

    click.echo(f'Inspection results for: "{query}"\n')
    click.echo("=" * 70)

    for i, exp in enumerate(exps, 1):
        click.echo(f"\n{i}. {exp.explain()}")


@cli.command()
def stats():
    """Show memory system statistics."""
    m = OMem()
    s = m.stats()

    click.echo("\nOMem Memory Statistics")
    click.echo("=" * 50)
    click.echo(f"  Total memories:       {s['total']}")
    click.echo(f"  Active:               {s['total'] - s['inactive']}")
    click.echo(f"  Inactive:             {s['inactive']}")
    click.echo(f"  Average importance:   {s['avg_importance']:.2f}")
    click.echo(f"  Knowledge graph:      {s['graph_edges']} edges")
    click.echo(
        f"\nNamespaces:             {', '.join(s['namespaces']) if s['namespaces'] else 'default'}"
    )
    click.echo("\nMemory types:")
    for mtype, count in s["types"].items():
        click.echo(f"    {mtype:15s} {count:>5d}")
    click.echo()


@cli.command()
@click.option("--namespace", "-n", help="Filter by namespace")
@click.option(
    "--format",
    "-f",
    "fmt",
    default="json",
    type=click.Choice(["json", "txt"]),
    help="Export format",
)
@click.option("--output", "-o", help="Output file")
def export(namespace, fmt, output):
    """Export memories to a file."""
    m = OMem()

    memories = m.all(namespace=namespace)

    if fmt == "json":
        data = {
            "memories": [mem.to_dict() for mem in memories],
            "stats": m.stats(),
            "exported_at": time.time(),
        }
        content = json.dumps(data, indent=2)
    else:
        lines = [
            f"{mem.content} | {mem.type.name} | {mem.importance:.2f}"
            for mem in memories
        ]
        content = "\n".join(lines)

    if output:
        with open(output, "w") as f:
            f.write(content)
        click.echo(f"Exported {len(memories)} memories to {output}")
    else:
        click.echo(content)


@cli.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("--namespace", "-n", default="default", help="Import namespace")
def load(file, namespace):
    """Load memories from a JSON file."""
    import builtins

    m = OMem()

    with open(file, "r") as f:
        data = json.load(f)

    if isinstance(data, dict) and "memories" in data:
        memories = data["memories"]
    elif isinstance(data, builtins.list):
        memories = data
    else:
        click.echo("Invalid file format. Expected list of memories.")
        return

    click.echo(f"Loading {len(memories)} memories...")

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

    click.echo(f"Loaded {count} memories into namespace '{namespace}'")


@cli.command()
@click.option("--compress", is_flag=True, help="Compress similar memories")
@click.option("--reflect", is_flag=True, help="Generate reflections")
@click.option("--forget", is_flag=True, help="Run forgetting cycle")
@click.option("--dream", is_flag=True, help="Run dream cycle")
@click.option("--all", "all_ops", is_flag=True, help="Run all maintenance")
def maintain(compress, reflect, forget, dream, all_ops):
    """Run maintenance operations."""
    m = OMem()

    if all_ops or not any([compress, reflect, forget, dream]):
        click.echo("Running full maintenance cycle...")
        result = m.sleep()
        click.echo("Maintenance complete")
        click.echo(f"  Compressed:  {result.get('compressed', 0)} memories")
        click.echo(f"  Reflected:   {result.get('reflected', 0)} insights")
        click.echo(f"  Forgotten:   {result.get('forgotten', 0)} memories")
        return

    if compress:
        click.echo("Compressing similar memories...")
        result = m.compress()
        click.echo(
            f"Compressed {result['compressed']} groups, deactivated {result['deactivated']}"
        )

    if reflect:
        click.echo("Generating reflections...")
        refs = m.reflect()
        click.echo(f"Generated {len(refs)} reflection insights")

    if forget:
        click.echo("Running forgetting cycle...")
        result = m.forget()
        click.echo(f"Forgot {len(result.forgotten_ids)} low-value memories")

    if dream:
        click.echo("Running dream cycle...")
        result = m.dream()
        click.echo(
            f"Dream complete: {result.clusters_formed} clusters, {result.insights_created} insights"
        )


@cli.command()
@click.option("--namespace", "-n", help="Namespace to clear")
@click.confirmation_option(prompt="Are you sure you want to clear all memories?")
def clear(namespace):
    """Clear all memories (use with caution)."""
    m = OMem()

    if namespace:
        m.clear(namespace=namespace)
        click.echo(f"Cleared namespace '{namespace}'")
    else:
        m.clear()
        click.echo("Cleared all memories")


@cli.command()
def namespaces():
    """List all namespaces."""
    m = OMem()
    ns_list = m.namespaces()

    if not ns_list:
        click.echo("No namespaces found.")
        return

    click.echo("Active namespaces:\n")
    for ns in ns_list:
        stats = m.namespace_stats(ns)
        click.echo(f"  • {ns:20s} {stats.get('total', 0):>5d} memories")


@cli.command()
def demo():
    """Run an interactive demo of OMem."""
    m = OMem()

    click.echo("\n" + "=" * 60)
    click.echo("  OMem Interactive Demo")
    click.echo("=" * 60 + "\n")

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

    click.echo("Adding memories...")
    for content in samples:
        mid = m.add(content)
        mem = m.get(mid)
        click.echo(f"  [{mem.type.name:11s}] imp={mem.importance:.2f} | {content[:50]}")

    s = m.stats()
    click.echo(f"\nStats: {s['total']} memories, {len(s['types'])} types\n")

    click.echo("Retrieval queries:")
    for q in ["Who am I?", "deployment production", "security urgent"]:
        results = m.recall(q, k=2)
        click.echo(f'\n  Q: "{q}"')
        for r in results:
            click.echo(f"    [{r.score:.3f}] {r.content[:60]}")

    click.echo("\nCompressing memories...")
    result = m.compress()
    click.echo(
        f"  Compressed: {result['compressed']} groups, deactivated: {result['deactivated']}"
    )

    click.echo("\nGenerating reflections...")
    refs = m.reflect()
    click.echo(f"  Reflected {len(refs)} insights")

    click.echo("\n" + "=" * 60)
    click.echo("  Demo complete! Try these commands:")
    click.echo('    omem search "your query"')
    click.echo("    omem list")
    click.echo("    omem stats")
    click.echo("=" * 60 + "\n")


@cli.command()
@click.option("--n", default=10_000, help="Number of memories to benchmark")
def benchmark(n):
    """Run a quick performance benchmark."""
    m = OMem()

    click.echo(f"\nBenchmarking with {n:,} memories...\n")

    t0 = time.perf_counter()
    for i in range(n):
        m.add(f"Benchmark entry {i}: domain {i % 100} topic {i % 50}", importance=0.5)
    add_time = time.perf_counter() - t0

    click.echo(
        f"  Add:      {add_time:.3f}s total | {(add_time / n) * 1000:.3f}ms/op | {n / add_time:,.0f} ops/s"
    )

    queries = 1000
    t0 = time.perf_counter()
    for i in range(queries):
        m.recall(f"domain {i % 100} topic {i % 50}", k=5)
    rag_time = time.perf_counter() - t0

    click.echo(
        f"  Recall:   {rag_time:.3f}s total | {(rag_time / queries) * 1000:.3f}ms/query | {queries / rag_time:,.0f} ops/s"
    )

    t0 = time.perf_counter()
    m.compress()
    comp_time = time.perf_counter() - t0
    click.echo(f"  Compress: {comp_time:.3f}s\n")

    s = m.stats()
    click.echo(f"  Final: {s['total']} active, {s['inactive']} inactive\n")


@cli.command()
@click.option("--port", default=7900, help="Dashboard port")
def dashboard(port):
    """Launch the OMem Memory Dashboard."""
    from .viz.server import serve as start_dashboard

    m = OMem()

    samples = [
        "My name is Mohit and I build AI systems",
        "Prefer Python for all backend development",
        "Working on OMem — open source AI memory",
        "Decided to use FAISS for vector indexing",
        "Step 1: design API, Step 2: implement core",
        "Yesterday released OMem v0.2.0",
        "Server latency caused by N+1 queries",
        "Currently optimizing compression engine",
    ]
    for s in samples:
        m.add(s)

    start_dashboard(omem=m, port=port)


@cli.command()
def health():
    """Check system health and connectivity."""
    import sys

    try:
        m = OMem()
        stats = m.stats()

        click.echo("Status: HEALTHY")
        click.echo(f"Version: {__version__}")
        click.echo(f"Memories: {stats['total']}")
        click.echo("Database: OK")
        sys.exit(0)
    except Exception as e:
        click.echo(f"Status: UNHEALTHY - {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--transport",
    default="stdio",
    type=click.Choice(["stdio"]),
    help="MCP transport protocol",
)
def serve(transport):
    """Start the OMem MCP server for Claude Desktop integration.

    The MCP (Model Context Protocol) server enables Claude Desktop and other
    MCP-compatible clients to use OMem as persistent cognitive memory.

    Example usage:
        omem serve

    For Claude Desktop configuration, add to your config file:
    {
      "mcpServers": {
        "omem": {
          "command": "omem",
          "args": ["serve"]
        }
      }
    }
    """
    click.echo("Starting OMem MCP Server...")
    click.echo(f"Transport: {transport}")
    click.echo("Ready for Claude Desktop connections.\n")

    try:
        from .integrations.mcp_server import mcp

        mcp.run(transport=transport)
    except KeyboardInterrupt:
        click.echo("\nOMem MCP Server stopped.")
    except Exception as e:
        click.echo(f"Error starting MCP server: {e}", err=True)
        raise


def _time_ago(timestamp):
    """Human-readable time ago."""
    seconds = time.time() - timestamp
    if seconds < 60:
        return "just now"
    elif seconds < 3600:
        return f"{int(seconds / 60)}m ago"
    elif seconds < 86400:
        return f"{int(seconds / 3600)}h ago"
    else:
        return f"{int(seconds / 86400)}d ago"


def main():
    cli()


if __name__ == "__main__":
    main()
