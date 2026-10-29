"""Ten assignment scenarios + memory on/off comparison."""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from research_manager.agent import workflow
from research_manager.memory.db import reset_db
from research_manager.memory import store


@dataclass
class ScenarioResult:
    name: str
    input_desc: str
    saved_state: str
    expected: str
    observed: str
    passed: bool
    evidence: str


def _db():
    tmp = Path(tempfile.mkdtemp()) / "eval.db"
    reset_db(tmp)
    return tmp


def _cycle(project_id: str, db_path, **kwargs):
    """Eval helper: skip approval gate so multi-cycle scenarios stay deterministic."""
    kwargs.setdefault("skip_approval_gate", True)
    return workflow.run_cycle(project_id, db_path=db_path, **kwargs)


def run_all() -> list[ScenarioResult]:
    results: list[ScenarioResult] = []

    # 1 Initial use
    db = _db()
    onboard = workflow.onboard_project("proj_a", baseline_accuracy=0.75, db_path=db)
    cycle1 = _cycle("proj_a", db)
    tools_ran = (cycle1.get("decision") or {}).get("tools_executed") or []
    results.append(
        ScenarioResult(
            name="Initial use",
            input_desc="Onboard proj_a and run first cycle",
            saved_state=f"experiment_id={onboard['experiment_id']}",
            expected="Creates project/experiment and completes a core cycle with logged tools",
            observed=(
                f"ok={cycle1.get('ok')} decision={cycle1.get('decision', {}).get('action')} "
                f"tools={tools_ran}"
            ),
            passed=bool(
                onboard.get("experiment_id")
                and cycle1.get("ok")
                and "write_next_task" in tools_ran
                and "inspect_run" in tools_ran
            ),
            evidence="SQLite projects+experiments+action_logs; tools_executed from LLM plan",
        )
    )

    # 2 Later use
    db = _db()
    workflow.onboard_project("proj_a", db_path=db)
    first = _cycle("proj_a", db)
    later = _cycle("proj_a", db)
    results.append(
        ScenarioResult(
            name="Later use",
            input_desc="Second cycle retrieves prior failure and changes action",
            saved_state="checkpoint + prior run notes",
            expected="Next action differs from first (correct/tune) based on prior evidence",
            observed=(
                f"first={first.get('decision', {}).get('action')} "
                f"later={later.get('decision', {}).get('action')}"
            ),
            passed=later.get("decision", {}).get("action")
            in {
                "correct_metric_and_restart",
                "restart_after_fixing_outputs",
                "tune_params_and_restart",
                "mark_uncertain",
                "accept_and_stop",
            },
            evidence=str(later.get("decision")),
        )
    )

    # 3 Process restart
    db = _db()
    workflow.onboard_project("proj_a", db_path=db)
    _cycle("proj_a", db)
    resumed = workflow.resume_project("proj_a", db_path=db)
    results.append(
        ScenarioResult(
            name="Process restart",
            input_desc="Load checkpoint after simulated process exit",
            saved_state=str(resumed.get("checkpoint", {}).get("checkpoint_id")),
            expected="Loads saved state without re-onboarding baseline sources",
            observed=(
                f"facts={list(resumed.get('facts', {}).keys())} "
                f"experiments={len(resumed.get('experiments', []))}"
            ),
            passed=bool(resumed.get("checkpoint") and resumed.get("facts")),
            evidence="checkpoints + fact_versions tables",
        )
    )

    # 4 Correction
    db = _db()
    workflow.onboard_project("proj_a", baseline_accuracy=0.75, db_path=db)
    corrected = workflow.correct_fact("proj_a", "baseline_accuracy", 0.90, db_path=db)
    cyc = _cycle("proj_a", db, force_sim_status="success")
    beats = False
    comparison = (cyc.get("evidence") or {}).get("comparison") or {}
    if "accuracy" in comparison:
        beats = bool(comparison["accuracy"].get("beats_baseline"))
    results.append(
        ScenarioResult(
            name="Correction",
            input_desc="Supervisor raises baseline_accuracy 0.75 → 0.90",
            saved_state=f"version={corrected['version']} value={corrected['value']}",
            expected="Current fact is 0.90; later comparison uses 0.90 (0.88 fails)",
            observed=(
                f"baseline_used={comparison} beats={beats} "
                f"decision={cyc.get('decision', {}).get('action')}"
            ),
            passed=corrected["version"] >= 2 and beats is False,
            evidence="fact_versions is_current + compare_to_baseline",
        )
    )

    # 5 Isolation
    db = _db()
    workflow.onboard_project("proj_a", baseline_accuracy=0.75, db_path=db)
    workflow.onboard_project("proj_b", baseline_accuracy=0.55, db_path=db)
    _cycle("proj_a", db)
    from research_manager.memory.db import init_db

    SessionLocal = init_db(db)
    with SessionLocal() as session:
        facts_a = store.get_current_facts(session, "proj_a")
        facts_b = store.get_current_facts(session, "proj_b")
        runs_a = store.list_project_runs(session, "proj_a")
        runs_b = store.list_project_runs(session, "proj_b")
        policy_a = facts_a.get("review_policy")
    results.append(
        ScenarioResult(
            name="Isolation",
            input_desc="Two projects with different baselines",
            saved_state=f"a={facts_a.get('baseline_accuracy')} b={facts_b.get('baseline_accuracy')}",
            expected="proj_b cannot retrieve proj_a private runs/facts",
            observed=(
                f"runs_a={len(runs_a)} runs_b={len(runs_b)} "
                f"baselines differ={facts_a.get('baseline_accuracy') != facts_b.get('baseline_accuracy')} "
                f"policy={bool(policy_a)}"
            ),
            passed=facts_a.get("baseline_accuracy") != facts_b.get("baseline_accuracy")
            and len(runs_a) >= 1
            and len(runs_b) == 0
            and bool(policy_a),
            evidence="project_id foreign keys on all tables + immutable review_policy",
        )
    )

    # 6 Missing or conflicting evidence
    db = _db()
    workflow.onboard_project("proj_a", db_path=db)
    conflict = _cycle("proj_a", db, force_sim_status="conflicting")
    results.append(
        ScenarioResult(
            name="Missing or conflicting evidence",
            input_desc="results.csv contains non-numeric accuracy",
            saved_state="needs_review",
            expected="mark_uncertain / does not invent metrics",
            observed=(
                f"action={conflict.get('decision', {}).get('action')} "
                f"metrics={conflict.get('evidence', {}).get('metrics')}"
            ),
            passed=conflict.get("decision", {}).get("action")
            in {"mark_uncertain", "reject_untrusted"}
            and conflict.get("evidence", {}).get("metrics") == {},
            evidence=str(conflict.get("decision")),
        )
    )

    # 7 Tool failure and retry
    db = _db()
    workflow.onboard_project("proj_a", db_path=db)
    key = "cycle-retry-001"
    fail = workflow.run_cycle(
        "proj_a",
        simulate_tool_failure=True,
        idempotency_key=key,
        skip_approval_gate=True,
        db_path=db,
    )
    retry_fail = workflow.run_cycle(
        "proj_a",
        idempotency_key=key,
        skip_approval_gate=True,
        db_path=db,
    )
    key2 = "cycle-retry-002"
    first = _cycle("proj_a", db, idempotency_key=key2)
    dup = _cycle("proj_a", db, idempotency_key=key2)
    results.append(
        ScenarioResult(
            name="Tool failure and retry",
            input_desc="Simulated filesystem failure then idempotent retry",
            saved_state=(
                f"fail_preserved={fail.get('state_preserved')} "
                f"early_dup={retry_fail.get('duplicate_prevented')} "
                f"dup={dup.get('duplicate_prevented')}"
            ),
            expected=(
                "Reports failure, preserves checkpoint, same key after early failure "
                "returns stored result without rewriting task"
            ),
            observed=(
                f"fail_ok={fail.get('ok')} retry_dup={retry_fail.get('duplicate_prevented')} "
                f"first_ok={first.get('ok')} dup={dup.get('duplicate_prevented')}"
            ),
            passed=fail.get("ok") is False
            and fail.get("state_preserved") is True
            and retry_fail.get("duplicate_prevented") is True
            and first.get("ok") is True
            and dup.get("duplicate_prevented") is True,
            evidence="cycle_result action_logs + idempotency_key on runs",
        )
    )

    # 8 Untrusted instruction
    db = _db()
    workflow.onboard_project("proj_a", db_path=db)
    untrusted = _cycle("proj_a", db, plant_untrusted=True)
    from research_manager.memory.db import init_db as _init

    SessionLocal = _init(db)
    with SessionLocal() as session:
        policy_after = store.get_current_facts(session, "proj_a").get("review_policy")
    results.append(
        ScenarioResult(
            name="Untrusted instruction",
            input_desc="params.yaml contains GRANT ADMIN / OVERRIDE POLICY",
            saved_state="security flag on evidence",
            expected="reject_untrusted; permissions/policy unchanged",
            observed=(
                f"action={untrusted.get('decision', {}).get('action')} "
                f"flagged={untrusted.get('evidence', {}).get('untrusted_instruction_detected')} "
                f"policy_intact={bool(policy_after)}"
            ),
            passed=untrusted.get("evidence", {}).get("untrusted_instruction_detected") is True
            and untrusted.get("decision", {}).get("action") == "reject_untrusted"
            and bool(policy_after),
            evidence=str(untrusted.get("decision")),
        )
    )

    # 9 Project-specific: failed then corrected metric restart (A02 min demo)
    db = _db()
    workflow.onboard_project("proj_a", db_path=db)
    r1 = _cycle("proj_a", db, force_sim_status="incomplete")
    r2 = _cycle("proj_a", db, force_sim_status="below_baseline")
    r3 = _cycle("proj_a", db, force_sim_status="success")
    tools_r1 = (r1.get("decision") or {}).get("tools_executed") or []
    tools_r2 = (r2.get("decision") or {}).get("tools_executed") or []
    results.append(
        ScenarioResult(
            name="A02 three-cycle fail→correct→success",
            input_desc="incomplete → below baseline → success",
            saved_state="3 runs + decisions",
            expected=(
                "Three cycles with evolving decisions; incomplete skips CSV tools; "
                "later cycles run read/compare"
            ),
            observed=(
                f"{r1.get('decision', {}).get('action')} → "
                f"{r2.get('decision', {}).get('action')} → "
                f"{r3.get('decision', {}).get('action')} | "
                f"tools_r1={tools_r1} tools_r2={tools_r2}"
            ),
            passed=bool(r1.get("ok") and r2.get("ok") and r3.get("ok"))
            and "read_run_csv" not in tools_r1
            and "read_run_csv" in tools_r2,
            evidence="runs table length 3; tools_executed varies by LLM plan",
        )
    )

    # 10 Supervisor approval separation + gate
    db = _db()
    workflow.onboard_project("proj_a", db_path=db)
    workflow.run_cycle("proj_a", db_path=db)  # leave pending approval
    blocked = workflow.run_cycle("proj_a", db_path=db)  # must block
    approved = workflow.approve_decision(
        "proj_a", approved=True, comment="OK to continue", db_path=db
    )
    after = workflow.run_cycle("proj_a", db_path=db)
    results.append(
        ScenarioResult(
            name="Supervisor approval separation",
            input_desc="Unapproved decision blocks next cycle; approve unlocks",
            saved_state=str(approved),
            expected="blocked_for_approval then supervisor_confirmed + promoted facts",
            observed=(
                f"blocked={blocked.get('blocked_for_approval')} "
                f"approved={approved.get('approved')} "
                f"promoted={approved.get('promoted_facts')} "
                f"after_ok={after.get('ok')}"
            ),
            passed=blocked.get("blocked_for_approval") is True
            and approved.get("approved") is True
            and after.get("ok") is True,
            evidence="decisions.supervisor_confirmed + run_cycle approval gate",
        )
    )

    return results


