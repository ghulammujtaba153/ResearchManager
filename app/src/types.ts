export type NextAction = {
  action: string
  label: string
  requires_approval: boolean
  decision?: PendingApproval
}

export type PendingApproval = {
  id: number
  run_id: number
  decision_type: string
  rationale: string
  next_params: Record<string, unknown>
  created_at: string | null
}

export type EvidenceItem = {
  source: string
  run_key: string
  metrics: Record<string, number>
  notes: string
  success: boolean
  missing_files?: string[]
}

export type RunRecord = {
  id: number
  experiment_id: number
  run_key: string
  metrics: Record<string, number>
  success: boolean
  notes: string
  artifacts_path: string
  created_at: string | null
}

export type DecisionRecord = {
  id: number
  run_id: number
  decision_type: string
  rationale: string
  next_params: Record<string, unknown>
  agent_suggested?: boolean
  supervisor_confirmed?: boolean | null
  supervisor_comment?: string
  created_at: string | null
}

export type ActionLogItem = {
  id: number
  event_type: string
  tool_name: string
  outcome: string
  error: string
  created_at: string | null
  input?: Record<string, unknown>
  output?: Record<string, unknown>
}

export type LastDecision = {
  action?: string
  rationale?: string
  llm_used?: boolean
  model?: string
  latency_ms?: number
  tools_to_use?: string[]
  tools_executed?: string[]
  llm_proposed?: {
    action?: string
    rationale?: string
    tools_to_use?: string[]
  }
  guard_overrode?: boolean
  guard_reason?: string
  created_at?: string | null
}

export type FactHistoryRow = {
  fact_key: string
  value: unknown
  version: number
  is_current: boolean
  approved_by: string
  source_ref?: string
  created_at: string | null
  superseded_at?: string | null
}

export type AgentSnapshot = {
  project_id: string
  current: {
    experiment_id: number | null
    name: string | null
    hypothesis: string
    status: string
    params: Record<string, unknown>
  }
  facts?: Record<string, unknown>
  pending_params?: Record<string, unknown>
  fact_bump?: {
    fact_key: string
    current_version: number
    current_value: unknown
    previous_version: number | null
    previous_value: unknown
    approved_by?: string
  } | null
  fact_history?: FactHistoryRow[]
  approval_required?: boolean
  checkpoint?: { checkpoint_id: number; created_at: string | null } | null
  last_decision?: LastDecision | null
  next_action: NextAction
  pending_approval: PendingApproval | null
  baselines: Record<string, unknown>
  experiments: Array<{
    id: number
    name: string
    hypothesis: string
    status: string
    params: Record<string, unknown>
    created_at: string | null
  }>
  runs: RunRecord[]
  decisions: DecisionRecord[]
  evidence: EvidenceItem[]
  action_log?: ActionLogItem[]
}

export type StoreSnapshot = {
  database: string
  project: { id: string; name: string; owner: string; created_at: string | null }
  counts: Record<string, number>
  experiments: Array<Record<string, unknown>>
  runs: Array<Record<string, unknown>>
  decisions: Array<Record<string, unknown>>
  facts: Array<Record<string, unknown>>
  checkpoints: Array<Record<string, unknown>>
  action_logs: Array<Record<string, unknown>>
}
