"""Working state carried through the LangGraph session."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class WorkingState(BaseModel):
    """In-session context for Planner + Results Analyst."""

    current_hypothesis: str = ""
    active_run_id: Optional[str] = None
    run_comparison: dict[str, Any] = Field(default_factory=dict)
    missing_outputs: list[str] = Field(default_factory=list)
    cycle_count: int = 0
    max_cycles: int = 3
    last_failure_reason: Optional[str] = None
    last_decision: Optional[str] = None
    messages: list[str] = Field(default_factory=list)
    done: bool = False
