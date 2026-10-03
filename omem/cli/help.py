"""CLI help grouping and categorized help screen."""

from __future__ import annotations

import os
from collections import OrderedDict
from difflib import get_close_matches

import click

from .ui import _c

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
    + _c("  Audit & rollback for AI agents\n", fg="white", bold=True)
)

# Simple default help — the 60-second path. Everything else stays registered
# and listed by `omem commands`. AST stays opt-in via OMEM_ENABLE_EXPERIMENTAL_AST=1.
SIMPLE_HELP_GROUPS = OrderedDict(
    [
        ("Get started", ["init", "demo", "agent"]),
        ("Everyday", ["remember", "recall", "status", "serve", "dashboard"]),
    ]
)

# Full catalog for `omem commands` (and when OMEM_CLI_ALL=1).
ALL_COMMAND_GROUPS = OrderedDict(
    [
        ("Get started", ["init", "demo", "agent"]),
        ("Everyday", ["remember", "recall", "status", "serve", "dashboard"]),
        ("Memory", ["list", "inspect", "stats", "sleep", "clear", "namespaces"]),
        ("State & context", ["state", "context", "knowledge"]),
        ("Governance", ["governance", "provenance", "observe", "runtime", "org"]),
        ("Connectors", ["ingest-docs", "ingest-url", "ingest-notion", "ingest-drive"]),
        ("Server", ["health", "export", "import", "version"]),
        ("Experimental AST", ["ingest", "sync", "codebase"]),
    ]
)

# Always hidden from help catalogs (still invokable).
_HELP_HIDDEN = frozenset({
    "add",
    "search",
    "maintain",
    "benchmark",
    "bench",
    "completion",
    "commands",  # listed in the footer, not as a row
})

_AST_HELP_CMDS = frozenset({"ingest", "sync", "codebase"})

# Commands shown only via `omem commands` / OMEM_CLI_ALL=1.
_ADVANCED_HELP_CMDS = frozenset(
    {
        "list",
        "inspect",
        "stats",
        "sleep",
        "clear",
        "namespaces",
        "state",
        "context",
        "knowledge",
        "governance",
        "provenance",
        "observe",
        "runtime",
        "org",
        "ingest-docs",
        "ingest-url",
        "ingest-notion",
        "ingest-drive",
        "health",
        "export",
        "import",
        "version",
    }
)


def _show_all_commands() -> bool:
    return os.environ.get("OMEM_CLI_ALL", "").strip() in {"1", "true", "yes"}


def _command_groups_for_help(*, all_commands: bool = False):
    from ..experimental import ast_enabled

    source = ALL_COMMAND_GROUPS if all_commands or _show_all_commands() else SIMPLE_HELP_GROUPS
    groups = OrderedDict()
    for category, cmd_list in source.items():
        if category.startswith("Experimental") and not ast_enabled():
            continue
        groups[category] = cmd_list
    return groups


def _help_hidden_names(*, all_commands: bool = False) -> set:
    from ..experimental import ast_enabled

    hidden = set(_HELP_HIDDEN)
    if not ast_enabled():
        hidden |= _AST_HELP_CMDS
    if not (all_commands or _show_all_commands()):
        hidden |= _ADVANCED_HELP_CMDS
    return hidden


def _write_command_groups(ctx, formatter, *, all_commands: bool = False) -> None:
    group = ctx.command
    commands = set(group.list_commands(ctx))
    hidden = _help_hidden_names(all_commands=all_commands)
    mapped = set()

    for category, cmd_list in _command_groups_for_help(all_commands=all_commands).items():
        available_cmds = [c for c in cmd_list if c in commands and c not in hidden]
        if not available_cmds:
            continue
        with formatter.section(category):
            rows = []
            for name in available_cmds:
                cmd = group.get_command(ctx, name)
                if cmd is None:
                    continue
                rows.append((name, cmd.get_short_help_str()))
                mapped.add(name)
            formatter.write_dl(rows)

    # Never leak intentionally-hidden names into an orphan "More" section.
    mapped |= hidden & commands
    orphans = sorted(commands - mapped)
    if orphans:
        with formatter.section("More"):
            rows = []
            for name in orphans:
                cmd = group.get_command(ctx, name)
                rows.append((name, cmd.get_short_help_str() if cmd else ""))
            formatter.write_dl(rows)


class OMemGroup(click.Group):
    """Click group with a categorized help screen and typo suggestions."""

    def format_help(self, ctx, formatter):
        formatter.write(CLI_BANNER)
        formatter.write("\n\n")
        self.format_usage(ctx, formatter)
        self.format_options(ctx, formatter)
        # Note: click.MultiCommand.format_options already calls format_commands
        # internally, so we do NOT call it again here to avoid duplication.
        if not _show_all_commands():
            formatter.write(
                "\n"
                + _c("  Tip: ", fg="bright_black")
                + "omem commands"
                + _c("  — full list\n", fg="bright_black")
            )

    def format_commands(self, ctx, formatter):
        _write_command_groups(ctx, formatter, all_commands=_show_all_commands())

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


