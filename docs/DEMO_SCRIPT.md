# 8-minute viva path

Click these in order. Name the table/file when you talk.

1. **Onboard** — approved facts on screen (`fact_versions`: `baseline_accuracy`, `review_policy`).
2. **Run cycle offline** — incomplete/fail; chips show `tools_executed` (inspect + write; CSV skipped). `action_logs`.
3. **Run cycle with Gemini** — `.env` has `GEMINI_API_KEY`. Point at `llm_used`, **LLM proposed** vs **Guard kept** if they differ, and LLM selected vs ran tools.
4. **Approve** the pending decision (gate banner; next cycle blocked until this). Pending params are **not** facts until approve.
5. **Resume after restart** — toast: checkpoint id + facts loaded, no re-onboard (`checkpoints`).
6. **Correct baseline** 0.75 → 0.90 — inline `v1 superseded → v2 current`; Fact history tab.
7. **Viva panel** (pick 1–2):
   - **Real subprocess execution** — click **Run real subprocess (live ML)**; point out it spawns an OS child process running `train_model.py` (gradient descent), writes `train.log`, and uses `read_run_logs` for automated failure diagnostics.
   - **Plant untrusted** (`reject_untrusted`, policy unchanged).
   - **Conflicting CSV** (no invented metrics).
   - **Tool-failure + retry** (`cycle_result` idempotency).
   - **Memory off vs on** (different baseline).
8. **Scientific Grounding & Preprint Tabs**:
   - **Trajectory tab** — vector SVG convergence chart against approved baseline with cycle statistics.
   - **Literature tab** — live ArXiv query for related work and one-click BibTeX citation copying.
   - **Paper draft tab** — autonomous preprint manuscript compiler generating `reports/{project_id}_preprint_paper.md` with abstract, methodology, results table, and bibliography.
9. **Action log + Fact history** tabs — timestamps, `finalize_action`, `tools_executed`. Cite eval **10/10** in `evaluation/scenario_results.md`.

**3-cycle demo** auto-approves between cycles if time is short.

If Gemini is down: stay on **Run cycle offline**; fallback is still evidence-responsive; disclose it.
