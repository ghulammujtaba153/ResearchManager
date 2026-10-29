# 8–10 minute live demo script

1. **Onboard** project `demo` — show approved facts (`baseline_accuracy`, `approved_metric`, `learning_rate`, `review_policy`).
2. **Run one cycle** — incomplete/fail; show evidence + action log tool calls.
3. Point at **decision chips**: `model`, `latency`, `llm_used`, **LLM selected** tools vs **ran** tools. For Gemini: ensure `.env` has `GEMINI_API_KEY` and do **not** set `RESEARCH_MANAGER_DETERMINISTIC`.
4. Show the **approval gate banner** — “Run one cycle” stays disabled until Approve/Reject.
5. **Resume after restart** — stop/restart API optional; click Resume; state returns without re-upload (logged `memory_read`).
6. **Correct baseline** (e.g. 0.75 → 0.90) — open **Fact history** tab; current vs superseded versions.
7. **Approve** the pending decision — mention that approved params can promote into long-term facts; then run the next cycle.
8. **Run one cycle** again — decision / comparison changes because of the corrected baseline.
9. Open **Action log** — timestamps, tool outcomes, `finalize_action` / `tools_executed`.
10. Optional: untrusted / conflicting path via API, or cite scenario suite **10/10** in `evaluation/scenario_results.md`.

**3-cycle demo button** auto-approves between cycles so the story can finish without manual clicks.

Backup if Gemini is down: deterministic fallback still evidence-responsive and still changes which tools run (e.g. incomplete skips CSV); disclose honestly and show `evaluation/scenario_results.md`.
