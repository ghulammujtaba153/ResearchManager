"""Local Subprocess Execution Engine.

Executes real training workloads in isolated subprocesses with timeout protection,
live log streaming, and telemetry capture.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
EXPERIMENTS_DIR = PROJECT_ROOT / "experiments"
TASKS_DIR = PROJECT_ROOT / "tasks"
TRAIN_SCRIPT = Path(__file__).resolve().parent / "train_model.py"


def execute_training_job(
    run_id: str,
    task_path: Path | None = None,
    *,
    timeout_sec: int = 30,
) -> dict[str, Any]:
    """Execute the training script as an isolated OS subprocess."""
    config_file = task_path or (TASKS_DIR / "next_experiment.yaml")
    if not config_file.exists():
        return {
            "ok": False,
            "error": f"Config file not found: {config_file}",
            "return_code": -1,
            "run_id": run_id,
        }

    run_dir = EXPERIMENTS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    log_file = run_dir / "train.log"

    env = os.environ.copy()
    env["MLFLOW_DISABLE_AGENT_HINT"] = "1"
    src_dir = str(PROJECT_ROOT / "src")
    existing_py_path = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{src_dir};{existing_py_path}" if existing_py_path else src_dir

    cmd = [
        sys.executable,
        str(TRAIN_SCRIPT),
        "--config",
        str(config_file),
        "--run-id",
        run_id,
    ]

    start_time = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_sec,
            cwd=str(PROJECT_ROOT),
            env=env,
        )
        duration = round(time.perf_counter() - start_time, 2)
        success = proc.returncode == 0

        # Append any captured stderr to train.log if it wasn't already logged
        if proc.stderr:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"\n[SUBPROCESS STDERR]\n{proc.stderr}\n")

        return {
            "ok": success,
            "return_code": proc.returncode,
            "duration_sec": duration,
            "run_id": run_id,
            "log_path": str(log_file),
            "stdout": proc.stdout[-1500:] if proc.stdout else "",
            "stderr": proc.stderr[-1500:] if proc.stderr else "",
            "error": None if success else f"Process exited with code {proc.returncode}",
        }

    except subprocess.TimeoutExpired:
        duration = round(time.perf_counter() - start_time, 2)
        timeout_msg = f"ERROR: Subprocess timed out after {timeout_sec}s."
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"\n{timeout_msg}\n")
        return {
            "ok": False,
            "return_code": -2,
            "duration_sec": duration,
            "run_id": run_id,
            "log_path": str(log_file),
            "error": timeout_msg,
        }
    except Exception as exc:  # noqa: BLE001
        duration = round(time.perf_counter() - start_time, 2)
        return {
            "ok": False,
            "return_code": -3,
            "duration_sec": duration,
            "run_id": run_id,
            "log_path": str(log_file),
            "error": str(exc),
        }

