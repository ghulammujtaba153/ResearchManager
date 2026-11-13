"""Statistical Verification & Scientific Trajectory Engine.

Calculates multi-run convergence statistics, Pareto trade-offs, and generates
scientific vector charts comparing experimental metrics against approved baselines.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
REPORTS_DIR = PROJECT_ROOT / "reports"


def compute_statistics(values: list[float]) -> dict[str, float]:
    """Calculate descriptive statistics (mean, std, min, max, stderr)."""
    if not values:
        return {"count": 0, "mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "stderr": 0.0}
    n = len(values)
    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / (n - 1) if n > 1 else 0.0
    std = math.sqrt(variance)
    stderr = std / math.sqrt(n) if n > 0 else 0.0
    return {
        "count": n,
        "mean": round(mean, 4),
        "std": round(std, 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "stderr": round(stderr, 4),
    }


def build_trajectory(runs: list[dict[str, Any]], baseline: float = 0.75) -> list[dict[str, Any]]:
    """Build cycle-by-cycle trajectory series for plotting and progress analysis."""
    trajectory = []
    # Sort runs chronologically
    sorted_runs = sorted(runs, key=lambda r: r.get("id", 0))
    for i, r in enumerate(sorted_runs, start=1):
        metrics = r.get("metrics") or {}
        # Parse accuracy and loss
        acc = metrics.get("accuracy") or metrics.get("acc")
        loss = metrics.get("loss")
        try:
            acc_val = float(acc) if acc is not None else None
        except (ValueError, TypeError):
            acc_val = None

        try:
            loss_val = float(loss) if loss is not None else None
        except (ValueError, TypeError):
            loss_val = None

        trajectory.append({
            "cycle": i,
            "run_key": r.get("run_key", f"run_{i}"),
            "accuracy": acc_val,
            "loss": loss_val,
            "baseline": baseline,
            "beats_baseline": acc_val is not None and acc_val >= baseline,
            "success": bool(r.get("success")),
            "notes": r.get("notes", ""),
        })
    return trajectory


def generate_svg_chart(trajectory: list[dict[str, Any]], baseline: float = 0.75, width: int = 600, height: int = 300) -> str:
    """Render an SVG vector chart of Accuracy vs Cycle with approved baseline threshold line."""
    pad_left = 60
    pad_right = 30
    pad_top = 40
    pad_bottom = 50

    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom

    n_points = max(len(trajectory), 2)
    max_acc = 1.0
    min_acc = 0.0

    def get_x(idx: int) -> float:
        return pad_left + (idx / (n_points - 1)) * plot_w

    def get_y(val: float) -> float:
        clamped = max(min(val, max_acc), min_acc)
        return pad_top + (1.0 - clamped) * plot_h

    # Baseline line Y
    baseline_y = get_y(baseline)

    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%">',
        f'  <rect width="{width}" height="{height}" fill="#0d1117" rx="8"/>',
        f'  <text x="{pad_left}" y="24" fill="#58a6ff" font-family="sans-serif" font-size="14" font-weight="bold">Experiment Accuracy Convergence vs Approved Baseline</text>',
        # Grid lines
        f'  <line x1="{pad_left}" y1="{pad_top}" x2="{width - pad_right}" y2="{pad_top}" stroke="#21262d" stroke-width="1"/>',
        f'  <line x1="{pad_left}" y1="{pad_top + plot_h / 2}" x2="{width - pad_right}" y2="{pad_top + plot_h / 2}" stroke="#21262d" stroke-width="1"/>',
        f'  <line x1="{pad_left}" y1="{height - pad_bottom}" x2="{width - pad_right}" y2="{height - pad_bottom}" stroke="#30363d" stroke-width="1"/>',
        f'  <line x1="{pad_left}" y1="{pad_top}" x2="{pad_left}" y2="{height - pad_bottom}" stroke="#30363d" stroke-width="1"/>',
        # Baseline threshold line (dashed red/gold)
        f'  <line x1="{pad_left}" y1="{baseline_y}" x2="{width - pad_right}" y2="{baseline_y}" stroke="#e3b341" stroke-dasharray="4,4" stroke-width="2"/>',
        f'  <text x="{width - pad_right - 120}" y="{baseline_y - 6}" fill="#e3b341" font-family="monospace" font-size="11">Baseline: {baseline:.2f}</text>',
        # Axis labels
        f'  <text x="14" y="{pad_top + 10}" fill="#8b949e" font-family="monospace" font-size="10">1.00</text>',
        f'  <text x="14" y="{baseline_y + 4}" fill="#e3b341" font-family="monospace" font-size="10">{baseline:.2f}</text>',
        f'  <text x="14" y="{height - pad_bottom}" fill="#8b949e" font-family="monospace" font-size="10">0.00</text>',
    ]

    points = []
    for idx, p in enumerate(trajectory):
        if p["accuracy"] is not None:
            cx = get_x(idx)
            cy = get_y(p["accuracy"])
            points.append((cx, cy, p))

    # Draw line connecting points
    if len(points) > 1:
        polyline_pts = " ".join(f"{x},{y}" for x, y, _ in points)
        svg_parts.append(f'  <polyline fill="none" stroke="#3fb950" stroke-width="2.5" points="{polyline_pts}"/>')

    # Draw point circles and labels
    for cx, cy, p in points:
        color = "#3fb950" if p["beats_baseline"] else "#f85149"
        svg_parts.append(f'  <circle cx="{cx}" cy="{cy}" r="5" fill="{color}" stroke="#0d1117" stroke-width="1.5"/>')
        svg_parts.append(f'  <text x="{cx - 10}" y="{cy - 10}" fill="#c9d1d9" font-family="monospace" font-size="11">{p["accuracy"]:.2f}</text>')
        svg_parts.append(f'  <text x="{cx - 14}" y="{height - pad_bottom + 18}" fill="#8b949e" font-family="sans-serif" font-size="10">C{p["cycle"]}</text>')

    svg_parts.append('</svg>')
    return "\n".join(svg_parts)


def export_trajectory_report(project_id: str, trajectory: list[dict[str, Any]], baseline: float = 0.75) -> Path:
    """Save an SVG chart to the reports directory."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    svg_content = generate_svg_chart(trajectory, baseline)
    chart_path = REPORTS_DIR / f"{project_id}_trajectory.svg"
    chart_path.write_text(svg_content, encoding="utf-8")
    return chart_path