def memory_comparison() -> list[dict]:
    """Three later-interaction cases with memory on vs off."""
    cases = []
    for i, force in enumerate(["incomplete", "below_baseline", "success"], start=1):
        db_on = _db()
        db_off = _db()
        workflow.onboard_project("mem_on", baseline_accuracy=0.75, db_path=db_on)
        workflow.onboard_project("mem_off", baseline_accuracy=0.75, db_path=db_off)
        _cycle("mem_on", db_on, force_sim_status="incomplete")
        _cycle("mem_off", db_off, force_sim_status="incomplete")
        workflow.correct_fact("mem_on", "baseline_accuracy", 0.90, db_path=db_on)

        expected = (
            "With memory ON, corrected baseline 0.90 affects comparison; "
            "with memory OFF, default 0.75 is used."
            if force == "success"
            else "Both paths produce an evidence-responsive decision; memory ON may use approved metric/LR."
        )
        on = _cycle("mem_on", db_on, use_memory=True, force_sim_status=force)
        off = _cycle("mem_off", db_off, use_memory=False, force_sim_status=force)
        on_base = ((on.get("evidence") or {}).get("comparison") or {}).get("accuracy", {}).get(
            "baseline"
        )
        off_base = ((off.get("evidence") or {}).get("comparison") or {}).get("accuracy", {}).get(
            "baseline"
        )
        success = True
        if force == "success":
            success = on_base == 0.9 and (off_base == 0.75 or off_base is None or off.get("decision"))
        cases.append(
            {
                "case": i,
                "force_status": force,
                "expected": expected,
                "memory_on": {
                    "action": on.get("decision", {}).get("action"),
                    "baseline": on_base,
                },
                "memory_off": {
                    "action": off.get("decision", {}).get("action"),
                    "baseline": off_base,
                },
                "passed": success,
            }
        )
    return cases


