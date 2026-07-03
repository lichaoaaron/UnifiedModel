export interface SkillResult {
  skill_name: string
  tool_name: string
  title: string
  status: 'pending' | 'running' | 'success' | 'failed'
  summary: string
  started_at: string
  finished_at: string
  duration_ms: number
  input: Record<string, unknown>
  output: Record<string, unknown>
  evidence: string[]
  execution_log: string[]
  explanation: string
}

export interface CallNode {
  id: string
  label: string
  is_root_cause: boolean
  is_entry: boolean
  node_type?: string  // "Service" | "Dependency" | "Instance" | "Interface" | "Business" | "BusinessFlow" | legacy "service"/"interface"
  is_call_chain?: boolean  // true if this node is part of the diagnosed call chain
  storm_role?: 'common_root' | 'secondary_local_issue' | 'propagated_impact' | 'noise'
  /** Extended visual roles for object-centered topology */
  visual_role?: 'entry' | 'candidate_root' | 'confirmed_root' | 'propagated' | 'direct_impact' | 'indirect_impact' | 'observed' | 'normal'
}

export interface CallEdge {
  source: string
  target: string
  label: string
  is_call_chain?: boolean  // true if this edge is part of the diagnosed call chain
}

export interface CallGraph {
  nodes: CallNode[]
  edges: CallEdge[]
  trace_summary?: string
  log_summary?: string
  metric_summary?: string
}

export interface DiagnosisSummary {
  root_cause_service: string
  root_cause_api: string
  root_cause_type: string
  exception_type: string
  bad_parameter: string
  impact_api: string
  business_impact: string[]
}

// ── Data Source Status ─────────────────────────────────────────────────────

export interface OpenSearchConnectivity {
  connected: boolean
  url: string
  latency_ms: number | null
  error: string | null
  configured: boolean
  version?: string
}

export interface DataSourceStatus {
  active_source: 'local_json' | 'opensearch' | 'unifiedmodel'
  opensearch_connectivity: OpenSearchConnectivity | null
  per_kind_source: Record<string, string>
  fallback_occurred: boolean
  warnings: string[]
}

// ── Entity Summary (from bind_entities skill) ────────────────────────────

export interface EntitySummaryData {
  services: string[]
  instances: string[]
  interfaces: string[]
}

// ── Unified Event Stream View Model ────────────────────────────────────────
// Both normal diagnosis mode and storm mode map their messages into
// EventStreamItem so that a single EventStream component can render them.

export type EventStreamMode = 'normal' | 'storm'

export type EventStreamKind =
  | 'object_selection'
  | 'evidence_confirmation'
  | 'root_cause_decision'
  | 'impact_scope_decision'
  | 'skill_call'
  | 'text'
  | 'storm_init'
  | 'storm_actor'
  | 'storm_phase_summary'
  | 'storm_final'
  | 'report'

export interface EventStreamItem {
  id: string
  mode: EventStreamMode
  /** Diagnosis phase label, e.g. "root_cause_decision" */
  phase?: string
  /** Actor / agent label (only populated in storm mode) */
  actor?: string
  kind: EventStreamKind
  /** Short human-readable title */
  title: string
  /** One-line summary shown in the collapsed row */
  summary: string
  status?: 'pending' | 'running' | 'success' | 'failed' | 'info'
  /** Node ids in the topology graph that this event relates to */
  related_nodes?: string[]
  evidence_refs?: string[]
  details?: {
    input?: Record<string, unknown>
    output?: Record<string, unknown>
    evidence?: string[]
    executionLog?: string[]
    explanation?: string
  }
  raw?: unknown
  timestamp?: string
}

