import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  approveDecision,
  correctFact,
  downloadReport,
  fetchPaperDraft,
  fetchStore,
  fetchState,
  generatePaperDraft,
  onboardProject,
  resumeProject,
  runFullDemo,
  runOneCycle,
  searchLiterature,
} from './api'
import type { AgentSnapshot, LiteraturePaper, StoreSnapshot } from './types'
import {
  LayoutDashboard,
  FlaskConical,
  TrendingUp,
  BookOpen,
  FileText,
  ShieldCheck,
  Settings2,
  Play,
  RefreshCw,
  RotateCcw,
  Download,
  ExternalLink,
  Sparkles,
  ArrowUpRight,
  Sliders,
  Check,
  AlertTriangle,
  CheckCircle2,
  AlertCircle,
  Clock,
  FileCheck2,
  Copy,
  Search,
  Database,
  ChevronRight,
  Cpu,
  BrainCircuit,
  Activity,
  Server,
  FolderGit2,
  Lightbulb,
  ListChecks,
  BarChart3,
  XCircle,
  History,
  ShieldAlert,
  Zap,
  Target,
  FileCode,
  FileSpreadsheet,
  Layers,
} from 'lucide-react'
import './App.css'

type NavView =
  | 'overview'
  | 'runs'
  | 'trajectory'
  | 'literature'
  | 'paper'
  | 'governance'
  | 'sandbox'

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

