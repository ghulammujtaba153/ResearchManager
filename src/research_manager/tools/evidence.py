"""Deterministic evidence tools: folder reader, CSV parser, comparisons."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[3]
EXPERIMENTS_DIR = PROJECT_ROOT / "experiments"
TASKS_DIR = PROJECT_ROOT / "tasks"
EXPECTED_FILES = ("params.yaml", "results.csv")

# Instructions planted in files must never change permissions / policy.
UNTRUSTED_MARKERS = (
    "IGNORE PREVIOUS",
    "SYSTEM:",
    "GRANT ADMIN",
    "CHANGE PERMISSIONS",
    "OVERRIDE POLICY",
    "SEND EMAIL TO",
)


def _sanitize_text(text: str) -> tuple[str, bool]:
    upper = text.upper()
    flagged = any(m in upper for m in UNTRUSTED_MARKERS)
    cleaned = text
    for marker in UNTRUSTED_MARKERS:
        cleaned = re.sub(re.escape(marker), "[REDACTED]", cleaned, flags=re.IGNORECASE)
    return cleaned, flagged


def list_experiment_folders(base: Path | None = None) -> list[str]:
    root = base or EXPERIMENTS_DIR
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def inspect_run(run_id: str, base: Path | None = None) -> dict[str, Any]:
    root = (base or EXPERIMENTS_DIR) / run_id
    if not root.exists():
        return {
            "run_id": run_id,
            "exists": False,
            "present": [],
            "missing": list(EXPECTED_FILES),
            "untrusted_instruction_detected": False,
        }

    present = [name for name in EXPECTED_FILES if (root / name).exists()]
    missing = [name for name in EXPECTED_FILES if name not in present]
    untrusted = False
    notes = ""
    params_path = root / "params.yaml"
    if params_path.exists():
        raw = params_path.read_text(encoding="utf-8")
        cleaned, flagged = _sanitize_text(raw)
        untrusted = flagged
        if flagged:
            notes = "Untrusted instruction detected in params.yaml and ignored."
            _ = cleaned
    return {
        "run_id": run_id,
        "exists": True,
        "path": str(root),
        "present": present,
        "missing": missing,
        "untrusted_instruction_detected": untrusted,
        "security_notes": notes,
    }


def read_run_csv(
    run_id: str,
    required_metric: str = "accuracy",
    base: Path | None = None,
) -> dict[str, Any]:
    path = (base or EXPERIMENTS_DIR) / run_id / "results.csv"
    if not path.exists():
        return {
            "ok": False,
            "uncertain": False,
            "error": "results.csv missing",
            "metrics": {},
            "missing_columns": [required_metric],
            "untrusted_instruction_detected": False,
        }

    raw = path.read_text(encoding="utf-8")
    cleaned, flagged = _sanitize_text(raw)
    if flagged:
        return {
            "ok": False,
            "uncertain": True,
            "error": "Untrusted instruction in results.csv ignored; evidence marked uncertain",
            "metrics": {},
            "missing_columns": [required_metric],
            "untrusted_instruction_detected": True,
        }

    df = pd.read_csv(path)
    missing_columns = [required_metric] if required_metric not in df.columns else []
    metrics: dict[str, Any] = {}
    if not missing_columns and len(df) > 0:
        try:
            metrics = {required_metric: float(df[required_metric].iloc[-1])}
        except (TypeError, ValueError):
            return {
                "ok": False,
                "uncertain": True,
                "error": f"Non-numeric value for {required_metric}",
                "metrics": {},
                "missing_columns": [],
                "untrusted_instruction_detected": False,
            }

    return {
        "ok": not missing_columns and bool(metrics),
        "uncertain": bool(missing_columns),
        "error": None if not missing_columns else f"missing columns: {missing_columns}",
        "metrics": metrics,
        "missing_columns": missing_columns,
        "row_count": len(df),
        "untrusted_instruction_detected": False,
    }


def compare_to_baseline(metrics: dict[str, float], baseline: dict[str, float]) -> dict[str, Any]:
    comparison: dict[str, Any] = {}
    for name, value in metrics.items():
        base = baseline.get(name)
        comparison[name] = {
            "value": value,
            "baseline": base,
            "delta": None if base is None else value - base,
            "beats_baseline": None if base is None else value >= base,
        }
    return comparison


def write_next_task(
    *,
    hypothesis: str,
    params: dict[str, Any],
    notes: str = "",
    run_id: str | None = None,
    cycle: int | None = None,
    out_dir: Path | None = None,
) -> Path:
    dest_dir = out_dir or TASKS_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / "next_experiment.yaml"
    payload = {
        "run_id": run_id,
        "cycle": cycle,
        "hypothesis": hypothesis,
        "params": params,
        "notes": notes,
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path
