export type WorkspaceStatus = 'active' | 'deleted' | 'conflicted';

export interface Page<T> {
  items: T[];
  next_token?: string;
}

export interface GraphStoreHealth {
  provider: string;
  status: string;
  message?: string;
}

export interface HealthResponse {
  status: string;
  graphstore: GraphStoreHealth;
}

export interface WorkspacePaths {
  root: string;
  tmp?: string;
}

export interface WorkspaceMetadata {
  id: string;
  name: string;
  description?: string;
  labels?: Record<string, string>;
  config?: Record<string, Record<string, unknown>>;
  paths: WorkspacePaths;
  status: WorkspaceStatus;
  resource_version: number;
  created_at: string;
  updated_at: string;
  deleted_at?: string;
}

export interface CreateWorkspaceRequest {
  id: string;
  name?: string;
  description?: string;
  labels?: Record<string, string>;
  config?: Record<string, Record<string, unknown>>;
}

export interface UpdateWorkspaceRequest {
  name?: string;
  description?: string;
  labels?: Record<string, string>;
  config?: Record<string, Record<string, unknown>>;
  if_match_version?: number;
  replace_labels?: boolean;
  replace_config?: boolean;
}

export interface ErrorDetail {
  field?: string;
  reason?: string;
  limit?: string;
}

export interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    retryable: boolean;
    details?: Record<string, string>;
  };
}

export interface BatchItemResult {
  id?: string;
  ok: boolean;
  code?: string;
  message?: string;
  details?: ErrorDetail[];
}

export interface WriteResult {
  accepted: number;
  failed: number;
  items?: BatchItemResult[];
}

export interface ValidationResult {
  valid: boolean;
  errors?: ErrorDetail[];
}

export interface UModelElement {
  kind: string;
  domain: string;
  name: string;
  version?: string;
  spec?: Record<string, unknown>;
}

export interface UModelImportRequest {
  path: string;
  common_schema_packs?: string[];
}

export interface UModelImportResult {
  workspace: string;
  source: string;
  imported: number;
  skipped: number;
  elements?: UModelElement[];
  errors?: ErrorDetail[];
}

export interface SampleImportResult {
  workspace: string;
  sample: string;
  umodel: UModelImportResult;
  entities: WriteResult;
  relations: WriteResult;
  entity_count: number;
  relation_count: number;
}

export interface QueryRequest {
  query: string;
  limit?: number;
  timeout_ms?: number;
  format?: string;
  time_range?: {
    from?: string;
    to?: string;
  };
  parameters?: Record<string, unknown>;
  entity_data?: EntityData;
  entityData?: EntityData;
  filterByEntities?: EntityData;
}

export interface EntityData {
  version?: number;
  header?: string[];
  data?: Array<string[] | { values: string[] } | Record<string, unknown>>;
}

export interface QueryExplain {
  source?: '.umodel' | '.entity' | '.topo';
  provider?: string;
  storage_provider?: string;
  cypher_dialect?: string;
  cypher_engine?: string;
  pushdown?: string[];
  fallback?: string[];
  operators?: string[];
  depth?: number;
  limit?: number;
  timeout_ms?: number;
  time_range_applied?: boolean;
}

export interface QueryResult {
  columns: string[];
  rows: Array<Record<string, unknown>>;
  page: {
    limit?: number;
    page_token?: string;
  };
  explain?: QueryExplain;
}

// The umodel-server wraps query/execute results in this envelope; the client
// flattens it back to QueryResult (see normalizeQueryResult in client.ts).
export interface QueryExecuteResponse {
  code: string;
  message: string;
  success: boolean;
  data: {
    data: unknown[][];
    header: string[];
    responseStatus: {
      result: string;
      retryPolicy: string;
      level: string;
      statusItem: unknown[];
    };
  };
}

export interface EntityWriteBatch {
  workspace?: string;
  idempotency_key?: string;
  partial_success?: boolean;
  entities: Array<Record<string, unknown>>;
}

