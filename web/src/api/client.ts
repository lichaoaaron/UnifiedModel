import type {
  AgentDiscovery,
  AgentResourceReadResult,
  AgentToolCallResult,
  CreateWorkspaceRequest,
  EntityWriteBatch,
  ErrorEnvelope,
  ExpireRequest,
  HealthResponse,
  Page,
  QueryExplain,
  QueryRequest,
  QueryResult,
  RelationWriteBatch,
  SampleImportResult,
  MModelElement,
  MModelImportRequest,
  MModelImportResult,
  UpdateWorkspaceRequest,
  ValidationResult,
  WorkspaceMetadata,
  WriteResult,
} from './types'

export class ApiError extends Error {
  readonly code: string
  readonly status: number
  readonly retryable: boolean
  readonly details?: Record<string, string>

  constructor(status: number, envelope?: ErrorEnvelope) {
    super(envelope?.error.message || `Request failed with HTTP ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.code = envelope?.error.code || 'HTTP_ERROR'
    this.retryable = envelope?.error.retryable || false
    this.details = envelope?.error.details
  }
}

export class MModelApi {
  readonly baseUrl: string

  constructor(baseUrl = '') {
    this.baseUrl = baseUrl.replace(/\/$/, '')
  }

  health(): Promise<HealthResponse> {
    return this.request('/healthz')
  }

  listWorkspaces(options: { includeDeleted?: boolean; includeConflicts?: boolean } = {}): Promise<Page<WorkspaceMetadata>> {
    const params = new URLSearchParams()
    params.set('page_size', '100')
    if (options.includeDeleted) params.set('include_deleted', 'true')
    if (options.includeConflicts) params.set('include_conflicts', 'true')
    return this.request(`/api/v1/workspaces?${params.toString()}`)
  }

  createWorkspace(payload: CreateWorkspaceRequest): Promise<WorkspaceMetadata> {
    return this.request('/api/v1/workspaces', {
      method: 'POST',
      body: payload,
    })
  }

  getWorkspace(workspace: string): Promise<WorkspaceMetadata> {
    return this.request(`/api/v1/workspaces/${encodeURIComponent(workspace)}`)
  }

  updateWorkspace(workspace: string, payload: UpdateWorkspaceRequest): Promise<WorkspaceMetadata> {
    return this.request(`/api/v1/workspaces/${encodeURIComponent(workspace)}`, {
      method: 'PUT',
      body: payload,
    })
  }

  deleteWorkspace(workspace: string): Promise<WorkspaceMetadata> {
    return this.request(`/api/v1/workspaces/${encodeURIComponent(workspace)}`, {
      method: 'DELETE',
    })
  }

  query(workspace: string, payload: QueryRequest): Promise<QueryResult> {
    return this.request(`/api/v1/query/${encodeURIComponent(workspace)}/execute`, {
      method: 'POST',
      body: payload,
    })
  }

  explain(workspace: string, payload: QueryRequest): Promise<QueryExplain> {
    return this.request(`/api/v1/query/${encodeURIComponent(workspace)}/explain`, {
      method: 'POST',
      body: payload,
    })
  }

  listMModel(workspace: string, limit = 100): Promise<QueryResult> {
    return this.query(workspace, { query: `.mmodel | sort name | limit ${limit}`, limit })
  }

  importMModel(workspace: string, payload: MModelImportRequest): Promise<MModelImportResult> {
    return this.request(`/api/v1/mmodel/${encodeURIComponent(workspace)}/import`, {
      method: 'POST',
      body: payload,
    })
  }

  importSampleData(workspace: string, sample = 'multi-domain-quickstart'): Promise<SampleImportResult> {
    return this.request(`/api/v1/samples/${encodeURIComponent(workspace)}/${encodeURIComponent(sample)}:import`, {
      method: 'POST',
      body: {},
    })
  }

  validateMModel(workspace: string, elements: MModelElement[]): Promise<ValidationResult> {
    return this.request(`/api/v1/mmodel/${encodeURIComponent(workspace)}/validate`, {
      method: 'POST',
      body: { elements },
    })
  }

  putMModel(workspace: string, elements: MModelElement[]): Promise<WriteResult> {
    return this.request(`/api/v1/mmodel/${encodeURIComponent(workspace)}/elements`, {
      method: 'POST',
      body: { elements },
    })
  }

  deleteMModel(workspace: string, ids: string[]): Promise<WriteResult> {
    return this.request(`/api/v1/mmodel/${encodeURIComponent(workspace)}/elements`, {
      method: 'DELETE',
      body: { ids },
    })
  }

  writeEntities(workspace: string, payload: EntityWriteBatch): Promise<WriteResult> {
    return this.request(`/api/v1/entitystore/${encodeURIComponent(workspace)}/entities:write`, {
      method: 'POST',
      body: payload,
    })
  }

  expireEntities(workspace: string, payload: ExpireRequest): Promise<WriteResult> {
    return this.request(`/api/v1/entitystore/${encodeURIComponent(workspace)}/entities:expire`, {
      method: 'POST',
      body: payload,
    })
  }

  writeRelations(workspace: string, payload: RelationWriteBatch): Promise<WriteResult> {
    return this.request(`/api/v1/entitystore/${encodeURIComponent(workspace)}/relations:write`, {
      method: 'POST',
      body: payload,
    })
  }

  expireRelations(workspace: string, payload: ExpireRequest): Promise<WriteResult> {
    return this.request(`/api/v1/entitystore/${encodeURIComponent(workspace)}/relations:expire`, {
      method: 'POST',
      body: payload,
    })
  }

  discoverAgent(workspace: string): Promise<AgentDiscovery> {
    return this.request(`/api/v1/agent/${encodeURIComponent(workspace)}/discover`)
  }

  readAgentResource(workspace: string, uri: string): Promise<AgentResourceReadResult> {
    return this.request(`/api/v1/agent/${encodeURIComponent(workspace)}/resources:read`, {
      method: 'POST',
      body: { uri },
    })
  }

  executeAgentTool(workspace: string, name: string, args: Record<string, unknown>): Promise<AgentToolCallResult> {
    return this.request(`/api/v1/agent/${encodeURIComponent(workspace)}/tools:execute`, {
      method: 'POST',
      body: { name, arguments: args },
    })
  }

  private async request<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      method: init.method || 'GET',
      headers: init.body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
    })
    const contentType = response.headers.get('content-type') || ''
    const payload = contentType.includes('application/json') ? await response.json() : undefined
    if (!response.ok) {
      throw new ApiError(response.status, payload as ErrorEnvelope | undefined)
    }
    return payload as T
  }
}
