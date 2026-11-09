import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  approveDecision,
  correctFact,
  downloadReport,
  fetchStore,
  fetchState,
  onboardProject,
  resumeProject,
  runFullDemo,
  runOneCycle,
} from './api'
import type { AgentSnapshot, StoreSnapshot } from './types'
import './App.css'

type TabId = 'log' | 'runs' | 'decisions' | 'facts' | 'store'

function statusClass(status: string) {
  if (status === 'completed' || status === 'ok' || status === 'pass') return 'ok'
  if (
    status === 'needs_review' ||
    status === 'iterating' ||
    status === 'approved_continue' ||
    status === 'fail' ||
    status === 'warn'
  ) {
    return 'warn'
  }
  if (status === 'failed' || status === 'danger' || status === 'error') return 'danger'
  return ''
}

function eventPhase(eventType: string, toolName: string) {
  const value = `${eventType} ${toolName}`.toLowerCase()
  if (value.includes('memory') || value.includes('checkpoint')) return 'Memory'
  if (value.includes('tool') || toolName) return 'Evidence'
  if (value.includes('decision') || value.includes('finalize')) return 'Decision'
  if (value.includes('approval') || value.includes('supervisor')) return 'Governance'
  return 'Workflow'
}

function eventLabel(eventType: string, toolName: string) {
  const labels: Record<string, string> = {
    onboard: 'Project plan created',
    tool_call: 'Evidence tool executed',
    llm_decision: 'Agent decision proposed',
    supervisor_approval: 'Supervisor decision recorded',
    memory_write: 'Persistent memory updated',
    memory_read: 'Persistent memory read',
  }
  if (toolName === 'finalize_action') return 'Decision guard finalized action'
  if (toolName === 'save_checkpoint') return 'Restart checkpoint saved'
  return labels[eventType] || eventType.replaceAll('_', ' ')
}

function payloadText(value: unknown) {
  if (value == null) return ''
  if (typeof value === 'string') return value
  return JSON.stringify(value, null, 2)
}

