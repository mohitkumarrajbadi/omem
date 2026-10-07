"""CLI visual helpers — color, glyphs, status lines."""

from __future__ import annotations

import os
from typing import Any

import click

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
