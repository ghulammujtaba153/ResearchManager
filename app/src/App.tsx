import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  approveDecision,
  correctFact,
  fetchState,
  onboardProject,
  resumeProject,
  runFullDemo,
  runOneCycle,
} from './api'
import type { AgentSnapshot } from './types'
import './App.css'

type TabId = 'log' | 'runs' | 'decisions' | 'facts'

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

function shortTime(iso: string | null | undefined) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
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
  const [baselineEdit, setBaselineEdit] = useState('0.75')
  const [tab, setTab] = useState<TabId>('log')

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

  async function withBusy(label: string, fn: () => Promise<void>) {
    setBusy(true)
    setError(null)
    try {
      await fn()
      await refresh()
      setToast(label)
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

      <nav className="workflow fade-in" aria-label="Demo workflow">
        {[
          { n: '01', label: 'Onboard' },
          { n: '02', label: 'Cycle' },
          { n: '03', label: 'Resume' },
          { n: '04', label: 'Correct' },
          { n: '05', label: 'Approve' },
        ].map((step) => (
          <div key={step.n} className="workflow-step">
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

          <section className="toolbar fade-in">
            <button
              className="btn"
              disabled={busy}
              onClick={() => withBusy('Project onboarded', async () => { await onboardProject(projectId) })}
            >
              Onboard
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
              disabled={busy || Boolean(snapshot.approval_required)}
              title={
                snapshot.approval_required
                  ? 'Approve or reject the pending decision first'
                  : undefined
              }
              onClick={() => withBusy('Cycle complete', async () => { await runOneCycle(projectId) })}
            >
              Run one cycle
            </button>
            <button
              className="btn"
              disabled={busy}
              onClick={() => withBusy('State resumed from checkpoint', async () => { await resumeProject(projectId) })}
            >
              Resume after restart
            </button>
            <button
              className="btn"
              disabled={busy}
              onClick={() => withBusy('State refreshed', async () => undefined)}
            >
              Refresh
            </button>
          </section>

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
                    <div className="evidence-top">
                      <span className="mono">{evidence.run_key}</span>
                      <span className={`status ${evidence.success ? 'ok' : 'warn'}`}>
                        {evidence.success ? 'supports claim' : 'gap / fail'}
                      </span>
                    </div>
                    <p className="evidence-notes">{evidence.notes || 'No analyst notes.'}</p>
                    <div className="fact-chips">
                      {Object.keys(evidence.metrics || {}).length === 0 ? (
                        <span className="chip muted-chip">No metrics parsed</span>
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
                        await correctFact({
                          project_id: projectId,
                          fact_key: 'baseline_accuracy',
                          value: Number(baselineEdit),
                        })
                      })
                    }
                  >
                    Approve new baseline
                  </button>
                </div>
              </article>

              {next?.requires_approval && (
                <article className="panel approval-panel">
                  <h2>Supervisor approval</h2>
                  <p className="decision-line">
                    <span className="mono">{snapshot.pending_approval?.decision_type}</span>
                    {' — '}
                    {snapshot.pending_approval?.rationale}
                  </p>
                  <textarea
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                    placeholder="Supervisor comment (optional)"
                  />
                  <div className="actions">
                    <button
                      className="btn primary"
                      disabled={busy}
                      onClick={() =>
                        withBusy('Decision approved', async () => {
                          await approveDecision({
                            project_id: projectId,
                            approved: true,
                            comment,
                          })
                          setComment('')
                        })
                      }
                    >
                      Approve
                    </button>
                    <button
                      className="btn ghost-danger"
                      disabled={busy}
                      onClick={() =>
                        withBusy('Decision rejected', async () => {
                          await approveDecision({
                            project_id: projectId,
                            approved: false,
                            comment,
                          })
                          setComment('')
                        })
                      }
                    >
                      Reject
                    </button>
                  </div>
                </article>
              )}
            </section>

            <section className="stack">
              <article className="panel">
                <div className="tabs">
                  {(
                    [
                      ['log', 'Action log'],
                      ['runs', 'Runs'],
                      ['decisions', 'Decisions'],
                      ['facts', 'Fact history'],
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
                      <ul className="timeline">
                        {snapshot.action_log.slice(0, 12).map((a) => (
                          <li key={a.id}>
                            <div className="timeline-main">
                              <span className={`pill ${statusClass(a.outcome)}`}>{a.outcome}</span>
                              <span className="mono">
                                {a.event_type}
                                {a.tool_name ? ` · ${a.tool_name}` : ''}
                              </span>
                            </div>
                            <div className="timeline-meta mono">
                              {shortTime(a.created_at)}
                              {a.error ? ` · ${a.error}` : ''}
                            </div>
                          </li>
                        ))}
                      </ul>
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
              </article>

              <article className="panel tip-panel">
                <h2>Viva demo path</h2>
                <ol className="demo-list">
                  <li>Onboard project</li>
                  <li>Run one cycle (incomplete / fail)</li>
                  <li>Resume after restart</li>
                  <li>Correct baseline, run again</li>
                  <li>Inspect action log + approve</li>
                </ol>
              </article>
            </section>
          </div>
        </>
      )}
    </div>
  )
}
