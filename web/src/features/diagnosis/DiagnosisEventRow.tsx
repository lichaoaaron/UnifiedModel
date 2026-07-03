import { useState } from 'react'
import type { EventStreamItem, CallGraph, EntitySummaryData } from './diagnosisTypes'
import { ChevronRight, ChevronDown, CheckCircle2, Loader, AlertTriangle, Info } from 'lucide-react'
import { DiagnosisTopoGraph } from './DiagnosisTopoGraph'
import { DiagnosisReportView } from './DiagnosisReportView'
import { phaseLabel } from './eventMapper'

interface Props {
  event: EventStreamItem
  highlightedNodeId?: string
  onNodeClick?: (nodeId: string) => void
  isFocused?: boolean
  entityData?: EntitySummaryData | null
}

// ── Status icon mapping ──────────────────────────────────────────────────
const STATUS_ICON: Record<string, typeof CheckCircle2> = {
  pending: Loader,
  running: Loader,
  success: CheckCircle2,
  failed: AlertTriangle,
  info: Info,
}

const STATUS_COLOR: Record<string, string> = {
  pending: '#9ca3af',
  running: '#3b82f6',
  success: '#10b981',
  failed: '#ef4444',
  info: '#6b7280',
}

// ── Fixed-size icon container for perfect vertical centering ─────────────
function IconBox({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <span className={`inline-flex items-center justify-center flex-shrink-0 w-[18px] h-[18px] ${className}`}>
      {children}
    </span>
  )
}

function StatusIcon({ status }: { status?: string }) {
  const Icon = STATUS_ICON[status ?? 'info'] ?? Info
  const color = STATUS_COLOR[status ?? 'info']
  return (
    <IconBox>
      <Icon size={14} style={{ color }} className={status === 'running' ? 'animate-spin' : ''} />
    </IconBox>
  )
}

// ── Label tag (actor / phase) — lighter, restrained ─────────────────────
function LabelTag({ text }: { text: string }) {
  return (
    <span className="flex-shrink-0 rounded-sm bg-[#f8fafc] border border-[#e5e7eb] px-1.5 py-px text-[10px] leading-[1.4] text-[#6b7280] font-normal select-none">
      {text}
    </span>
  )
}

// ── Collapsed event row — stable flex columns ────────────────────────────
function CollapsedRow({ event, onToggle, open, isFocused, onNodeClick }: { event: EventStreamItem; onToggle: () => void; open: boolean; isFocused?: boolean; onNodeClick?: (nodeId: string) => void }) {
  const phase = event.phase ? phaseLabel(event.phase) : ''
  const hasDetails = !!(event.details && Object.keys(event.details).length > 0) || !!event.raw
  const skillName = event.title || ''
  const summaryText = event.summary

  return (
    <div
      className={`event-row group flex items-center gap-1.5 px-3 cursor-pointer border-l-2 transition-colors ${isFocused ? 'border-[#0e639c] bg-[#eff6ff]' : 'border-transparent hover:border-[#c4c4c4] hover:bg-[#f8fafc]'}`}
      style={{ minHeight: 36, lineHeight: '1.4' }}
      onClick={onToggle}
    >
      {/* Arrow column — always reserved space to prevent layout jitter */}
      <IconBox className="text-[#9ca3af] group-hover:text-[#4b5563]">
        {hasDetails ? (
          open ? <ChevronDown size={14} /> : <ChevronRight size={14} />
        ) : (
          <span className="w-[14px]" />
        )}
      </IconBox>

      {/* Status icon column */}
      <StatusIcon status={event.status} />

      {/* Actor tag (storm only) */}
      {event.actor && <LabelTag text={event.actor} />}

      {/* Phase tag */}
      {phase && <LabelTag text={phase} />}

      {/* Main content: skill name / title, summary — unified 13px sans-serif */}
      <div className="flex-1 min-w-0 flex items-baseline gap-1.5 text-[13px] leading-[1.4]">
        {skillName && (
          <span className="text-[13px] text-[#374151] flex-shrink-0 font-medium select-all">
            {skillName}
          </span>
        )}
        {skillName && summaryText && (
          <span className="text-[#9ca3af] flex-shrink-0 font-mono select-none">·</span>
        )}
        {summaryText && (
          <span className="text-[#4b5563] truncate">{summaryText}</span>
        )}
      </div>

      {/* Related-node tokens — clickable, stopPropagation to avoid toggle */}
      {event.related_nodes && event.related_nodes.length > 0 && (
        <span className="flex-shrink-0 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          {event.related_nodes.slice(0, 3).map((nodeId) => {
            const display = nodeId.length > 18 ? nodeId.slice(0, 17) + '…' : nodeId
            return (
              <button
                key={nodeId}
                className="text-[10px] leading-[1.4] px-1.5 py-px rounded-sm border border-[#e5e7eb] bg-[#fcfcfc] text-[#6b7280] hover:bg-[#eff6ff] hover:border-[#0e639c] hover:text-[#0e639c] transition-colors cursor-pointer font-normal"
                title={`在拓扑中定位 ${nodeId}`}
                onClick={(e) => {
                  e.stopPropagation()
                  onNodeClick?.(nodeId)
                }}
              >{display}</button>
            )
          })}
          {event.related_nodes.length > 3 && (
            <span className="text-[10px] text-[#c4c4c4] select-none">+{event.related_nodes.length - 3}</span>
          )}
        </span>
      )}

      {/* Expand hint */}
      {hasDetails && (
        <span className="flex-shrink-0 text-[10px] text-[#c4c4c4] opacity-0 group-hover:opacity-100 transition-opacity select-none">
          详情
        </span>
      )}
    </div>
  )
}

