import type { AgentSnapshot } from './types'
import type { StoreSnapshot } from './types'

export type CycleOptions = {
  use_memory?: boolean
  idempotency_key?: string
  force_sim_status?: string
  plant_untrusted?: boolean
  simulate_tool_failure?: boolean
  skip_approval_gate?: boolean
  deterministic?: boolean | null
  runner_mode?: 'simulator' | 'real'
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  })
  if (!res.ok) {
    const detail = await res.text()
    throw new Error(detail || `Request failed (${res.status})`)
  }
  return res.json() as Promise<T>
}

export function fetchState(projectId = 'demo') {
  return request<AgentSnapshot>(`/api/state?project_id=${encodeURIComponent(projectId)}`)
}

export function fetchStore(projectId = 'demo') {
  return request<StoreSnapshot>(`/api/store?project_id=${encodeURIComponent(projectId)}`)
}

export async function downloadReport(projectId = 'demo') {
  const res = await fetch(`/api/report?project_id=${encodeURIComponent(projectId)}`)
  if (!res.ok) {
    throw new Error((await res.text()) || `Report request failed (${res.status})`)
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `research-report-${projectId || 'project'}.html`
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

export function onboardProject(projectId: string, baseline = 0.75) {
  return request<{ ok: boolean; snapshot: AgentSnapshot }>('/api/onboard', {
    method: 'POST',
    body: JSON.stringify({ project_id: projectId, baseline_accuracy: baseline }),
  })
}

export function runFullDemo(projectId = 'demo', maxCycles = 3) {
  return request<{ ok: boolean; snapshot: AgentSnapshot }>('/api/demo', {
    method: 'POST',
    body: JSON.stringify({ project_id: projectId, max_cycles: maxCycles }),
  })
}

export function runOneCycle(projectId = 'demo', options: CycleOptions = {}) {
  return request<{ ok: boolean; result: Record<string, unknown>; snapshot: AgentSnapshot }>(
    '/api/cycle',
    {
      method: 'POST',
      body: JSON.stringify({ project_id: projectId, ...options }),
    },
  )
}

export function resumeProject(projectId = 'demo') {
  return request<{ ok: boolean; result: Record<string, unknown>; snapshot: AgentSnapshot }>(
    `/api/resume?project_id=${encodeURIComponent(projectId)}`,
    { method: 'POST' },
  )
}

export function approveDecision(payload: {
  project_id: string
  approved: boolean
  comment?: string
  override_params?: Record<string, unknown>
}) {
  return request<{ ok: boolean; snapshot: AgentSnapshot }>('/api/approve', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function correctFact(payload: {
  project_id: string
  fact_key: string
  value: number | string
}) {
  return request<{ ok: boolean; snapshot: AgentSnapshot }>('/api/correct', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
