import React, { useState, useEffect, useRef } from 'react'
import type { DiagnosisMessage } from '../types/diagnosis'
import { AlertTriangle, ChevronDown, ChevronRight, CheckCircle, Loader, Terminal } from 'lucide-react'

interface Props {
  msg: DiagnosisMessage
  autoOpenKey?: string
  onAutoOpenSettled?: (key: string) => void
  enableAnimation?: boolean
}

const UMODEL_PHRASES: Record<string, string> = {
  set_time_range: '锁定诊断上下文',
  analyze_trace: 'Trace → 服务调用关系',
  bind_entities: '可观测数据 → 服务/接口/实例实体',
  analyze_log: '日志 → 异常证据节点',
  check_metrics: '指标 → 运行实例状态',
  analyze_graph: '多源证据 → 实时观测图谱',
  infer_root_cause: '实体关系 + 证据链 → 候选根因',
  analyze_impact: '调用链路 + 业务关系 → 影响面',
  alert_context: '告警窗口 → 分支上下文',
  evidence_consistency: '多分支证据 → 一致性校验',
}

function umodelPhrase(msg: DiagnosisMessage): string {
  const skillKey = msg.skill_name ?? msg.tool_name?.split('/').pop() ?? ''
  return UMODEL_PHRASES[skillKey] ?? msg.content ?? skillKey
}

/** Renders execution_log lines one-by-one with a typewriter effect.
 *  Animation plays only on first open; subsequent toggles show all lines instantly.
 */
function AnimatedLog({ lines, enabled = true }: { lines: string[]; enabled?: boolean }) {
  const [visibleCount, setVisibleCount] = useState(enabled ? 0 : lines.length)
  const animatedRef = useRef(false)

  useEffect(() => {
    if (!enabled) {
      setVisibleCount(lines.length)
      return
    }
    if (animatedRef.current) {
      // Already played — show all immediately on re-open
      setVisibleCount(lines.length)
      return
    }
    animatedRef.current = true
    setVisibleCount(0)
    let i = 0
    const timer = setInterval(() => {
      i += 1
      setVisibleCount(i)
      if (i >= lines.length) {clearInterval(timer)}
    }, 60)
    return () => clearInterval(timer)
  }, [lines, enabled])

  return (
    <div className="bg-[#f8fafc] border border-[#e2e8f0] rounded p-2 space-y-0.5 max-h-36 overflow-y-auto">
      {lines.slice(0, visibleCount).map((line, i) => (
        <div
          key={i}
          className="flex items-start gap-1.5 text-sm font-mono text-[#374151] animate-fadeIn"
        >
          <span className="text-[#64748b] flex-shrink-0">{String(i + 1).padStart(2, '0')}</span>
          <span>{line}</span>
        </div>
      ))}
      {visibleCount < lines.length && (
        <div className="flex items-center gap-1 text-sm font-mono text-[#64748b] opacity-70">
          <Loader size={10} className="animate-spin" />
          <span>...</span>
        </div>
      )}
    </div>
  )
}

function TypewriterText({ text, enabled }: { text: string; enabled: boolean }) {
  const [visibleLength, setVisibleLength] = useState(enabled ? 0 : text.length)

  useEffect(() => {
    if (!enabled) {
      setVisibleLength(text.length)
      return
    }
    setVisibleLength(0)
    const timer = setInterval(() => {
      setVisibleLength(current => {
        const next = Math.min(text.length, current + 2)
        if (next >= text.length) {clearInterval(timer)}
        return next
      })
    }, 18)
    return () => clearInterval(timer)
  }, [text, enabled])

  return <>{text.slice(0, visibleLength)}</>
}

function useProgressiveSections(enabled: boolean, open: boolean, signature: string) {
  const [visibleSections, setVisibleSections] = useState(enabled ? 0 : Number.MAX_SAFE_INTEGER)
  const playedSignaturesRef = useRef(new Set<string>())

  useEffect(() => {
    if (!open || !enabled) {
      setVisibleSections(Number.MAX_SAFE_INTEGER)
      return
    }
    if (playedSignaturesRef.current.has(signature)) {
      setVisibleSections(Number.MAX_SAFE_INTEGER)
      return
    }
    playedSignaturesRef.current.add(signature)
    setVisibleSections(0)
    const timers = [1, 2, 3, 4, 5, 6].map(index => window.setTimeout(() => {
      setVisibleSections(index)
    }, index * 360))
    return () => timers.forEach(timer => window.clearTimeout(timer))
  }, [enabled, open, signature])

  return visibleSections
}

