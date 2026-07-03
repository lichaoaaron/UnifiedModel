import type { DiagnoseRequest, DiagnosisResponse, DiagnosisMessage, CallGraph, DiagnosisSummary, DataSourceStatus } from '../types/diagnosis'

// Vite proxy forwards /api/diagnose to localhost:8000
const BASE_URL = '/api'

export async function runDiagnosis(req: DiagnoseRequest): Promise<DiagnosisResponse> {
  const resp = await fetch(`${BASE_URL}/diagnose`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
    signal: AbortSignal.timeout(120_000),
  })
  if (!resp.ok) throw new Error(`Diagnosis API: ${resp.status}`)
  return resp.json()
}

export interface StreamCallbacks {
  onMessage: (msg: DiagnosisMessage) => void
  onSkillStart: (msg: DiagnosisMessage) => void
  onSkill: (msg: DiagnosisMessage) => void
  onCallGraph: (msg: DiagnosisMessage) => void
  onReport: (msg: DiagnosisMessage) => void
  onDone: (data: { case_id: string; summary: DiagnosisSummary; call_graph: CallGraph; session_id?: string; mode?: string; intent?: string; executed_skills?: string[]; current_focus?: Record<string, unknown>; memory_summary?: Record<string, unknown>; data_source_status?: DataSourceStatus }) => void
  onSession?: (data: { session_id?: string; mode?: string; intent?: string; executed_skills?: string[]; current_focus?: Record<string, unknown>; resolved_context?: Record<string, unknown>; memory_summary?: Record<string, unknown> }) => void
  onDataSourceStatus?: (status: DataSourceStatus) => void
  onError: (err: string) => void
}

export function streamDiagnosis(req: DiagnoseRequest, callbacks: StreamCallbacks): () => void {
  const controller = new AbortController()

  fetch(`${BASE_URL}/diagnose/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
    signal: controller.signal,
  }).then(async (resp) => {
    if (!resp.ok || !resp.body) {
      callbacks.onError(`请求失败：${resp.status}`)
      return
    }
    const reader = resp.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      const parts = buffer.split('\n\n')
      buffer = parts.pop() ?? ''

      for (const part of parts) {
        const eventMatch = part.match(/^event: (\w+)/)
        const dataMatch = part.match(/^data: (.+)$/m)
        if (!eventMatch || !dataMatch) continue
        const eventType = eventMatch[1]
        const payload = JSON.parse(dataMatch[1])

        if (eventType === 'message') callbacks.onMessage(payload)
        else if (eventType === 'skill_start') callbacks.onSkillStart(payload)
        else if (eventType === 'skill') callbacks.onSkill(payload)
        else if (eventType === 'call_graph') callbacks.onCallGraph(payload)
        else if (eventType === 'report') callbacks.onReport(payload)
        else if (eventType === 'session') callbacks.onSession?.(payload)
        else if (eventType === 'data_source_status') callbacks.onDataSourceStatus?.(payload)
        else if (eventType === 'done') callbacks.onDone(payload)
      }
    }
  }).catch((err) => {
    if (err.name !== 'AbortError') callbacks.onError('请求失败，请确认诊断后端服务已启动（端口 8000）')
  })

  return () => controller.abort()
}

// Agentic streaming: POST /api/diagnose/agentic-stream.
// SSE events are plain `data: {...}` lines with no `event:` prefix.

export interface AgenticStreamCallbacks {
  onAssistantDelta: (content: string) => void
  onAssistantReplace: (content: string) => void
  onAssistantMessageDone: () => void
  onSkillStart: (skill: string, title: string, reason?: string) => void
  onSkillDone: (skill: string, result: { summary: string; evidence: string[]; execution_log: string[]; duration_ms?: number; root_cause_status?: string; confidence?: string; output?: Record<string, unknown> }, callGraph?: CallGraph) => void
  onSkillError: (skill: string, error: string, result: { summary: string; evidence: string[]; execution_log: string[]; duration_ms?: number; recovery_action?: string; output?: Record<string, unknown> }, recoveryAction?: string) => void
  onReportDelta: (content: string) => void
  onReportDone: (report: { summary?: unknown }) => void
  onDone: (summary?: DiagnosisSummary, session?: { session_id?: string; mode?: string; intent?: string; executed_skills?: string[]; current_focus?: Record<string, unknown>; memory_summary?: Record<string, unknown> }) => void
  onSession?: (session: { session_id?: string; mode?: string; intent?: string; executed_skills?: string[]; current_focus?: Record<string, unknown>; resolved_context?: Record<string, unknown>; memory_summary?: Record<string, unknown> }) => void
  onDataSourceStatus?: (status: DataSourceStatus) => void
  onError: (err: string) => void
}

export function streamAgenticDiagnosis(req: DiagnoseRequest, cb: AgenticStreamCallbacks): () => void {
  const controller = new AbortController()

  fetch(`${BASE_URL}/diagnose/agentic-stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
    signal: controller.signal,
  }).then(async (resp) => {
    if (!resp.ok || !resp.body) {
      cb.onError(`请求失败：${resp.status}`)
      return
    }
    const reader = resp.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''

    const processEvent = (event: Record<string, unknown>) => {
      const type = event.type as string
      if (type === 'assistant_delta') {
        cb.onAssistantDelta(event.content as string)
      } else if (type === 'assistant_replace') {
        cb.onAssistantReplace(event.content as string)
      } else if (type === 'assistant_message_done') {
        cb.onAssistantMessageDone()
      } else if (type === 'skill_start') {
        cb.onSkillStart(event.skill as string, event.title as string, event.reason as string | undefined)
      } else if (type === 'skill_done') {
        cb.onSkillDone(event.skill as string, event.result as never, event.call_graph as CallGraph | undefined)
      } else if (type === 'skill_error') {
        cb.onSkillError(event.skill as string, event.error as string, event.result as never, event.recovery_action as string | undefined)
      } else if (type === 'report_delta') {
        cb.onReportDelta(event.content as string)
      } else if (type === 'report_done') {
        cb.onReportDone(event as never)
      } else if (type === 'session') {
        cb.onSession?.(event as never)
      } else if (type === 'data_source_status') {
        cb.onDataSourceStatus?.(event as unknown as DataSourceStatus)
      } else if (type === 'done') {
        cb.onDone(event.summary as DiagnosisSummary | undefined, event as never)
      }
    }

    const processBuffer = (flush = false) => {
      const parts = buffer.split('\n\n')
      buffer = flush ? '' : (parts.pop() ?? '')
      for (const part of parts) {
        const dataMatch = part.match(/^data: (.+)$/m)
        if (!dataMatch) continue
        let event: Record<string, unknown>
        try { event = JSON.parse(dataMatch[1]) } catch { continue }
        processEvent(event)
      }
    }

    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        if (buffer.trim()) processBuffer(true)
        break
      }
      buffer += decoder.decode(value, { stream: true })
      processBuffer(false)
    }
  }).catch((err) => {
    if (err.name !== 'AbortError') cb.onError('请求失败，请确认诊断后端服务已启动（端口 8000）')
  })

  return () => controller.abort()
}
