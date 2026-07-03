import type { DiagnosisMessage, EventStreamItem } from './diagnosisTypes'

const SKILL_PHASE_MAP: Record<string, string> = {
  set_time_range: 'object_selection',
  alert_context: 'object_selection',
  bind_entities: 'object_selection',
  analyze_trace: 'evidence_confirmation',
  analyze_log: 'evidence_confirmation',
  check_metrics: 'evidence_confirmation',
  analyze_graph: 'evidence_confirmation',
  evidence_consistency: 'evidence_confirmation',
  infer_root_cause: 'root_cause_decision',
  analyze_impact: 'impact_scope_decision',
  generate_report: 'report',
}

const KIND_MAP: Record<string, EventStreamItem['kind']> = {
  object_selection: 'object_selection',
  evidence_confirmation: 'evidence_confirmation',
  root_cause_decision: 'root_cause_decision',
  impact_scope_decision: 'impact_scope_decision',
  report: 'report',
}

const PHASE_LABELS: Record<string, string> = {
  object_selection: '识别对象',
  evidence_confirmation: '证据确认',
  root_cause_decision: '根因判定',
  impact_scope_decision: '影响面',
  report: '报告',
}

function phaseLabel(phase: string): string {
  return PHASE_LABELS[phase] ?? phase
}
/** Extract entityIds from evidence/summary/raw for related_nodes enrichment. */
function extractRelatedNodes(skillKey: string, msg: DiagnosisMessage): string[] {
  const ids = new Set<string>()

  // ── Priority 1: Structured entity data from bind_entities output ────
  if (skillKey === 'bind_entities' && msg.output) {
    const output = msg.output as Record<string, unknown>
    for (const key of ['services', 'instances', 'interfaces', 'containers']) {
      const arr = output[key]
      if (Array.isArray(arr)) {
        for (const item of arr) {
          if (typeof item === 'string' && isValidEntityName(item)) {
            ids.add(item)
          }
        }
      }
    }
    // Also extract from bindings array if present
    const bindings = output['bindings']
    if (Array.isArray(bindings)) {
      for (const b of bindings) {
        if (typeof b === 'object' && b !== null) {
          const name = (b as Record<string, unknown>).name || (b as Record<string, unknown>).ip || (b as Record<string, unknown>).path
          if (typeof name === 'string' && isValidEntityName(name)) {
            ids.add(name)
          }
        }
      }
    }
    if (ids.size > 0) return [...ids].slice(0, 20)
  }

  // ── Priority 2: Other skills — also check output for entity-like fields
  if (msg.output) {
    const output = msg.output as Record<string, unknown>
    for (const key of ['services', 'root_cause_service', 'root_cause_component']) {
      const val = output[key]
      if (typeof val === 'string' && isValidEntityName(val)) {
        ids.add(val)
      } else if (Array.isArray(val)) {
        for (const item of val) {
          if (typeof item === 'string' && isValidEntityName(item)) {
            ids.add(item)
          }
        }
      }
    }
  }

  // ── Priority 3: Regex fallback from evidence/summary text ───────────
  if (msg.evidence) {
    for (const line of msg.evidence) {
      const matches = line.match(/([\w.-]+(?:\s*[\w.-]+){0,3})\s*(?:异常|失败|超时|拒绝|瓶颈|压力|root|候选|确认)/gi)
      if (matches) {
        for (const m of matches) {
          const trimmed = m.replace(/\s*(异常|失败|超时|拒绝|瓶颈|压力|root|候选|确认)\s*/gi, '').trim()
          if (isValidEntityName(trimmed)) ids.add(trimmed)
        }
      }
    }
  }
  // From root_cause_status — only if it looks like a real entity name
  if (msg.root_cause_status && isValidEntityName(msg.root_cause_status)) {
    ids.add(msg.root_cause_status)
  }
  // From summary — extract service/interface/dependency names
  const summary = msg.summary ?? ''
  const namePatterns = [
    /(\S+)\s*(?:异常|失败|超时|拒绝|不可用|瓶颈|告警|根因|入口|传播|影响)/g,
    /(?:service|node|组件|实例|依赖|接口|dep|svc|ins)\s*[:：]\s*(\S+)/gi,
  ]
  for (const pat of namePatterns) {
    let m: RegExpExecArray | null
    while ((m = pat.exec(summary)) !== null) {
      const name = m[1]?.trim()
      if (name && isValidEntityName(name)) ids.add(name)
    }
  }
  return ids.size > 0 ? [...ids].slice(0, 8) : []
}