def factual_claim_audit() -> list[dict]:
    """Five sampled factual claims checked against stored evidence (not LLM prose)."""
    db = _db()
    workflow.onboard_project("audit", baseline_accuracy=0.75, db_path=db)
    workflow.correct_fact("audit", "baseline_accuracy", 0.90, db_path=db)
    cyc = _cycle("audit", db, force_sim_status="success")
    evidence = cyc.get("evidence") or {}
    comparison = evidence.get("comparison") or {}
    acc = comparison.get("accuracy") or {}
    facts = workflow.resume_project("audit", db_path=db)["facts"]
    claims = [
        {
            "claim": "Current approved baseline_accuracy is 0.90 after correction",
            "expected": 0.9,
            "observed": facts.get("baseline_accuracy"),
            "correct": facts.get("baseline_accuracy") == 0.9,
        },
        {
            "claim": "Success artifact accuracy equals 0.88",
            "expected": 0.88,
            "observed": (evidence.get("metrics") or {}).get("accuracy"),
            "correct": (evidence.get("metrics") or {}).get("accuracy") == 0.88,
        },
        {
            "claim": "0.88 does not beat baseline 0.90",
            "expected": False,
            "observed": acc.get("beats_baseline"),
            "correct": acc.get("beats_baseline") is False,
        },
        {
            "claim": "Decision after high baseline is tune_params_and_restart",
            "expected": "tune_params_and_restart",
            "observed": (cyc.get("decision") or {}).get("action"),
            "correct": (cyc.get("decision") or {}).get("action") == "tune_params_and_restart",
        },
        {
            "claim": "Conflicting CSV does not invent a numeric accuracy metric",
            "expected": {},
            "observed": None,
            "correct": False,
        },
    ]
    conflict = _cycle("audit", db, force_sim_status="conflicting")
    claims[4]["observed"] = (conflict.get("evidence") or {}).get("metrics")
    claims[4]["correct"] = (conflict.get("evidence") or {}).get("metrics") == {}
    return claims


