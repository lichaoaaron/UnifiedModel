import type { CallGraph, DiagnoseRequest, DiagnosisMessage, DiagnosisSummary, StormCase, StormOverview, StormRoundSummary } from '../types/diagnosis'
import caseJson from '../fixtures/storm_mode_complex/01_checkout_payment_storm/case.json'
import traceJson from '../fixtures/storm_mode_complex/01_checkout_payment_storm/trace.json'
import logJson from '../fixtures/storm_mode_complex/01_checkout_payment_storm/log.json'
import metricJson from '../fixtures/storm_mode_complex/01_checkout_payment_storm/metric.json'
import { RESOURCE_BASE } from '../../../../api/constants'

// Demo-only adapter for storm-mode playback. It consumes bundled demo case data
// and must not affect the normal /api/diagnose or /api/diagnose/agentic-stream path.

type StormDemoSkillMessage = DiagnosisMessage & { stream_id: string }

export interface StormDemoCallbacks {
  onOverview: (overview: StormOverview) => void
  onAssistantStatus: (content: string) => void
  onAssistantDone: () => void
  onSkillStart: (message: StormDemoSkillMessage) => void
  onSkillDone: (message: StormDemoSkillMessage) => void
  onRoundSummary: (summary: StormRoundSummary) => void
  onTopology: (graph: CallGraph) => void
  onReportDelta: (content: string) => void
  onReportDone: () => void
  onDone: (summary: DiagnosisSummary) => void
  onError: (error: string) => void
}

interface TraceSpan {
  _source?: {
    traceId?: string
    serviceName?: string
    status?: { code?: number; message?: string }
    ['status.code']?: number
    ['derived.error']?: string
    ['derived.root_candidate']?: string
  }
}

interface LogRecord {
  serviceName?: string
  ['log.attributes.log@level']?: string
  ['log.attributes.message']?: string
}

interface MetricRecord {
  name?: string
  value?: string
  threshold?: string
  unit?: string
  ['resource.attributes.compose_service']?: string
}

const stormCase = caseJson as StormCase
const traceRecords = traceJson as TraceSpan[]
const logRecords = logJson as LogRecord[]
const metricRecords = metricJson as MetricRecord[]
const BASE_URL = `${RESOURCE_BASE}/diagnosis/api`

function completedEvidenceCount(roundId: number) {
  return stormCase.rounds.reduce((total, round) => {
    if (round.round_id > roundId) {return total}
    return total + round.branch_actions.reduce((sum, action) => sum + action.evidence_delta.length, 0)
  }, 0)
}

function buildOverview(currentRound = 0, completedEvidence = 0): StormOverview {
  const overview = stormCase.storm_task_overview
  return {
    alert_api: stormCase.alert_event.api,
    alert_time: stormCase.alert_event.time,
    time_window: `${stormCase.alert_event.time_window.start} - ${stormCase.alert_event.time_window.end}`,
    symptom: stormCase.alert_event.symptom,
    severity: stormCase.alert_event.severity,
    tenant: stormCase.alert_event.tenant,
    business_flow: stormCase.alert_event.business_flow,
    error_trace_count: overview.error_trace_count,
    diagnosis_branch_count: overview.diagnosis_branch_count,
    current_round: String(currentRound),
    evidence_progress: String(completedEvidence),
    convergence_status: stormCase.final_convergence.status,
    confidence: currentRound >= stormCase.rounds.length ? stormCase.final_convergence.confidence : null,
  }
}

function summarizeObservability() {
  const uniqueTraceIds = new Set(traceRecords.map(record => record._source?.traceId).filter(Boolean))
  const errorServices = new Set(
    traceRecords
      .filter(record => record._source?.['derived.error'] === '1' || record._source?.['status.code'] === 2)
      .map(record => record._source?.serviceName)
      .filter(Boolean),
  )
  const rootCandidates = new Set(
    traceRecords
      .filter(record => record._source?.['derived.root_candidate'] === '1')
      .map(record => record._source?.serviceName)
      .filter(Boolean),
  )
  const highSignals = metricRecords
    .filter(metric => Number(metric.value) >= Number(metric.threshold))
    .map(metric => `${metric['resource.attributes.compose_service']}:${metric.name}=${metric.value}${metric.unit ?? ''}`)

  return {
    traceCount: uniqueTraceIds.size || stormCase.storm_task_overview.error_trace_count,
    errorServices: [...errorServices],
    rootCandidates: [...rootCandidates],
    logCount: logRecords.length,
    metricSignals: highSignals,
  }
}