function storeValue(value: unknown) {
  if (value == null) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function planSteps(snapshot: AgentSnapshot) {
  const hasExperiment = snapshot.current.experiment_id != null
  const hasRun = snapshot.runs.length > 0
  const hasEvidence = snapshot.evidence.length > 0
  const hasDecision = snapshot.last_decision != null
  return [
    { label: 'Confirm hypothesis and approved facts', done: hasExperiment },
    { label: 'Write parameters and execute the next run', done: hasRun },
    { label: 'Read artifacts and validate metrics', done: hasEvidence },
    { label: snapshot.next_action.label, done: hasDecision && !snapshot.next_action.requires_approval },
  ]
}

function metricEntries(metrics: Record<string, number>) {
  return Object.entries(metrics).filter(([key]) => !['epochs'].includes(key))
}

function shortTime(iso: string | null | undefined) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

function workflowStage(snapshot: AgentSnapshot | null) {
  if (!snapshot?.current?.experiment_id) return 0
  if (snapshot.approval_required) return 3
  if (snapshot.runs.length === 0) return 1
  if (snapshot.current.status === 'completed') return 3
  return 2
}

export default function App() {
  const [projectId, setProjectId] = useState('demo')
  const [projectDraft, setProjectDraft] = useState('demo')
  const [snapshot, setSnapshot] = useState<AgentSnapshot | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [comment, setComment] = useState('')
  const [overrideLr, setOverrideLr] = useState('')
  const [baselineEdit, setBaselineEdit] = useState('0.75')
  const [tab, setTab] = useState<TabId>('log')
  const [storeSnapshot, setStoreSnapshot] = useState<StoreSnapshot | null>(null)
  const [retryKey, setRetryKey] = useState('viva-retry-001')

  const refresh = useCallback(async () => {
    const data = await fetchState(projectId)
    setSnapshot(data)
    setError(null)
    const baseline = data.facts?.baseline_accuracy
    if (typeof baseline === 'number') setBaselineEdit(String(baseline))
  }, [projectId])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    ;(async () => {
      try {
        await refresh()
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [refresh])

  useEffect(() => {
    if (!toast) return
    const t = window.setTimeout(() => setToast(null), 2800)
    return () => window.clearTimeout(t)
  }, [toast])

  async function withBusy(label: string, fn: () => Promise<string | void>) {
    setBusy(true)
    setError(null)
    try {
      const extra = await fn()
      await refresh()
      setToast(extra || label)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  function applyProject() {
    const next = projectDraft.trim() || 'demo'
    setProjectDraft(next)
    setProjectId(next)
  }

  const current = snapshot?.current
  const next = snapshot?.next_action
  const runCount = snapshot?.runs.length ?? 0
  const cycleHint = useMemo(() => Math.min(runCount, 3), [runCount])

  const facts = snapshot?.facts ?? {}
  const evidence = snapshot?.evidence?.[0]
  const latestRun = snapshot?.runs?.[0]
  const stage = workflowStage(snapshot)
  const primaryAction = !snapshot?.current?.experiment_id
    ? 'onboard'
    : snapshot.approval_required
      ? 'approve'
      : 'run'

  async function showStore() {
    setTab('store')
    try {
      setStoreSnapshot(await fetchStore(projectId))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <div className="shell">
      <header className="hero fade-in">
        <div className="hero-copy">
          <p className="eyebrow">Agentic experiment control</p>
          <h1 className="brand">
            Research <em>Manager</em>
          </h1>
          <p className="tagline">
            Plan a run, read local evidence, diagnose failures, and approve the next action — with
            memory that survives restart.
          </p>
        </div>
        <div className="hero-side">
          <label className="project-field">
            <span>Project ID</span>
            <div className="project-row">
              <input
                value={projectDraft}
                onChange={(e) => setProjectDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') applyProject()
                }}
                spellCheck={false}
              />
              <button className="btn" type="button" onClick={applyProject} disabled={busy}>
                Switch
              </button>
            </div>
          </label>
          <div className="pulse-row">
            <span className={`live-dot ${busy ? 'busy' : 'idle'}`} />
            <span className="mono">{busy ? 'agent working…' : 'ready'}</span>
          </div>
        </div>
      </header>

      <nav className="workflow fade-in" aria-label="Research workflow">
        {[
          { n: '01', label: 'Plan' },
          { n: '02', label: 'Run' },
          { n: '03', label: 'Read evidence' },
          { n: '04', label: 'Choose next step' },
        ].map((step) => (
          <div key={step.n} className={`workflow-step ${stage >= Number(step.n) ? 'complete' : ''} ${stage + 1 === Number(step.n) ? 'active' : ''}`}>
            <span>{step.n}</span>
            {step.label}
          </div>
        ))}
      </nav>

      {toast && <div className="toast fade-in">{toast}</div>}

      {error && (
        <div className="error-banner fade-in">
          <div>{error}</div>
          <button
            className="btn primary"
            disabled={busy || loading}
            onClick={() => withBusy('Reconnected', async () => undefined)}
          >
            Retry connection
          </button>
        </div>
      )}

      {loading && !snapshot ? (
        <p className="muted loading-line">Loading agent state…</p>
      ) : !snapshot ? (
        <p className="muted loading-line">API unreachable. Start `python -m research_manager.api`.</p>
      ) : (
        <>
          {snapshot.approval_required && (
            <div className="gate-banner fade-in">
              Next cycle is blocked until you approve or reject the pending agent decision.
            </div>
          )}

          <section className="workspace-bar fade-in">
            <div>
              <span className="section-kicker">Research workspace</span>
              <strong>
                {!current?.experiment_id
                  ? 'Start by defining the approved baseline'
                  : snapshot.approval_required
                    ? 'Supervisor review is required'
                    : latestRun
                      ? 'Evidence is ready for the next decision'
                      : 'Plan the first experiment run'}
              </strong>
              <p className="muted small">
                {current?.hypothesis || 'Create a project to begin the plan → run → evidence loop.'}
              </p>
            </div>
            <div className="workspace-actions">
            <button
              className="btn primary"
              disabled={busy}
              onClick={() => {
                if (primaryAction === 'onboard') {
                  return withBusy('Project planned', async () => { await onboardProject(projectId) })
                }
                if (primaryAction === 'approve') {
                  document.querySelector('.approval-panel')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
                  return
                }
                return withBusy('Evidence collected', async () => {
                  await runOneCycle(projectId, { deterministic: true })
                })
              }}
            >
              {primaryAction === 'onboard'
                ? 'Create experiment plan'
                : primaryAction === 'approve'
                  ? 'Review decision'
                  : 'Run next experiment'}
            </button>
            <button
              className="btn primary"
              disabled={busy}
              onClick={() => withBusy('3-cycle demo finished', async () => { await runFullDemo(projectId, 3) })}
            >
              Run 3-cycle demo
            </button>
            <button
              className="btn"
              disabled={busy}
              onClick={() =>
                withBusy('State resumed from checkpoint', async () => {
                  const res = await resumeProject(projectId)
                  const cp = res.snapshot?.checkpoint
                  return `Resumed checkpoint #${cp?.checkpoint_id ?? 'none'}; facts loaded, no re-onboard`
                })
              }
            >
              Resume after restart
            </button>
            <button
              className="btn"
              disabled={busy}
              onClick={() => withBusy('Professional report downloaded', async () => { await downloadReport(projectId) })}
            >
              Download report
            </button>
            <button className="btn" disabled={busy} onClick={showStore}>
              View SQLite store
            </button>
            <button
              className="btn"
              disabled={busy}
              onClick={() => withBusy('State refreshed', async () => undefined)}
            >
              Refresh
            </button>
            </div>
          </section>

          <details className="advanced-tools fade-in">
            <summary>Advanced evaluation tools</summary>
            <div className="viva-actions">
              <button
                className="btn"
                disabled={busy}
                onClick={() =>
                  withBusy('Cycle complete (Gemini)', async () => {
                    await runOneCycle(projectId, { deterministic: false })
                  })
                }
              >
                Run with Gemini
              </button>
              <button
                className="btn"
                disabled={busy}
                onClick={() =>
                  withBusy('Real subprocess training finished', async () => {
                    const res = await runOneCycle(projectId, { runner_mode: 'real' })
                    const runnerRes = (res.result?.sim as { runner_result?: { duration_sec?: number } } | undefined)?.runner_result
                    return `Real subprocess ran in ${runnerRes?.duration_sec ?? 0.3}s`
                  })
                }
              >
                Run real training
              </button>
              <button
                className="btn"
                disabled={busy}
                onClick={() =>
                  withBusy('Untrusted instruction planted', async () => {
                    await runOneCycle(projectId, {
                      plant_untrusted: true,
                      skip_approval_gate: true,
                      deterministic: true,
                    })
                  })
                }
              >
                Plant untrusted instruction
              </button>
              <button
                className="btn"
                disabled={busy}
                onClick={() =>
                  withBusy('Conflicting CSV cycle', async () => {
                    await runOneCycle(projectId, {
                      force_sim_status: 'conflicting',
                      skip_approval_gate: true,
                      deterministic: true,
                    })
                  })
                }
              >
                Force conflicting CSV
              </button>
              <button
                className="btn"
                disabled={busy}
                onClick={() =>
                  withBusy('Tool failure then retry', async () => {
                    const key = retryKey
                    const fail = await runOneCycle(projectId, {
                      simulate_tool_failure: true,
                      idempotency_key: key,
                      skip_approval_gate: true,
                      deterministic: true,
                    })
                    const retry = await runOneCycle(projectId, {
                      idempotency_key: key,
                      skip_approval_gate: true,
                      deterministic: true,
                    })
                    setRetryKey(`viva-retry-${Date.now()}`)
                    return `fail ok=${String(fail.result?.ok)} · retry duplicate=${String(retry.result?.duplicate_prevented)} (key ${key})`
                  })
                }
              >
                Simulate tool failure + retry
              </button>
              <button
                className="btn"
                disabled={busy}
                onClick={() =>
                  withBusy('Memory on vs off', async () => {
                    const off = await runOneCycle(projectId, {
                      use_memory: false,
                      force_sim_status: 'success',
                      skip_approval_gate: true,
                      deterministic: true,
                    })
                    const on = await runOneCycle(projectId, {
                      use_memory: true,
                      force_sim_status: 'success',
                      skip_approval_gate: true,
                      deterministic: true,
                    })
                    const offBase = JSON.stringify(
                      (off.snapshot.evidence?.[0] as { metrics?: unknown } | undefined)?.metrics,
                    )
                    const onFacts = JSON.stringify(on.snapshot.facts?.baseline_accuracy)
                    return `memory OFF cycle then ON; approved baseline now ${onFacts} (OFF metrics ${offBase})`
                  })
                }
              >
                Memory off vs on
              </button>
            </div>
          </details>

          <div className="grid fade-in">
            <section className="stack">
              <article className="panel state-panel">
                <div className="panel-head">
                  <h2>Current state</h2>
                  <span className={`status ${statusClass(current?.status ?? '')}`}>
                    {current?.status ?? 'idle'}
                  </span>
                </div>

                <p className="hypothesis">
                  {current?.hypothesis || 'No active hypothesis yet. Onboard this project to begin.'}
                </p>

                <div className="metric-strip">
                  <div>
                    <span>Experiment</span>
                    <strong className="mono">
                      {current?.name ?? '—'}
                      {current?.experiment_id != null ? ` #${current.experiment_id}` : ''}
                    </strong>
                  </div>
                  <div>
                    <span>Cycles logged</span>
                    <strong className="mono">
                      {cycleHint}/3
                    </strong>
                  </div>
                  <div>
                    <span>Checkpoint</span>
                    <strong className="mono">
                      {snapshot.checkpoint ? `#${snapshot.checkpoint.checkpoint_id}` : 'none'}
                    </strong>
                  </div>
                </div>

                <div className="kv">
                  <div className="kv-row">
                    <span>params</span>
                    <code className="code-block">{JSON.stringify(current?.params ?? {}, null, 2)}</code>
                  </div>
                  <div className="kv-row">
                    <span>approved facts</span>
                    <div className="fact-chips">
                      {Object.keys(facts).length === 0 ? (
                        <span className="muted">None yet</span>
                      ) : (
                        Object.entries(facts).map(([key, value]) => (
                          <span key={key} className="chip">
                            <em>{key}</em>{' '}
                            {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                          </span>
                        ))
                      )}
                    </div>
                  </div>
                  <div className="kv-row">
                    <span>pending params</span>
                    <div className="fact-chips">
                      {Object.keys(snapshot.pending_params ?? {}).length === 0 ? (
                        <span className="muted">None — experiment params match approved facts</span>
                      ) : (
                        Object.entries(snapshot.pending_params ?? {}).map(([key, value]) => (
                          <span key={key} className="chip chip-pending">
                            <em>{key}</em> {String(value)} (not a fact until approve)
                          </span>
                        ))
                      )}
                    </div>
                  </div>
                  {snapshot.fact_bump && snapshot.fact_bump.previous_version != null && (
                    <div className="kv-row">
                      <span>fact version</span>
                      <span className="chip chip-llm">
                        <em>{snapshot.fact_bump.fact_key}</em> v{snapshot.fact_bump.previous_version}{' '}
                        superseded → v{snapshot.fact_bump.current_version} current (
                        {String(snapshot.fact_bump.current_value)})
                      </span>
                    </div>
                  )}
                </div>

                <div className="next-box">
                  <strong>Recommended next action</strong>
                  <p>{next?.label}</p>
                  {next?.requires_approval && <span className="badge warn">Approval required</span>}
                </div>

                {snapshot.last_decision && (
                  <div className="decision-meta">
                    <div className="fact-chips">
                      <span className={`chip ${snapshot.last_decision.llm_used ? 'chip-llm' : ''}`}>
                        <em>decision</em> {snapshot.last_decision.action}
                      </span>
                      <span className="chip">
                        <em>model</em>{' '}
                        {snapshot.last_decision.llm_used
                          ? snapshot.last_decision.model || 'gemini'
                          : 'deterministic'}
                      </span>
                      {snapshot.last_decision.latency_ms != null && (
                        <span className="chip">
                          <em>latency</em> {snapshot.last_decision.latency_ms} ms
                        </span>
                      )}
                      {snapshot.last_decision.llm_proposed?.action && (
                        <span className="chip">
                          <em>LLM proposed</em> {snapshot.last_decision.llm_proposed.action}
                        </span>
                      )}
                      {snapshot.last_decision.guard_overrode && (
                        <span className="chip chip-guard">
                          <em>Guard</em> kept {snapshot.last_decision.action}
                          {snapshot.last_decision.guard_reason
                            ? ` (${snapshot.last_decision.guard_reason})`
                            : ''}
                        </span>
                      )}
                    </div>
                    {(snapshot.last_decision.tools_to_use?.length ||
                      snapshot.last_decision.tools_executed?.length) && (
                      <div className="fact-chips tools-row">
                        {snapshot.last_decision.tools_to_use?.map((t) => (
                          <span key={`sel-${t}`} className="chip">
                            <em>LLM selected</em> {t}
                          </span>
                        ))}
                        {snapshot.last_decision.tools_executed?.map((t) => (
                          <span key={`exec-${t}`} className="chip chip-exec">
                            <em>ran</em> {t}
                          </span>
                        ))}
                      </div>
                    )}
                    <p className="muted small">{snapshot.last_decision.rationale}</p>
                  </div>
                )}
              </article>

              <article className="panel">
                <h2>Supporting evidence</h2>
                {!evidence ? (
                  <p className="muted">No run artifacts yet. Run a cycle to collect folder/CSV evidence.</p>
                ) : (
                  <div className="evidence-card">
                    {evidence.missing_files?.length ? (
                      <div className="evidence-state pending">
                        <strong>Awaiting experiment artifacts</strong>
                        <span>
                          The run was inspected, but {evidence.missing_files.join(' and ')} {evidence.missing_files.length === 1 ? 'is' : 'are'} not available yet.
                        </span>
                      </div>
                    ) : null}
                    <div className="evidence-top">
                      <span className="mono">{evidence.run_key}</span>
                      <span className={`status ${evidence.success ? 'ok' : evidence.missing_files?.length ? 'warn' : 'danger'}`}>
                        {evidence.success ? 'supports claim' : evidence.missing_files?.length ? 'awaiting files' : 'needs review'}
                      </span>
                    </div>
                    <p className="evidence-notes">{evidence.notes || 'No analyst notes.'}</p>
                    <div className="fact-chips">
                      {Object.keys(evidence.metrics || {}).length === 0 ? (
                        <span className="chip muted-chip">
                          {evidence.missing_files?.includes('results.csv')
                            ? 'Metrics will appear after results.csv is produced'
                            : 'No metrics available'}
                        </span>
                      ) : (
                        Object.entries(evidence.metrics).map(([k, v]) => (
                          <span key={k} className="chip">
                            <em>{k}</em> {v}
                          </span>
                        ))
                      )}
                    </div>
                    <p className="path mono">{evidence.source}</p>
                  </div>
                )}
              </article>

              <article className="panel">
                <h2>Correction</h2>
                <p className="muted small">
                  Approve a new baseline. History is preserved; later decisions use the current version.
                </p>
                <div className="correct-row">
                  <label>
                    baseline_accuracy
                    <input
                      className="field"
                      value={baselineEdit}
                      onChange={(e) => setBaselineEdit(e.target.value)}
                    />
                  </label>
                  <button
                    className="btn primary"
                    disabled={busy}
                    onClick={() =>
                      withBusy('Baseline corrected', async () => {
                        const res = await correctFact({
                          project_id: projectId,
                          fact_key: 'baseline_accuracy',
                          value: Number(baselineEdit),
                        })
                        const bump = res.snapshot?.fact_bump
                        if (bump?.previous_version != null) {
                          return `v${bump.previous_version} superseded → v${bump.current_version} current (${bump.fact_key}=${String(bump.current_value)})`
                        }
                      })
                    }
                  >
                    Approve new baseline
                  </button>
                </div>
              </article>

              {next?.requires_approval && (
                <article className="panel approval-panel">
                  <h2>Supervisor approval & steering</h2>
                  <p className="decision-line">
                    <span className="mono">{snapshot.pending_approval?.decision_type}</span>
                    {' — '}
                    {snapshot.pending_approval?.rationale}
                  </p>
                  {snapshot.pending_approval?.next_params &&
                    Object.keys(snapshot.pending_approval.next_params).length > 0 && (
                      <div className="override-row">
                        <span className="muted small">Proposed parameters to promote:</span>
                        <div className="fact-chips">
                          {Object.entries(snapshot.pending_approval.next_params).map(([k, v]) => (
                            <span key={k} className="chip chip-pending">
                              <em>{k}</em> {String(v)}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  <div className="override-row">
                    <label className="muted small" htmlFor="override-lr-input">
                      Supervisor override for learning_rate (optional):
                    </label>
                    <input
                      id="override-lr-input"
                      type="number"
                      step="0.01"
                      className="mono"
                      placeholder={`e.g. 0.05 (current proposal: ${snapshot.pending_approval?.next_params?.learning_rate ?? 'none'})`}
                      value={overrideLr}
                      onChange={(e) => setOverrideLr(e.target.value)}
                    />
                  </div>
                  <textarea
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                    placeholder="Supervisor guidance or feedback (passed to next cycle if rejected)"
                  />
                  <div className="actions">
                    <button
                      className="btn primary"
                      disabled={busy}
                      onClick={() =>
                        withBusy(
                          overrideLr.trim() ? 'Approved with supervisor override' : 'Decision approved',
                          async () => {
                            const overrides: Record<string, unknown> = {}
                            if (overrideLr.trim()) {
                              const parsed = parseFloat(overrideLr)
                              if (!Number.isNaN(parsed)) overrides.learning_rate = parsed
                            }
                            await approveDecision({
                              project_id: projectId,
                              approved: true,
                              comment,
                              override_params:
                                Object.keys(overrides).length > 0 ? overrides : undefined,
                            })
                            setComment('')
                            setOverrideLr('')
                          },
                        )
                      }
                    >
                      {overrideLr.trim() ? 'Approve with overrides' : 'Approve'}
                    </button>
                    <button
                      className="btn ghost-danger"
                      disabled={busy}
                      onClick={() =>
                        withBusy('Decision rejected with guidance', async () => {
                          await approveDecision({
                            project_id: projectId,
                            approved: false,
                            comment,
                          })
                          setComment('')
                          setOverrideLr('')
                        })
                      }
                    >
                      Reject with guidance
                    </button>
                  </div>
                </article>
              )}
            </section>

            <section className="stack">
              <article className="panel plan-panel">
                <div className="panel-head">
                  <div>
                    <h2>Execution plan</h2>
                    <p className="muted small">Evidence-driven plan for the current research cycle.</p>
                  </div>
                  <span className="plan-count">
                    {planSteps(snapshot).filter((step) => step.done).length}/{planSteps(snapshot).length}
                  </span>
                </div>
                <ol className="plan-list">
                  {planSteps(snapshot).map((step, index) => (
                    <li key={`${step.label}-${index}`} className={step.done ? 'done' : index === planSteps(snapshot).findIndex((item) => !item.done) ? 'active' : ''}>
                      <span className="plan-marker">{step.done ? '✓' : String(index + 1).padStart(2, '0')}</span>
                      <span>{step.label}</span>
                    </li>
                  ))}
                </ol>
                <div className="technique-row">
                  <span className="technique-chip">Deterministic evidence guards</span>
                  <span className="technique-chip">Versioned memory</span>
                  <span className="technique-chip">Idempotent retries</span>
                  <span className="technique-chip">Human approval gate</span>
                </div>
              </article>
              <article className="panel analytics-panel">
                <div className="panel-head">
                  <div>
                    <h2>Experiment analytics</h2>
                    <p className="muted small">Multi-metric view of the latest evidence artifact.</p>
                  </div>
                  <span className="mono">{latestRun?.run_key ?? 'no run'}</span>
                </div>
                {!latestRun || metricEntries(latestRun.metrics).length === 0 ? (
                  <p className="muted">Metrics will appear after a readable results.csv is produced.</p>
                ) : (
                  <div className="analytics-grid">
                    {metricEntries(latestRun.metrics).map(([name, value]) => {
                      const baseline = name === 'accuracy' && typeof facts.baseline_accuracy === 'number'
                        ? facts.baseline_accuracy
                        : null
                      const delta = baseline == null ? null : value - baseline
                      return (
                        <div className="analytics-card" key={name}>
                          <span>{name.replaceAll('_', ' ')}</span>
                          <strong>{typeof value === 'number' ? value.toFixed(4) : String(value)}</strong>
                          {delta != null && (
                            <small className={delta >= 0 ? 'metric-up' : 'metric-down'}>
                              {delta >= 0 ? '+' : ''}{delta.toFixed(4)} vs baseline
                            </small>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )}
                <div className="validation-strip">
                  <span>Validation protocol</span>
                  <strong>Fixed seed · held-out validation · artifact-backed comparison</strong>
                </div>
              </article>
              <article className="panel">
                <div className="tabs">
                  {(
                    [
                      ['log', 'Action log'],
                      ['runs', 'Runs'],
                      ['decisions', 'Decisions'],
                      ['facts', 'Fact history'],
                      ['store', 'SQLite store'],
                    ] as const
                  ).map(([id, label]) => (
                    <button
                      key={id}
                      type="button"
                      className={`tab ${tab === id ? 'active' : ''}`}
                      onClick={() => setTab(id)}
                    >
                      {label}
                    </button>
                  ))}
                </div>

                {tab === 'log' && (
                  <>
                    {!snapshot.action_log?.length ? (
                      <p className="muted">No events yet.</p>
                    ) : (
                      <>
                        <div className="log-intro">
                          <span className="mono">LIVE TRACE</span>
                          <span className="muted small">Persistent events from the current project, newest first.</span>
                        </div>
                        <ul className="timeline rich-timeline">
                          {snapshot.action_log.slice(0, 20).map((a) => (
                          <li key={a.id}>
                            <div className="timeline-main">
                              <span className={`pill ${statusClass(a.outcome)}`}>{a.outcome}</span>
                              <span className="log-phase">{eventPhase(a.event_type, a.tool_name)}</span>
                              <strong>{eventLabel(a.event_type, a.tool_name)}</strong>
                            </div>
                            <div className="timeline-meta">
                              <span className="mono">{shortTime(a.created_at)}</span>
                              {a.tool_name && <span className="mono">tool={a.tool_name}</span>}
                              {a.error && <span className="log-error">{a.error}</span>}
                            </div>
                            {(Object.keys(a.input || {}).length > 0 || Object.keys(a.output || {}).length > 0) && (
                              <details className="log-details">
                                <summary>Technical details</summary>
                                <div className="log-payloads">
                                  {Object.keys(a.input || {}).length > 0 && (
                                    <div>
                                      <span className="payload-label">input</span>
                                      <pre>{payloadText(a.input)}</pre>
                                    </div>
                                  )}
                                  {Object.keys(a.output || {}).length > 0 && (
                                    <div>
                                      <span className="payload-label">output</span>
                                      <pre>{payloadText(a.output)}</pre>
                                    </div>
                                  )}
                                </div>
                              </details>
                            )}
                          </li>
                          ))}
                        </ul>
                      </>
                    )}
                  </>
                )}

                {tab === 'runs' && (
                  <>
                    {snapshot.runs.length === 0 ? (
                      <p className="muted">No runs recorded.</p>
                    ) : (
                      <ul className="timeline">
                        {snapshot.runs.slice(0, 10).map((run) => (
                          <li key={run.id}>
                            <div className="timeline-main">
                              <span className={`status ${run.success ? 'ok' : 'warn'}`}>
                                {run.success ? 'pass' : 'fail'}
                              </span>
                              <span className="mono">{run.run_key}</span>
                            </div>
                            <div className="timeline-meta">{run.notes}</div>
                            <div className="timeline-meta mono">{shortTime(run.created_at)}</div>
                          </li>
                        ))}
                      </ul>
                    )}
                  </>
                )}

                {tab === 'decisions' && (
                  <>
                    {snapshot.decisions.length === 0 ? (
                      <p className="muted">No decisions yet.</p>
                    ) : (
                      <ul className="timeline">
                        {snapshot.decisions.slice(0, 10).map((d) => (
                          <li key={d.id}>
                            <div className="timeline-main">
                              <span className="mono">{d.decision_type}</span>
                            </div>
                            <div className="timeline-meta">{d.rationale}</div>
                            <div className="timeline-meta mono">
                              agent={String(d.agent_suggested)} · supervisor=
                              {String(d.supervisor_confirmed)} · {shortTime(d.created_at)}
                            </div>
                          </li>
                        ))}
                      </ul>
                    )}
                  </>
                )}

                {tab === 'facts' && (
                  <>
                    {!snapshot.fact_history?.length ? (
                      <p className="muted">No fact versions yet. Onboard to seed approved facts.</p>
                    ) : (
                      <ul className="timeline">
                        {snapshot.fact_history.slice(0, 20).map((f) => (
                          <li key={`${f.fact_key}-${f.version}`}>
                            <div className="timeline-main">
                              <span className={`pill ${f.is_current ? 'ok' : ''}`}>
                                {f.is_current ? 'current' : 'superseded'}
                              </span>
                              <span className="mono">
                                {f.fact_key} v{f.version}
                              </span>
                            </div>
                            <div className="timeline-meta mono">
                              {typeof f.value === 'object'
                                ? JSON.stringify(f.value)
                                : String(f.value)}{' '}
                              · by {f.approved_by} · {shortTime(f.created_at)}
                            </div>
                          </li>
                        ))}
                      </ul>
                    )}
                  </>
                )}

                {tab === 'store' && (
                  <div className="store-view">
                    {!storeSnapshot ? (
                      <p className="muted">Loading the read-only SQLite store view…</p>
                    ) : (
                      <>
                        <div className="store-toolbar">
                          <div>
                            <span className="mono">AUTHORITATIVE STORE</span>
                            <strong>{storeSnapshot.database}</strong>
                          </div>
                          <button className="btn" type="button" onClick={showStore}>Refresh store</button>
                        </div>
                        <div className="store-counts">
                          {Object.entries(storeSnapshot.counts).map(([name, count]) => (
                            <span className="chip" key={name}><em>{name}</em> {count}</span>
                          ))}
                        </div>
                        {([
                          ['experiments', storeSnapshot.experiments],
                          ['runs', storeSnapshot.runs],
                          ['decisions', storeSnapshot.decisions],
                          ['facts', storeSnapshot.facts],
                          ['checkpoints', storeSnapshot.checkpoints],
                          ['action_logs', storeSnapshot.action_logs],
                        ] as const).map(([name, rows]) => (
                          <details className="store-table" key={name} open={name === 'experiments' || name === 'runs'}>
                            <summary>{name} <span>{rows.length} rows shown</span></summary>
                            {!rows.length ? (
                              <p className="muted small">No records stored.</p>
                            ) : (
                              <div className="store-scroll">
                                <table>
                                  <thead>
                                    <tr>
                                      {Object.keys(rows[0]).map((key) => <th key={key}>{key}</th>)}
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {rows.map((row, index) => (
                                      <tr key={`${name}-${String(row.id ?? index)}`}>
                                        {Object.keys(rows[0]).map((key) => (
                                          <td key={key}><code>{storeValue(row[key])}</code></td>
                                        ))}
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            )}
                          </details>
                        ))}
                      </>
                    )}
                  </div>
                )}
              </article>

              <article className="panel tip-panel">
                <h2>Viva demo path</h2>
                <ol className="demo-list">
                  <li>Onboard — facts in SQLite <span className="mono">fact_versions</span></li>
                  <li>Run cycle offline — inspect <span className="mono">tools_executed</span></li>
                  <li>Run cycle with Gemini — chips show llm_used / LLM proposed vs Guard</li>
                  <li>Approve (gate blocks next cycle) then Resume — checkpoint, no re-onboard</li>
                  <li>Correct baseline — v1 superseded → v2 current</li>
                  <li>Viva panel: untrusted, conflicting CSV, tool-failure retry, memory off vs on</li>
                  <li>Action log tab — <span className="mono">action_logs</span></li>
                  <li>Fact history tab — current vs superseded</li>
                </ol>
              </article>
            </section>
          </div>
        </>
      )}
    </div>
  )
}
