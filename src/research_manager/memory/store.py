"""Memory lifecycle operations: projects, facts, checkpoints, action log."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from research_manager.memory.models import (
    ActionLog,
    Checkpoint,
    Decision,
    Experiment,
    FactVersion,
    Project,
    Run,
)

IMMUTABLE_FACT_KEYS = frozenset({"review_policy"})
CHECKPOINT_LIMIT = 20


def ensure_project(session: Session, project_id: str, name: str | None = None) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        project = Project(id=project_id, name=name or project_id)
        session.add(project)
        session.commit()
        session.refresh(project)
    return project


def log_action(
    session: Session,
    *,
    project_id: str,
    event_type: str,
    tool_name: str = "",
    input_data: dict | None = None,
    output_data: dict | None = None,
    outcome: str = "ok",
    error: str = "",
    idempotency_key: str | None = None,
) -> ActionLog | None:
    """Append action log. Duplicate idempotency keys are ignored (retry-safe)."""
    entry = ActionLog(
        project_id=project_id,
        event_type=event_type,
        tool_name=tool_name,
        input_json=json.dumps(input_data or {}),
        output_json=json.dumps(output_data or {}),
        outcome=outcome,
        error=error,
        idempotency_key=idempotency_key,
    )
    session.add(entry)
    try:
        session.commit()
        session.refresh(entry)
        return entry
    except IntegrityError:
        session.rollback()
        return None


def get_action_by_idempotency(session: Session, idempotency_key: str) -> ActionLog | None:
    return session.query(ActionLog).filter_by(idempotency_key=idempotency_key).one_or_none()


def get_current_fact(session: Session, project_id: str, fact_key: str) -> FactVersion | None:
    return (
        session.query(FactVersion)
        .filter_by(project_id=project_id, fact_key=fact_key, is_current=True)
        .one_or_none()
    )


def get_current_facts(session: Session, project_id: str) -> dict[str, Any]:
    rows = (
        session.query(FactVersion)
        .filter_by(project_id=project_id, is_current=True)
        .all()
    )
    out: dict[str, Any] = {}
    for row in rows:
        out[row.fact_key] = json.loads(row.value_json)
    return out


def list_fact_history(
    session: Session,
    project_id: str,
    fact_key: str | None = None,
) -> list[dict[str, Any]]:
    q = session.query(FactVersion).filter_by(project_id=project_id)
    if fact_key:
        q = q.filter_by(fact_key=fact_key)
    rows = q.order_by(FactVersion.fact_key.asc(), FactVersion.version.desc()).all()
    return [
        {
            "fact_key": r.fact_key,
            "value": json.loads(r.value_json),
            "version": r.version,
            "is_current": r.is_current,
            "approved_by": r.approved_by,
            "source_ref": r.source_ref,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "superseded_at": r.superseded_at.isoformat() if r.superseded_at else None,
        }
        for r in rows
    ]


def set_fact(
    session: Session,
    *,
    project_id: str,
    fact_key: str,
    value: Any,
    approved_by: str = "system",
    source_ref: str = "",
) -> FactVersion:
    """Approve a new fact version; previous current row is superseded (history kept)."""
    ensure_project(session, project_id)
    if fact_key in IMMUTABLE_FACT_KEYS:
        existing = get_current_fact(session, project_id, fact_key)
        if existing is not None and approved_by not in {"supervisor", "system", "onboarding"}:
            raise PermissionError(
                f"Fact '{fact_key}' is immutable policy and cannot be changed by {approved_by}"
            )
        if existing is not None and approved_by == "untrusted":
            raise PermissionError(f"Fact '{fact_key}' cannot be changed by untrusted content")

    current = get_current_fact(session, project_id, fact_key)
    next_version = 1
    if current is not None:
        # review_policy: only allow identical re-affirm by supervisor/system
        if fact_key in IMMUTABLE_FACT_KEYS:
            current_val = json.loads(current.value_json)
            if current_val != value and approved_by not in {"supervisor"}:
                raise PermissionError(
                    f"Immutable policy '{fact_key}' can only be changed by supervisor confirmation"
                )
        current.is_current = False
        current.superseded_at = datetime.utcnow()
        next_version = current.version + 1
    row = FactVersion(
        project_id=project_id,
        fact_key=fact_key,
        value_json=json.dumps(value),
        version=next_version,
        is_current=True,
        source_ref=source_ref,
        approved_by=approved_by,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    log_action(
        session,
        project_id=project_id,
        event_type="memory_write",
        tool_name="set_fact",
        input_data={"fact_key": fact_key, "value": value, "version": next_version},
        outcome="ok",
    )
    return row


def save_checkpoint(
    session: Session,
    *,
    project_id: str,
    experiment_id: int | None,
    state: dict[str, Any],
) -> Checkpoint:
    cp = Checkpoint(
        project_id=project_id,
        experiment_id=experiment_id,
        state_json=json.dumps(state),
    )
    session.add(cp)
    session.commit()
    session.refresh(cp)
    # Bound working-state history
    old = (
        session.query(Checkpoint)
        .filter_by(project_id=project_id)
        .order_by(Checkpoint.id.desc())
        .offset(CHECKPOINT_LIMIT)
        .all()
    )
    for row in old:
        session.delete(row)
    session.commit()
    log_action(
        session,
        project_id=project_id,
        event_type="memory_write",
        tool_name="save_checkpoint",
        input_data={"experiment_id": experiment_id},
        outcome="ok",
    )
    return cp


def load_latest_checkpoint(
    session: Session,
    project_id: str,
    *,
    log: bool = True,
) -> dict[str, Any] | None:
    cp = (
        session.query(Checkpoint)
        .filter_by(project_id=project_id)
        .order_by(Checkpoint.id.desc())
        .first()
    )
    if cp is None:
        return None
    if log:
        log_action(
            session,
            project_id=project_id,
            event_type="memory_read",
            tool_name="load_checkpoint",
            output_data={"checkpoint_id": cp.id},
            outcome="ok",
        )
    return {
        "checkpoint_id": cp.id,
        "experiment_id": cp.experiment_id,
        "state": json.loads(cp.state_json),
        "created_at": cp.created_at.isoformat() if cp.created_at else None,
    }


def create_experiment(
    session: Session,
    *,
    project_id: str,
    name: str,
    hypothesis: str,
    params: dict[str, Any],
) -> Experiment:
    ensure_project(session, project_id)
    exp = Experiment(
        project_id=project_id,
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
    *,
    project_id: str,
    experiment_id: int,
    run_key: str,
    metrics: dict[str, Any],
    artifacts_path: str,
    success: bool,
    notes: str = "",
    idempotency_key: str | None = None,
) -> Run:
    if idempotency_key:
        existing = session.query(Run).filter_by(idempotency_key=idempotency_key).one_or_none()
        if existing is not None:
            return existing
    run = Run(
        project_id=project_id,
        experiment_id=experiment_id,
        run_key=run_key,
        metrics_json=json.dumps(metrics),
        artifacts_path=artifacts_path,
        success=success,
        notes=notes,
        idempotency_key=idempotency_key,
    )
    session.add(run)
    try:
        session.commit()
        session.refresh(run)
    except IntegrityError:
        session.rollback()
        existing = session.query(Run).filter_by(idempotency_key=idempotency_key).one_or_none()
        if existing is None:
            raise
        return existing
    return run


def log_decision(
    session: Session,
    *,
    project_id: str,
    run_id: int,
    decision_type: str,
    rationale: str,
    next_params: dict[str, Any] | None = None,
    agent_suggested: bool = True,
    supervisor_confirmed: bool | None = None,
    supervisor_comment: str = "",
) -> Decision:
    decision = Decision(
        project_id=project_id,
        run_id=run_id,
        decision_type=decision_type,
        rationale=rationale,
        next_params_json=json.dumps(next_params or {}),
        agent_suggested=agent_suggested,
        supervisor_confirmed=supervisor_confirmed,
        supervisor_comment=supervisor_comment,
    )
    session.add(decision)
    session.commit()
    session.refresh(decision)
    return decision


def latest_pending_decision(session: Session, project_id: str) -> Decision | None:
    return (
        session.query(Decision)
        .filter_by(project_id=project_id, supervisor_confirmed=None, agent_suggested=True)
        .order_by(Decision.id.desc())
        .first()
    )


def list_project_runs(session: Session, project_id: str, limit: int = 20) -> list[Run]:
    return (
        session.query(Run)
        .filter_by(project_id=project_id)
        .order_by(Run.id.desc())
        .limit(limit)
        .all()
    )


def count_project_runs(session: Session, project_id: str) -> int:
    return session.query(Run).filter_by(project_id=project_id).count()


def list_project_experiments(session: Session, project_id: str) -> list[Experiment]:
    return (
        session.query(Experiment)
        .filter_by(project_id=project_id)
        .order_by(Experiment.id.desc())
        .all()
    )


def list_action_logs(session: Session, project_id: str, limit: int = 50) -> list[ActionLog]:
    return (
        session.query(ActionLog)
        .filter_by(project_id=project_id)
        .order_by(ActionLog.id.desc())
        .limit(limit)
        .all()
    )