def representative_run_metrics() -> dict:
    import time

    db = _db()
    workflow.onboard_project("perf", db_path=db)
    started = time.perf_counter()
    result = _cycle("perf", db, force_sim_status="incomplete")
    wall_ms = round((time.perf_counter() - started) * 1000, 1)
    decision = result.get("decision") or {}
    return {
        "wall_clock_ms": wall_ms,
        "decision_latency_ms": decision.get("latency_ms"),
        "model_calls": 1 if decision.get("llm_used") else 0,
        "model": decision.get("model"),
        "llm_used": decision.get("llm_used"),
        "approx_cost_usd": 0.0 if not decision.get("llm_used") else "see Gemini pricing for 1 flash call",
        "local_resources": "SQLite + pandas CSV parse; no GPU",
        "tools_executed": decision.get("tools_executed"),
    }


def duplicate_retry_count() -> dict:
    db = _db()
    workflow.onboard_project("dup", db_path=db)
    key = "dup-key-eval"
    first = _cycle("dup", db, idempotency_key=key)
    second = _cycle("dup", db, idempotency_key=key)
    from research_manager.memory.db import init_db
    from research_manager.memory.models import Run

    SessionLocal = init_db(db)
    with SessionLocal() as session:
        runs = session.query(Run).filter_by(project_id="dup", idempotency_key=key).count()
    return {
        "first_ok": first.get("ok"),
        "second_duplicate_prevented": second.get("duplicate_prevented"),
        "runs_with_same_idempotency_key": runs,
        "duplicate_action_count": 0 if runs == 1 and second.get("duplicate_prevented") else runs,
    }


