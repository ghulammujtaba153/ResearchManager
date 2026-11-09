"""FastAPI backend for the Research Experiment Manager UI."""

from __future__ import annotations

import json
from html import escape
import os
import secrets
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from research_manager.agent import workflow
from research_manager.memory.db import init_db
from research_manager.memory import store
from research_manager.memory.models import (
    ActionLog,
    Checkpoint,
    Decision,
    Experiment,
    FactVersion,
    Project,
    Run,
)

def require_api_key(request: Request) -> None:
    configured_key = os.getenv("RESEARCH_MANAGER_API_KEY")
    require_auth = os.getenv("RESEARCH_MANAGER_REQUIRE_AUTH", "").lower() in {
        "1",
        "true",
        "yes",
    }
    if not configured_key:
        if require_auth:
            raise HTTPException(
                status_code=503,
                detail="API authentication is required but RESEARCH_MANAGER_API_KEY is not configured",
            )
        return

    supplied_key = request.headers.get("X-API-Key")
    authorization = request.headers.get("Authorization", "")
    if supplied_key is None and authorization.lower().startswith("bearer "):
        supplied_key = authorization[7:].strip()
    if not supplied_key or not secrets.compare_digest(supplied_key, configured_key):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


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
    skip_approval_gate: bool = False
    deterministic: bool | None = None
    runner_mode: str = "simulator"