function AnimatedEvidence({ items, enabled }: { items: string[]; enabled: boolean }) {
  const [visibleCount, setVisibleCount] = useState(enabled ? 0 : items.length)

  useEffect(() => {
    if (!enabled) {
      setVisibleCount(items.length)
      return
    }
    setVisibleCount(0)
    let index = 0
    const timer = setInterval(() => {
      index += 1
      setVisibleCount(index)
      if (index >= items.length) {clearInterval(timer)}
    }, 180)
    return () => clearInterval(timer)
  }, [items, enabled])

  return (
    <ul className="space-y-1">
      {items.slice(0, visibleCount).map((e, i) => (
        <li key={i} className="flex items-start gap-1.5 text-sm text-[#374151] animate-fadeIn">
          <span className="mt-0.5 text-[#0e639c]">›</span>
          <span>{e}</span>
        </li>
      ))}
    </ul>
  )
}

function getTypewriterDuration(text: string): number {
  return Math.ceil(text.length / 2) * 18
}

function getAutoOpenAnimationDuration(msg: DiagnosisMessage): number {
  const durations = [0]

  if (msg.summary) {durations.push(360 + getTypewriterDuration(msg.summary))}

  const secondSectionTexts = [
    [msg.root_cause_status, msg.confidence ? `confidence=${msg.confidence}` : ''].filter(Boolean).join(' · '),
    msg.explanation ?? '',
    msg.recovery_action ?? '',
  ].filter(Boolean)
  if (secondSectionTexts.length > 0) {
    durations.push(720 + Math.max(...secondSectionTexts.map(getTypewriterDuration)))
  }

  if (msg.execution_log && msg.execution_log.length > 0) {
    durations.push(1080 + msg.execution_log.length * 60)
  }

  if (msg.evidence && msg.evidence.length > 0) {
    durations.push(1440 + msg.evidence.length * 180)
  }

  if (msg.input && Object.keys(msg.input).length > 0) {durations.push(1800)}
  if (msg.output && Object.keys(msg.output).length > 0) {durations.push(2160)}

  // Keep a conservative buffer so following cards appear only after animation visibly settles.
  return Math.max(...durations) + 1800
}