function branchName(branchId: string) {
  return stormCase.branches.find(branch => branch.branch_id === branchId)?.name ?? `分支 ${branchId}`
}

function branchRole(branchId: string) {
  return stormCase.branches.find(branch => branch.branch_id === branchId)?.expected_role ?? 'unknown'
}

function buildExecutionLog(branchId: string, skill: string, evidenceDelta: string[]) {
  const observation = summarizeObservability()
  const firstEvidence = evidenceDelta[0] ?? '等待证据补齐'
  return [
    `风暴分支=${branchId}，Skill=${skill}`,
    `已读取 Error Trace ${observation.traceCount} 条，日志 ${observation.logCount} 条`,
    `分支角色提示=${branchRole(branchId)}`,
    `新增证据：${firstEvidence}`,
  ]
}

function buildSkillMessage(roundId: number, actionIndex: number, branchId: string, selectedSkill: string, reason: string, evidenceDelta: string[]): StormDemoSkillMessage {
  const streamId = `storm-r${roundId}-${branchId}-${actionIndex}-${selectedSkill}`
  const branch = stormCase.branches.find(item => item.branch_id === branchId)
  return {
    role: 'assistant',
    type: 'skill_call',
    stream_id: streamId,
    skill_name: selectedSkill,
    tool_name: `分支 ${branchId} · ${selectedSkill}`,
    status: 'running',
    default_collapsed: true,
    content: `分支 ${branchId} · ${selectedSkill}`,
    summary: '',
    explanation: reason,
    evidence: [],
    execution_log: [],
    input: {
      round_id: roundId,
      branch_id: branchId,
      selected_skill: selectedSkill,
      branch_name: branch?.name,
      branch_hypothesis: branch?.branch_hypothesis,
    },
    output: {},
  }
}

function completeSkillMessage(message: StormDemoSkillMessage, evidenceDelta: string[], durationMs: number): StormDemoSkillMessage {
  const selectedSkill = message.skill_name ?? 'unknown'
  const branchId = String(message.input?.branch_id ?? '')
  return {
    ...message,
    status: 'success',
    duration_ms: durationMs,
    summary: `${selectedSkill} 完成：${branchName(branchId)} 新增 ${evidenceDelta.length} 条证据。`,
    evidence: evidenceDelta,
    execution_log: buildExecutionLog(branchId, selectedSkill, evidenceDelta),
    output: {
      selected_skill: selectedSkill,
      reason: message.explanation,
      evidence_delta: evidenceDelta,
      branch_role: branchRole(branchId),
    },
  }
}

function edgeParts(edge: string) {
  const [source, target] = edge.split('->').map(part => part.trim())
  return source && target ? { source, target } : null
}

function stormRoleForNode(nodeId: string) {
  if (nodeId === stormCase.final_convergence.common_root_cause.service) {return 'common_root' as const}
  if (stormCase.final_convergence.secondary_findings.some(finding => finding.component === nodeId)) {return 'secondary_local_issue' as const}
  const relatedBranch = stormCase.branches.find(branch => {
    const actionText = stormCase.rounds
      .flatMap(round => round.branch_actions)
      .filter(action => action.branch_id === branch.branch_id)
      .flatMap(action => [action.reason, ...action.evidence_delta])
      .join(' ')
    return `${branch.name} ${branch.initial_signal} ${branch.branch_hypothesis} ${actionText}`
      .toLowerCase()
      .includes(nodeId.toLowerCase())
  })
  if (relatedBranch?.expected_role === 'secondary_local_issue') {return 'secondary_local_issue' as const}
  if (relatedBranch?.expected_role === 'propagated_impact' || relatedBranch?.expected_role === 'downstream_symptom') {return 'propagated_impact' as const}
  if (relatedBranch?.expected_role === 'noise') {return 'noise' as const}
  return undefined
}

function nodeType(nodeId: string) {
  if (nodeId.includes('redis') || nodeId.includes('mysql') || nodeId.includes('third-party')) {return 'Dependency'}
  return 'Service'
}