// ── Lightweight CLI-style detail section ─────────────────────────────────
function DetailSection({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mt-2.5 first:mt-0">
      <div className="text-[10px] font-medium text-[#9ca3af] uppercase tracking-wider mb-1.5">
        {label}
      </div>
      {children}
    </div>
  )
}

// ── JSON block — default collapsed ───────────────────────────────────────
function JsonBlock({ data, label }: { data: unknown; label: string }) {
  const [jsonOpen, setJsonOpen] = useState(false)
  const jsonText = JSON.stringify(data, null, 2)
  const lineCount = jsonText.split('\n').length

  return (
    <div>
      <button
        className="flex items-center gap-1 text-[11px] text-[#6b7280] hover:text-[#374151] transition-colors font-mono"
        onClick={(e) => { e.stopPropagation(); setJsonOpen(!jsonOpen) }}
      >
        {jsonOpen ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
        <span>{label}</span>
        <span className="text-[10px] text-[#9ca3af]">({lineCount} 行)</span>
      </button>
      {jsonOpen && (
        <pre className="mt-1.5 overflow-x-auto rounded-sm bg-[#1e1e1e] px-3 py-2 text-[11px] leading-[1.55] text-[#d4d4d4] max-h-64 overflow-y-auto font-mono">
          {jsonText}
        </pre>
      )}
    </div>
  )
}

// ── Evidence / Log helpers ───────────────────────────────────────────────
function EvidenceList({ items }: { items: string[] }) {
  return (
    <ul className="space-y-0.5">
      {items.map((item, i) => (
        <li key={i} className="flex items-start gap-1.5 text-[12px] leading-[1.5] text-[#374151]">
          <span className="text-[#9ca3af] mt-px flex-shrink-0">›</span>
          <span>{item}</span>
        </li>
      ))}
    </ul>
  )
}

function LogList({ items }: { items: string[] }) {
  return (
    <div className="bg-[#f8fafc] border border-[#e5e7eb] rounded-sm p-2 space-y-px max-h-36 overflow-y-auto font-mono">
      {items.map((line, i) => (
        <div key={i} className="flex items-start gap-1.5 text-[11px] leading-[1.5] text-[#374151]">
          <span className="text-[#9ca3af] flex-shrink-0 select-none">{String(i + 1).padStart(2, '0')}</span>
          <span>{line}</span>
        </div>
      ))}
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════
export default function EventRow({ event, highlightedNodeId: _highlightedNodeId, onNodeClick, isFocused, entityData }: Props) {
  const [open, setOpen] = useState(false)
  const d = event.details

  const hasDetails = !!(d && Object.keys(d).length > 0) || !!event.raw

  const showExplanation = d?.explanation != null
  const showExecutionLog = d?.executionLog != null && d.executionLog.length > 0
  const showEvidence = d?.evidence != null && d.evidence.length > 0
  const showInput = d?.input != null && Object.keys(d.input).length > 0
  const showOutput = d?.output != null && Object.keys(d.output).length > 0
  const showRawJson = event.raw != null && !d
  const showReport = event.kind === 'report' && event.raw != null && typeof event.raw === 'object' && 'content' in event.raw
  const showInlineTopo = event.kind === 'object_selection' && event.raw != null && typeof event.raw === 'object' && 'nodes' in event.raw

  const toggle = () => {
    if (hasDetails) setOpen(!open)
  }

  return (
    <div className="event-row-group">
      <CollapsedRow event={event} open={open} onToggle={toggle} isFocused={isFocused} onNodeClick={onNodeClick} />

      {/* Expanded detail — CLI-style, no card nesting */}
      {open && hasDetails && (
        <div className="ml-[18px] pl-[36px] py-2 pr-4 border-l border-[#e5e7eb] text-[12px] leading-[1.55] text-[#4b5563] animate-fadeIn">

          {showExplanation && d && (
            <DetailSection label="解释">
              <p className="whitespace-pre-wrap">{d.explanation}</p>
            </DetailSection>
          )}

          {showExecutionLog && d && (
            <DetailSection label="执行日志">
              <LogList items={d.executionLog!} />
            </DetailSection>
          )}

          {showEvidence && d && (
            <DetailSection label="证据">
              <EvidenceList items={d.evidence!} />
            </DetailSection>
          )}

          {showInput && d && (
            <DetailSection label="输入">
              <JsonBlock data={d.input} label="原始输入 JSON" />
            </DetailSection>
          )}

          {showOutput && d && (
            <DetailSection label="输出">
              <JsonBlock data={d.output} label="原始输出 JSON" />
            </DetailSection>
          )}

          {showRawJson && (
            <DetailSection label="调试数据">
              <JsonBlock data={event.raw} label="原始报告 JSON" />
            </DetailSection>
          )}

          {showReport && (
            <DetailSection label="报告内容">
              <DiagnosisReportView content={(event.raw as { content: string }).content} entityData={entityData} />
            </DetailSection>
          )}

          {showInlineTopo && (
            <DetailSection label="拓扑">
              <DiagnosisTopoGraph graph={event.raw as CallGraph} />
            </DetailSection>
          )}
        </div>
      )}
    </div>
  )
}
