"""Deprecated: use research_manager.tools.evidence instead.

Kept as a thin re-export so older imports keep working.
"""

from __future__ import annotations

from research_manager.tools.evidence import EXPECTED_FILES, EXPERIMENTS_DIR, inspect_run, list_experiment_folders

__all__ = ["EXPECTED_FILES", "EXPERIMENTS_DIR", "inspect_run", "list_experiment_folders"]