export default function SkillToolCard({ msg, autoOpenKey, onAutoOpenSettled, enableAnimation = true }: Props) {
  const shouldAutoOpen = !msg.default_collapsed && (msg.skill_name === 'infer_root_cause' || msg.status === 'failed')
  const [open, setOpen] = useState(shouldAutoOpen)
  const settledAutoOpenRef = useRef(new Set<string>())
  const isRunning = msg.status === 'running'
  const isFailed = msg.status === 'failed'
  const statusLabel = isRunning ? '执行中Skill工具' : isFailed ? '异常Skill工具' : '已执行Skill工具'
  const phrase = umodelPhrase(msg)

  const durationLabel = msg.duration_ms != null
    ? msg.duration_ms >= 1000
      ? `${(msg.duration_ms / 1000).toFixed(1)} s`
      : `${msg.duration_ms} ms`
    : null
  const progressiveSignature = [
    msg.summary,
    msg.root_cause_status,
    msg.confidence,
    msg.explanation,
    msg.recovery_action,
    msg.execution_log?.join('\n'),
    msg.evidence?.join('\n'),
    msg.input ? JSON.stringify(msg.input) : '',
    msg.output ? JSON.stringify(msg.output) : '',
  ].join('|')
  const shouldRunProgressiveAnimation = enableAnimation && shouldAutoOpen
  const visibleSections = useProgressiveSections(shouldRunProgressiveAnimation, open, progressiveSignature)
  const progressiveAnimationActive = enableAnimation && shouldAutoOpen && visibleSections !== Number.MAX_SAFE_INTEGER

  useEffect(() => {
    if (shouldAutoOpen) {setOpen(true)}
  }, [shouldAutoOpen])

  useEffect(() => {
    if (!shouldAutoOpen || !autoOpenKey || !onAutoOpenSettled) {return}
    if (!open || settledAutoOpenRef.current.has(autoOpenKey)) {
      settledAutoOpenRef.current.add(autoOpenKey)
      onAutoOpenSettled(autoOpenKey)
      return
    }
    const timer = window.setTimeout(() => {
      settledAutoOpenRef.current.add(autoOpenKey)
      onAutoOpenSettled(autoOpenKey)
    }, getAutoOpenAnimationDuration(msg))
    return () => window.clearTimeout(timer)
  }, [autoOpenKey, msg, onAutoOpenSettled, open, shouldAutoOpen])

  return (
    <div className="rounded-md border border-[#dbe7f3] bg-white text-sm overflow-hidden shadow-[0_1px_5px_rgba(15,23,42,0.06)]">
      {/* Header row */}
      <button
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-[#f8fafc] transition-colors"
        onClick={() => setOpen(o => !o)}
      >
        {isRunning && <Loader size={13} className="text-[#0e639c] animate-spin flex-shrink-0" />}
        {isFailed && <AlertTriangle size={13} className="text-[#b45309] flex-shrink-0" />}
        {!isRunning && !isFailed && <CheckCircle size={13} className="text-[#0e639c] flex-shrink-0" />}
        <span className="text-[#334155] font-mono text-sm">{statusLabel}</span>
        <span className="text-[#9ca3af] font-mono text-sm">·</span>
        <span className="text-[#0e639c] font-mono text-sm font-semibold">UModel：{phrase}</span>
        <span className="text-[#9ca3af] font-mono text-sm">·</span>
        <span className="text-[#475569] font-mono text-sm font-semibold">{msg.tool_name}</span>
        {!isRunning && durationLabel && (
          <span className="ml-1 text-[#64748b] font-mono text-sm opacity-80">{durationLabel}</span>
        )}
        <span className="ml-auto flex-shrink-0">
          {open
            ? <ChevronDown size={13} className="text-[#9ca3af]" />
            : <ChevronRight size={13} className="text-[#9ca3af]" />
          }
        </span>
      </button>

      {/* Expanded detail */}
      {open && (
        <div className="border-t border-[#e2e8f0] px-3 py-2 space-y-3">
          {msg.summary && visibleSections >= 1 && (
            <div>
              <div className="text-[#0e639c] text-sm font-semibold mb-1">摘要</div>
              <div className="text-[#1f2937] text-sm leading-relaxed">
                <TypewriterText text={msg.summary} enabled={progressiveAnimationActive} />
              </div>
            </div>
          )}

          {(msg.root_cause_status || msg.confidence) && visibleSections >= 2 && (
            <div>
              <div className="text-[#0e639c] text-sm font-semibold mb-1">根因置信度</div>
              <div className="text-[#1f2937] text-sm leading-relaxed">
                <TypewriterText text={[msg.root_cause_status, msg.confidence ? `confidence=${msg.confidence}` : ''].filter(Boolean).join(' · ')} enabled={progressiveAnimationActive} />
              </div>
            </div>
          )}

          {msg.explanation && visibleSections >= 2 && (
            <div>
              <div className="text-[#0e639c] text-sm font-semibold mb-1">执行原因</div>
              <div className="text-[#1f2937] text-sm leading-relaxed">
                <TypewriterText text={msg.explanation} enabled={progressiveAnimationActive} />
              </div>
            </div>
          )}

          {msg.recovery_action && visibleSections >= 2 && (
            <div>
              <div className="text-[#92400e] text-sm font-semibold mb-1">异常恢复</div>
              <div className="text-[#1f2937] text-sm leading-relaxed">
                <TypewriterText text={msg.recovery_action} enabled={progressiveAnimationActive} />
              </div>
            </div>
          )}

          {/* Execution Log — animated typewriter */}
          {msg.execution_log && msg.execution_log.length > 0 && visibleSections >= 3 && (
            <div>
              <div className="flex items-center gap-1.5 text-[#0e639c] text-sm font-semibold mb-1">
                <Terminal size={11} />
                执行日志
              </div>
              <AnimatedLog lines={msg.execution_log} enabled={progressiveAnimationActive} />
            </div>
          )}

          {msg.evidence && msg.evidence.length > 0 && visibleSections >= 4 && (
            <div>
              <div className="text-[#0e639c] text-sm font-semibold mb-1">🔍 证据</div>
              <AnimatedEvidence items={msg.evidence} enabled={progressiveAnimationActive} />
            </div>
          )}

          {msg.input && Object.keys(msg.input).length > 0 && visibleSections >= 5 && (
            <div>
              <div className="text-[#0e639c] text-sm font-semibold mb-1">📥 输入</div>
              <pre className="text-sm text-[#334155] bg-[#f8fafc] border border-[#e2e8f0] rounded p-2 overflow-auto max-h-28 font-mono">
                {JSON.stringify(msg.input, null, 2)}
              </pre>
            </div>
          )}

          {msg.output && Object.keys(msg.output).length > 0 && visibleSections >= 6 && (
            <div>
              <div className="text-[#0e639c] text-sm font-semibold mb-1">📤 输出</div>
              <pre className="text-sm text-[#334155] bg-[#f8fafc] border border-[#e2e8f0] rounded p-2 overflow-auto max-h-28 font-mono">
                {JSON.stringify(msg.output, null, 2)}
              </pre>
            </div>
          )}

        </div>
      )}
    </div>
  )
}