export interface RelationWriteBatch {
  workspace?: string;
  idempotency_key?: string;
  partial_success?: boolean;
  relations: Array<Record<string, unknown>>;
}

export interface ExpireRequest {
  workspace?: string;
  ids: string[];
  reason?: string;
}

export interface AgentTool {
  name: string;
  description: string;
  enabled: boolean;
  requires_explicit_write_enable?: boolean;
  input_schema?: unknown;
  output_schema?: unknown;
}

export interface AgentResource {
  uri: string;
  name: string;
  kind: string;
  description: string;
  mime_type: string;
  read_only: boolean;
}

export interface AgentNextAction {
  id: string;
  title: string;
  description: string;
  tool: string;
  query_api: {
    method: string;
    path: string;
    body: QueryRequest;
  };
}

export interface AgentDiscovery {
  workspace: string;
  tools: AgentTool[];
  resources: AgentResource[];
  next_actions?: AgentNextAction[];
}

export interface AgentResourceReadResult {
  uri: string;
  mime_type: string;
  content: unknown;
}

export interface AgentToolCallResult {
  name: string;
  ok: boolean;
  output?: unknown;
  error?: unknown;
}

// ── Diagnosis API types (standalone diagnosis service, port 8000) ─────────
// Phase 2: kept in sync with web/src/api/types.ts so the diagnosis workbench
// can be ported without another types pass. Unused until the diagnosis page
// lands (requires a second upstream, jsonData.diagnosisUrl).

export interface DiagnoseRequest {
  entity_id?: string;
  time_range?: { from?: string; to?: string };
  symptom?: string;
  api?: string;
  time?: string;
  session_id?: string;
  message?: string;
  mode?: 'diagnosis' | 'observability';
  case_id?: string;
}

export interface RootCause {
  entity_id: string;
  entity_type?: string;
  score?: number;
  confidence?: string;
  evidence_summary?: string[];
  reasoning_chain?: string[];
}

export interface ImpactResult {
  diagnosis_id: string;
  root_cause_entity: string;
  affected_services: string[];
  business_impact?: Record<string, unknown>;
  topology_highlight?: {
    nodes: Array<{ id: string; label: string; node_type: string }>;
    edges: Array<{ source: string; target: string; label: string }>;
  };
}

export interface ReportResult {
  diagnosis_id: string;
  report_markdown: string;
  summary?: {
    root_cause_service?: string;
    root_cause_type?: string;
    confidence?: string;
  };
  evidence_citations?: string[];
}

export interface CallNode {
  id: string;
  label: string;
  is_root_cause?: boolean;
  is_entry?: boolean;
  node_type?: string;
  is_call_chain?: boolean;
  visual_role?: 'entry' | 'candidate_root' | 'confirmed_root' | 'propagated' | 'observed' | 'normal';
}

export interface CallEdge {
  source: string;
  target: string;
  label?: string;
  is_call_chain?: boolean;
}

export interface CallGraph {
  nodes: CallNode[];
  edges: CallEdge[];
  trace_summary?: string;
  log_summary?: string;
  metric_summary?: string;
}

export interface DiagnosisSummary {
  root_cause_service?: string;
  root_cause_api?: string;
  root_cause_type?: string;
  exception_type?: string;
  confidence?: string;
  is_confirmed?: boolean;
  impact_api?: string;
  business_impact?: Record<string, unknown>;
}

export interface SkillResult {
  skill_name: string;
  tool_name?: string;
  status: 'success' | 'error' | 'running';
  summary: string;
  duration_ms?: number;
  evidence?: string[];
  execution_log?: string[];
  explanation?: string;
  output?: Record<string, unknown>;
}

export interface DiagnosisResponse {
  diagnosis_id?: string;
  case_id?: string;
  session_id?: string;
  mode?: string;
  summary?: DiagnosisSummary;
  call_graph?: CallGraph;
  skills?: SkillResult[];
  evidence_chain?: string[];
  final_report?: string;
  root_causes?: RootCause[];
  messages?: unknown[];
}
