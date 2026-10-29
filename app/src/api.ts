import type { AgentSnapshot } from './types'

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

export function runOneCycle(projectId = 'demo', useMemory = true) {
  return request<{ ok: boolean; snapshot: AgentSnapshot }>('/api/cycle', {
    method: 'POST',
    body: JSON.stringify({ project_id: projectId, use_memory: useMemory }),
  })
}

export function resumeProject(projectId = 'demo') {
  return request<{ ok: boolean; snapshot: AgentSnapshot }>(
    `/api/resume?project_id=${encodeURIComponent(projectId)}`,
    { method: 'POST' },
  )
}

export function approveDecision(payload: {
  project_id: string
  approved: boolean
  comment?: string
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