/** Filter out meta-terms, short junk, pure numbers, and measurement fragments. */
function isValidEntityName(name: string): boolean {
  if (name.length < 3) return false
  if (/^\d+$/.test(name)) return false
  // Chinese quantifier fragments: "个日志", "条trace" etc.
  if (/^[个数条只张片辆次回]/.test(name)) return false
  // Diagnostic meta-terms and internal IDs
  const blacklist = /^(trace|log|metric|dcc|root|candidate|noise|entry|impact|propagat|observ|confirm|skill|null|none|unknown|未?知|全部|所有|总计|合计)$/i
  if (blacklist.test(name)) return false
  // Pure uppercase acronyms ≤ 4 chars (likely meta, not entity)
  if (/^[A-Z]{2,4}$/.test(name) && !/[a-z]/.test(name)) return false
  // Common Chinese meta fragments
  if (/^(条|个|种|类|级|层|次)\s*(日志|trace|错误|异常|告警|指标)/.test(name)) return false
  return true
}
/** Build human-readable narrative summaries for key decision events. */
function buildNarrativeSummary(skillKey: string, rawSummary: string, msg: DiagnosisMessage): string {
  // For evidence-gathering skills, keep the original summary — it's already descriptive
  if (['analyze_trace', 'analyze_log', 'check_metrics', 'analyze_graph', 'bind_entities',
       'set_time_range', 'alert_context', 'evidence_consistency'].includes(skillKey)) {
    return rawSummary || `${skillKey} 完成`
  }

  // For infer_root_cause — produce a decision narrative
  if (skillKey === 'infer_root_cause' && msg.status === 'success') {
    const parts: string[] = []
    if (msg.root_cause_status) {
      parts.push(`确认 ${msg.root_cause_status} 为根因`)
    }
    if (msg.summary) {
      parts.push(msg.summary)
    } else if (msg.confidence) {
      parts.push(`置信度 ${msg.confidence}`)
    }
    if (parts.length > 0) return parts.join(' · ')
    if (rawSummary.includes('root_cause') || rawSummary.includes('根因')) return rawSummary
    return `根因已判定`
  }

  // For analyze_impact — produce an impact narrative
  if (skillKey === 'analyze_impact' && msg.status === 'success') {
    if (msg.summary) return msg.summary
    return `影响面分析完成`
  }

  // For report generation
  if (skillKey === 'generate_report') {
    return `诊断报告生成中...`
  }

  // Fallback: return the original summary
  return rawSummary || `${skillKey} 完成`
}
/**
 * Map a single DiagnosisMessage into zero or more EventStreamItems.
 * Returns an array because some messages (e.g. report) may be split.
 */
