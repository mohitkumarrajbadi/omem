"""Partner demos — kill-resume, poison recovery, and first-run story."""

from .kill_resume import run_kill_resume
from .poison import run_poison_recovery
from .story import (
    DEMO_NAMESPACE,
    lineage_report,
    mcp_config,
    merge_cursor_mcp,
    seed_story,
    story_ids,
    story_present,
)

__all__ = [
    "run_kill_resume",
    "run_poison_recovery",
    "DEMO_NAMESPACE",
    "lineage_report",
    "mcp_config",
    "merge_cursor_mcp",
    "seed_story",
    "story_ids",
    "story_present",
]
