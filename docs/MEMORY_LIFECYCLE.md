# Memory lifecycle

**Authoritative store:** SQLite at `memory/experiments.db`.  
Exports (CSV/Excel) are review views only and must not overwrite supervisor decisions.

## Components

| Component | What is stored | When written | When retrieved | Who may access | Correction / deletion |
|---|---|---|---|---|---|
| Working state (checkpoints) | Goal, cycle, missing outputs, last decision, tools executed | End of each cycle | Process restart / resume (logged); UI snapshot (quiet, `log=False`) | Same `project_id` only | Keep last **20** checkpoints per project; older rows deleted |
| Long-term facts | `baseline_accuracy`, `approved_metric`, `learning_rate`, immutable `review_policy` | Onboarding; supervisor correction; promote on **approve** | Start of each cycle (if memory enabled); `GET /api/facts` | Same `project_id` | `set_fact` supersedes prior version (`is_current=false`); history kept |
| Action history | Tool calls, memory R/W, LLM decisions (`tools_to_use` / `tools_executed`), cycle results, errors | Every tool/LLM/memory event | UI log / evaluation | Same `project_id` | Append-only; retries use idempotency keys / `cycle_result:{key}` |
| Source knowledge | Experiment folders + CSV/YAML artifacts | Simulator / researcher | `inspect_run`, `read_run_csv` (when selected) | Local filesystem under project runs | Files are evidence; untrusted instructions are redacted |

## Approved facts only

- Agent param tweaks update `experiment.params_json` during the cycle.
- They become **current long-term facts** only when the supervisor **approves** the decision (`approved_by=supervisor`).
- Later cycles read only current approved fact versions — not pending agent suggestions.

## Immutable policy

- Onboarding seeds `review_policy` (e.g. `read_only_tools`, `allow_email`, `max_cycles`).
- Untrusted planted content cannot overwrite it; only supervisor (or system/onboarding) may change policy.

## Identifiers and versions

- Stable `project_id` isolates all tables.
- Timestamps on runs, decisions, facts, checkpoints, action logs.
- Facts keep `version`, `is_current`, `source_ref`, `approved_by`, `superseded_at`.
- Runs/decisions keep source paths as evidence references.
- UI **Fact history** tab and `GET /api/facts?project_id=` expose current + superseded rows.

## Approval gate

If the latest agent decision has `supervisor_confirmed is None` and experiment status is `needs_review` or `iterating`, **`run_cycle` is blocked** until approve/reject. Accept-and-stop may auto-confirm.

## Resume rule

After a process restart, call `resume` / `POST /api/resume` to load the latest checkpoint and current facts. Do not re-upload baseline materials. Resume alone does not clear a pending approval.
