"""Compatibility wrappers around the agent workflow."""

from __future__ import annotations

from research_manager.agent import workflow
from research_manager.state import WorkingState


def run_demo(max_cycles: int = 3, project_id: str = "demo") -> WorkingState:
    return workflow.run_demo(project_id=project_id, max_cycles=max_cycles)


def run_one_cycle(project_id: str = "demo") -> WorkingState:
    result = workflow.run_cycle(project_id)
    return WorkingState.model_validate(result["state"])
