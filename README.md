# Research Experiment Manager

Agentic research assistant (assignment A02) that plans experiments, reads local result evidence, diagnoses incomplete runs, and chooses the next experiment with persistent memory, approvals, and audited logs.

## Features mapped to marking criteria

- **Tools:** `inspect_run`, `read_run_csv`, `read_run_logs` (diagnoses OOM, NaN loss, stack traces), `write_next_task`, deterministic `compare_to_baseline` — LLM `tools_to_use` selects which follow-up tools actually run
- **Execution:** Dual mode — reproducible simulated artifact dropper (offline CI/eval) and live OS subprocess runner (`train_model.py`) with real gradient descent and `train.log` telemetry
- **Assertive Invariants (P1):** Six formal safety contracts (`INV_SECURITY`, `INV_COMPLETENESS`, `INV_EVIDENCE_INTEGRITY`, `INV_BASELINE_THRESHOLD`, `INV_VOCABULARY`, `INV_PARAM_BOUNDS`) verify proposals while preserving agent exploration
- **Collaborative Steering (P2):** Supervisors counter-propose hyperparameters (`--lr`, UI overrides) and reject with targeted feedback injected directly into agent context
- **Scientific Literature & Paper Drafter:** ArXiv API integration (`search_arxiv`) with BibTeX citations, multi-run trajectory analytics (`generate_svg_chart`), and autonomous preprint manuscript drafting (`reports/{project_id}_preprint_paper.md`)
- **LLM decision:** Gemini chooses tools + next action from evidence (`GEMINI_API_KEY`); deterministic fallback if offline; guards override unsafe actions
- **3 cycles + restart:** checkpoints resume without re-uploading baselines (last 20 kept per project)
- **Correction:** versioned facts (`fact_versions`); agent param tweaks promote only after supervisor approve
- **Isolation:** all records keyed by `project_id`; immutable `review_policy` cannot be changed by untrusted content
- **UI/CLI:** full web workspace with Trajectory SVG plot, ArXiv literature search, Preprint Manuscript generator, approval gate banner, and store viewer
- **Reliability:** action log + `cycle_result` idempotency for mid-cycle failure retries; quiet UI checkpoint reads
- **Evaluation:** `evaluation/run_scenarios.py` — **10/10** scenarios, memory **3/3**, claims **5/5**

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
copy .env.example .env   # set GEMINI_API_KEY
npm install               # install root Neon tooling dependencies
cd app
npm install
```

## Run

```powershell
# API
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH="src"
python -m research_manager.api

# UI (other terminal)
cd app
npm run dev
```

CLI:

```powershell
python -m research_manager onboard --project-id demo
python -m research_manager cycle --project-id demo             # simulated run
python -m research_manager cycle --project-id demo --real      # real ML gradient descent training
python -m research_manager approve --project-id demo --comment "Proceed with LR tune" --lr 0.05
python -m research_manager literature --query "warm restarts" --limit 3
python -m research_manager paper --project-id demo --query "SGDR"
python -m research_manager resume --project-id demo
python -m research_manager demo --project-id demo
```

### Live deployment hardening

Set `RESEARCH_MANAGER_API_KEY` and `RESEARCH_MANAGER_REQUIRE_AUTH=true` before
exposing the API. Clients may send either `X-API-Key` or
`Authorization: Bearer <key>`.
For multi-user or concurrent deployments, set `RESEARCH_MANAGER_DATABASE_URL` to a
PostgreSQL SQLAlchemy URL and run schema migrations before startup. The deployed
Neon application uses `DATABASE_URL`; local demos fall back to SQLite when no
PostgreSQL URL is configured.

Neon deployments write `DATABASE_URL` to `.env`; the backend automatically uses it
with the `psycopg` driver. The frontend build can be run from the repository root
with `npm run build`. Use `DATABASE_URL_UNPOOLED` for schema migrations and the
pooled `DATABASE_URL` for normal application traffic.

When API authentication is enabled, clients must send the configured key. The
current frontend does not inject an API key automatically, so use local demo mode,
configure a reverse proxy, or add a frontend key mechanism before enabling auth for
browser use.

## Evaluate

```powershell
python evaluation/run_scenarios.py
```

Outputs: `evaluation/scenario_results.json`, `evaluation/scenario_results.md`

## Docs

- `docs/TECHNICAL_REPORT.md` — submission draft (architecture, loop, memory, reliability, eval)
- `docs/MEMORY_LIFECYCLE.md` — working / long-term / policy / resume rules
- `docs/DEMO_SCRIPT.md` — 8–10 minute viva path

## Gemini live decision

```powershell
# .env must contain GEMINI_API_KEY
# Do NOT set RESEARCH_MANAGER_DETERMINISTIC when demoing LLM
$env:PYTHONPATH="src"
python -m research_manager cycle --project-id demo
```

UI shows `model` / `latency` / `llm_used`, **LLM proposed** vs **Guard**, and **LLM selected** vs **ran** tool chips. Use **Run cycle with Gemini** for the live viva step; **Run cycle offline** for the fallback.

## Approval gate

After a non-accept cycle, the next cycle is **blocked** until Approve / Reject. The 3-cycle demo auto-approves between cycles; eval uses `skip_approval_gate` where needed.

## Local MLflow tracking

Real subprocess runs can log parameters, metrics, and artifacts to a local MLflow server. Set
`MLFLOW_TRACKING_URI` before starting the API, or add it to `.env`:

```powershell
$env:MLFLOW_TRACKING_URI="sqlite:///mlflow.db"
$env:MLFLOW_EXPERIMENT_NAME="ResearchManager"
mlflow server --backend-store-uri "sqlite:///mlflow.db" --default-artifact-root ".\mlartifacts" --host 127.0.0.1 --port 5000
```

In another terminal, start the API and frontend, then choose **Run real training** under
Advanced evaluation tools. Open `http://127.0.0.1:5000` to inspect the run. Each run logs
parameters, accuracy, precision, recall, F1, loss, duration, and `params.yaml`, `results.csv`,
`metrics.json`, and `train.log`.