export function mapDiagnosisMessageToEvent(msg: DiagnosisMessage, index: number): EventStreamItem[] {
  const base: Pick<EventStreamItem, 'mode' | 'timestamp'> = {
    mode: 'normal',
    timestamp: new Date().toISOString(),
  }

  // ── User message ──────────────────────────────────────────────────────
  if (msg.role === 'user') {
    return [{
      ...base,
      id: `user-${index}`,
      kind: 'text',
      phase: 'object_selection',
      title: '用户输入',
      summary: msg.content ?? '',
      status: 'info',
    }]
  }

  // ── Skill call ─────────────────────────────────────────────────────────
  if (msg.type === 'skill_call') {
    const skillKey = msg.skill_name ?? msg.tool_name?.split('/').pop() ?? ''
    const phase = SKILL_PHASE_MAP[skillKey] ?? 'evidence_confirmation'
    const rawSummary = msg.summary || msg.content || ''
    // Build narrative summary for key decision events
    const narrativeSummary = buildNarrativeSummary(skillKey, rawSummary, msg)
    // Enrich related_nodes from available structured data
    const relatedNodes = extractRelatedNodes(skillKey, msg)
    return [{
      ...base,
      id: `skill-${index}-${skillKey}`,
      kind: KIND_MAP[phase] ?? 'skill_call',
      phase,
      title: skillKey,
      summary: narrativeSummary,
      status: msg.status === 'running' ? 'running' : msg.status === 'failed' ? 'failed' : 'success',
      related_nodes: relatedNodes,
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

  // ── Plain text / streaming ─────────────────────────────────────────────
  if (msg.type === 'text' || msg.type === 'assistant_streaming') {
    const content = msg.content ?? ''
    if (!content.trim()) return []

    // Session mode line — show simplified display name only
    if (content.startsWith('模式：')) {
      return [{
        ...base,
        id: `meta-${index}`,
        kind: 'text',
        phase: 'object_selection',
        title: '诊断会话',
        summary: content.replace(/模式：/, ''),
        status: 'info',
      }]
    }

    // Filter out internal planner noise ("已选择 Skill", "本轮 Skill", "Intent：")
    if (/已选择\s*Skill|本轮\s*Skill|Intent[：:]/.test(content)) {
      return []
    }
    // Old backend opening fluff (already removed from backend; keep as safety net)
    if (/我将按照系统化故障排查流程进行分析/.test(content)) {
      return []
    }

    // Error / recovery hint from skill error callback
    if (content.includes('执行遇到问题')) {
      return [{
        ...base,
        id: `text-${index}`,
        kind: 'text',
        title: '异常提示',
        summary: content,
        status: 'failed',
      }]
    }

    // Evidence conflict / root cause unconfirmed
    if (content.includes('证据冲突') || content.includes('根因待确认') || content.includes('无法确认根因')) {
      return [{
        ...base,
        id: `text-${index}`,
        kind: 'text',
        phase: 'root_cause_decision',
        title: '根因判定',
        summary: content,
        status: 'info',
      }]
    }

    return [{
      ...base,
      id: `text-${index}`,
      kind: 'text',
      title: '',
      summary: content,
      status: 'info',
    }]
  }

  // ── Call graph ─────────────────────────────────────────────────────────
  if (msg.type === 'call_graph') {
    // Call graphs are displayed in the topology panel, but we emit a
    // lightweight event for the timeline as well.
    return [{
      ...base,
      id: `topo-${index}`,
      kind: 'object_selection',
      phase: 'object_selection',
      title: '拓扑更新',
      summary: `${msg.call_graph?.nodes.length ?? 0} 个节点, ${msg.call_graph?.edges.length ?? 0} 条边`,
      status: 'info',
      raw: msg.call_graph,
    }]
  }

  // ── Report ─────────────────────────────────────────────────────────────
  if (msg.type === 'report' || msg.type === 'report_streaming') {
    const title = msg.report_title || '诊断报告'
    const renderPlain = msg.render_as === 'plain' || msg.report_title === ''
    return [{
      ...base,
      id: `report-${index}`,
      kind: 'report',
      phase: 'report',
      title,
      summary: renderPlain ? (msg.content ?? '') : `点击展开查看${title}`,
      status: msg.type === 'report_streaming' ? 'running' : 'success',
      raw: msg,
    }]
  }

  // ── Fallback ───────────────────────────────────────────────────────────
  return [{
    ...base,
    id: `unknown-${index}`,
    kind: 'text',
    title: '',
    summary: JSON.stringify(msg),
    status: 'info',
  }]
}

/**
 * Convert an array of DiagnosisMessages into a unified event stream.
 * Call graphs are filtered out since they are rendered in the topology panel.
 */
export function buildNormalEventStream(messages: DiagnosisMessage[]): EventStreamItem[] {
  const events: EventStreamItem[] = []
  for (let i = 0; i < messages.length; i++) {
    const mapped = mapDiagnosisMessageToEvent(messages[i], i)
    for (const evt of mapped) {
      events.push(evt)
    }
  }
  return events
}

export { phaseLabel, PHASE_LABELS }
