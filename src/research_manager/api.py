"""FastAPI backend for the Research Experiment Manager UI."""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from research_manager.agent import workflow
from research_manager.memory.db import init_db
from research_manager.memory import store
from research_manager.memory.models import Decision

app = FastAPI(title="Research Experiment Manager", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class OnboardRequest(BaseModel):
    project_id: str = "demo"
    name: str | None = None
    baseline_accuracy: float = 0.75


class CycleRequest(BaseModel):
    project_id: str = "demo"
    use_memory: bool = True
    idempotency_key: str | None = None
    force_sim_status: str | None = None
    plant_untrusted: bool = False
    simulate_tool_failure: bool = False


class ApproveRequest(BaseModel):
    project_id: str = "demo"
    approved: bool = True
    comment: str = ""


class CorrectRequest(BaseModel):
    project_id: str = "demo"
    fact_key: str
    value: Any
    approved_by: str = "supervisor"


class DemoRequest(BaseModel):
    project_id: str = "demo"
    max_cycles: int = Field(default=3, ge=1, le=10)


def _snapshot(project_id: str) -> dict[str, Any]:
    SessionLocal = init_db()
    with SessionLocal() as session:
        store.ensure_project(session, project_id)
        experiments = store.list_project_experiments(session, project_id)
        runs = store.list_project_runs(session, project_id)
        decisions = (
            session.query(Decision)
            .filter_by(project_id=project_id)
            .order_by(Decision.id.desc())
            .limit(20)
            .all()
        )
        facts = store.get_current_facts(session, project_id)
        fact_history = store.list_fact_history(session, project_id)
        logs = store.list_action_logs(session, project_id, limit=30)
        checkpoint = store.load_latest_checkpoint(session, project_id, log=False)
        latest = experiments[0] if experiments else None
        pending = store.latest_pending_decision(session, project_id)

        pending_approval = None
        if pending is not None and pending.decision_type not in ("accept_and_stop",):
            pending_approval = {
                "id": pending.id,
                "run_id": pending.run_id,
                "decision_type": pending.decision_type,
                "rationale": pending.rationale,
                "next_params": json.loads(pending.next_params_json or "{}"),
                "created_at": pending.created_at.isoformat() if pending.created_at else None,
            }

        return {
            "project_id": project_id,
            "current": {
                "experiment_id": latest.id if latest else None,
                "name": latest.name if latest else None,
                "hypothesis": latest.hypothesis if latest else "",
                "status": latest.status if latest else "idle",
                "params": json.loads(latest.params_json) if latest else {},
            },
            "facts": facts,
            "fact_history": fact_history,
            "checkpoint": checkpoint,
            "approval_required": pending_approval is not None
            and latest is not None
            and latest.status in {"needs_review", "iterating"},
            "next_action": _recommend(latest, pending_approval),
            "pending_approval": pending_approval,
            "baselines": {"accuracy": facts.get("baseline_accuracy")},
            "experiments": [
                {
                    "id": e.id,
                    "name": e.name,
                    "hypothesis": e.hypothesis,
                    "status": e.status,
                    "params": json.loads(e.params_json or "{}"),
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in experiments
            ],
            "runs": [
                {
                    "id": r.id,
                    "experiment_id": r.experiment_id,
                    "run_key": r.run_key,
                    "metrics": json.loads(r.metrics_json or "{}"),
                    "success": r.success,
                    "notes": r.notes,
                    "artifacts_path": r.artifacts_path,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in runs
            ],
            "decisions": [
                {
                    "id": d.id,
                    "run_id": d.run_id,
                    "decision_type": d.decision_type,
                    "rationale": d.rationale,
                    "next_params": json.loads(d.next_params_json or "{}"),
                    "agent_suggested": d.agent_suggested,
                    "supervisor_confirmed": d.supervisor_confirmed,
                    "supervisor_comment": d.supervisor_comment,
                    "created_at": d.created_at.isoformat() if d.created_at else None,
                }
                for d in decisions
            ],
            "evidence": [
                {
                    "source": runs[0].artifacts_path,
                    "run_key": runs[0].run_key,
                    "metrics": json.loads(runs[0].metrics_json or "{}"),
                    "notes": runs[0].notes,
                    "success": runs[0].success,
                }
            ]
            if runs
            else [],
            "action_log": [
                {
                    "id": a.id,
                    "event_type": a.event_type,
                    "tool_name": a.tool_name,
                    "outcome": a.outcome,
                    "error": a.error,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                    "output": json.loads(a.output_json or "{}"),
                }
                for a in logs
            ],
            "last_decision": _last_llm_decision(logs),
        }


def _last_llm_decision(logs) -> dict[str, Any] | None:
    finalize = None
    selection = None
    for a in logs:
        payload = json.loads(a.output_json or "{}")
        if a.tool_name == "finalize_action":
            finalize = (a, payload)
            break
        if selection is None and (
            a.event_type == "llm_decision" or a.tool_name == "decide_next_action"
        ):
            selection = (a, payload)
    chosen = finalize or selection
    if chosen is None:
        return None
    a, payload = chosen
    return {
        "action": payload.get("action"),
        "rationale": payload.get("rationale"),
        "llm_used": bool(payload.get("llm_used")),
        "model": payload.get("model"),
        "latency_ms": payload.get("latency_ms"),
        "tools_to_use": payload.get("tools_to_use", []),
        "tools_executed": payload.get("tools_executed", []),
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _recommend(latest, pending_approval) -> dict[str, Any]:
    if latest is None:
        return {
            "action": "onboard",
            "label": "Onboard project and set approved baseline",
            "requires_approval": False,
        }
    if pending_approval and latest.status in {"needs_review", "iterating"}:
        return {
            "action": "approve_decision",
            "label": f"Approve or reject before next cycle: {pending_approval['decision_type']}",
            "requires_approval": True,
            "decision": pending_approval,
        }
    if latest.status == "completed":
        return {
            "action": "review_complete",
            "label": "Review completed runs or correct a baseline fact",
            "requires_approval": False,
        }
    return {
        "action": "run_next_cycle",
        "label": "Run next planner → evidence → decision cycle",
        "requires_approval": False,
    }


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/state")
def get_state(project_id: str = Query(default="demo")) -> dict[str, Any]:
    return _snapshot(project_id)


@app.get("/api/facts")
def get_facts(
    project_id: str = Query(default="demo"),
    fact_key: str | None = Query(default=None),
) -> dict[str, Any]:
    SessionLocal = init_db()
    with SessionLocal() as session:
        store.ensure_project(session, project_id)
        return {
            "project_id": project_id,
            "current": store.get_current_facts(session, project_id),
            "history": store.list_fact_history(session, project_id, fact_key),
        }


@app.post("/api/onboard")
def onboard(body: OnboardRequest) -> dict[str, Any]:
    result = workflow.onboard_project(
        body.project_id,
        name=body.name,
        baseline_accuracy=body.baseline_accuracy,
    )
    return {"ok": True, "result": result, "snapshot": _snapshot(body.project_id)}


@app.post("/api/demo")
def start_demo(body: DemoRequest | None = None) -> dict[str, Any]:
    project_id = body.project_id if body else "demo"
    max_cycles = body.max_cycles if body else 3
    state = workflow.run_demo(project_id=project_id, max_cycles=max_cycles)
    return {"ok": True, "state": state.model_dump(), "snapshot": _snapshot(project_id)}


@app.post("/api/cycle")
def cycle_once(body: CycleRequest | None = None) -> dict[str, Any]:
    body = body or CycleRequest()
    try:
        result = workflow.run_cycle(
            body.project_id,
            use_memory=body.use_memory,
            idempotency_key=body.idempotency_key,
            force_sim_status=body.force_sim_status,
            plant_untrusted=body.plant_untrusted,
            simulate_tool_failure=body.simulate_tool_failure,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "result": result, "snapshot": _snapshot(body.project_id)}


@app.post("/api/resume")
def resume(project_id: str = Query(default="demo")) -> dict[str, Any]:
    try:
        result = workflow.resume_project(project_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "result": result, "snapshot": _snapshot(project_id)}


@app.post("/api/approve")
def approve(body: ApproveRequest) -> dict[str, Any]:
    try:
        result = workflow.approve_decision(
            body.project_id,
            approved=body.approved,
            comment=body.comment,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "result": result, "snapshot": _snapshot(body.project_id)}


@app.post("/api/correct")
def correct(body: CorrectRequest) -> dict[str, Any]:
    result = workflow.correct_fact(
        body.project_id,
        body.fact_key,
        body.value,
        approved_by=body.approved_by,
    )
    return {"ok": True, "result": result, "snapshot": _snapshot(body.project_id)}


def main() -> None:
    import uvicorn

    uvicorn.run("research_manager.api:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