function buildTopologyGraph(): CallGraph {
  const entryService = stormCase.topology.entry.split(':')[0]
  const edges = stormCase.topology.edges
    .map(edgeParts)
    .filter((edge): edge is { source: string; target: string } => Boolean(edge))
  const primaryPath = new Set(findPath(entryService, stormCase.final_convergence.common_root_cause.service, edges))

  return {
    nodes: stormCase.topology.nodes.map(nodeId => ({
      id: nodeId,
      label: nodeId,
      is_root_cause: nodeId === stormCase.final_convergence.common_root_cause.service,
      is_entry: nodeId === entryService,
      node_type: nodeType(nodeId),
      is_call_chain: primaryPath.has(nodeId),
      storm_role: stormRoleForNode(nodeId),
    })),
    edges: edges.map(edge => ({
      source: edge.source,
      target: edge.target,
      label: 'calls',
      is_call_chain: primaryPath.has(edge.source) && primaryPath.has(edge.target),
    })),
    trace_summary: `Error Trace ${stormCase.storm_task_overview.error_trace_count} 条；异常服务：${summarizeObservability().errorServices.join('、')}`,
    log_summary: logRecords.map(record => `${record.serviceName}:${record['log.attributes.log@level']}`).join('；'),
    metric_summary: summarizeObservability().metricSignals.join('；'),
  }
}

function findPath(entryNode: string, targetNode: string, edges: Array<{ source: string; target: string }>) {
  const queue: string[][] = [[entryNode]]
  const visited = new Set<string>()
  while (queue.length > 0) {
    const path = queue.shift() ?? []
    const current = path[path.length - 1]
    if (current === targetNode) {return path}
    if (visited.has(current)) {continue}
    visited.add(current)
    for (const edge of edges.filter(item => item.source === current)) {
      queue.push([...path, edge.target])
    }
  }
  return [entryNode, targetNode].filter(Boolean)
}

function buildStormReportContext(request: DiagnoseRequest) {
  const final = stormCase.final_convergence
  const root = final.common_root_cause
  const observation = summarizeObservability()
  const roundSummaries = stormCase.rounds.map(round => `第 ${round.round_id} 轮 ${round.intent}：${round.round_summary}`).join('\n')
  const branchEvidence = stormCase.rounds
    .flatMap(round => round.branch_actions.map(action => `${action.branch_id}/${action.selected_skill}：${action.evidence_delta.join('；')}`))
    .join('\n')

  return {
    request: {
      mode: request.mode ?? 'storm',
      session_id: request.session_id,
      message: request.message,
    },
    api: stormCase.alert_event.api,
    time: `${stormCase.alert_event.time_window.start} - ${stormCase.alert_event.time_window.end}`,
    symptom: stormCase.alert_event.symptom,
    root_cause: {
      is_confirmed: true,
      root_cause_service: root.service,
      root_cause_api: root.interface,
      root_cause_type: root.type,
      exception_type: root.type,
      confidence: String(final.confidence),
    },
    trace: {
      summary: `Error Trace ${observation.traceCount} 条；异常服务：${observation.errorServices.join('、')}；共同根因覆盖 ${final.covered_error_traces}。\n${roundSummaries}\n${branchEvidence}`,
    },
    log: {
      summary: logRecords.map(record => `${record.serviceName}:${record['log.attributes.message']}`).join('；'),
    },
    metric: {
      conclusion: observation.metricSignals.join('；'),
    },
    impact: {
      affected_services: stormCase.topology.nodes,
      affected_apis: [root.interface, stormCase.alert_event.api].filter(Boolean),
      affected_capabilities: final.business_impact.map(name => ({ name })),
      affected_processes: [{ name: stormCase.alert_event.business_flow }],
      affected_pages: [],
      affected_user_groups: [{ name: stormCase.alert_event.tenant }],
      impact_scale: 'unavailable',
    },
    storm: {
      status: final.status,
      secondary_findings: final.secondary_findings,
      excluded_candidates: final.excluded_candidates,
      recommended_actions: final.recommended_actions,
    },
  }
}

