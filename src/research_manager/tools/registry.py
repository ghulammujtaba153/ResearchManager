"""CRUD helpers for the experiment registry."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from research_manager.memory.models import Baseline, Decision, Experiment, Run


def create_experiment(
    session: Session,
    name: str,
    hypothesis: str,
    params: dict[str, Any],
) -> Experiment:
    exp = Experiment(
        name=name,
        hypothesis=hypothesis,
        params_json=json.dumps(params),
        status="planned",
    )
    session.add(exp)
    session.commit()
    session.refresh(exp)
    return exp


def log_run(
    session: Session,
    experiment_id: int,
    run_key: str,
    metrics: dict[str, Any],
    artifacts_path: str,
    success: bool,
    notes: str = "",
) -> Run:
    run = Run(
        experiment_id=experiment_id,
        run_key=run_key,
        metrics_json=json.dumps(metrics),
        artifacts_path=artifacts_path,
        success=success,
        notes=notes,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def log_decision(
    session: Session,
    run_id: int,
    decision_type: str,
    rationale: str,
    next_params: dict[str, Any] | None = None,
) -> Decision:
    decision = Decision(
        run_id=run_id,
        decision_type=decision_type,
        rationale=rationale,
        next_params_json=json.dumps(next_params or {}),
    )
    session.add(decision)
    session.commit()
    session.refresh(decision)
    return decision


def upsert_baseline(session: Session, metric_name: str, value: float, source_run_id: int | None = None) -> Baseline:
    baseline = session.query(Baseline).filter_by(metric_name=metric_name).one_or_none()
    if baseline is None:
        baseline = Baseline(metric_name=metric_name, value=value, source_run_id=source_run_id)
        session.add(baseline)
    else:
        baseline.value = value
        baseline.source_run_id = source_run_id
    session.commit()
    session.refresh(baseline)
    return baseline


def get_baselines(session: Session) -> dict[str, float]:
    return {b.metric_name: b.value for b in session.query(Baseline).all()}
