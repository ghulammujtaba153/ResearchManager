# Research Experiment Manager — Technical Report

**Project ID:** A02 · Agentic AI assignment  
**System:** Research Experiment Manager  
**Authoritative store:** SQLite (`memory/experiments.db`)  
**Interfaces:** React UI (`app/`), FastAPI (`/api/*`), CLI (`python -m research_manager`)

---

## 1. Problem and scope

Experimental research is a recurring loop: plan a run, inspect result folders and CSVs, diagnose incomplete or weak runs, then choose the next parameters. Manual tracking loses failure history, approved baselines drift, and restarts force re-explaining context.

**Goal.** Build an agentic assistant that:

1. Onboards a project with approved baseline facts.
2. Runs multi-cycle plan → evidence → decision loops.
3. Persists working and long-term memory across process restarts.
4. Supports supervisor correction and approval without inventing missing evidence.

**In scope.** Local experiment folders, CSV metrics, task YAML writes, SQLite registry, Gemini decisions (with deterministic fallback), React/CLI control surfaces, 10-scenario evaluation.

**Out of scope (extensions).** Live model training, MLflow production tracking, multi-user auth, mobile clients.

**Acceptance criteria.** ≥3 tools (retrieve + persist), evidence-responsive next-action decision, ≥3 cycles with restart, versioned fact correction, usable UI showing state/next action/evidence/approval, audited logs with idempotent retries.

---

## 2. Architecture

A **single coordinator** owns the loop (`src/research_manager/agent/workflow.py`). Planner and analyst roles are logical stages, not separate incompatible memories; all share `project_id` and approved facts.

```
UI / CLI
   │
   ▼
FastAPI (api.py)
   │
   ▼
Workflow coordinator
   ├─ Memory store (facts, checkpoints, action log)
   ├─ Tools (inspect_run, read_run_csv, write_next_task, compare)
   ├─ Simulator (demo artifacts) / real folders
   └─ Decision (Gemini or deterministic fallback)
   │
   ▼
SQLite + experiments/ + tasks/
```

**Why this shape.** The catalogue idea needs tight coupling between evidence tools and durable records. A multi-agent split would add handoff risk without changing the core acceptance tests. Tool calculations (metrics, baseline deltas, permissions) stay in deterministic code; the model only selects the next action and tool emphasis.

---

## 3. Decision loop

Each cycle:

1. **Retrieve** current approved facts + latest checkpoint (if memory enabled). Block if a prior agent decision still needs supervisor approval.
2. **Write** `tasks/next_experiment.yaml` and **inspect** the run folder (minimum local evidence).
3. **LLM tool selection:** `decide_next_action` returns `tools_to_use` among `{read_run_csv, compare_to_baseline}`; only those selected tools run.
4. **Finalize action** from full evidence with deterministic guards (untrusted / missing / conflicting override unsafe LLM actions). Hypothesis text updates on tune/correct actions.
5. **Persist** run, decision, action log, checkpoint. Param tweaks stay on the experiment until supervisor approve promotes long-term facts.

### Action vocabulary

| Action | Meaning |
|---|---|
| `restart_after_fixing_outputs` | Incomplete folder / missing `results.csv` |
| `correct_metric_and_restart` | Wrong/missing metric column vs approved metric |
| `tune_params_and_restart` | Metric present but below approved baseline |
| `accept_and_stop` | Beats baseline |
| `mark_uncertain` | Conflicting/unreadable evidence — do not invent |
| `reject_untrusted` | Planted instruction in source ignored |

Deterministic code validates numbers, redacts untrusted markers, and performs stable record updates. The LLM must not invent metrics when files are missing.

---

## 4. Tools

| Tool | Type | Role |
|---|---|---|
| `inspect_run` | Local evidence read | Lists present/missing artifacts; flags untrusted text |
| `read_run_csv` | Local evidence read | Parses required metric; marks uncertain on bad values |
| `write_next_task` | Persistent controlled write | Writes next experiment task YAML |
| `compare_to_baseline` | Deterministic calc | Delta vs approved baseline (not LLM math) |

Splitting wrappers of the same operation was avoided; each tool has a distinct side effect or evidence type.

**Integration rule.** One real end-to-end read (filesystem CSV/folder) and one real persistent write (task YAML + SQLite) are provided. API keys stay in `.env` (not committed).

---

## 5. Memory lifecycle

See also `docs/MEMORY_LIFECYCLE.md`.

### Working state

Bounded `WorkingState` (hypothesis, active run, comparison, missing outputs, cycle count, last decision). Persisted as **checkpoints** after each cycle (last 20 kept per project). UI snapshot loads use quiet checkpoint reads (`log=False`); explicit resume logs `memory_read`.

### Long-term memory

Versioned **facts** (`baseline_accuracy`, `approved_metric`, `learning_rate`, immutable `review_policy`). Agent param tweaks do **not** become current facts until `approve_decision` promotes them with `approved_by=supervisor`. Corrections call `set_fact`, which marks the prior row `is_current=false` and keeps history (`GET /api/facts`, UI Fact history tab). Later cycles read only current **approved** facts.

