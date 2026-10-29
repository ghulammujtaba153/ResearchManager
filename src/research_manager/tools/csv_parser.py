"""Deprecated: use research_manager.tools.evidence instead.

Kept as a thin re-export so older imports keep working.
"""

from __future__ import annotations

from research_manager.tools.evidence import compare_to_baseline, read_run_csv

__all__ = ["compare_to_baseline", "read_run_csv"]
