import { useEffect, useState, type ReactNode } from 'react'
import type { DiagnosisMessage, DiagnosisMode } from '../types/diagnosis'
import SkillToolCard from './SkillToolCard'
import ServiceCallGraph from './ServiceCallGraph'
import DiagnosisReport from './DiagnosisReport'
import StormOverviewCard from './StormOverviewCard'
import StormRoundSummary from './StormRoundSummary'
import { ActivitySquare, Check, Copy, Pencil } from 'lucide-react'

interface Props {
  messages: DiagnosisMessage[]
  loading?: boolean
  mode?: DiagnosisMode
  onEditUserMessage?: (content: string) => void
}

function GeneratingDots() {
  return (
    <span className="generating-dots" aria-label="正在生成">
      <span />
      <span />
      <span />
    </span>
  )
}

function GeneratingRow({ label = '正在组织诊断结果' }: { label?: string }) {
  return (
    <div className="max-w-[85%] text-[#6b7280] text-sm leading-relaxed flex items-center gap-2">
      <span>{label}</span>
      <GeneratingDots />
    </div>
  )
}

function AssistantStatusText({ content, isStreaming }: { content?: string; isStreaming: boolean }) {
  return (
    <div className="max-w-[85%] text-[#6b7280] text-sm leading-relaxed flex items-center gap-2">
      <span>{content}</span>
      {isStreaming && <GeneratingDots />}
    </div>
  )
}

function isTableSeparator(line: string): boolean {
  return /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(line.trim())
}

function splitTableRow(line: string): string[] {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(cell => cell.trim())
}

function latestIntent(messages: DiagnosisMessage[]): string | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const content = messages[index].content ?? ''
    const match = content.match(/Intent：([a-z_]+)/)
    if (match) return match[1]
  }
  return null
}

function loadingLabelFor(messages: DiagnosisMessage[], mode?: DiagnosisMode): string {
  const intent = latestIntent(messages)
  if (intent === 'followup_inspect_logs') return '正在查询日志...'
  if (intent === 'followup_inspect_metrics') return '正在查询指标...'
  if (intent === 'followup_inspect_traces') return '正在查询 Trace...'
  if (intent === 'followup_inspect_service_map') return '正在分析服务拓扑...'
  if (intent === 'followup_inspect_business_impact') return '正在分析业务影响...'
  if (intent === 'observability_query') return '正在分析服务异常...'
  if (mode === 'observability') return '正在查询观测数据...'
  return '正在组织诊断结果...'
}

function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = []
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g
  let lastIndex = 0
  let match: RegExpExecArray | null
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) nodes.push(text.slice(lastIndex, match.index))
    const token = match[0]
    if (token.startsWith('**')) {
      nodes.push(<strong key={nodes.length} className="font-semibold text-[#111827]">{token.slice(2, -2)}</strong>)
    } else if (token.startsWith('`')) {
      nodes.push(<code key={nodes.length} className="rounded bg-[#f3f4f6] px-1 py-0.5 text-[0.92em] text-[#111827]">{token.slice(1, -1)}</code>)
    } else {
      const linkMatch = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/)
      const label = linkMatch?.[1] ?? token
      const href = linkMatch?.[2] ?? '#'
      nodes.push(
        <a key={nodes.length} className="text-[#0e639c] underline underline-offset-2" href={href} target="_blank" rel="noreferrer">
          {label}
        </a>,
      )
    }
    lastIndex = pattern.lastIndex
  }
  if (lastIndex < text.length) nodes.push(text.slice(lastIndex))
  return nodes
}