function streamStormReport(callbacks: StormDemoCallbacks, request: DiagnoseRequest): () => void {
  const controller = new AbortController()
  fetch(`${BASE_URL}/storm/report-stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ context: buildStormReportContext(request) }),
    signal: controller.signal,
  }).then(async response => {
    if (!response.ok || !response.body) {
      callbacks.onError(`风暴诊断报告生成失败：${response.status}`)
      return
    }
    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''

    const processBuffer = (flush = false) => {
      const parts = buffer.split('\n\n')
      buffer = flush ? '' : (parts.pop() ?? '')
      for (const part of parts) {
        const dataMatch = part.match(/^data: (.+)$/m)
        if (!dataMatch) {continue}
        const event = JSON.parse(dataMatch[1]) as { type?: string; content?: string }
        if (event.type === 'report_delta' && event.content) {callbacks.onReportDelta(event.content)}
        if (event.type === 'report_done') {
          callbacks.onReportDone()
          callbacks.onDone(buildSummary())
        }
      }
    }

    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        if (buffer.trim()) {processBuffer(true)}
        break
      }
      buffer += decoder.decode(value, { stream: true })
      processBuffer(false)
    }
  }).catch(error => {
    if (error.name !== 'AbortError') {callbacks.onError('风暴诊断报告生成失败，请确认后端服务已启动（端口 8000）')}
  })
  return () => controller.abort()
}

function buildSummary(): DiagnosisSummary {
  const root = stormCase.final_convergence.common_root_cause
  return {
    root_cause_service: root.service,
    root_cause_api: root.interface,
    root_cause_type: root.type,
    exception_type: root.type,
    bad_parameter: '',
    impact_api: root.interface,
    business_impact: stormCase.final_convergence.business_impact,
  }
}

export function streamStormDemoDiagnosis(request: DiagnoseRequest, callbacks: StormDemoCallbacks): () => void {
  const timers: number[] = []
  let abortReportStream: (() => void) | null = null
  let aborted = false
  let delay = 0

  const schedule = (stepDelay: number, task: () => void) => {
    delay += stepDelay
    const timer = window.setTimeout(() => {
      if (!aborted) {task()}
    }, delay)
    timers.push(timer)
  }

  const scheduleBatch = (stepDelay: number, tasks: Array<{ offset: number; task: () => void }>) => {
    delay += stepDelay
    const batchStart = delay
    for (const item of tasks) {
      const timer = window.setTimeout(() => {
        if (!aborted) {item.task()}
      }, batchStart + item.offset)
      timers.push(timer)
    }
    delay += Math.max(0, ...tasks.map(item => item.offset))
  }

  try {
    schedule(120, () => callbacks.onOverview(buildOverview()))

    for (const round of stormCase.rounds) {
      schedule(100, () => callbacks.onOverview(buildOverview(round.round_id, completedEvidenceCount(round.round_id - 1))))
      schedule(360, () => callbacks.onAssistantStatus(
        `正在执行第 ${round.round_id} 轮：${round.intent}。本轮将根据各分支缺失证据选择不同 Skill。`,
      ))
      schedule(420, callbacks.onAssistantDone)

      const messages = round.branch_actions.map((action, actionIndex) => buildSkillMessage(
        round.round_id,
        actionIndex,
        action.branch_id,
        action.selected_skill,
        action.reason,
        action.evidence_delta,
      ))

      scheduleBatch(100, messages.map(message => ({
        offset: 0,
        task: () => callbacks.onSkillStart(message),
      })))

      scheduleBatch(0, messages.map((message, messageIndex) => {
        const action = round.branch_actions[messageIndex]
        const durationMs = skillDelay(round.round_id, messageIndex)
        return {
          offset: durationMs,
          task: () => callbacks.onSkillDone(completeSkillMessage(message, action.evidence_delta, durationMs)),
        }
      }))

      schedule(320, () => callbacks.onRoundSummary({
        round_id: round.round_id,
        intent: round.intent,
        goal: round.goal,
        summary: round.round_summary,
        is_extra_round: round.is_extra_round,
      }))
      schedule(100, () => callbacks.onOverview(buildOverview(round.round_id, completedEvidenceCount(round.round_id))))
    }

    schedule(420, () => callbacks.onAssistantStatus('正在合并多分支证据，并在本体层拓扑中标记共同根因、传播影响与噪声节点。'))
    schedule(420, callbacks.onAssistantDone)
    schedule(160, () => callbacks.onTopology(buildTopologyGraph()))
    schedule(520, () => {
      abortReportStream = streamStormReport(callbacks, request)
    })
  } catch (error) {
    callbacks.onError(error instanceof Error ? error.message : '风暴模式演示数据加载失败')
  }

  return () => {
    aborted = true
    timers.forEach(timer => window.clearTimeout(timer))
    abortReportStream?.()
  }
}

function skillDelay(roundId: number, actionIndex: number) {
  const delays = [100, 920, 2400, 4300, 6100, 8000]
  return delays[(roundId + actionIndex) % delays.length]
}