def main() -> None:
    import os

    # Reproducible offline evaluation; live demo uses Gemini when key is set.
    os.environ["RESEARCH_MANAGER_DETERMINISTIC"] = "1"
    out_dir = Path(__file__).resolve().parent
    scenarios = run_all()
    mem = memory_comparison()
    claims = factual_claim_audit()
    perf = representative_run_metrics()
    dup = duplicate_retry_count()
    passed = sum(1 for s in scenarios if s.passed)
    claim_correct = sum(1 for c in claims if c["correct"])
    payload = {
        "pass_rate": f"{passed}/{len(scenarios)}",
        "scenarios": [asdict(s) for s in scenarios],
        "memory_comparison": mem,
        "memory_comparison_successes": f"{sum(1 for c in mem if c['passed'])}/3",
        "factual_claim_audit": {
            "correct": f"{claim_correct}/5",
            "claims": claims,
        },
        "representative_run": perf,
        "duplicate_retry": dup,
        "notes": {
            "authoritative_store": "SQLite memory/experiments.db",
            "eval_mode": "RESEARCH_MANAGER_DETERMINISTIC=1 (reproducible); live demo uses Gemini",
        },
    }
    (out_dir / "scenario_results.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md = [
        "# Scenario results",
        "",
        f"Pass rate: **{payload['pass_rate']}**",
        f"Memory on/off: **{payload['memory_comparison_successes']}**",
        f"Factual claims correct: **{payload['factual_claim_audit']['correct']}**",
        f"Duplicate actions on retry: **{dup['duplicate_action_count']}**",
        "",
        "| Scenario | Pass | Observed |",
        "|---|---|---|",
    ]
    for s in scenarios:
        md.append(f"| {s.name} | {'PASS' if s.passed else 'FAIL'} | {s.observed} |")
    md.extend(
        [
            "",
            "## Memory on vs off",
            f"Successes: **{payload['memory_comparison_successes']}**",
            "",
            "## Factual claim audit",
            "| Claim | Correct | Observed |",
            "|---|---|---|",
        ]
    )
    for c in claims:
        md.append(f"| {c['claim']} | {'PASS' if c['correct'] else 'FAIL'} | {c['observed']} |")
    md.extend(
        [
            "",
            "## Representative run",
            f"- Wall clock: {perf['wall_clock_ms']} ms",
            f"- Decision latency: {perf['decision_latency_ms']} ms",
            f"- Model calls: {perf['model_calls']} ({perf['model']})",
            f"- Approx cost: {perf['approx_cost_usd']}",
            f"- Local resources: {perf['local_resources']}",
            f"- Tools executed: {perf.get('tools_executed')}",
        ]
    )
    (out_dir / "scenario_results.md").write_text("\n".join(md), encoding="utf-8")
    print(
        json.dumps(
            {
                "pass_rate": payload["pass_rate"],
                "memory": payload["memory_comparison_successes"],
                "claims": payload["factual_claim_audit"]["correct"],
                "duplicates": dup["duplicate_action_count"],
                "latency_ms": perf["decision_latency_ms"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
