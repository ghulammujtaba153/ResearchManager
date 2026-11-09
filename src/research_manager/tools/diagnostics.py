"""Log Diagnostic and Telemetry Tool for real ML runs."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
EXPERIMENTS_DIR = PROJECT_ROOT / "experiments"

# Pattern rules for diagnosing machine learning training failures
PATTERNS = {
    "CUDA_OOM": (
        re.compile(r"(CUDA out of memory|OutOfMemoryError|ResourceExhaustedError)", re.IGNORECASE),
        "GPU memory exhausted. Reduce batch_size by half or enable gradient checkpointing.",
    ),
    "NAN_LOSS": (
        re.compile(r"(loss is nan|loss became inf|gradients exploded|DivergenceError)", re.IGNORECASE),
        "Numerical divergence detected (Loss is NaN/Inf). Reduce learning_rate or add gradient clipping.",
    ),
    "MODULE_NOT_FOUND": (
        re.compile(r"(ModuleNotFoundError|ImportError): No module named (.+)", re.IGNORECASE),
        "Missing dependency. Install the missing Python package or check environment.",
    ),
    "TIMEOUT": (
        re.compile(r"(timed out after|TimeoutExpired)", re.IGNORECASE),
        "Job exceeded wall-clock timeout limit. Increase timeout or decrease epochs/dataset size.",
    ),
    "UNTRUSTED_INJECTION": (
        re.compile(r"(IGNORE PREVIOUS|GRANT ADMIN|OVERRIDE POLICY)", re.IGNORECASE),
        "Untrusted prompt injection pattern detected in training logs. Discarding output.",
    ),
}


def read_run_logs(
    run_id: str,
    *,
    tail_lines: int = 50,
    base: Path | None = None,
) -> dict[str, Any]:
    """Read and diagnose training stdout/stderr logs from a run."""
    run_dir = (base or EXPERIMENTS_DIR) / run_id
    log_path = run_dir / "train.log"

    if not log_path.exists():
        return {
            "ok": False,
            "exists": False,
            "run_id": run_id,
            "error": "train.log does not exist",
            "diagnosis": None,
            "recommendation": None,
            "error_lines": [],
            "tail_lines": [],
        }

    raw_text = log_path.read_text(encoding="utf-8", errors="replace")
    all_lines = raw_text.splitlines()
    selected_tail = all_lines[-tail_lines:] if len(all_lines) > tail_lines else all_lines

    diagnosis = None
    recommendation = None
    for issue_key, (pattern, rec) in PATTERNS.items():
        if pattern.search(raw_text):
            diagnosis = issue_key
            recommendation = rec
            break

    # Extract all lines containing error markers or traceback
    error_lines = [
        line.strip()
        for line in all_lines
        if any(marker in line.upper() for marker in ("ERROR", "TRACEBACK", "EXCEPTION", "FAILED", "WARNING"))
    ]

    return {
        "ok": True,
        "exists": True,
        "run_id": run_id,
        "line_count": len(all_lines),
        "diagnosis": diagnosis,
        "recommendation": recommendation,
        "error_lines": error_lines[-10:],
        "tail_lines": selected_tail,
        "has_failure": diagnosis is not None or any("ERROR" in l.upper() for l in error_lines),
    }