### Source knowledge

Experiment folders and CSVs support retrieval. They do **not** alone prove the agent remembers decisions; decisions and logs in SQLite do.

### Isolation and authority

- Stable `project_id` on projects, experiments, runs, decisions, facts, logs, checkpoints.
- SQLite is authoritative. Any spreadsheet/CSV export is a review view and must not overwrite supervisor fields.
- Agent-suggested decisions are stored separately from `supervisor_confirmed` / comments.

---

## 6. Reliability and controls

- **Action log:** tool calls, memory reads/writes, LLM decisions (`tools_to_use` / `tools_executed`), errors, timestamps.
- **Idempotency keys** on runs and `cycle_result:{key}` logs: retries after mid-cycle failure return the stored outcome without rewriting the task file.
- **Tool failure path:** simulated filesystem failure preserves checkpoint and returns an error without inventing success.
- **Untrusted content:** markers such as `GRANT ADMIN` / `OVERRIDE POLICY` in YAML/CSV are flagged; action `reject_untrusted` leaves permissions unchanged. Planted text cannot mutate immutable `review_policy`.
- **Approvals:** unapproved `needs_review` / `iterating` decisions **block** the next `run_cycle` until approve/reject (UI banner + API). Eval/demo may pass `skip_approval_gate` or auto-approve between cycles.

---

## 7. Evaluation

Harness: `evaluation/run_scenarios.py`  
Artifacts: `evaluation/scenario_results.json`, `evaluation/scenario_results.md`

### Compulsory scenarios (8) + A02-specific (2)

| # | Scenario | Result (latest harness) |
|---|---|---|
| 1 | Initial use | PASS |
| 2 | Later use | PASS |
| 3 | Process restart | PASS |
| 4 | Correction | PASS |
| 5 | Isolation | PASS |
| 6 | Missing/conflicting evidence | PASS |
| 7 | Tool failure and retry | PASS |
| 8 | Untrusted instruction | PASS |
| 9 | A02 three-cycle fail→tune→success | PASS |
| 10 | Supervisor approval separation | PASS |

**Pass rate:** 10/10  

**Memory on vs off:** 3/3 (corrected baseline affects comparison only when memory retrieval is enabled).

Offline harness sets `RESEARCH_MANAGER_DETERMINISTIC=1` for reproducible CI-style runs. Live demonstration uses Gemini with the same tools and schema; `llm_used` is logged per decision.

### Metrics appendix (representative)

See generated `evaluation/scenario_results.json` fields:

- evidence correctness for five sampled factual claims
- duplicate action count in retry tests
- approximate model calls, latency, and local resource notes for one representative cycle

---

## 8. Usability and demonstration

**UI** shows current state, recommended next action, supporting evidence, approval gate banner, correction, resume, action log / runs / decisions / **fact history** tabs, and LLM tool chips (`tools_to_use` vs `tools_executed`).  
**API** also exposes `GET /api/facts?project_id=` (current + history).  
**CLI** mirrors onboard / cycle / resume / correct / demo.  
**Demo script (8–10 min):** see `docs/DEMO_SCRIPT.md` — onboard → cycle → gate → resume → correct → approve → later cycle → inspect log / fact history.

---

## 9. Limitations

1. Training is **simulated** (artifact dropper) so demos stay reproducible without GPUs.
2. If Gemini is unavailable, evidence-responsive **deterministic fallback** still selects actions; viva should show at least one live LLM decision when the key works.
3. Source knowledge is local folders, not remote GitHub/PDF pipelines (optional for other catalogue ideas).
4. MLflow tracking is an optional extension, not required for the minimum mark.

---

## 10. Implementation decisions

| Decision | Rationale |
|---|---|
| SQLite over vector DB | Structured facts, deadlines-like baselines, and action history fit relational rows |
| Single coordinator | Shared project memory; fewer conflicting agent copies |
| Idempotent retries + early `cycle_result` | Safe retry even when failure happens before a Run row exists |
| Separate supervisor fields + approve gate | Human judgment required before the next cycle; facts promote on approve |
| LLM selects tools; code validates | Inspectable tool decisions without letting the model invent metrics |
| Gemini + fallback | Meets LLM requirement while keeping offline eval stable |

### Disclosure

Built with Python, FastAPI, React/Vite, SQLAlchemy, LangChain Google GenAI, and AI coding assistance. The student must be able to explain and modify the workflow, memory schema, tools, and evaluation harness.

---

## Appendix A — Repository map

```
app/                         React UI
src/research_manager/
  agent/workflow.py          Coordinator loop
  agent/llm.py               Gemini + fallback
  tools/evidence.py          Tools
  memory/models.py           Schema
  memory/store.py            Lifecycle operations
  api.py                     HTTP API
  main.py                    CLI
evaluation/                  Scenarios + results
docs/                        Report + memory lifecycle
sample_inputs/               Anonymized notes
```

## Appendix B — Configuration

Copy `.env.example` → `.env` and set `GEMINI_API_KEY` / `GEMINI_MODEL`. Never commit secrets.