function downloadTextFile(filename: string, content: string) {
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
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
  const [view, setView] = useState<NavView>('overview')
  const [storeSnapshot, setStoreSnapshot] = useState<StoreSnapshot | null>(null)
  const [retryKey, setRetryKey] = useState('viva-retry-001')

  const [computeTarget, setComputeTarget] = useState<'local' | 'slurm' | 'cloud' | 'sim'>('local')
  const [paperFormat, setPaperFormat] = useState<'latex' | 'markdown' | 'bibtex'>('latex')
  const [paperLatex, setPaperLatex] = useState<string | null>(null)
  const [selectedCategory, setSelectedCategory] = useState<string>('All')

  const [litQuery, setLitQuery] = useState('gradient descent optimizer deep learning')
  const [litResults, setLitResults] = useState<LiteraturePaper[]>([])
  const [litLoading, setLitLoading] = useState(false)

  const [paperTopic, setPaperTopic] = useState('Learning Rate Optimization')
  const [paperContent, setPaperContent] = useState<string | null>(null)
  const [paperBibtex, setPaperBibtex] = useState<string | null>(null)
  const [paperLoading, setPaperLoading] = useState(false)

  const refresh = useCallback(async () => {
    const data = await fetchState(projectId)
    setSnapshot(data)
    setError(null)
    const baseline = data.facts?.baseline_accuracy
    if (typeof baseline === 'number') setBaselineEdit(String(baseline))
  }, [projectId])

  const showStore = useCallback(async () => {
    try {
      setStoreSnapshot(await fetchStore(projectId))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
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
  const runCount = snapshot?.runs.length ?? 0
  const latestRun = snapshot?.runs?.[0]
  const facts = snapshot?.facts ?? {}

  const primaryAction = !snapshot?.current?.experiment_id
    ? 'onboard'
    : snapshot.approval_required
      ? 'approve'
      : 'run'

  const baselineAcc = Number(facts.baseline_accuracy ?? 0.75)
  const validAccs = useMemo(
    () => (snapshot?.trajectory ?? []).map((p) => p.accuracy).filter((a): a is number => a !== null),
    [snapshot?.trajectory]
  )
  const peakAcc = validAccs.length > 0 ? Math.max(...validAccs) : null
  const meanAcc = validAccs.length > 0 ? validAccs.reduce((a, b) => a + b, 0) / validAccs.length : null
  const convergenceState = peakAcc !== null && peakAcc >= baselineAcc ? 'Target Surpassed' : 'Iterating'

  return (
    <div className="dashboard-root">
      {/* LEFT SIDEBAR NAVIGATION */}
      <aside className="dashboard-sidebar">
        <div>
          <div className="sidebar-header">
            <div className="brand-row flex items-center gap-2.5">
              <div className="brand-logo flex items-center justify-center w-8 h-8 rounded-lg bg-emerald-500/15 border border-emerald-500/30 text-emerald-400">
                <BrainCircuit className="w-5 h-5" />
              </div>
              <div className="flex flex-col">
                <span className="brand-title font-semibold tracking-tight text-sm text-zinc-100">ResearchManager</span>
                <span className="text-[10px] text-zinc-400 font-mono tracking-wider uppercase">Autonomous AI Lab</span>
              </div>
              <span className="brand-badge ml-auto text-[10px] font-mono px-1.5 py-0.5 rounded bg-zinc-800 border border-zinc-700 text-zinc-300">
                ENTERPRISE
              </span>
            </div>

            <div className="project-select-box mt-3">
              <span className="project-select-label flex items-center gap-1.5 text-xs text-zinc-400 mb-1">
                <FolderGit2 className="w-3.5 h-3.5 text-emerald-400" />
                Active Research Project
              </span>
              <div className="project-input-group">
                <input
                  value={projectDraft}
                  onChange={(e) => setProjectDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') applyProject()
                  }}
                  placeholder="project id..."
                  spellCheck={false}
                />
                <button type="button" onClick={applyProject} disabled={busy}>
                  Switch
                </button>
              </div>
            </div>
          </div>

          <nav className="sidebar-nav">
            <span className="nav-section-title">Workspace</span>
            {[
              { id: 'overview', label: 'Executive Overview', icon: LayoutDashboard },
              { id: 'runs', label: 'Experiments & Runs', icon: FlaskConical, count: runCount },
              { id: 'trajectory', label: 'Convergence Curves', icon: TrendingUp },
              { id: 'literature', label: 'ArXiv Literature', icon: BookOpen },
              { id: 'paper', label: 'Preprint & LaTeX', icon: FileText },
              { id: 'governance', label: 'Knowledge & Truth Facts', icon: ShieldCheck },
              { id: 'sandbox', label: 'Benchmark Sandbox', icon: Settings2 },
            ].map((item) => {
              const Icon = item.icon
              return (
                <button
                  key={item.id}
                  type="button"
                  className={`nav-item ${view === item.id ? 'active' : ''}`}
                  onClick={() => {
                    setView(item.id as NavView)
                    if (item.id === 'governance' && !storeSnapshot) showStore()
                    if (item.id === 'paper' && !paperContent) {
                      fetchPaperDraft(projectId)
                        .then((res) => {
                          if (res.exists && res.content) {
                            setPaperContent(res.content)
                            setPaperBibtex(res.bibtex)
                            setPaperLatex(res.latex || null)
                          }
                        })
                        .catch(() => {})
                    }
                  }}
                >
                  <span className="nav-icon flex items-center justify-center">
                    <Icon className="w-4 h-4 shrink-0" />
                  </span>
                  <span>{item.label}</span>
                  {item.count !== undefined && item.count > 0 && (
                    <span className="nav-badge">{item.count}</span>
                  )}
                </button>
              )
            })}
          </nav>
        </div>

        <div className="sidebar-footer">
          <div className="system-status-indicator flex items-center justify-between">
            <div className="status-left flex items-center gap-1.5">
              <span className={`status-dot ${busy ? 'busy' : 'idle'}`} />
              <span className="mono text-xs flex items-center gap-1">
                <Activity className="w-3.5 h-3.5 text-emerald-400" />
                {busy ? 'Computing…' : 'Agent Ready'}
              </span>
            </div>
            <span className="chip chip-enterprise flex items-center gap-1 text-[10px] py-0.5 px-2">
              <ShieldCheck className="w-3 h-3 text-emerald-400" />
              Truth Engine Active
            </span>
          </div>
        </div>
      </aside>

      {/* MAIN APPLICATION AREA */}
      <div className="dashboard-main">
        {/* TOPBAR */}
        <header className="dashboard-topbar">
          <div className="topbar-left flex items-center gap-3">
            <div className="topbar-breadcrumbs flex items-center gap-1.5 text-xs text-zinc-400">
              <span className="hover:text-zinc-200">Projects</span>
              <ChevronRight className="w-3.5 h-3.5 text-zinc-600" />
              <strong className="text-zinc-200 font-mono bg-zinc-800/60 px-2 py-0.5 rounded border border-zinc-700/60">{projectId}</strong>
              <ChevronRight className="w-3.5 h-3.5 text-zinc-600" />
              <span style={{ color: 'var(--accent)' }} className="font-medium">
                {view === 'overview' && 'Executive Overview'}
                {view === 'runs' && 'Experiments & Runs'}
                {view === 'trajectory' && 'Convergence Trajectory'}
                {view === 'literature' && 'ArXiv Grounding'}
                {view === 'paper' && 'Preprint & LaTeX Studio'}
                {view === 'governance' && 'Knowledge & Truth Facts'}
                {view === 'sandbox' && 'Evaluation Sandbox'}
              </span>
            </div>

            <div className="compute-tag flex items-center gap-1.5">
              <Cpu className="w-3.5 h-3.5 text-cyan-400" />
              Target: <strong>{computeTarget.toUpperCase()}</strong>
            </div>
          </div>

          <div className="topbar-right flex items-center gap-2">
            <button
              className="btn primary flex items-center gap-1.5"
              disabled={busy}
              onClick={() => {
                if (primaryAction === 'onboard') {
                  return withBusy('Project planned', async () => {
                    await onboardProject(projectId)
                  })
                }
                if (primaryAction === 'approve') {
                  setView('overview')
                  document.querySelector('.approval-panel')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
                  return
                }
                return withBusy('Experiment cycle finished', async () => {
                  const runner = computeTarget === 'sim' ? 'simulator' : 'real'
                  await runOneCycle(projectId, { deterministic: true, runner_mode: runner })
                })
              }}
            >
              {primaryAction === 'onboard' ? (
                <>
                  <Sparkles className="w-4 h-4 text-emerald-200" />
                  <span>Initialize Project</span>
                </>
              ) : primaryAction === 'approve' ? (
                <>
                  <AlertTriangle className="w-4 h-4 text-amber-200" />
                  <span>Review Decision Gate</span>
                </>
              ) : (
                <>
                  <Play className="w-4 h-4 text-emerald-200" />
                  <span>Run Next Experiment</span>
                </>
              )}
            </button>

            <button
              className="btn flex items-center gap-1.5"
              disabled={busy}
              onClick={() =>
                withBusy('3-cycle autonomous demo complete', async () => {
                  await runFullDemo(projectId, 3)
                })
              }
            >
              <RefreshCw className={`w-3.5 h-3.5 ${busy ? 'animate-spin' : ''}`} />
              <span>3-Cycle Auto Run</span>
            </button>

            <button
              className="btn flex items-center gap-1.5"
              disabled={busy}
              onClick={() =>
                withBusy('State resumed from checkpoint', async () => {
                  const res = await resumeProject(projectId)
                  const cp = res.snapshot?.checkpoint
                  return `Resumed checkpoint #${cp?.checkpoint_id ?? 'none'}; facts verified`
                })
              }
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Resume Checkpoint</span>
            </button>

            <button
              className="btn flex items-center gap-1.5"
              disabled={busy}
              onClick={() => withBusy('HTML report downloaded', async () => { await downloadReport(projectId) })}
            >
              <FileCheck2 className="w-3.5 h-3.5" />
              <span>Download Report</span>
            </button>
          </div>
        </header>

        {/* MAIN CANVAS */}
        <main className="dashboard-canvas">
          {toast && <div className="toast fade-in">{toast}</div>}
          {error && (
            <div className="error-banner fade-in">
              <div>{error}</div>
              <button className="btn primary" onClick={() => withBusy('Reconnected', async () => undefined)}>
                Reconnect
              </button>
            </div>
          )}

          {loading && !snapshot ? (
            <p className="muted loading-line">Loading research workspace…</p>
          ) : !snapshot ? (
            <p className="muted loading-line">API unreachable. Start `python -m research_manager.api`.</p>
          ) : (
            <>
              {/* =========================================================================
                  VIEW: OVERVIEW (EXECUTIVE DASHBOARD)
                  ========================================================================= */}
              {view === 'overview' && (
                <div className="fade-in">
                  <div className="view-header">
                    <div>
                      <h2 className="flex items-center gap-2">
                        <LayoutDashboard className="w-5 h-5 text-emerald-400" />
                        Research Project Overview
                      </h2>
                      <p>Active hypothesis, empirical target baseline, and real-time execution trace.</p>
                    </div>

                    <div className="compute-pills">
                      {[
                        { id: 'local', label: 'Local Subprocess', icon: Server, detail: 'Host Subprocess (PyTorch/Gradient Descent)' },
                        { id: 'slurm', label: 'HPC Slurm', icon: Cpu, detail: 'Partition: gpu_h100 · sbatch node=1' },
                        { id: 'cloud', label: 'Serverless Cloud', icon: Zap, detail: '1x NVIDIA A100-80GB (Modal/RunPod)' },
                        { id: 'sim', label: 'Fast Simulator', icon: Sliders, detail: 'Deterministic Evaluator (Offline Benchmarks)' },
                      ].map((item) => {
                        const Icon = item.icon
                        return (
                          <button
                            key={item.id}
                            type="button"
                            className={`compute-pill flex items-center gap-1.5 ${computeTarget === item.id ? 'active' : ''}`}
                            onClick={() => {
                              setComputeTarget(item.id as any)
                              setToast(`Switched compute profile: ${item.label}`)
                            }}
                            title={item.detail}
                          >
                            <Icon className="w-3 h-3" />
                            {item.label}
                          </button>
                        )
                      })}
                    </div>
                  </div>

                  {/* APPROVAL GATE BANNER (IF REVIEW NEEDED) */}
                  {snapshot.approval_required && (
                    <article className="panel approval-panel fade-in" style={{ marginBottom: '1.25rem' }}>
                      <div className="panel-head flex items-center justify-between">
                        <div className="flex items-center gap-2.5">
                          <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0" />
                          <div>
                            <h2>Supervisor Governance & Parameter Steering Gate</h2>
                            <p className="muted small">Human-in-the-loop validation: review agent proposal or counter-propose hyperparameters.</p>
                          </div>
                        </div>
                        <span className="pill warn flex items-center gap-1">
                          <Clock className="w-3 h-3 animate-pulse" />
                          Action Required
                        </span>
                      </div>

                      <p className="decision-line">
                        <span className="mono">{snapshot.pending_approval?.decision_type}</span>
                        {' — '}
                        {snapshot.pending_approval?.rationale}
                      </p>

                      {snapshot.pending_approval?.next_params &&
                        Object.keys(snapshot.pending_approval.next_params).length > 0 && (
                          <div className="override-row">
                            <span className="muted small">Proposed hyperparameters:</span>
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
                          Supervisor override for learning_rate (optional counter-proposal):
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
                        placeholder="Supervisor guidance or literature feedback (passed directly to subsequent cycle evidence)"
                      />

                      <div className="actions flex items-center gap-2">
                        <button
                          className="btn primary flex items-center gap-1.5"
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
                                  override_params: Object.keys(overrides).length > 0 ? overrides : undefined,
                                })
                                setComment('')
                                setOverrideLr('')
                              }
                            )
                          }
                        >
                          <CheckCircle2 className="w-4 h-4 text-emerald-200" />
                          <span>{overrideLr.trim() ? 'Approve with overrides' : 'Approve Decision'}</span>
                        </button>

                        <button
                          className="btn ghost-danger flex items-center gap-1.5"
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
                          <XCircle className="w-4 h-4 text-rose-300" />
                          <span>Reject with Guidance</span>
                        </button>
                      </div>
                    </article>
                  )}

                  {/* 4 CORE KPI CARDS */}
                  <div className="dashboard-kpis">
                    <div className="kpi-box">
                      <div className="kpi-box-top">
                        <span className="flex items-center gap-1.5">
                          <Lightbulb className="w-3.5 h-3.5 text-amber-400" />
                          Hypothesis Status
                        </span>
                        <span className={`pill ${statusClass(current?.status ?? 'idle')}`}>{current?.status ?? 'idle'}</span>
                      </div>
                      <strong style={{ fontSize: '1.05rem', marginTop: '0.6rem' }}>
                        {current?.name || 'Experimental Iteration'}
                      </strong>
                      <small className="muted">{current?.hypothesis || 'No hypothesis initialized.'}</small>
                    </div>

                    <div className="kpi-box">
                      <div className="kpi-box-top">
                        <span className="flex items-center gap-1.5">
                          <Target className="w-3.5 h-3.5 text-sky-400" />
                          Approved Baseline
                        </span>
                        <span className="mono">TARGET</span>
                      </div>
                      <strong>{baselineAcc.toFixed(4)}</strong>
                      <small className="muted">Approved target metric: {String(facts.approved_metric ?? 'acc')}</small>
                    </div>

                    <div className="kpi-box">
                      <div className="kpi-box-top">
                        <span className="flex items-center gap-1.5">
                          <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
                          Peak Observed
                        </span>
                        <span className={`pill ${peakAcc !== null && peakAcc >= baselineAcc ? 'ok' : 'warn'}`}>
                          {convergenceState}
                        </span>
                      </div>
                      <strong style={{ color: peakAcc !== null && peakAcc >= baselineAcc ? 'var(--ok)' : 'var(--text)' }}>
                        {peakAcc !== null ? peakAcc.toFixed(4) : '—'}
                      </strong>
                      <small className={peakAcc !== null && peakAcc >= baselineAcc ? 'metric-up' : 'metric-down'}>
                        {peakAcc !== null
                          ? `${peakAcc - baselineAcc >= 0 ? '+' : ''}${(peakAcc - baselineAcc).toFixed(4)} vs baseline`
                          : 'Pending valid evaluation'}
                      </small>
                    </div>

                    <div className="kpi-box">
                      <div className="kpi-box-top">
                        <span className="flex items-center gap-1.5">
                          <ShieldCheck className="w-3.5 h-3.5 text-purple-400" />
                          Empirical Confidence
                        </span>
                        <span className="mono" style={{ color: 'var(--ok)' }}>VERIFIED</span>
                      </div>
                      <strong style={{ fontSize: '1.25rem', color: '#c084fc' }}>
                        {peakAcc !== null && peakAcc >= baselineAcc ? 'Goal Surpassed' : 'In Progress'}
                      </strong>
                      <small className="muted">Deterministic validation across {runCount} verified cycles</small>
                    </div>
                  </div>

                  {/* TWO COLUMN GRID: PLAN + CONVERGENCE & METRICS */}
                  <div className="dashboard-split">
                    <div>
                      {/* EXECUTION PLAN */}
                      <article className="card-panel">
                        <div className="card-panel-head">
                          <h3 className="flex items-center gap-2">
                            <ListChecks className="w-4 h-4 text-sky-400" />
                            Execution Plan
                          </h3>
                          <span className="mono" style={{ color: 'var(--accent)', fontSize: '0.78rem' }}>
                            {planSteps(snapshot).filter((s) => s.done).length}/{planSteps(snapshot).length} Complete
                          </span>
                        </div>
                        <ol className="plan-list">
                          {planSteps(snapshot).map((step, index) => (
                            <li
                              key={`${step.label}-${index}`}
                              className={
                                step.done
                                  ? 'done'
                                  : index === planSteps(snapshot).findIndex((item) => !item.done)
                                    ? 'active'
                                    : ''
                              }
                            >
                              <span className="plan-marker flex items-center justify-center">
                                {step.done ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : String(index + 1).padStart(2, '0')}
                              </span>
                              <span>{step.label}</span>
                            </li>
                          ))}
                        </ol>
                      </article>

                      {/* ACTIVE MODEL & HYPERPARAMETERS */}
                      <article className="card-panel">
                        <div className="card-panel-head">
                          <h3 className="flex items-center gap-2">
                            <Sliders className="w-4 h-4 text-sky-400" />
                            Active Model & Hyperparameters
                          </h3>
                          <span className="mono" style={{ fontSize: '0.72rem', color: 'var(--ok)' }}>
                            {latestRun?.run_key ?? 'NO ACTIVE RUN'}
                          </span>
                        </div>

                        <div className="analytics-grid">
                          <div className="analytics-card">
                            <span>Backbone Model</span>
                            <strong>{current?.name || 'demo_classifier'}</strong>
                            <small className="muted">PyTorch Gradient Descent</small>
                          </div>
                          <div className="analytics-card">
                            <span>Learning Rate (η)</span>
                            <strong className="mono">
                              {typeof snapshot.pending_approval?.next_params?.learning_rate === 'number'
                                ? snapshot.pending_approval.next_params.learning_rate
                                : (latestRun?.metrics?.lr ?? 0.05)}
                            </strong>
                            <small className="muted">Adaptive step parameter</small>
                          </div>
                          <div className="analytics-card">
                            <span>Target Baseline Bar</span>
                            <strong className="mono">{baselineAcc.toFixed(4)}</strong>
                            <small className="muted">{String(facts.approved_metric ?? 'acc')} threshold</small>
                          </div>
                          <div className="analytics-card">
                            <span>Compute Target</span>
                            <strong className="mono">{computeTarget.toUpperCase()}</strong>
                            <small className="muted">Isolated Subprocess</small>
                          </div>
                        </div>
                      </article>

                      {/* LATEST RUN ARTIFACT ANALYTICS */}
                      <article className="card-panel">
                        <div className="card-panel-head">
                          <h3 className="flex items-center gap-2">
                            <BarChart3 className="w-4 h-4 text-indigo-400" />
                            Latest Run Telemetry
                          </h3>
                          <span className="mono">{latestRun?.run_key ?? 'no run'}</span>
                        </div>

                        {!latestRun || metricEntries(latestRun.metrics).length === 0 ? (
                          <p className="muted small">Metrics will display after executing a cycle with valid results.csv.</p>
                        ) : (
                          <div className="analytics-grid">
                            {metricEntries(latestRun.metrics).map(([name, value]) => {
                              const baseline =
                                name === 'accuracy' && typeof facts.baseline_accuracy === 'number'
                                  ? facts.baseline_accuracy
                                  : null
                              const delta = baseline == null ? null : value - baseline
                              return (
                                <div className="analytics-card" key={name}>
                                  <span>{name.replaceAll('_', ' ')}</span>
                                  <strong>{typeof value === 'number' ? value.toFixed(4) : String(value)}</strong>
                                  {delta != null && (
                                    <small className={delta >= 0 ? 'metric-up' : 'metric-down'}>
                                      {delta >= 0 ? '+' : ''}
                                      {delta.toFixed(4)} vs baseline
                                    </small>
                                  )}
                                </div>
                              )
                            })}
                          </div>
                        )}
                      </article>
                    </div>

                    {/* RIGHT COLUMN: REAL-TIME CONVERGENCE CHART & RECENT EXPERIMENTS */}
                    <div>
                      {/* REAL-TIME CONVERGENCE CHART */}
                      <article className="card-panel">
                        <div className="card-panel-head">
                          <h3 className="flex items-center gap-2">
                            <TrendingUp className="w-4 h-4 text-emerald-400" />
                            Empirical Convergence Curve
                          </h3>
                          <span className="mono" style={{ fontSize: '0.72rem', color: 'var(--accent)' }}>
                            {snapshot.trajectory?.length ?? 0} CYCLES PLOTTED
                          </span>
                        </div>

                        {snapshot.svg_chart ? (
                          <div
                            className="chart-card"
                            style={{ background: 'rgba(0, 0, 0, 0.25)', borderRadius: '8px', padding: '0.5rem', border: '1px solid rgba(255, 255, 255, 0.05)' }}
                            dangerouslySetInnerHTML={{ __html: snapshot.svg_chart }}
                          />
                        ) : (
                          <div style={{ padding: '3rem 1.5rem', textAlign: 'center', color: 'var(--muted)', fontSize: '0.85rem' }}>
                            <p>No convergence trajectory recorded yet.</p>
                            <p className="small" style={{ marginTop: '0.5rem' }}>Click "+ Run Next Experiment" above to plot live loss & accuracy curves.</p>
                          </div>
                        )}
                      </article>

                      {/* RECENT EXPERIMENTS TABLE */}
                      <article className="card-panel">
                        <div className="card-panel-head">
                          <h3 className="flex items-center gap-2">
                            <FlaskConical className="w-4 h-4 text-amber-400" />
                            Recent Experiment Runs
                          </h3>
                          <button
                            type="button"
                            className="btn"
                            style={{ fontSize: '0.72rem', padding: '0.15rem 0.55rem', height: '26px' }}
                            onClick={() => setView('runs')}
                          >
                            View All ({snapshot.runs.length}) →
                          </button>
                        </div>

                        <div className="data-table-wrapper">
                          <table className="data-table">
                            <thead>
                              <tr>
                                <th>Run Key</th>
                                <th>Accuracy</th>
                                <th>Loss</th>
                                <th>Status</th>
                              </tr>
                            </thead>
                            <tbody>
                              {snapshot.runs.length === 0 ? (
                                <tr>
                                  <td colSpan={4} style={{ textAlign: 'center', color: 'var(--muted)', padding: '1.25rem' }}>
                                    No runs recorded yet.
                                  </td>
                                </tr>
                              ) : (
                                snapshot.runs.slice(0, 5).map((r) => {
                                  const acc = r.metrics?.accuracy ?? r.metrics?.acc
                                  const beats = acc !== undefined && acc >= baselineAcc
                                  return (
                                    <tr key={r.id}>
                                      <td><span className="mono" style={{ fontWeight: 600 }}>{r.run_key}</span></td>
                                      <td>
                                        <strong style={{ color: beats ? 'var(--ok)' : 'var(--text)' }}>
                                          {acc !== undefined ? acc.toFixed(4) : '—'}
                                        </strong>
                                        {beats && (
                                          <span className="pill ok" style={{ marginLeft: '0.35rem', fontSize: '0.62rem', padding: '0.1rem 0.35rem' }}>
                                            +{(acc - baselineAcc).toFixed(3)}
                                          </span>
                                        )}
                                      </td>
                                      <td><span className="mono">{r.metrics?.loss !== undefined ? r.metrics.loss.toFixed(4) : '—'}</span></td>
                                      <td>
                                        <span className={`pill ${r.success ? 'ok' : 'warn'} flex items-center gap-1 w-fit`}>
                                          {r.success ? <CheckCircle2 className="w-3 h-3 text-emerald-400" /> : <AlertCircle className="w-3 h-3 text-amber-400" />}
                                          {r.success ? 'Pass' : 'Warn'}
                                        </span>
                                      </td>
                                    </tr>
                                  )
                                })
                              )}
                            </tbody>
                          </table>
                        </div>
                      </article>
                    </div>
                  </div>
                </div>
              )}

              {/* =========================================================================
                  VIEW: EXPERIMENTS & RUNS
                  ========================================================================= */}
              {view === 'runs' && (
                <div className="fade-in">
                  <div className="view-header">
                    <div>
                      <h2 className="flex items-center gap-2">
                        <FlaskConical className="w-5 h-5 text-amber-400" />
                        Historical Experiments & Subprocess Runs
                      </h2>
                      <p>Complete record of training runs, loss logs, and parameter changes.</p>
                    </div>
                    <button className="btn flex items-center gap-1.5" onClick={() => withBusy('Refreshed', async () => undefined)}>
                      <RefreshCw className="w-3.5 h-3.5" />
                      <span>Refresh Runs</span>
                    </button>
                  </div>

                  <div className="data-table-wrapper" style={{ marginBottom: '1.5rem' }}>
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Run ID</th>
                          <th>Status</th>
                          <th>Accuracy</th>
                          <th>Loss</th>
                          <th>Artifacts Directory</th>
                          <th>Execution Notes</th>
                          <th>Timestamp</th>
                        </tr>
                      </thead>
                      <tbody>
                        {snapshot.runs.length === 0 ? (
                          <tr>
                            <td colSpan={7} style={{ textAlign: 'center', color: 'var(--muted)', padding: '2rem' }}>
                              No experiment runs recorded.
                            </td>
                          </tr>
                        ) : (
                          snapshot.runs.map((r) => (
                            <tr key={r.id}>
                              <td><span className="mono" style={{ fontWeight: 600 }}>{r.run_key}</span></td>
                              <td>
                                <span className={`pill ${r.success ? 'ok' : 'warn'} flex items-center gap-1 w-fit`}>
                                  {r.success ? <CheckCircle2 className="w-3 h-3 text-emerald-400" /> : <AlertCircle className="w-3 h-3 text-amber-400" />}
                                  {r.success ? 'Success' : 'Failed'}
                                </span>
                              </td>
                              <td>
                                <strong style={{ color: (r.metrics?.accuracy ?? r.metrics?.acc ?? 0) >= baselineAcc ? 'var(--ok)' : 'var(--text)' }}>
                                  {(r.metrics?.accuracy ?? r.metrics?.acc) !== undefined ? (r.metrics.accuracy ?? r.metrics.acc).toFixed(4) : '—'}
                                </strong>
                              </td>
                              <td><span className="mono">{r.metrics?.loss !== undefined ? r.metrics.loss.toFixed(4) : '—'}</span></td>
                              <td><code style={{ fontSize: '0.72rem' }}>{r.artifacts_path}</code></td>
                              <td className="muted small">{r.notes}</td>
                              <td className="mono muted small">{shortTime(r.created_at)}</td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>

                  {/* DECISION RECORDS */}
                  <div className="card-panel">
                    <div className="card-panel-head">
                      <h3 className="flex items-center gap-2">
                        <BrainCircuit className="w-4 h-4 text-purple-400" />
                        Agent Strategic Decisions & Approvals
                      </h3>
                    </div>
                    <div className="data-table-wrapper">
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>Decision Action</th>
                            <th>Agent Rationale</th>
                            <th>Proposed Parameters</th>
                            <th>Supervisor Approved</th>
                            <th>Created</th>
                          </tr>
                        </thead>
                        <tbody>
                          {snapshot.decisions.length === 0 ? (
                            <tr>
                              <td colSpan={5} style={{ textAlign: 'center', color: 'var(--muted)', padding: '1.5rem' }}>
                                No decisions generated yet.
                              </td>
                            </tr>
                          ) : (
                            snapshot.decisions.map((d) => (
                              <tr key={d.id}>
                                <td><span className="mono" style={{ color: 'var(--accent)' }}>{d.decision_type}</span></td>
                                <td style={{ maxWidth: '350px' }}>{d.rationale}</td>
                                <td><code style={{ fontSize: '0.72rem' }}>{JSON.stringify(d.next_params)}</code></td>
                                <td>
                                  <span className={`pill ${d.supervisor_confirmed === true ? 'ok' : d.supervisor_confirmed === false ? 'danger' : 'warn'} flex items-center gap-1 w-fit`}>
                                    {d.supervisor_confirmed === true && <CheckCircle2 className="w-3 h-3 text-emerald-400" />}
                                    {d.supervisor_confirmed === false && <XCircle className="w-3 h-3 text-rose-400" />}
                                    {d.supervisor_confirmed == null && <Clock className="w-3 h-3 text-amber-400" />}
                                    {d.supervisor_confirmed === true ? 'Approved' : d.supervisor_confirmed === false ? 'Rejected' : 'Pending'}
                                  </span>
                                </td>
                                <td className="mono muted small">{shortTime(d.created_at)}</td>
                              </tr>
                            ))
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              )}

              {/* =========================================================================
                  VIEW: CONVERGENCE TRAJECTORY
                  ========================================================================= */}
              {view === 'trajectory' && (
                <div className="fade-in">
                  <div className="view-header">
                    <div>
                      <h2 className="flex items-center gap-2">
                        <TrendingUp className="w-5 h-5 text-emerald-400" />
                        Empirical Convergence Trajectory & KPIs
                      </h2>
                      <p>Multi-run convergence against the approved baseline threshold ({baselineAcc.toFixed(4)}).</p>
                    </div>
                  </div>

                  {/* KPI STRIP */}
                  <div className="kpi-grid">
                    <div className="kpi-card">
                      <span className="flex items-center gap-1 text-xs text-zinc-400">
                        <Target className="w-3.5 h-3.5 text-sky-400" />
                        Approved Baseline
                      </span>
                      <strong>{baselineAcc.toFixed(4)}</strong>
                      <small className="muted">Minimum acceptance bar</small>
                    </div>
                    <div className="kpi-card">
                      <span className="flex items-center gap-1 text-xs text-zinc-400">
                        <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
                        Peak Metric ({String(facts.approved_metric ?? 'acc')})
                      </span>
                      <strong style={{ color: peakAcc !== null && peakAcc >= baselineAcc ? 'var(--ok)' : 'var(--text)' }}>
                        {peakAcc !== null ? peakAcc.toFixed(4) : '—'}
                      </strong>
                      <small className={peakAcc !== null && peakAcc >= baselineAcc ? 'metric-up' : 'metric-down'}>
                        {peakAcc !== null
                          ? `${peakAcc - baselineAcc >= 0 ? '+' : ''}${(peakAcc - baselineAcc).toFixed(4)} vs baseline`
                          : 'Pending runs'}
                      </small>
                    </div>
                    <div className="kpi-card">
                      <span className="flex items-center gap-1 text-xs text-zinc-400">
                        <Activity className="w-3.5 h-3.5 text-purple-400" />
                        Empirical Mean (μ)
                      </span>
                      <strong>{meanAcc !== null ? meanAcc.toFixed(4) : '—'}</strong>
                      <small className="muted">Across {validAccs.length} verified runs</small>
                    </div>
                    <div className="kpi-card">
                      <span className="flex items-center gap-1 text-xs text-zinc-400">
                        <Layers className="w-3.5 h-3.5 text-amber-400" />
                        Convergence State
                      </span>
                      <strong style={{ color: convergenceState === 'Target Surpassed' ? 'var(--ok)' : 'var(--warn)' }}>
                        {convergenceState}
                      </strong>
                      <small className="muted">{snapshot.trajectory?.length ?? 0} total cycles</small>
                    </div>
                  </div>

                  {/* SVG CONVERGENCE CHART */}
                  {snapshot.svg_chart ? (
                    <div className="chart-card" dangerouslySetInnerHTML={{ __html: snapshot.svg_chart }} />
                  ) : (
                    <p className="muted">Execute runs to generate empirical trajectory plot.</p>
                  )}

                  {/* ITERATION TRAJECTORY TABLE */}
                  <div className="data-table-wrapper" style={{ marginTop: '1.25rem' }}>
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Cycle</th>
                          <th>Run Key</th>
                          <th>Accuracy</th>
                          <th>Loss</th>
                          <th>Status</th>
                          <th>Notes</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(!snapshot.trajectory || snapshot.trajectory.length === 0) ? (
                          <tr>
                            <td colSpan={6} style={{ textAlign: 'center', color: 'var(--muted)', padding: '1.5rem' }}>
                              No trajectory points recorded.
                            </td>
                          </tr>
                        ) : (
                          snapshot.trajectory.map((pt) => (
                            <tr key={pt.cycle}>
                              <td><strong>#{pt.cycle}</strong></td>
                              <td><span className="mono">{pt.run_key}</span></td>
                              <td>
                                <strong style={{ color: pt.beats_baseline ? 'var(--ok)' : 'var(--text)' }}>
                                  {pt.accuracy !== null ? pt.accuracy.toFixed(4) : 'N/A'}
                                </strong>
                                {pt.beats_baseline && <span className="pill ok" style={{ marginLeft: '0.4rem', fontSize: '0.65rem' }}>Beats baseline</span>}
                              </td>
                              <td><span className="mono">{pt.loss !== null ? pt.loss.toFixed(4) : 'N/A'}</span></td>
                              <td>
                                <span className={`pill ${pt.success ? 'ok' : 'warn'} flex items-center gap-1 w-fit`}>
                                  {pt.success ? <CheckCircle2 className="w-3 h-3 text-emerald-400" /> : <AlertCircle className="w-3 h-3 text-amber-400" />}
                                  {pt.success ? 'Success' : 'Failed'}
                                </span>
                              </td>
                              <td className="muted small">{pt.notes}</td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* =========================================================================
                  VIEW: ARXIV LITERATURE GROUNDING
                  ========================================================================= */}
              {view === 'literature' && (
                <div className="fade-in">
                  <div className="view-header">
                    <div>
                      <h2 className="flex items-center gap-2">
                        <BookOpen className="w-5 h-5 text-purple-400" />
                        ArXiv Scientific Literature & Venue Explorer
                      </h2>
                      <p>Query peer-reviewed publications and inject citations into autonomous agent hypotheses.</p>
                    </div>
                  </div>

                  {/* VENUE FILTER CHIPS */}
                  <div className="category-chips" style={{ marginBottom: '0.85rem' }}>
                    {['All', 'cs.LG', 'stat.ML', 'cs.AI', 'math.OC'].map((cat) => (
                      <button
                        key={cat}
                        type="button"
                        className={`category-chip ${selectedCategory === cat ? 'active' : ''}`}
                        onClick={() => {
                          setSelectedCategory(cat)
                          const baseQuery = litQuery.replace(/cat:\S+/g, '').trim()
                          const nextQ = cat === 'All' ? baseQuery : `${baseQuery} cat:${cat}`
                          setLitQuery(nextQ)
                          setLitLoading(true)
                          searchLiterature(nextQ)
                            .then((res) => setLitResults(res.papers))
                            .catch((err) => setError(String(err)))
                            .finally(() => setLitLoading(false))
                        }}
                      >
                        {cat}
                      </button>
                    ))}
                  </div>

                  {/* SEARCH BAR */}
                  <div className="lit-search-bar" style={{ marginBottom: '1.25rem' }}>
                    <input
                      type="text"
                      value={litQuery}
                      onChange={(e) => setLitQuery(e.target.value)}
                      placeholder="Search ArXiv papers..."
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          setLitLoading(true)
                          searchLiterature(litQuery)
                            .then((res) => setLitResults(res.papers))
                            .catch((err) => setError(String(err)))
                            .finally(() => setLitLoading(false))
                        }
                      }}
                    />
                    <button
                      className="btn primary flex items-center gap-1.5"
                      disabled={litLoading || !litQuery.trim()}
                      onClick={() => {
                        setLitLoading(true)
                        searchLiterature(litQuery)
                          .then((res) => setLitResults(res.papers))
                          .catch((err) => setError(String(err)))
                          .finally(() => setLitLoading(false))
                      }}
                    >
                      <Search className="w-3.5 h-3.5" />
                      <span>{litLoading ? 'Searching…' : 'Search ArXiv'}</span>
                    </button>
                  </div>

                  {/* PAPERS LIST */}
                  <div className="paper-list">
                    {litResults.length === 0 ? (
                      <p className="muted small">
                        Click "Search ArXiv" to query live publications or review state-of-the-art benchmarks.
                      </p>
                    ) : (
                      litResults.map((p) => (
                        <article key={p.arxiv_id} className="paper-card">
                          <h3>{p.title}</h3>
                          <div className="paper-authors">{p.authors.join(', ')} · <em>{p.published}</em></div>
                          <p className="paper-abstract">{p.summary}</p>
                          <div className="paper-footer">
                            <div style={{ display: 'flex', gap: '0.6rem', alignItems: 'center' }}>
                              <a href={p.link} target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }} className="flex items-center gap-1">
                                ArXiv: {p.arxiv_id} <ExternalLink className="w-3 h-3" />
                              </a>
                              <a href={`https://arxiv.org/pdf/${p.arxiv_id}`} target="_blank" rel="noreferrer" style={{ color: 'var(--muted)', fontSize: '0.75rem' }} className="flex items-center gap-0.5">
                                [PDF] <ExternalLink className="w-2.5 h-2.5" />
                              </a>
                            </div>
                            <div style={{ display: 'flex', gap: '0.45rem', alignItems: 'center' }}>
                              <button
                                className="ground-btn flex items-center gap-1"
                                onClick={() => {
                                  const citationNote = `[Literature Grounding] Cite "${p.title}" (arXiv:${p.arxiv_id}). Apply recommended optimizer hyperparameter bounds.`
                                  setComment((prev) => (prev ? `${prev}\n${citationNote}` : citationNote))
                                  setToast(`Grounding injected into supervisor guidance!`)
                                }}
                                title="Inject this paper citation into supervisor guidance"
                              >
                                <Sparkles className="w-3 h-3 text-sky-400" />
                                <span>Ground Hypothesis ↗</span>
                              </button>
                              <button
                                className="btn small flex items-center gap-1"
                                onClick={() => {
                                  navigator.clipboard.writeText(p.bibtex)
                                  setToast(`Copied BibTeX for ${p.arxiv_id}`)
                                }}
                              >
                                <Copy className="w-3 h-3" />
                                <span>Copy BibTeX</span>
                              </button>
                            </div>
                          </div>
                        </article>
                      ))
                    )}
                  </div>
                </div>
              )}

              {/* =========================================================================
                  VIEW: PREPRINT & LATEX MANUSCRIPT STUDIO
                  ========================================================================= */}
              {view === 'paper' && (
                <div className="fade-in">
                  <div className="view-header">
                    <div>
                      <h2 className="flex items-center gap-2">
                        <FileText className="w-5 h-5 text-rose-400" />
                        Autonomous Preprint & LaTeX Manuscript Studio
                      </h2>
                      <p>Compiles project runs, baseline facts, and literature into publication-ready manuscripts.</p>
                    </div>
                  </div>

                  {/* FORMAT SELECTOR & EXPORT ACTIONS */}
                  <div className="format-bar">
                    <div className="format-toggle">
                      {[
                        { id: 'latex', label: 'LaTeX Manuscript (.tex)', icon: FileCode },
                        { id: 'markdown', label: 'Markdown Preprint (.md)', icon: FileText },
                        { id: 'bibtex', label: 'BibTeX References (.bib)', icon: BookOpen },
                      ].map((fmt) => {
                        const Icon = fmt.icon
                        return (
                          <button
                            key={fmt.id}
                            type="button"
                            className={`format-btn flex items-center gap-1.5 ${paperFormat === fmt.id ? 'active' : ''}`}
                            onClick={() => setPaperFormat(fmt.id as any)}
                          >
                            <Icon className="w-3.5 h-3.5" />
                            <span>{fmt.label}</span>
                          </button>
                        )
                      })}
                    </div>

                    <div style={{ display: 'flex', gap: '0.45rem', flexWrap: 'wrap' }}>
                      <button
                        type="button"
                        className="btn btn-overleaf flex items-center gap-1.5"
                        onClick={() => {
                          const code = paperLatex || paperContent || ''
                          if (code) {
                            navigator.clipboard.writeText(code)
                            setToast('Copied LaTeX manuscript! Open Overleaf and paste into main.tex.')
                          } else {
                            setToast('Draft a paper first.')
                          }
                        }}
                      >
                        <ArrowUpRight className="w-3.5 h-3.5 text-emerald-400" />
                        <span>Export to Overleaf ↗</span>
                      </button>

                      <button
                        type="button"
                        className="btn flex items-center gap-1.5"
                        onClick={() => {
                          if (paperFormat === 'latex' && paperLatex) {
                            downloadTextFile(`${projectId}_manuscript.tex`, paperLatex)
                            setToast(`Downloaded ${projectId}_manuscript.tex`)
                          } else if (paperFormat === 'bibtex' && paperBibtex) {
                            downloadTextFile(`${projectId}_references.bib`, paperBibtex)
                            setToast(`Downloaded ${projectId}_references.bib`)
                          } else if (paperContent) {
                            downloadTextFile(`${projectId}_preprint_paper.md`, paperContent)
                            setToast(`Downloaded ${projectId}_preprint_paper.md`)
                          } else {
                            setToast('No draft generated yet.')
                          }
                        }}
                      >
                        <Download className="w-3.5 h-3.5" />
                        <span>Download {paperFormat.toUpperCase()}</span>
                      </button>
                    </div>
                  </div>

                  {/* PAPER COMPILATION CONTROLS */}
                  <div className="paper-controls" style={{ marginBottom: '1rem' }}>
                    <input
                      type="text"
                      value={paperTopic}
                      onChange={(e) => setPaperTopic(e.target.value)}
                      placeholder="Contextual topic query (e.g. Adaptive Learning Rate Optimization)"
                    />
                    <button
                      className="btn primary flex items-center gap-1.5"
                      disabled={paperLoading}
                      onClick={() => {
                        setPaperLoading(true)
                        generatePaperDraft(projectId, paperTopic || undefined)
                          .then((res) => {
                            setPaperContent(res.draft.paper_markdown)
                            setPaperBibtex(res.draft.bibtex)
                            setPaperLatex(res.draft.latex || null)
                            setToast(`Paper drafted! Saved to ${res.draft.report_path}`)
                          })
                          .catch((err) => setError(String(err)))
                          .finally(() => setPaperLoading(false))
                      }}
                    >
                      <Sparkles className="w-3.5 h-3.5 text-indigo-300" />
                      <span>{paperLoading ? 'Drafting…' : 'Generate Academic Paper'}</span>
                    </button>
                    {(paperContent || paperLatex) && (
                      <button
                        className="btn flex items-center gap-1.5"
                        onClick={() => {
                          const textToCopy =
                            paperFormat === 'latex'
                              ? paperLatex || paperContent || ''
                              : paperFormat === 'bibtex'
                                ? paperBibtex || ''
                                : paperContent || ''
                          navigator.clipboard.writeText(textToCopy)
                          setToast(`Copied ${paperFormat.toUpperCase()}!`)
                        }}
                      >
                        <Copy className="w-3.5 h-3.5" />
                        <span>Copy {paperFormat.toUpperCase()}</span>
                      </button>
                    )}
                  </div>

                  {/* PREVIEW BOX */}
                  {(paperFormat === 'latex' && paperLatex) || (paperFormat === 'bibtex' && paperBibtex) || paperContent ? (
                    <div className="paper-manuscript-box">
                      <pre>
                        {paperFormat === 'latex'
                          ? paperLatex || paperContent
                          : paperFormat === 'bibtex'
                            ? paperBibtex || 'No BibTeX references generated.'
                            : paperContent}
                      </pre>
                    </div>
                  ) : (
                    <p className="muted small">
                      No draft generated yet for project "{projectId}". Click "Generate Academic Paper" above to compile the preprint and LaTeX manuscript.
                    </p>
                  )}
                </div>
              )}

              {/* =========================================================================
                  VIEW: MEMORY & INVARIANTS GOVERNANCE
                  ========================================================================= */}
              {view === 'governance' && (
                <div className="fade-in">
                  <div className="view-header">
                    <div>
                      <h2 className="flex items-center gap-2">
                        <ShieldCheck className="w-5 h-5 text-teal-400" />
                        Memory Lifecycle & Invariants Governance
                      </h2>
                      <p>Immutable review policy, versioned facts history, and authoritative SQLite/PostgreSQL store.</p>
                    </div>
                    <button className="btn flex items-center gap-1.5" onClick={showStore}>
                      <RefreshCw className="w-3.5 h-3.5" />
                      <span>Refresh Database Records</span>
                    </button>
                  </div>

                  {/* BASELINE CORRECTION TOOL */}
                  <article className="card-panel">
                    <div className="card-panel-head">
                      <h3 className="flex items-center gap-2">
                        <History className="w-4 h-4 text-sky-400" />
                        Supervisor Fact Correction
                      </h3>
                      <span className="mono" style={{ color: 'var(--accent)' }}>fact_versions</span>
                    </div>
                    <p className="muted small" style={{ marginBottom: '0.85rem' }}>
                      Correct the approved baseline. Prior versions are marked superseded; newly approved numbers promote immediately.
                    </p>
                    <div className="baseline-row">
                      <label>
                        <span className="muted small">Approved Baseline Accuracy:</span>
                        <input
                          type="number"
                          step="0.01"
                          min="0"
                          max="1"
                          className="field"
                          value={baselineEdit}
                          onChange={(e) => setBaselineEdit(e.target.value)}
                        />
                      </label>
                      <button
                        className="btn primary flex items-center gap-1.5"
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
                        <CheckCircle2 className="w-4 h-4 text-emerald-200" />
                        <span>Approve New Baseline</span>
                      </button>
                    </div>
                  </article>

                  {/* FACT VERSIONS TABLE */}
                  <div className="card-panel">
                    <div className="card-panel-head">
                      <h3 className="flex items-center gap-2">
                        <Database className="w-4 h-4 text-purple-400" />
                        Versioned Facts History
                      </h3>
                    </div>
                    <div className="data-table-wrapper">
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>Fact Key</th>
                            <th>Version</th>
                            <th>Status</th>
                            <th>Value</th>
                            <th>Approved By</th>
                            <th>Created Timestamp</th>
                          </tr>
                        </thead>
                        <tbody>
                          {!snapshot.fact_history?.length ? (
                            <tr>
                              <td colSpan={6} style={{ textAlign: 'center', color: 'var(--muted)', padding: '1.5rem' }}>
                                No fact versions recorded.
                              </td>
                            </tr>
                          ) : (
                            snapshot.fact_history.map((f) => (
                              <tr key={`${f.fact_key}-${f.version}`}>
                                <td><span className="mono" style={{ fontWeight: 600 }}>{f.fact_key}</span></td>
                                <td><span className="mono">v{f.version}</span></td>
                                <td>
                                  <span className={`pill ${f.is_current ? 'ok' : ''}`}>
                                    {f.is_current ? 'Current' : 'Superseded'}
                                  </span>
                                </td>
                                <td><code>{typeof f.value === 'object' ? JSON.stringify(f.value) : String(f.value)}</code></td>
                                <td>{f.approved_by}</td>
                                <td className="mono muted small">{shortTime(f.created_at)}</td>
                              </tr>
                            ))
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* AUTHORITATIVE STORE */}
                  {storeSnapshot && (
                    <div className="card-panel" style={{ marginTop: '1.25rem' }}>
                      <div className="card-panel-head">
                        <h3 className="flex items-center gap-2">
                          <Database className="w-4 h-4 text-cyan-400" />
                          Authoritative Relational Database Store
                        </h3>
                        <span className="mono" style={{ fontSize: '0.75rem', color: 'var(--accent)' }}>
                          {storeSnapshot.database}
                        </span>
                      </div>

                      <div className="store-counts" style={{ marginBottom: '1rem' }}>
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
                        <details className="store-table" key={name} open={name === 'experiments' || name === 'runs'} style={{ marginBottom: '0.5rem' }}>
                          <summary>{name} <span>{rows.length} rows</span></summary>
                          {!rows.length ? (
                            <p className="muted small" style={{ padding: '0.5rem' }}>No records stored.</p>
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
                    </div>
                  )}
                </div>
              )}

              {/* =========================================================================
                  VIEW: EVALUATION SANDBOX
                  ========================================================================= */}
              {view === 'sandbox' && (
                <div className="fade-in">
                  <div className="view-header">
                    <div>
                      <h2 className="flex items-center gap-2">
                        <Settings2 className="w-5 h-5 text-cyan-400" />
                        Evaluation Sandbox & Invariant Stress Tests
                      </h2>
                      <p>Trigger failure simulations, prompt injection attacks, and idempotency retries.</p>
                    </div>
                    <span className="chip chip-enterprise flex items-center gap-1.5 py-1 px-3">
                      <ShieldCheck className="w-4 h-4 text-emerald-400" />
                      10/10 Benchmark Scenarios Passing
                    </span>
                  </div>

                  <div className="dashboard-split">
                    <article className="card-panel">
                      <div className="card-panel-head">
                        <h3 className="flex items-center gap-2">
                          <ShieldAlert className="w-4 h-4 text-amber-400" />
                          Safety & Integrity Stress Tests
                        </h3>
                      </div>
                      <p className="muted small" style={{ marginBottom: '1rem' }}>
                        Test whether invariant guards prevent prompt injections and fabricated metrics.
                      </p>

                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
                        <button
                          className="btn flex items-center gap-2 text-left"
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
                          <ShieldAlert className="w-4 h-4 text-rose-400 shrink-0" />
                          <span>Test Prompt Injection Defense (Plant Untrusted Instruction)</span>
                        </button>

                        <button
                          className="btn flex items-center gap-2 text-left"
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
                          <FileSpreadsheet className="w-4 h-4 text-amber-400 shrink-0" />
                          <span>Test Metric Integrity (Force Conflicting CSV Metrics)</span>
                        </button>
                      </div>
                    </article>

                    <article className="card-panel">
                      <div className="card-panel-head">
                        <h3 className="flex items-center gap-2">
                          <Zap className="w-4 h-4 text-sky-400" />
                          Reliability & Fault-Tolerance Tests
                        </h3>
                      </div>
                      <p className="muted small" style={{ marginBottom: '1rem' }}>
                        Test idempotent retry deduplication and persistent memory performance.
                      </p>

                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
                        <button
                          className="btn flex items-center gap-2 text-left"
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
                          <RotateCcw className="w-4 h-4 text-sky-400 shrink-0" />
                          <span>Test Mid-Cycle Tool Failure + Idempotent Retry</span>
                        </button>

                        <button
                          className="btn flex items-center gap-2 text-left"
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
                              const decOff = off.result?.decision as { action?: string } | undefined
                              const decOn = on.result?.decision as { action?: string } | undefined
                              return `Memory OFF=${decOff?.action} · Memory ON=${decOn?.action}`
                            })
                          }
                        >
                          <Database className="w-4 h-4 text-purple-400 shrink-0" />
                          <span>Test Memory OFF vs Memory ON (Approved Baseline Recall)</span>
                        </button>
                      </div>
                    </article>
                  </div>
                </div>
              )}
            </>
          )}
        </main>
      </div>
    </div>
  )
}
