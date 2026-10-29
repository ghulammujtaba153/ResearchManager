"""Core agent workflow: tools → evidence → LLM decision → persistent writes."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from research_manager.agent.llm import (
    decide_next_action,
    enforce_deterministic_guards,
    _deterministic_decide,
)
from research_manager.memory import store
from research_manager.memory.db import init_db
from research_manager.memory.models import Decision, Experiment, Run
from research_manager.simulator.fake_runs import simulate_from_task
from research_manager.state import WorkingState
from research_manager.tools import evidence as tools

PROJECT_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_POLICY = {
    "read_only_tools": True,
    "allow_email": False,
    "max_cycles": 3,
    "untrusted_cannot_change_policy": True,
}


def _metric_from_facts(facts: dict[str, Any]) -> str:
    approved = facts.get("approved_metric", "accuracy")
    if isinstance(approved, dict):
        return str(approved.get("name", "accuracy"))
    return str(approved)


def _baseline_from_facts(facts: dict[str, Any]) -> dict[str, float]:
    baseline = facts.get("baseline_accuracy", 0.75)
    if isinstance(baseline, dict):
        return {str(k): float(v) for k, v in baseline.items()}
    return {"accuracy": float(baseline)}


def _hypothesis_for_action(action: str, base: str, params: dict[str, Any]) -> str:
    if action == "correct_metric_and_restart":
        return f"Correct metric to '{params.get('metric_name', 'accuracy')}' and retry."
    if action == "tune_params_and_restart":
        return f"Tune learning_rate to {params.get('learning_rate')} to beat approved baseline."
    if action == "restart_after_fixing_outputs":
        return "Restart after fixing missing experiment outputs."
    if action == "accept_and_stop":
        return base or "Accepted run meets approved baseline."
    if action == "reject_untrusted":
        return "Reject untrusted instructions; keep approved policy."
    if action == "mark_uncertain":
        return "Hold: conflicting or missing evidence — do not invent metrics."
    return base


def onboard_project(
    project_id: str,
    *,
    name: str | None = None,
    baseline_accuracy: float = 0.75,
    approved_metric: str = "accuracy",
    learning_rate: float = 0.1,
    db_path=None,
) -> dict[str, Any]:
    SessionLocal = init_db(db_path)
    with SessionLocal() as session:
        store.ensure_project(session, project_id, name=name or project_id)
        store.set_fact(
            session,
            project_id=project_id,
            fact_key="baseline_accuracy",
            value=baseline_accuracy,
            approved_by="supervisor",
            source_ref="onboarding",
        )
        store.set_fact(
            session,
            project_id=project_id,
            fact_key="approved_metric",
            value=approved_metric,
            approved_by="supervisor",
            source_ref="onboarding",
        )
        store.set_fact(
            session,
            project_id=project_id,
            fact_key="learning_rate",
            value=learning_rate,
            approved_by="supervisor",
            source_ref="onboarding",
        )
        store.set_fact(
            session,
            project_id=project_id,
            fact_key="review_policy",
            value=DEFAULT_POLICY,
            approved_by="onboarding",
            source_ref="onboarding",
        )
        exp = store.create_experiment(
            session,
            project_id=project_id,
            name=f"{project_id}_classifier",
            hypothesis="Improve accuracy over approved baseline via iterative runs.",
            params={"learning_rate": learning_rate, "epochs": 3, "metric_name": "acc"},
        )
        state = WorkingState(
            current_hypothesis=exp.hypothesis,
            max_cycles=int(DEFAULT_POLICY["max_cycles"]),
        )
        store.save_checkpoint(
            session,
            project_id=project_id,
            experiment_id=exp.id,
            state=state.model_dump(),
        )
        store.log_action(
            session,
            project_id=project_id,
            event_type="onboard",
            tool_name="onboard_project",
            output_data={"experiment_id": exp.id},
        )
        return {
            "project_id": project_id,
            "experiment_id": exp.id,
            "facts": store.get_current_facts(session, project_id),
        }


def _blocked_for_approval(session, project_id: str, exp: Experiment) -> dict[str, Any] | None:
    pending = store.latest_pending_decision(session, project_id)
    if pending is None:
        return None
    if pending.decision_type == "accept_and_stop":
        return None
    if exp.status in {"needs_review", "iterating", "approved_continue"}:
        # Block while iterating/needs_review with unconfirmed agent suggestion.
        # approved_continue means supervisor already approved — allow next cycle.
        if exp.status == "approved_continue":
            return None
        return {
            "ok": False,
            "error": "Approval required before next cycle",
            "blocked_for_approval": True,
            "pending_decision_id": pending.id,
            "pending_decision_type": pending.decision_type,
        }
    return None


def run_cycle(
    project_id: str,
    *,
    use_memory: bool = True,
    force_sim_status: str | None = None,
    plant_untrusted: bool = False,
    simulate_tool_failure: bool = False,
    idempotency_key: str | None = None,
    skip_approval_gate: bool = False,
    db_path=None,
) -> dict[str, Any]:
    """One interaction cycle with LLM-selected tools and approval gating."""
    SessionLocal = init_db(db_path)
    with SessionLocal() as session:
        store.ensure_project(session, project_id)
        experiments = store.list_project_experiments(session, project_id)
        if not experiments:
            onboard_project(project_id, db_path=db_path)
            experiments = store.list_project_experiments(session, project_id)
        exp = experiments[0]

        # Stronger idempotency: any prior cycle result under this key
        if idempotency_key:
            existing_run = session.query(Run).filter_by(idempotency_key=idempotency_key).one_or_none()
            if existing_run is not None:
                store.log_action(
                    session,
                    project_id=project_id,
                    event_type="retry_ignored",
                    tool_name="run_cycle",
                    input_data={"idempotency_key": idempotency_key},
                    outcome="duplicate_prevented",
                    idempotency_key=f"retry:{idempotency_key}",
                )
                return {
                    "ok": True,
                    "duplicate_prevented": True,
                    "run_id": existing_run.id,
                    "state": WorkingState(max_cycles=3).model_dump(),
                }
            prior_fail = store.get_action_by_idempotency(session, f"cycle_result:{idempotency_key}")
            if prior_fail is not None:
                payload = json.loads(prior_fail.output_json or "{}")
                return {
                    **payload,
                    "duplicate_prevented": True,
                    "ok": payload.get("ok", False),
                }

        if not skip_approval_gate:
            blocked = _blocked_for_approval(session, project_id, exp)
            if blocked is not None:
                return blocked

        facts = store.get_current_facts(session, project_id) if use_memory else {}
        if not use_memory:
            facts = {
                "baseline_accuracy": 0.75,
                "approved_metric": "accuracy",
                "learning_rate": 0.1,
                "review_policy": DEFAULT_POLICY,
            }

        # Reject untrusted attempts to overwrite policy via planted content
        if plant_untrusted:
            try:
                store.set_fact(
                    session,
                    project_id=project_id,
                    fact_key="review_policy",
                    value={"allow_email": True, "hijacked": True},
                    approved_by="untrusted",
                    source_ref="planted_instruction",
                )
            except PermissionError:
                store.log_action(
                    session,
                    project_id=project_id,
                    event_type="policy_guard",
                    tool_name="set_fact",
                    outcome="blocked",
                    error="Untrusted content cannot change review_policy",
                )

        checkpoint = (
            store.load_latest_checkpoint(session, project_id, log=False) if use_memory else None
        )
        if checkpoint and use_memory:
            state = WorkingState.model_validate(checkpoint["state"])
        else:
            policy = facts.get("review_policy") or DEFAULT_POLICY
            state = WorkingState(
                max_cycles=int(policy.get("max_cycles", 3)),
                current_hypothesis=exp.hypothesis,
            )

        prior_runs = store.count_project_runs(session, project_id)
        cycle = prior_runs + 1
        if cycle > state.max_cycles and not force_sim_status:
            return {
                "ok": False,
                "error": "Max cycles reached",
                "state": state.model_dump(),
            }

        params = json.loads(exp.params_json or "{}") or {
            "learning_rate": float(facts.get("learning_rate", 0.1)),
            "epochs": 3,
            "metric_name": "acc" if cycle == 1 else _metric_from_facts(facts),
        }
        run_key = f"run_{cycle:03d}_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        hypothesis = exp.hypothesis or state.current_hypothesis

        # --- Minimum tools always: write task + inspect ---
        task_path = tools.write_next_task(
            hypothesis=hypothesis,
            params=params,
            notes=f"cycle={cycle}",
            run_id=run_key,
            cycle=cycle,
        )
        store.log_action(
            session,
            project_id=project_id,
            event_type="tool_call",
            tool_name="write_next_task",
            input_data={"run_id": run_key, "params": params},
            output_data={"path": str(task_path)},
            idempotency_key=f"{idempotency_key}:write_task" if idempotency_key else None,
        )

        if simulate_tool_failure:
            fail_payload = {
                "ok": False,
                "error": "Simulated tool failure: filesystem timeout",
                "state_preserved": True,
                "state": state.model_dump(),
                "tools_executed": ["write_next_task"],
            }
            store.log_action(
                session,
                project_id=project_id,
                event_type="tool_call",
                tool_name="inspect_run",
                outcome="error",
                error="Simulated tool failure: filesystem timeout",
                idempotency_key=f"{idempotency_key}:fail" if idempotency_key else None,
            )
            if idempotency_key:
                store.log_action(
                    session,
                    project_id=project_id,
                    event_type="cycle_result",
                    tool_name="run_cycle",
                    outcome="error",
                    error=fail_payload["error"],
                    output_data=fail_payload,
                    idempotency_key=f"cycle_result:{idempotency_key}",
                )
            store.save_checkpoint(
                session,
                project_id=project_id,
                experiment_id=exp.id,
                state=state.model_dump(),
            )
            return fail_payload

        sim = simulate_from_task(
            force_status=force_sim_status,
            plant_untrusted=plant_untrusted,
        )
        folder = tools.inspect_run(run_key)
        store.log_action(
            session,
            project_id=project_id,
            event_type="tool_call",
            tool_name="inspect_run",
            input_data={"run_id": run_key},
            output_data=folder,
        )
        tools_executed = ["write_next_task", "inspect_run"]

        partial_evidence = {
            "run_id": run_key,
            "cycle": cycle,
            "params": params,
            "missing_outputs": folder.get("missing", []),
            "missing_columns": [],
            "metrics": {},
            "comparison": {},
            "success": False,
            "uncertain": False,
            "conflicting": force_sim_status == "conflicting",
            "untrusted_instruction_detected": folder.get("untrusted_instruction_detected"),
            "sim_status": sim.get("status"),
            "csv_parsed": False,
        }

        # LLM (or fallback) chooses follow-up tools + provisional action
        plan = decide_next_action(partial_evidence, facts if use_memory else {})
        store.log_action(
            session,
            project_id=project_id,
            event_type="llm_decision",
            tool_name="decide_next_action",
            input_data={
                "phase": "tool_selection",
                "evidence_keys": list(partial_evidence.keys()),
                "use_memory": use_memory,
            },
            output_data=plan,
        )

        selected = set(plan.get("tools_to_use") or [])
        required_metric = _metric_from_facts(facts)
        parsed: dict[str, Any] = {
            "ok": False,
            "metrics": {},
            "missing_columns": [],
            "uncertain": False,
            "untrusted_instruction_detected": False,
        }
        comparison: dict[str, Any] = {}

        if "read_run_csv" in selected:
            parsed = tools.read_run_csv(run_key, required_metric=required_metric)
            store.log_action(
                session,
                project_id=project_id,
                event_type="tool_call",
                tool_name="read_run_csv",
                input_data={"run_id": run_key, "required_metric": required_metric},
                output_data=parsed,
            )
            tools_executed.append("read_run_csv")

        baseline = _baseline_from_facts(facts)
        if "compare_to_baseline" in selected and parsed.get("ok"):
            comparison = tools.compare_to_baseline(parsed["metrics"], baseline)
            store.log_action(
                session,
                project_id=project_id,
                event_type="tool_call",
                tool_name="compare_to_baseline",
                input_data={"metrics": parsed["metrics"], "baseline": baseline},
                output_data=comparison,
            )
            tools_executed.append("compare_to_baseline")
        elif "compare_to_baseline" in selected and not parsed.get("ok"):
            store.log_action(
                session,
                project_id=project_id,
                event_type="tool_call",
                tool_name="compare_to_baseline",
                outcome="skipped",
                error="compare skipped: metrics unavailable",
                input_data={"selected": True},
            )

        full_evidence = {
            "run_id": run_key,
            "cycle": cycle,
            "params": params,
            "missing_outputs": folder.get("missing", []),
            "missing_columns": parsed.get("missing_columns", []),
            "metrics": parsed.get("metrics", {}),
            "comparison": comparison,
            "success": bool(
                parsed.get("ok")
                and comparison
                and all(v.get("beats_baseline") for v in comparison.values())
            ),
            "uncertain": bool(parsed.get("uncertain")),
            "conflicting": force_sim_status == "conflicting",
            "untrusted_instruction_detected": folder.get("untrusted_instruction_detected")
            or parsed.get("untrusted_instruction_detected"),
            "sim_status": sim.get("status"),
            "csv_parsed": "read_run_csv" in tools_executed,
        }

        # Final action from full evidence + guards (keeps LLM tool plan)
        safe = _deterministic_decide(full_evidence, facts if use_memory else {})
        decision = enforce_deterministic_guards(plan, full_evidence, facts if use_memory else {})
        decision["action"] = safe["action"]
        decision["params_updates"] = safe.get("params_updates") or plan.get("params_updates") or {}
        decision["tools_to_use"] = plan.get("tools_to_use") or safe.get("tools_to_use")
        decision["tools_executed"] = tools_executed
        decision["rationale"] = safe.get("rationale") or decision.get("rationale")
        decision["llm_used"] = plan.get("llm_used", False)
        decision["latency_ms"] = plan.get("latency_ms")
        decision["model"] = plan.get("model")

        store.log_action(
            session,
            project_id=project_id,
            event_type="llm_decision",
            tool_name="finalize_action",
            input_data={"tools_executed": tools_executed},
            output_data=decision,
        )

        new_params = {**params, **(decision.get("params_updates") or {})}
        hypothesis = _hypothesis_for_action(
            decision.get("action", ""),
            hypothesis,
            new_params,
        )

        state.cycle_count = cycle
        state.active_run_id = run_key
        state.current_hypothesis = hypothesis
        state.missing_outputs = full_evidence["missing_outputs"]
        state.run_comparison = comparison
        state.last_failure_reason = decision.get("rationale")
        state.last_decision = decision.get("action")
        state.messages.append(f"[tools_selected] {decision.get('tools_to_use')}")
        state.messages.append(f"[tools_executed] {tools_executed}")
        state.messages.append(f"[decision] {decision.get('action')}: {decision.get('rationale')}")
        state.done = decision.get("action") == "accept_and_stop"

        run = store.log_run(
            session,
            project_id=project_id,
            experiment_id=exp.id,
            run_key=run_key,
            metrics=parsed.get("metrics", {}),
            artifacts_path=str(PROJECT_ROOT / "experiments" / run_key),
            success=bool(full_evidence["success"]),
            notes=decision.get("rationale", ""),
            idempotency_key=idempotency_key,
        )
        # Accept can auto-confirm; other actions need supervisor approval
        auto_confirm = decision.get("action") == "accept_and_stop"
        store.log_decision(
            session,
            project_id=project_id,
            run_id=run.id,
            decision_type=decision.get("action", "unknown"),
            rationale=decision.get("rationale", ""),
            next_params=new_params,
            agent_suggested=True,
            supervisor_confirmed=True if auto_confirm else None,
            supervisor_comment="auto-accepted" if auto_confirm else "",
        )

        exp.params_json = json.dumps(new_params)
        exp.hypothesis = hypothesis
        if state.done:
            exp.status = "completed"
        elif decision.get("action") in {"mark_uncertain", "reject_untrusted"}:
            exp.status = "needs_review"
        else:
            exp.status = "iterating"
        session.commit()

        # Do NOT promote agent param tweaks into long-term facts here.
        # Supervisor approve_decision promotes pending params.

        store.save_checkpoint(
            session,
            project_id=project_id,
            experiment_id=exp.id,
            state=state.model_dump(),
        )

        result = {
            "ok": True,
            "duplicate_prevented": False,
            "project_id": project_id,
            "experiment_id": exp.id,
            "run_key": run_key,
            "evidence": full_evidence,
            "decision": decision,
            "tools_executed": tools_executed,
            "state": state.model_dump(),
            "sim": sim,
            "llm_used": decision.get("llm_used", False),
        }
        if idempotency_key:
            store.log_action(
                session,
                project_id=project_id,
                event_type="cycle_result",
                tool_name="run_cycle",
                outcome="ok",
                output_data={k: v for k, v in result.items() if k != "sim"},
                idempotency_key=f"cycle_result:{idempotency_key}",
            )
        return result


def run_demo(project_id: str = "demo", max_cycles: int = 3, db_path=None) -> WorkingState:
    onboard_project(project_id, db_path=db_path)
    state = WorkingState(max_cycles=max_cycles)
    for _ in range(max_cycles):
        result = run_cycle(project_id, skip_approval_gate=True, db_path=db_path)
        if not result.get("ok"):
            break
        # Auto-approve between demo cycles so the story can continue
        if not result.get("state", {}).get("done"):
            try:
                approve_decision(project_id, approved=True, comment="demo auto-approve", db_path=db_path)
            except RuntimeError:
                pass
        state = WorkingState.model_validate(result["state"])
        if state.done:
            break
    return state


def resume_project(project_id: str, db_path=None) -> dict[str, Any]:
    """Full process restart support: load checkpoint + facts without re-onboarding."""
    SessionLocal = init_db(db_path)
    with SessionLocal() as session:
        cp = store.load_latest_checkpoint(session, project_id, log=True)
        facts = store.get_current_facts(session, project_id)
        experiments = store.list_project_experiments(session, project_id)
        if cp is None and not experiments:
            raise RuntimeError(f"No saved state for project {project_id}")
        return {
            "project_id": project_id,
            "checkpoint": cp,
            "facts": facts,
            "fact_history": store.list_fact_history(session, project_id),
            "experiments": [
                {
                    "id": e.id,
                    "name": e.name,
                    "status": e.status,
                    "hypothesis": e.hypothesis,
                    "params": json.loads(e.params_json or "{}"),
                }
                for e in experiments
            ],
        }


def correct_fact(
    project_id: str,
    fact_key: str,
    value: Any,
    *,
    approved_by: str = "supervisor",
    db_path=None,
) -> dict[str, Any]:
    SessionLocal = init_db(db_path)
    with SessionLocal() as session:
        row = store.set_fact(
            session,
            project_id=project_id,
            fact_key=fact_key,
            value=value,
            approved_by=approved_by,
            source_ref="supervisor_correction",
        )
        return {
            "fact_key": fact_key,
            "version": row.version,
            "value": value,
            "is_current": row.is_current,
            "facts": store.get_current_facts(session, project_id),
            "fact_history": store.list_fact_history(session, project_id, fact_key),
        }


def approve_decision(
    project_id: str,
    *,
    approved: bool,
    comment: str = "",
    db_path=None,
) -> dict[str, Any]:
    SessionLocal = init_db(db_path)
    with SessionLocal() as session:
        decision = (
            session.query(Decision)
            .filter_by(project_id=project_id)
            .order_by(Decision.id.desc())
            .first()
        )
        if decision is None:
            raise RuntimeError("No decision to approve")
        decision.supervisor_confirmed = approved
        decision.supervisor_comment = comment
        decision.agent_suggested = True
        exp = (
            session.query(Experiment)
            .filter_by(project_id=project_id)
            .order_by(Experiment.id.desc())
            .first()
        )
        promoted: dict[str, Any] = {}
        if exp is not None:
            exp.status = "approved_continue" if approved else "needs_review"
            if approved:
                pending_params = json.loads(decision.next_params_json or "{}")
                # Promote only supervisor-approved long-term facts
                if "learning_rate" in pending_params:
                    store.set_fact(
                        session,
                        project_id=project_id,
                        fact_key="learning_rate",
                        value=pending_params["learning_rate"],
                        approved_by="supervisor",
                        source_ref=f"approve_decision:{decision.id}",
                    )
                    promoted["learning_rate"] = pending_params["learning_rate"]
                if "metric_name" in pending_params:
                    store.set_fact(
                        session,
                        project_id=project_id,
                        fact_key="approved_metric",
                        value=pending_params["metric_name"],
                        approved_by="supervisor",
                        source_ref=f"approve_decision:{decision.id}",
                    )
                    promoted["approved_metric"] = pending_params["metric_name"]
        session.commit()
        store.log_action(
            session,
            project_id=project_id,
            event_type="supervisor_approval",
            tool_name="approve_decision",
            input_data={"approved": approved, "comment": comment, "promoted": promoted},
            outcome="ok",
        )
        return {
            "decision_id": decision.id,
            "approved": approved,
            "promoted_facts": promoted,
        }
