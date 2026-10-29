# Research Experiment Manager

Agentic research assistant (assignment A02) that plans experiments, reads local result evidence, diagnoses incomplete runs, and chooses the next experiment with persistent memory, approvals, and audited logs.

## Features mapped to marking criteria

- **Tools:** `inspect_run`, `read_run_csv`, `write_next_task`, deterministic `compare_to_baseline` — LLM `tools_to_use` selects which follow-up tools actually run
- **LLM decision:** Gemini chooses tools + next action from evidence (`GEMINI_API_KEY`); deterministic fallback if offline; guards override unsafe actions
- **3 cycles + restart:** checkpoints resume without re-uploading baselines (last 20 kept per project)
- **Correction:** versioned facts (`fact_versions`); agent param tweaks promote only after supervisor approve
- **Isolation:** all records keyed by `project_id`; immutable `review_policy` cannot be changed by untrusted content
- **UI/CLI:** state, next action, evidence, approval gate banner, fact history, LLM tool chips, action log
- **Reliability:** action log + `cycle_result` idempotency for mid-cycle failure retries; quiet UI checkpoint reads
- **Evaluation:** `evaluation/run_scenarios.py` — **10/10** scenarios, memory **3/3**, claims **5/5**

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
copy .env.example .env   # set GEMINI_API_KEY
cd app
npm install
```

## Run

```powershell
# API
.\.venv\Scripts\Activate.ps1
python -m research_manager.api

# UI (other terminal)
cd app
npm run dev
```

CLI:

```powershell
python -m research_manager onboard --project-id demo
python -m research_manager cycle --project-id demo
python -m research_manager resume --project-id demo
python -m research_manager demo --project-id demo
```

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
python -m research_manager cycle --project-id demo
```

UI shows `model` / `latency` / `llm_used`, plus **LLM selected** vs **ran** tool chips after each cycle.

## Approval gate

After a non-accept cycle, the next cycle is **blocked** until Approve / Reject. The 3-cycle demo auto-approves between cycles; eval uses `skip_approval_gate` where needed.