function PlainAssistantAnswer({ content, isStreaming }: { content?: string; isStreaming: boolean }) {
  const lines = (content ?? '').split('\n')
  const blocks: JSX.Element[] = []
  let index = 0
  let blockIndex = 0

  while (index < lines.length) {
    const line = lines[index]
    if (!line.trim()) {
      index += 1
      continue
    }

    if (line.trim().startsWith('|') && lines[index + 1] && isTableSeparator(lines[index + 1])) {
      const header = splitTableRow(line)
      const rows: string[][] = []
      index += 2
      while (index < lines.length && lines[index].trim().startsWith('|')) {
        rows.push(splitTableRow(lines[index]))
        index += 1
      }
      blocks.push(
        <div key={blockIndex++} className="overflow-x-auto rounded-lg border border-[#e5e7eb]">
          <table className="min-w-full text-xs text-left border-collapse">
            <thead className="bg-[#f9fafb] text-[#4b5563]">
              <tr>{header.map((cell, cellIndex) => <th key={cellIndex} className="px-3 py-2 font-semibold border-b border-[#e5e7eb]">{renderInline(cell)}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={rowIndex} className="border-t border-[#f3f4f6]">
                  {row.map((cell, cellIndex) => <td key={cellIndex} className="px-3 py-2 text-[#374151]">{renderInline(cell)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      )
      continue
    }

    if (line.trim().startsWith('```')) {
      const codeLines: string[] = []
      index += 1
      while (index < lines.length && !lines[index].trim().startsWith('```')) {
        codeLines.push(lines[index])
        index += 1
      }
      if (index < lines.length) index += 1
      blocks.push(
        <pre key={blockIndex++} className="overflow-x-auto rounded-lg bg-[#111827] px-3 py-2 text-xs leading-relaxed text-white">
          <code>{codeLines.join('\n')}</code>
        </pre>,
      )
      continue
    }

    if (line.trim().startsWith('- ') || /^\d+\.\s+/.test(line.trim())) {
      const items: string[] = []
      while (index < lines.length && (lines[index].trim().startsWith('- ') || /^\d+\.\s+/.test(lines[index].trim()))) {
        items.push(lines[index].trim().replace(/^(?:-\s+|\d+\.\s+)/, ''))
        index += 1
      }
      blocks.push(
        <ul key={blockIndex++} className="list-disc pl-5 space-y-1 text-sm text-[#374151]">
          {items.map((item, itemIndex) => <li key={itemIndex}>{renderInline(item)}</li>)}
        </ul>,
      )
      continue
    }

    const paragraph: string[] = []
    while (
      index < lines.length
      && lines[index].trim()
      && !lines[index].trim().startsWith('|')
      && !lines[index].trim().startsWith('- ')
      && !/^\d+\.\s+/.test(lines[index].trim())
      && !lines[index].trim().startsWith('```')
    ) {
      paragraph.push(lines[index].trim())
      index += 1
    }
    blocks.push(<p key={blockIndex++} className="text-sm leading-relaxed text-[#374151]">{renderInline(paragraph.join(' '))}</p>)
  }

  return (
    <div className="max-w-[90%] space-y-3 text-sm leading-relaxed text-[#374151]">
      {blocks}
      {isStreaming && (
        <div className="text-[#6b7280] inline-flex items-center gap-1.5">
          正在整理查询结果
          <GeneratingDots />
        </div>
      )}
    </div>
  )
}

function buildInferRootCauseGateKey(msg: DiagnosisMessage, index: number): string {
  return [
    msg.run_id ?? 'history',
    index,
    msg.summary ?? '',
    msg.root_cause_status ?? '',
    msg.confidence ?? '',
    msg.explanation ?? '',
    msg.execution_log?.join('\n') ?? '',
    msg.evidence?.join('\n') ?? '',
  ].join('|')
}

export default function AgentChatPanel({ messages, loading = false, mode, onEditUserMessage }: Props) {
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null)
  const [releasedInferRootCauseKey, setReleasedInferRootCauseKey] = useState<string | null>(null)
  const hasActiveGeneration = messages.some(msg =>
    msg.type === 'assistant_streaming'
    || msg.type === 'report_streaming'
    || (msg.type === 'skill_call' && msg.status === 'running')
  )
  const enableSkillAutoAnimation = false
  let inferRootCauseGateIndex = -1
  let inferRootCauseGateKey: string | null = null
  if (enableSkillAutoAnimation) {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const msg = messages[index]
      if (
        msg.type === 'skill_call'
        && msg.skill_name === 'infer_root_cause'
        && msg.default_collapsed !== true
        && msg.status !== 'running'
      ) {
        inferRootCauseGateIndex = index
        inferRootCauseGateKey = buildInferRootCauseGateKey(msg, index)
        break
      }
    }
  }
  const hasDeferredFollowingContent = inferRootCauseGateKey != null
    && releasedInferRootCauseKey !== inferRootCauseGateKey
    && messages.some((_, index) => index > inferRootCauseGateIndex)

  useEffect(() => {
    if (!inferRootCauseGateKey) {
      setReleasedInferRootCauseKey(null)
    }
  }, [inferRootCauseGateKey])

  if (messages.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center gap-3 py-24 select-none">
        <div className="relative w-16 h-16 rounded-2xl bg-[#007acc] flex items-center justify-center shadow-[0_10px_30px_rgba(0,122,204,0.22)]">
          <ActivitySquare size={30} className="text-white" />
          <span className="absolute -right-1 -bottom-1 w-4 h-4 rounded-full bg-[#10b981] border-2 border-white" />
        </div>
        <p className="text-[#111827] text-base font-semibold">Mobile Ops 智能诊断</p>
        <p className="text-[#6b7280] text-xs max-w-sm leading-relaxed">
          基于 MModel 可观测本体编排 Trace、Log、Metric 与实体关系 Skill，生成可解释的根因定位、证据链和影响面分析。
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4 w-full max-w-7xl mx-auto px-5 py-5">
      {messages.map((msg, i) => {
        if (hasDeferredFollowingContent && i > inferRootCauseGateIndex) {
          return null
        }

        if (msg.role === 'user') {
          const content = msg.content ?? ''
          const copied = copiedIndex === i
          const followsReport = i > 0 && messages[i - 1]?.type === 'report'
          return (
            <div key={i} className={`flex items-start justify-end ${followsReport ? 'mt-8' : ''}`}>
              <div className="flex max-w-[78%] flex-col items-end gap-1.5">
                <div className="bg-[#f3f4f6] text-[#111827] rounded-xl rounded-tr-sm px-4 py-2.5 text-sm leading-relaxed shadow-[0_2px_10px_rgba(15,23,42,0.08)]">
                  {content}
                </div>
                <div className="flex items-center gap-2 pr-1 text-[#8b949e]">
                  <button
                    className="rounded p-1 hover:bg-[#f3f4f6] hover:text-[#4b5563] transition-colors"
                    title={copied ? '已复制' : '复制'}
                    onClick={() => {
                      navigator.clipboard?.writeText(content)
                      setCopiedIndex(i)
                      window.setTimeout(() => setCopiedIndex(current => current === i ? null : current), 5000)
                    }}
                  >
                    {copied ? <Check size={15} /> : <Copy size={15} />}
                  </button>
                  <button
                    className="rounded p-1 hover:bg-[#f3f4f6] hover:text-[#4b5563] transition-colors"
                    title="修改"
                    onClick={() => onEditUserMessage?.(content)}
                  >
                    <Pencil size={15} />
                  </button>
                </div>
              </div>
            </div>
          )
        }

        if (msg.type === 'text' || msg.type === 'assistant_streaming') {
          const isStreaming = msg.type === 'assistant_streaming'
          return (
            <div key={i} className="flex items-center">
              <AssistantStatusText content={msg.content} isStreaming={isStreaming} />
            </div>
          )
        }

        if (msg.type === 'skill_call') {
          const autoOpenKey = msg.skill_name === 'infer_root_cause'
            ? buildInferRootCauseGateKey(msg, i)
            : undefined
          return (
            <div key={i} className="flex items-start">
              <div className="flex-1 max-w-[90%]">
                <SkillToolCard
                  msg={msg}
                  autoOpenKey={autoOpenKey}
                  onAutoOpenSettled={autoOpenKey ? setReleasedInferRootCauseKey : undefined}
                  enableAnimation={enableSkillAutoAnimation}
                />
              </div>
            </div>
          )
        }

        if (msg.type === 'storm_overview') {
          return (
            <div key={i} className="flex items-start">
              <div className="flex-1 max-w-[90%]">
                {msg.storm_overview && <StormOverviewCard overview={msg.storm_overview} />}
              </div>
            </div>
          )
        }

        if (msg.type === 'storm_round_summary') {
          return (
            <div key={i} className="flex items-start">
              <div className="flex-1 max-w-[90%]">
                {msg.storm_round_summary && <StormRoundSummary summary={msg.storm_round_summary} />}
              </div>
            </div>
          )
        }

        if (msg.type === 'report' || msg.type === 'report_streaming') {
          const isStreaming = msg.type === 'report_streaming'
          const renderPlain = msg.render_as === 'plain' || msg.report_title === ''
          if (renderPlain) {
            return (
              <div key={i} className="flex items-start">
                <PlainAssistantAnswer content={msg.content} isStreaming={isStreaming} />
              </div>
            )
          }
          return (
            <div key={i} className="flex items-start">
              <div className="flex-1 max-w-[90%] bg-white border border-[#e5e7eb] rounded-xl p-4 shadow-[0_8px_24px_rgba(15,23,42,0.08)]">
                <div className="flex items-center gap-2 text-sm text-[#0e639c] font-semibold mb-3">
                  <span>{msg.report_title ?? 'Mobile Ops 故障诊断报告'}</span>
                  {isStreaming && (
                    <span className="text-[#6b7280] font-normal inline-flex items-center gap-1.5">
                      报告生成中
                      <GeneratingDots />
                    </span>
                  )}
                </div>
                {(msg.content ?? '').trim() ? (
                  <DiagnosisReport content={msg.content ?? ''} />
                ) : isStreaming && (
                  <div className="rounded-lg border border-[#e5e7eb] bg-[#f9fafb] px-3 py-2 text-sm text-[#6b7280] flex items-center gap-2">
                    正在生成报告分节
                    <GeneratingDots />
                  </div>
                )}
              </div>
            </div>
          )
        }

        if (msg.type === 'call_graph') {
          return (
            <div key={i} className="flex items-start">
              <div className="flex-1 max-w-[90%]">
                {msg.call_graph && <ServiceCallGraph graph={msg.call_graph} />}
              </div>
            </div>
          )
        }

        return null
      })}
      {(loading && !hasActiveGeneration) || hasDeferredFollowingContent ? <GeneratingRow label={loadingLabelFor(messages, mode)} /> : null}
    </div>
  )
}
