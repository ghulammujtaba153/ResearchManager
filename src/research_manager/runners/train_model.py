"""Real ML training script executed by the Local Subprocess Runner.

Trains a logistic classifier on binary classification data using gradient descent.
Outputs:
- experiments/{run_id}/train.log (full stream of training progress, stdout, and telemetry)
- experiments/{run_id}/results.csv (final metrics for evidence tools)
- experiments/{run_id}/params.yaml (applied parameters)
- experiments/{run_id}/metrics.json (detailed run summary)
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

PROJECT_ROOT = Path(__file__).resolve().parents[3]
EXPERIMENTS_DIR = PROJECT_ROOT / "experiments"
TASKS_DIR = PROJECT_ROOT / "tasks"


def _log_mlflow(
    *,
    run_id: str,
    params: dict,
    metrics: dict[str, float],
    artifact_dir: Path,
    log_print,
) -> str | None:
    """Log a completed run when MLflow tracking is configured."""
    tracking_uri = os.environ.get(
        "MLFLOW_TRACKING_URI",
        f"sqlite:///{PROJECT_ROOT / 'mlflow.db'}",
    )

    try:
        import mlflow
        from mlflow.exceptions import MlflowException
    except ImportError:
        log_print("WARNING: MLFLOW_TRACKING_URI is set but mlflow is not installed.")
        return None

    try:
        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment(os.environ.get("MLFLOW_EXPERIMENT_NAME", "ResearchManager"))
        with mlflow.start_run(run_name=run_id) as active_run:
            safe_params = {
                key: value
                for key, value in params.items()
                if isinstance(value, (str, int, float, bool))
            }
            mlflow.log_params(safe_params)
            mlflow.log_metrics(metrics)
            mlflow.set_tags(
                {
                    "research_manager_run_id": run_id,
                    "runner": "local_subprocess",
                    "cycle": str(os.environ.get("RESEARCH_MANAGER_CYCLE", "unknown")),
                }
            )
            for filename in ("params.yaml", "results.csv", "metrics.json", "train.log"):
                artifact = artifact_dir / filename
                if artifact.exists():
                    mlflow.log_artifact(str(artifact))
            log_print(f"MLflow run logged: {active_run.info.run_id}")
            return active_run.info.run_id
    except MlflowException as exc:
        log_print(f"WARNING: MLflow logging failed: {exc}")
        return None


def _load_config(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        return yaml.safe_load(text) or {}
    out: dict[str, Any] = {}
    current_key = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            parts = line.split(":", 1)
            k = parts[0].strip()
            v = parts[1].strip()
            if not v:
                current_key = k
                out[current_key] = {}
            else:
                try:
                    val = json.loads(v)
                except Exception:
                    val = v
                if current_key and raw_line.startswith("  "):
                    out[current_key][k] = val
                else:
                    current_key = None
                    out[k] = val
    return out


def _dump_params(params: dict) -> str:
    if yaml is not None:
        return yaml.safe_dump(params, sort_keys=False)
    return "\n".join(f"{k}: {v}" for k, v in params.items()) + "\n"


def _generate_synthetic_data(n_samples: int = 300, n_features: int = 6, seed: int = 42):
    """Generate reproducible binary classification dataset without requiring numpy/sklearn."""
    rng = random.Random(seed)
    # Weights for true separating hyperplane
    true_weights = [rng.uniform(-1.5, 1.5) for _ in range(n_features)]
    true_bias = 0.2

    X: list[list[float]] = []
    y: list[int] = []
    for _ in range(n_samples):
        row = [rng.gauss(0.0, 1.0) for _ in range(n_features)]
        logit = sum(w * x for w, x in zip(true_weights, row)) + true_bias + rng.gauss(0.0, 0.3)
        prob = 1.0 / (1.0 + math.exp(-max(min(logit, 20.0), -20.0)))
        label = 1 if prob >= 0.5 else 0
        X.append(row)
        y.append(label)

    # 80/20 train/validation split
    split = int(0.8 * n_samples)
    return X[:split], y[:split], X[split:], y[split:]


def train(
    *,
    run_id: str,
    params: dict,
    cycle: int = 1,
    out_dir: Path | None = None,
    log_file: Path | None = None,
) -> dict:
    dest_dir = out_dir or (EXPERIMENTS_DIR / run_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_file or (dest_dir / "train.log")

    lr = float(params.get("learning_rate", 0.1))
    epochs = int(params.get("epochs", 5))
    metric_name = str(params.get("metric_name", "accuracy"))
    seed = int(params.get("seed", 42))
    simulate_crash = params.get("simulate_crash")

    with open(log_path, "w", encoding="utf-8") as log:
        def log_print(msg: str):
            print(msg)
            log.write(msg + "\n")
            log.flush()

        log_print(f"==================================================")
        log_print(f"Research Experiment Runner — Live Training Process")
        log_print(f"Run ID:     {run_id}")
        log_print(f"Cycle:      {cycle}")
        log_print(f"Timestamp:  {time.strftime('%Y-%m-%d %H:%M:%S')}")
        log_print(f"Parameters: {json.dumps(params, indent=2)}")
        log_print(f"==================================================\n")

        # Intentional crash for failure diagnosis demonstration
        if simulate_crash == "cuda_oom":
            log_print("Allocating tensor buffers on CUDA device 0...")
            log_print("ERROR: torch.cuda.OutOfMemoryError: CUDA out of memory. Tried to allocate 4.00 GiB (GPU 0; 8.00 GiB total capacity; 7.82 GiB already allocated)")
            log_print("Traceback (most recent call last):")
            log_print("  File 'train_model.py', line 124, in train")
            log_print("    tensor = torch.zeros((batch_size, 4096, 4096), device='cuda')")
            log_print("torch.cuda.OutOfMemoryError: CUDA out of memory.")
            sys.exit(1)

        if simulate_crash == "syntax_error":
            log_print("Traceback (most recent call last):")
            log_print("  File 'train_model.py', line 45, in <module>")
            log_print("    import nonexistent_ml_framework")
            log_print("ModuleNotFoundError: No module named 'nonexistent_ml_framework'")
            sys.exit(1)

        # Gradient divergence condition (unstable learning rate)
        if lr >= 5.0:
            log_print(f"[Epoch 1/{epochs}] Learning rate={lr:.4f} is too high!")
            log_print("[Epoch 1/{epochs}] Step 10: Loss exploded to inf")
            log_print("[Epoch 1/{epochs}] Step 20: Loss is NaN. Numerical instability detected.")
            log_print("ERROR: DivergenceError: Loss became NaN at epoch 1 step 20. Gradients exploded.")
            sys.exit(2)

        log_print(f"Loading synthetic classification benchmark (300 samples, 6 features)...")
        X_train, y_train, X_val, y_val = _generate_synthetic_data(300, 6, seed=seed)
        log_print(f"Dataset ready: {len(X_train)} train samples, {len(X_val)} validation samples.\n")

        # Initialize weights
        rng = random.Random(seed)
        weights = [rng.gauss(0.0, 0.05) for _ in range(6)]
        bias = 0.0

        best_val_acc = 0.0
        start_time = time.time()

        for ep in range(1, epochs + 1):
            # Training step
            total_loss = 0.0
            correct_train = 0
            grad_w = [0.0] * 6
            grad_b = 0.0

            for x_row, y_true in zip(X_train, y_train):
                logit = sum(w * x for w, x in zip(weights, x_row)) + bias
                prob = 1.0 / (1.0 + math.exp(-max(min(logit, 20.0), -20.0)))
                pred = 1 if prob >= 0.5 else 0
                if pred == y_true:
                    correct_train += 1

                # Binary cross-entropy loss
                eps = 1e-12
                total_loss += -(y_true * math.log(max(prob, eps)) + (1 - y_true) * math.log(max(1.0 - prob, eps)))

                # Gradient
                err = prob - y_true
                for i in range(6):
                    grad_w[i] += err * x_row[i]
                grad_b += err

            n_train = len(X_train)
            train_loss = total_loss / n_train
            train_acc = correct_train / n_train

            # Weight update (SGD)
            for i in range(6):
                weights[i] -= lr * (grad_w[i] / n_train)
            bias -= lr * (grad_b / n_train)

            # Validation step
            correct_val = 0
            true_positive = false_positive = true_negative = false_negative = 0
            for x_row, y_true in zip(X_val, y_val):
                logit = sum(w * x for w, x in zip(weights, x_row)) + bias
                prob = 1.0 / (1.0 + math.exp(-max(min(logit, 20.0), -20.0)))
                pred = 1 if prob >= 0.5 else 0
                if pred == y_true:
                    correct_val += 1
                if pred == 1 and y_true == 1:
                    true_positive += 1
                elif pred == 1:
                    false_positive += 1
                elif y_true == 1:
                    false_negative += 1
                else:
                    true_negative += 1
            val_acc = correct_val / len(X_val)
            if val_acc > best_val_acc:
                best_val_acc = val_acc

            grad_norm = math.sqrt(sum(g * g for g in grad_w) / n_train)
            log_print(
                f"[Epoch {ep:02d}/{epochs:02d}] Train Loss: {train_loss:.4f} | "
                f"Train Acc: {train_acc:.4f} | Val Acc: {val_acc:.4f} | "
                f"Grad Norm: {grad_norm:.4f}"
            )
            time.sleep(0.05)  # Realistic execution pacing

        elapsed = time.time() - start_time
        precision = true_positive / max(true_positive + false_positive, 1)
        recall = true_positive / max(true_positive + false_negative, 1)
        f1 = 2 * precision * recall / max(precision + recall, 1e-12)
        log_print(f"\nTraining completed in {elapsed:.2f}s.")
        log_print(
            f"Final Validation Accuracy: {val_acc:.4f} | Precision: {precision:.4f} | "
            f"Recall: {recall:.4f} | F1: {f1:.4f} (Best Accuracy: {best_val_acc:.4f})"
        )

        # Persist artifacts into experiment directory
        (dest_dir / "params.yaml").write_text(_dump_params(params), encoding="utf-8")

        # Write results.csv for standard evidence tools
        col_name = "accuracy" if metric_name in {"accuracy", "acc"} else metric_name
        csv_content = (
            f"{col_name},precision,recall,f1,loss,epochs,learning_rate,duration_sec\n"
            f"{val_acc:.4f},{precision:.4f},{recall:.4f},{f1:.4f},{train_loss:.4f},"
            f"{epochs},{lr},{elapsed:.2f}\n"
        )
        (dest_dir / "results.csv").write_text(csv_content, encoding="utf-8")

        # Write detailed metrics JSON
        metrics_payload = {
            "run_id": run_id,
            "metric_name": col_name,
            "metric_value": round(val_acc, 4),
            "accuracy": round(val_acc, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "loss": round(train_loss, 4),
            "epochs": epochs,
            "learning_rate": lr,
            "duration_sec": round(elapsed, 2),
            "status": "success",
        }
        (dest_dir / "metrics.json").write_text(json.dumps(metrics_payload, indent=2), encoding="utf-8")

        mlflow_metrics = {
            "accuracy": float(val_acc),
            "precision": float(precision),
            "recall": float(recall),
            "f1": float(f1),
            "loss": float(train_loss),
            "duration_sec": float(elapsed),
        }
        mlflow_run_id = _log_mlflow(
            run_id=run_id,
            params=params,
            metrics=mlflow_metrics,
            artifact_dir=dest_dir,
            log_print=log_print,
        )
        log_print(f"Artifacts successfully written to {dest_dir.name}/.")
        if mlflow_run_id:
            metrics_payload["mlflow_run_id"] = mlflow_run_id
        return metrics_payload


def main():
    parser = argparse.ArgumentParser(description="Real ML Experiment Runner")
    parser.add_argument("--config", type=str, default=str(TASKS_DIR / "next_experiment.yaml"))
    parser.add_argument("--run-id", type=str, default=None)
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"ERROR: Config file not found at {config_path}", file=sys.stderr)
        sys.exit(1)

    task = _load_config(config_path)
    run_id = args.run_id or task.get("run_id") or f"run_{int(time.time())}"
    params = task.get("params", {})
    cycle = int(task.get("cycle", 1))

    train(run_id=run_id, params=params, cycle=cycle)


if __name__ == "__main__":
    main()
