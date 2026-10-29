"""Results Analyst: inspect folders/CSVs and diagnose incomplete runs."""

from __future__ import annotations

from typing import Any

from research_manager.tools.evidence import compare_to_baseline, inspect_run, read_run_csv

DEFAULT_BASELINE = {"accuracy": 0.75}


def analyze_run(run_id: str, baseline: dict[str, float] | None = None) -> dict[str, Any]:
    baseline = baseline or DEFAULT_BASELINE
    folder = inspect_run(run_id)

    if not folder["exists"] or folder["missing"]:
        reason = f"Incomplete run: missing {folder.get('missing', [])}"
        return {
            "success": False,
            "failure_reason": reason,
            "missing_outputs": folder.get("missing", []),
            "metrics": {},
            "comparison": {},
            "decision": "restart_after_fixing_outputs",
        }

    parsed = read_run_csv(run_id)
    if not parsed["ok"]:
        reason = parsed.get("error") or "CSV parse failed"
        return {
            "success": False,
            "failure_reason": reason,
            "missing_outputs": parsed.get("missing_columns", []),
            "metrics": {},
            "comparison": {},
            "decision": "correct_metric_and_restart",
        }

    comparison = compare_to_baseline(parsed["metrics"], baseline)
    beats = all(v.get("beats_baseline") for v in comparison.values())
    if not beats:
        return {
            "success": False,
            "failure_reason": "Metrics below baseline",
            "missing_outputs": [],
            "metrics": parsed["metrics"],
            "comparison": comparison,
            "decision": "tune_params_and_restart",
        }

    return {
        "success": True,
        "failure_reason": None,
        "missing_outputs": [],
        "metrics": parsed["metrics"],
        "comparison": comparison,
        "decision": "accept_and_stop",
    }
