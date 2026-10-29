"""Deprecated planner stub.

The live decision path is research_manager.agent.workflow + evidence tools.
This module remains only for backwards-compatible imports.
"""

from __future__ import annotations

from typing import Any

from research_manager.tools.task_writer import write_next_task


def plan_next_run(
    cycle: int,
    last_failure_reason: str | None,
    previous_params: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Legacy rule-based planner; prefer workflow.run_cycle."""
    params = dict(previous_params or {"learning_rate": 0.1, "epochs": 3})
    run_id = run_id or f"run_{cycle:03d}"
    if cycle == 1:
        hypothesis = "Baseline classifier with default learning rate."
        notes = "Initial run. Expect results.csv with metric column 'acc'."
        params["metric_name"] = "acc"
    elif cycle == 2 and last_failure_reason and "missing" in last_failure_reason.lower():
        hypothesis = "Correct metric column name and retry the same params."
        notes = "Corrected metric from 'acc' to 'accuracy'."
        params["metric_name"] = "accuracy"
    else:
        hypothesis = "Increase learning rate to beat baseline accuracy."
        notes = "Previous accuracy below baseline; raising learning_rate."
        params["metric_name"] = "accuracy"
        params["learning_rate"] = round(float(params.get("learning_rate", 0.1)) * 2, 4)

    path = write_next_task(
        hypothesis=hypothesis,
        params=params,
        notes=notes,
        run_id=run_id,
        cycle=cycle,
    )
    return {"hypothesis": hypothesis, "params": params, "notes": notes, "task_path": str(path)}