export interface DiagnosisMessage {
  role: 'user' | 'assistant'
  type: 'text' | 'skill_call' | 'report' | 'report_streaming' | 'call_graph' | 'assistant_streaming' | 'storm_overview' | 'storm_round_summary'
  content?: string
  skill_name?: string
  tool_name?: string
  status?: string
  summary?: string
  duration_ms?: number
  input?: Record<string, unknown>
  output?: Record<string, unknown>
  evidence?: string[]
  execution_log?: string[]
  explanation?: string
  root_cause_status?: string
  confidence?: string
  recovery_action?: string
  call_graph?: CallGraph
  storm_overview?: StormOverview
  storm_round_summary?: StormRoundSummary
  report_title?: string
  render_as?: 'plain' | 'report'
  /** unique id used for streaming text bubbles */
  stream_id?: string
  /** diagnosis run id — used to scope call_graph updates to the current run only */
  run_id?: string
  /** storm demo hint: keep Skill cards collapsed by default */
  default_collapsed?: boolean
}

export interface StormAlertEvent {
  api: string
  time: string
  time_window: {
    start: string
    end: string
  }
  symptom: string
  severity: string
  tenant: string
  business_flow: string
}

export interface StormTaskOverview {
  error_trace_count: number
  diagnosis_branch_count: number
  default_rounds: string[]
  runtime_adjustment: {
    skipped_rounds: string[]
    extra_rounds: string[]
    early_stop: boolean
  }
}

export interface StormBranch {
  branch_id: string
  name: string
  trace_count: number
  initial_signal: string
  branch_hypothesis: string
  expected_role: string
}

export interface StormBranchAction {
  branch_id: string
  selected_skill: string
  reason: string
  evidence_delta: string[]
}

export interface StormRound {
  round_id: number
  intent: string
  goal: string
  is_extra_round?: boolean
  branch_actions: StormBranchAction[]
  round_summary: string
}

export interface StormTopology {
  entry: string
  nodes: string[]
  edges: string[]
}

export interface StormCommonRootCause {
  service: string
  component: string
  interface: string
  type: string
  message: string
}

export interface StormSecondaryFinding {
  component: string
  type: string
  role: string
  covered_error_traces: string
}

export interface StormExcludedCandidate {
  component: string
  reason: string
}

export interface StormFinalConvergence {
  status: string
  common_root_cause: StormCommonRootCause
  confidence: number | null
  covered_error_traces: string
  secondary_findings: StormSecondaryFinding[]
  excluded_candidates: StormExcludedCandidate[]
  business_impact: string[]
  recommended_actions: string[]
}

export interface StormCase {
  case_id: string
  name: string
  purpose: string
  alert_event: StormAlertEvent
  storm_task_overview: StormTaskOverview
  topology: StormTopology
  branches: StormBranch[]
  rounds: StormRound[]
  final_convergence: StormFinalConvergence
  presentation_notes?: string[]
}

export interface StormOverview {
  alert_api: string
  alert_time: string
  time_window: string
  symptom: string
  severity: string
  tenant: string
  business_flow: string
  error_trace_count: number
  diagnosis_branch_count: number
  current_round: string
  evidence_progress: string
  convergence_status: string
  confidence: number
}

export interface StormRoundSummary {
  round_id: number
  intent: string
  goal: string
  summary: string
  is_extra_round?: boolean
}

export interface DiagnosisResponse {
  case_id: string
  summary: DiagnosisSummary
  skills: SkillResult[]
  call_graph: CallGraph
  evidence_chain: string[]
  final_report: string
  messages: DiagnosisMessage[]
  session_id?: string
  mode?: DiagnosisMode
  intent?: string
  executed_skills?: string[]
  answer?: string
  evidence_refs?: Record<string, unknown>
  current_focus?: Record<string, unknown>
  resolved_context?: Record<string, unknown>
  memory_summary?: Record<string, unknown>
}

export interface DiagnoseRequest {
  api: string
  time: string
  symptom: string
  mode?: DiagnosisMode
  case_id?: string
  data_dir?: string
  session_id?: string
  message?: string
}

export type DiagnosisMode = 'observability' | 'diagnosis' | 'storm'

export interface HistoryRecord {
  id: string
  createdAt: string        // ISO timestamp
  userText: string         // original user input
  summary?: DiagnosisSummary
  messages: DiagnosisMessage[]
  status?: 'running' | 'complete'
  unread?: boolean
}
