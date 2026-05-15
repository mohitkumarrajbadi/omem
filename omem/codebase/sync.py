"""Incremental synchronization for the Project Memory layer.
Uses ``git diff`` and file hashing to update only changed Python files.
"""

import os
import subprocess
import logging
from typing import Set, List

from ..api import OMem
from .ingester import ProjectIngester
from .graph import ProjectGraph
from .utils import default_ignore_dirs, normalize_path

logger = logging.getLogger(__name__)

class ProjectSync:
    """Manages incremental updates to the Project Memory.

    Parameters
    ----------
    omem: OMem
        Core OMem instance.
    root_dir: str
        Root of the repository to monitor.
    namespace: str, optional
        Namespace used for all project memories (default ``"project"``).
    """

    def __init__(self, omem: OMem, root_dir: str, namespace: str = "project"):
        self.omem = omem
        self.root_dir = os.path.abspath(root_dir)
        self.namespace = namespace
        self.graph = ProjectGraph(omem, namespace)
        self.ignore_dirs = default_ignore_dirs()

    # ---------------------------------------------------------------------
    # Git helpers
    # ---------------------------------------------------------------------
    def _git_diff_files(self) -> Set[str]:
        """Return a set of relative file paths that have changed since HEAD.
        Includes modified, added, and deleted files.
        """
        changed: Set[str] = set()
        try:
            # Modified / deleted tracked files
            result = subprocess.run(
                ["git", "diff", "--name-status", "HEAD"],
                cwd=self.root_dir,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    # format: "M\tpath/to/file.py" or "D\tpath"
                    status, rel_path = line.split('\t', 1)
                    if rel_path.lower().endswith('.py'):
                        changed.add(rel_path)
            # Untracked (new) files
            result = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                cwd=self.root_dir,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                for rel_path in result.stdout.splitlines():
                    if rel_path.lower().endswith('.py'):
                        changed.add(rel_path)
        except Exception as e:
            logger.warning("Git diff failed (%s); falling back to full crawl", e)
        return changed

    # ---------------------------------------------------------------------
    # Sync logic
    # ---------------------------------------------------------------------
    def sync(self) -> int:
        """Perform an incremental sync.

        Returns
        -------
        int
            Number of symbols processed (added/updated + deletions).
        """
        changed_files = self._git_diff_files()
        if not changed_files:
            logger.info("No Python changes detected by git diff.")
            return 0

        ingester = ProjectIngester(self.root_dir)
        total_processed = 0

        for rel_path in changed_files:
            abs_path = os.path.join(self.root_dir, rel_path)
            if os.path.exists(abs_path):
                # Modified or newly added file – parse and upsert
                symbols = ingester.parse_file(abs_path)
                self.graph.sync_symbols(symbols)
                total_processed += len(symbols)
            else:
                # Deleted file – remove all symbols that pointed to it
                total_processed += self._delete_file_symbols(abs_path)
        return total_processed

    def _delete_file_symbols(self, file_path: str) -> int:
        """Remove all memories whose metadata ``file_path`` matches *file_path*.
        Returns the number of deletions performed.
        """
        deleted = 0
        # Retrieve all project memories (namespace scoped) and filter
        for mem in self.omem.all(namespace=self.namespace):
            if mem.metadata.get("file_path") == file_path:
                try:
                    self.omem.delete(mem.id)
                    deleted += 1
                except Exception:
                    pass
        if deleted:
            logger.info("Deleted %d stale symbols for removed file %s", deleted, file_path)
        return deleted