class ApproveRequest(BaseModel):
    project_id: str = "demo"
    approved: bool = True
    comment: str = ""
    override_params: dict[str, Any] | None = None


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
        latest = experiments[0] if experiments else None
        runs = (
            store.list_project_runs(
                session,
                project_id,
                experiment_id=latest.id if latest else None,
            )
            if latest
            else []
        )
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

        current_params = json.loads(latest.params_json) if latest and latest.params_json else {}
        pending_params = _pending_vs_facts(current_params, facts)

        return {
            "project_id": project_id,
            "current": {
                "experiment_id": latest.id if latest else None,
                "name": latest.name if latest else None,
                "hypothesis": latest.hypothesis if latest else "",
                "status": latest.status if latest else "idle",
                "params": current_params,
            },
            "facts": facts,
            "pending_params": pending_params,
            "fact_bump": _fact_bump(fact_history, "baseline_accuracy"),
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
                    "missing_files": [
                        filename
                        for filename in ("params.yaml", "results.csv")
                        if not (Path(runs[0].artifacts_path) / filename).exists()
                    ],
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
                    "input": json.loads(a.input_json or "{}"),
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
    proposed = payload.get("llm_proposed") or {}
    return {
        "action": payload.get("action"),
        "rationale": payload.get("rationale"),
        "llm_used": bool(payload.get("llm_used")),
        "model": payload.get("model"),
        "latency_ms": payload.get("latency_ms"),
        "tools_to_use": payload.get("tools_to_use", []),
        "tools_executed": payload.get("tools_executed", []),
        "llm_proposed": proposed,
        "guard_overrode": bool(payload.get("guard_overrode")),
        "guard_reason": payload.get("guard_reason"),
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _report_html(snapshot: dict[str, Any]) -> str:
    """Render a self-contained, printable experiment report."""
    current = snapshot["current"]
    runs = snapshot["runs"]
    decisions = snapshot["decisions"]
    facts = snapshot["facts"]
    evidence = snapshot["evidence"][0] if snapshot["evidence"] else None
    status = str(current["status"]).replace("_", " ").title()
    outcome = (
        "Completed successfully"
        if status == "Completed"
        else "Requires review" if status in {"Needs Review", "Iterating"} else status
    )

    def text(value: Any) -> str:
        return escape(str(value if value is not None else "—"))

    def code(value: Any) -> str:
        return escape(json.dumps(value, indent=2, default=str))

    run_rows = "".join(
        f"""<tr>
          <td>{text(index)}</td><td><code>{text(run["run_key"])}</code></td>
          <td>{text("Pass" if run["success"] else "Incomplete / review")}</td>
          <td><code>{code(run["metrics"])}</code></td>
          <td>{text(run["notes"])}</td>
        </tr>"""
        for index, run in enumerate(reversed(runs), 1)
    ) or '<tr><td colspan="5" class="muted">No runs recorded.</td></tr>'

    decision_rows = "".join(
        f"""<tr>
          <td>{text(decision["decision_type"].replace("_", " "))}</td>
          <td>{text(decision["rationale"])}</td>
          <td>{text("Approved" if decision.get("supervisor_confirmed") is True else "Pending" if decision.get("supervisor_confirmed") is None else "Rejected")}</td>
          <td>{text(decision.get("supervisor_comment") or "—")}</td>
        </tr>"""
        for decision in reversed(decisions)
    ) or '<tr><td colspan="4" class="muted">No decisions recorded.</td></tr>'

    fact_rows = "".join(
        f"<tr><td><code>{text(key)}</code></td><td><code>{code(value)}</code></td></tr>"
        for key, value in facts.items()
    ) or '<tr><td colspan="2" class="muted">No approved facts recorded.</td></tr>'

    evidence_block = (
        f"""<div class="callout {'success' if evidence['success'] else 'warning'}">
          <strong>{text("Supporting evidence" if evidence["success"] else "Evidence requires attention")}</strong>
          <p>Run <code>{text(evidence["run_key"])}</code> reported:</p>
          <pre>{code(evidence["metrics"])}</pre>
          <p>{text(evidence["notes"])}</p>
        </div>"""
        if evidence
        else '<div class="callout warning"><strong>No evidence recorded</strong><p>Run an experiment cycle to collect result files.</p></div>'
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Research Experiment Report — {text(snapshot["project_id"])}</title>
<style>
  :root {{ color-scheme: light; --ink:#17231e; --muted:#607269; --line:#d8e2dc; --accent:#168653; --soft:#eef7f1; --warn:#996b19; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; color:var(--ink); background:#f6f8f6; font:15px/1.55 Arial, sans-serif; }}
  main {{ max-width:980px; margin:0 auto; padding:48px 56px; background:#fff; min-height:100vh; }}
  header {{ border-bottom:3px solid var(--accent); padding-bottom:28px; margin-bottom:30px; }}
  .eyebrow {{ color:var(--accent); font-size:11px; font-weight:700; letter-spacing:.16em; text-transform:uppercase; }}
  h1 {{ font:40px/1.05 Georgia, serif; margin:8px 0; }}
  h2 {{ margin:32px 0 12px; font-size:19px; border-bottom:1px solid var(--line); padding-bottom:8px; }}
  h3 {{ font-size:15px; margin:18px 0 6px; }}
  p {{ margin:7px 0; }}
  .subtitle, .muted {{ color:var(--muted); }}
  .meta {{ display:flex; flex-wrap:wrap; gap:9px 24px; color:var(--muted); font-size:13px; }}
  .summary {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin:24px 0; }}
  .metric {{ border:1px solid var(--line); padding:14px; background:#fbfdfb; }}
  .metric span {{ display:block; color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.08em; }}
  .metric strong {{ display:block; margin-top:5px; font-size:18px; }}
  .callout {{ padding:15px 17px; border-left:4px solid var(--accent); background:var(--soft); margin:14px 0; }}
  .callout.warning {{ border-color:#c99532; background:#fff9ed; }}
  .callout p {{ margin:5px 0; }}
  table {{ width:100%; border-collapse:collapse; margin:10px 0 20px; font-size:13px; }}
  th, td {{ border-bottom:1px solid var(--line); padding:9px 8px; text-align:left; vertical-align:top; }}
  th {{ background:#f0f5f1; color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.06em; }}
  code, pre {{ font-family:Consolas, monospace; font-size:12px; }}
  pre {{ white-space:pre-wrap; margin:7px 0; }}
  .footer {{ border-top:1px solid var(--line); margin-top:38px; padding-top:14px; color:var(--muted); font-size:12px; }}
  @media (max-width:700px) {{ main {{ padding:28px 20px; }} h1 {{ font-size:32px; }} .summary {{ grid-template-columns:repeat(2,1fr); }} table {{ display:block; overflow-x:auto; }} }}
  @media print {{ body {{ background:#fff; }} main {{ padding:0; max-width:none; }} .no-print {{ display:none; }} }}
</style>
</head>
<body>
<main>
  <header>
    <div class="eyebrow">Research Manager · Experiment report</div>
    <h1>{text(current["name"] or "Research experiment")}</h1>
    <p class="subtitle">{text(current["hypothesis"])}</p>
    <div class="meta"><span>Project: <strong>{text(snapshot["project_id"])}</strong></span><span>Generated: {text(__import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds"))}</span></div>
  </header>
  <div class="summary">
    <div class="metric"><span>Outcome</span><strong>{text(outcome)}</strong></div>
    <div class="metric"><span>Experiment</span><strong>#{text(current["experiment_id"])}</strong></div>
    <div class="metric"><span>Runs</span><strong>{len(runs)}</strong></div>
    <div class="metric"><span>Baseline</span><strong>{text(facts.get("baseline_accuracy"))}</strong></div>
  </div>
  <h2>Executive conclusion</h2>
  {evidence_block}
  <p>This experiment followed the controlled research loop: plan the run, execute the workload, inspect local artifacts, compare the reported metric with the approved baseline, and select the next action. Supervisor approval was kept separate from agent recommendations.</p>
  <h2>Experiment configuration</h2>
  <table><tr><th>Hypothesis</th><td>{text(current["hypothesis"])}</td></tr><tr><th>Parameters</th><td><pre>{code(current["params"])}</pre></td></tr><tr><th>Next action</th><td>{text(snapshot["next_action"]["label"])}</td></tr></table>
  <h2>Run history</h2>
  <table><thead><tr><th>Cycle</th><th>Run</th><th>Result</th><th>Metrics</th><th>Analyst notes</th></tr></thead><tbody>{run_rows}</tbody></table>
  <h2>Decision and approval record</h2>
  <table><thead><tr><th>Decision</th><th>Rationale</th><th>Supervisor state</th><th>Comment</th></tr></thead><tbody>{decision_rows}</tbody></table>
  <h2>Approved memory</h2>
  <table><thead><tr><th>Fact</th><th>Approved value</th></tr></thead><tbody>{fact_rows}</tbody></table>
  <h2>Reproducibility and audit trail</h2>
  <p>Checkpoint: <code>{text(snapshot["checkpoint"]["checkpoint_id"] if snapshot["checkpoint"] else "none")}</code>. The authoritative state is stored in SQLite. Tool calls, model decisions, evidence reads, and supervisor actions are recorded in the action log.</p>
  <div class="footer">Generated by Research Manager · This report reflects the persisted project state at generation time.</div>
</main>
</body>
</html>"""


def _pending_vs_facts(params: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    pending: dict[str, Any] = {}
    lr = params.get("learning_rate")
    if lr is not None and lr != facts.get("learning_rate"):
        pending["learning_rate"] = lr
    metric = params.get("metric_name")
    if metric is not None and metric != facts.get("approved_metric"):
        pending["metric_name"] = metric
    return pending


def _fact_bump(history: list[dict[str, Any]], fact_key: str) -> dict[str, Any] | None:
    rows = [r for r in history if r.get("fact_key") == fact_key]
    current = next((r for r in rows if r.get("is_current")), None)
    if current is None:
        return None
    prev = next(
        (r for r in rows if not r.get("is_current") and r.get("version") == current["version"] - 1),
        None,
    )
    return {
        "fact_key": fact_key,
        "current_version": current.get("version"),
        "current_value": current.get("value"),
        "previous_version": prev.get("version") if prev else None,
        "previous_value": prev.get("value") if prev else None,
        "approved_by": current.get("approved_by"),
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
def get_state(
    project_id: str = Query(default="demo"),
    _: None = Depends(require_api_key),
) -> dict[str, Any]:
    return _snapshot(project_id)


@app.get("/api/store")
def get_store(
    project_id: str = Query(default="demo"),
    _: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Return a read-only, UI-friendly view of the persistent SQLite store."""
    SessionLocal = init_db()
    with SessionLocal() as session:
        store.ensure_project(session, project_id)
        project = session.get(Project, project_id)
        experiments = session.query(Experiment).filter_by(project_id=project_id).order_by(Experiment.id.desc()).all()
        runs = session.query(Run).filter_by(project_id=project_id).order_by(Run.id.desc()).limit(50).all()
        decisions = session.query(Decision).filter_by(project_id=project_id).order_by(Decision.id.desc()).limit(50).all()
        facts = session.query(FactVersion).filter_by(project_id=project_id).order_by(FactVersion.id.desc()).limit(50).all()
        checkpoints = session.query(Checkpoint).filter_by(project_id=project_id).order_by(Checkpoint.id.desc()).limit(20).all()
        logs = session.query(ActionLog).filter_by(project_id=project_id).order_by(ActionLog.id.desc()).limit(50).all()

        def json_value(value: str) -> Any:
            try:
                return json.loads(value or "{}")
            except json.JSONDecodeError:
                return value

        return {
            "database": "memory/experiments.db",
            "project": {
                "id": project.id,
                "name": project.name,
                "owner": project.owner,
                "created_at": project.created_at.isoformat() if project.created_at else None,
            },
            "counts": {
                "experiments": len(experiments),
                "runs": len(runs),
                "decisions": len(decisions),
                "facts": len(facts),
                "checkpoints": len(checkpoints),
                "action_logs": len(logs),
            },
            "experiments": [
                {"id": e.id, "name": e.name, "status": e.status, "hypothesis": e.hypothesis,
                 "params": json_value(e.params_json), "created_at": e.created_at.isoformat() if e.created_at else None}
                for e in experiments
            ],
            "runs": [
                {"id": r.id, "experiment_id": r.experiment_id, "run_key": r.run_key,
                 "success": r.success, "metrics": json_value(r.metrics_json), "notes": r.notes,
                 "artifacts_path": r.artifacts_path, "created_at": r.created_at.isoformat() if r.created_at else None}
                for r in runs
            ],
            "decisions": [
                {"id": d.id, "run_id": d.run_id, "decision_type": d.decision_type,
                 "rationale": d.rationale, "next_params": json_value(d.next_params_json),
                 "supervisor_confirmed": d.supervisor_confirmed, "supervisor_comment": d.supervisor_comment,
                 "created_at": d.created_at.isoformat() if d.created_at else None}
                for d in decisions
            ],
            "facts": [
                {"id": f.id, "fact_key": f.fact_key, "value": json_value(f.value_json),
                 "version": f.version, "is_current": f.is_current, "approved_by": f.approved_by,
                 "created_at": f.created_at.isoformat() if f.created_at else None}
                for f in facts
            ],
            "checkpoints": [
                {"id": c.id, "experiment_id": c.experiment_id, "state": json_value(c.state_json),
                 "created_at": c.created_at.isoformat() if c.created_at else None}
                for c in checkpoints
            ],
            "action_logs": [
                {"id": a.id, "event_type": a.event_type, "tool_name": a.tool_name, "outcome": a.outcome,
                 "input": json_value(a.input_json), "output": json_value(a.output_json), "error": a.error,
                 "created_at": a.created_at.isoformat() if a.created_at else None}
                for a in logs
            ],
        }


@app.get("/api/report", response_class=HTMLResponse)
def download_report(
    project_id: str = Query(default="demo"),
    _: None = Depends(require_api_key),
) -> HTMLResponse:
    snapshot = _snapshot(project_id)
    filename = f"research-report-{project_id.replace(' ', '-').lower()}.html"
    return HTMLResponse(
        content=_report_html(snapshot),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/facts")
def get_facts(
    project_id: str = Query(default="demo"),
    fact_key: str | None = Query(default=None),
    _: None = Depends(require_api_key),
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
def onboard(body: OnboardRequest, _: None = Depends(require_api_key)) -> dict[str, Any]:
    result = workflow.onboard_project(
        body.project_id,
        name=body.name,
        baseline_accuracy=body.baseline_accuracy,
    )
    return {"ok": True, "result": result, "snapshot": _snapshot(body.project_id)}


@app.post("/api/demo")
def start_demo(
    body: DemoRequest | None = None,
    _: None = Depends(require_api_key),
) -> dict[str, Any]:
    project_id = body.project_id if body else "demo"
    max_cycles = body.max_cycles if body else 3
    state = workflow.run_demo(project_id=project_id, max_cycles=max_cycles)
    return {"ok": True, "state": state.model_dump(), "snapshot": _snapshot(project_id)}


@app.post("/api/cycle")
def cycle_once(
    body: CycleRequest | None = None,
    _: None = Depends(require_api_key),
) -> dict[str, Any]:
    body = body or CycleRequest()
    try:
        result = workflow.run_cycle(
            body.project_id,
            use_memory=body.use_memory,
            idempotency_key=body.idempotency_key,
            force_sim_status=body.force_sim_status,
            plant_untrusted=body.plant_untrusted,
            simulate_tool_failure=body.simulate_tool_failure,
            skip_approval_gate=body.skip_approval_gate,
            deterministic=body.deterministic,
            runner_mode=body.runner_mode,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "result": result, "snapshot": _snapshot(body.project_id)}


@app.post("/api/resume")
def resume(
    project_id: str = Query(default="demo"),
    _: None = Depends(require_api_key),
) -> dict[str, Any]:
    try:
        result = workflow.resume_project(project_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "result": result, "snapshot": _snapshot(project_id)}


@app.post("/api/approve")
def approve(body: ApproveRequest, _: None = Depends(require_api_key)) -> dict[str, Any]:
    try:
        result = workflow.approve_decision(
            body.project_id,
            approved=body.approved,
            comment=body.comment,
            override_params=body.override_params,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "result": result, "snapshot": _snapshot(body.project_id)}


@app.post("/api/correct")
def correct(body: CorrectRequest, _: None = Depends(require_api_key)) -> dict[str, Any]:
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
