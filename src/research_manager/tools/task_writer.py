"""Write the next experiment task for the researcher or simulator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TASKS_DIR = PROJECT_ROOT / "tasks"


def write_next_task(
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
