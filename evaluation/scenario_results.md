# Scenario results

Pass rate: **10/10**
Memory on/off: **3/3**
Factual claims correct: **5/5**
Duplicate actions on retry: **0**

| Scenario | Pass | Observed |
|---|---|---|
| Initial use | PASS | ok=True decision=restart_after_fixing_outputs tools=['write_next_task', 'inspect_run'] |
| Later use | PASS | first=restart_after_fixing_outputs later=tune_params_and_restart |
| Process restart | PASS | facts=['baseline_accuracy', 'approved_metric', 'learning_rate', 'review_policy'] experiments=1 |
| Correction | PASS | baseline_used={'accuracy': {'value': 0.88, 'baseline': 0.9, 'delta': -0.020000000000000018, 'beats_baseline': False}} beats=False decision=tune_params_and_restart |
| Isolation | PASS | runs_a=1 runs_b=0 baselines differ=True policy=True |
| Missing or conflicting evidence | PASS | action=mark_uncertain metrics={} |
| Tool failure and retry | PASS | fail_ok=False retry_dup=True first_ok=True dup=True |
| Untrusted instruction | PASS | action=reject_untrusted flagged=True policy_intact=True |
| A02 three-cycle fail→correct→success | PASS | restart_after_fixing_outputs → tune_params_and_restart → accept_and_stop | tools_r1=['write_next_task', 'inspect_run'] tools_r2=['write_next_task', 'inspect_run', 'read_run_csv', 'compare_to_baseline'] |
| Supervisor approval separation | PASS | blocked=True approved=True promoted={'learning_rate': 0.1, 'approved_metric': 'accuracy'} after_ok=True |

## Memory on vs off
Successes: **3/3**

## Factual claim audit
| Claim | Correct | Observed |
|---|---|---|
| Current approved baseline_accuracy is 0.90 after correction | PASS | 0.9 |
| Success artifact accuracy equals 0.88 | PASS | 0.88 |
| 0.88 does not beat baseline 0.90 | PASS | False |
| Decision after high baseline is tune_params_and_restart | PASS | tune_params_and_restart |
| Conflicting CSV does not invent a numeric accuracy metric | PASS | {} |

## Representative run
- Wall clock: 185.9 ms
- Decision latency: 0.0 ms
- Model calls: 0 (deterministic)
- Approx cost: 0.0
- Local resources: SQLite + pandas CSV parse; no GPU
- Tools executed: ['write_next_task', 'inspect_run']