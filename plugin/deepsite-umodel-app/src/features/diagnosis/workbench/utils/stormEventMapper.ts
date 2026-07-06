import type { DiagnosisMessage, EventStreamItem, StormOverview } from '../types/diagnosis'

let stormEventIndex = 0

function nextId(prefix: string): string {
  stormEventIndex += 1
  return `${prefix}-${stormEventIndex}`
}

/**
 * Map a storm-mode DiagnosisMessage into zero or more EventStreamItems.
 */
export function mapStormMessageToEvent(msg: DiagnosisMessage): EventStreamItem[] {
  const base: Pick<EventStreamItem, 'mode' | 'timestamp'> = {
    mode: 'storm',
    timestamp: new Date().toISOString(),
  }

  // ── User message ──────────────────────────────────────────────────────
  if (msg.role === 'user') {
    return [{
      ...base,
      id: nextId('storm-user'),
      kind: 'storm_init',
      phase: 'init',
      title: '用户输入',
      summary: msg.content ?? '',
      status: 'info',
    }]
  }

  // ── Session line ──────────────────────────────────────────────────────
  if (msg.type === 'text' || msg.type === 'assistant_streaming') {
    const content = msg.content ?? ''
    if (content.includes('模式：')) {
      return [{
        ...base,
        id: nextId('storm-meta'),
        kind: 'storm_init',
        phase: 'init',
        title: '风暴初始化',
        summary: content.replace(/模式：/, ''),
        status: 'info',
      }]
    }
    // Filter out internal planner noise
    if (/已选择\s*Skill|本轮\s*Skill|Intent[：:]/.test(content)) {
      return []
    }
    return [{
      ...base,
      id: nextId('storm-text'),
      kind: 'text',
      title: '',
      summary: content,
      status: 'info',
    }]
  }

  // ── Storm overview ────────────────────────────────────────────────────
  if (msg.type === 'storm_overview' && msg.storm_overview) {
    return [{
      ...base,
      id: nextId('storm-overview'),
      kind: 'storm_init',
      phase: 'init',
      title: '风暴任务总览',
      summary: buildOverviewSummary(msg.storm_overview),
      status: 'info',
      raw: msg.storm_overview,
    }]
  }

  // ── Storm round summary ───────────────────────────────────────────────
  if (msg.type === 'storm_round_summary' && msg.storm_round_summary) {
    return [{
      ...base,
      id: nextId('storm-round'),
      kind: 'storm_phase_summary',
      phase: `phase_${msg.storm_round_summary.round_id}`,
      title: `Phase ${msg.storm_round_summary.round_id} 汇总`,
      summary: msg.storm_round_summary.summary ?? msg.storm_round_summary.intent ?? '',
      status: 'success',
      raw: msg.storm_round_summary,
    }]
  }

  // ── Skill call (storm actor) ──────────────────────────────────────────
  if (msg.type === 'skill_call') {
    const skillKey = msg.skill_name ?? msg.tool_name?.split('/').pop() ?? ''
    const actor = skillKey.startsWith('storm.') ? skillKey : `storm.${skillKey}`
    return [{
      ...base,
      id: nextId(`storm-actor-${skillKey}`),
      kind: 'storm_actor',
      actor,
      title: actor,
      summary: msg.summary || msg.content || '',
      status: msg.status === 'running' ? 'running' : msg.status === 'failed' ? 'failed' : 'success',
      details: {
        input: msg.input,
        output: msg.output,
        evidence: msg.evidence,
        executionLog: msg.execution_log,
        explanation: msg.explanation,
      },
      raw: msg,
    }]
  }

  // ── Call graph ────────────────────────────────────────────────────────
  if (msg.type === 'call_graph') {
    return [{
      ...base,
      id: nextId('storm-topo'),
      kind: 'object_selection',
      phase: 'init',
      title: '拓扑更新',
      summary: `${msg.call_graph?.nodes.length ?? 0} 个节点, ${msg.call_graph?.edges.length ?? 0} 条边`,
      status: 'info',
      raw: msg.call_graph,
    }]
  }

  // ── Report ────────────────────────────────────────────────────────────
  if (msg.type === 'report' || msg.type === 'report_streaming') {
    return [{
      ...base,
      id: nextId('storm-report'),
      kind: 'report',
      phase: 'report',
      title: msg.report_title || '风暴诊断报告',
      summary: msg.content ? (msg.content.length > 200 ? msg.content.slice(0, 200) + '...' : msg.content) : '报告生成中...',
      status: msg.type === 'report_streaming' ? 'running' : 'success',
      raw: msg,
    }]
  }

  return []
}

function buildOverviewSummary(overview: StormOverview): string {
  const parts = [
    `告警: ${overview.alert_api}`,
    `时间: ${overview.time_window}`,
    `${overview.error_trace_count} 条 Error Trace`,
    `${overview.diagnosis_branch_count} 个诊断分支`,
    `轮次 ${overview.current_round}`,
  ]
  return parts.join(' · ')
}

/**
 * Convert storm-mode messages into a unified event stream.
 */
export function buildStormEventStream(messages: DiagnosisMessage[]): EventStreamItem[] {
  stormEventIndex = 0
  const events: EventStreamItem[] = []
  for (const msg of messages) {
    const mapped = mapStormMessageToEvent(msg)
    for (const evt of mapped) {
      events.push(evt)
    }
  }
  return events
}
