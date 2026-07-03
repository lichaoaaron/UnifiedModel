/**
 * DiagnosisReport — Renders the final report (type: 'report') as structured blocks.
 * Parses content split by 【...】 section headers.
 * Optionally renders an entity summary card when entityData is provided.
 */

import type { EntitySummaryData } from './diagnosisTypes'

interface Section {
  title: string
  body: string
}

function parseReport(content: string): Section[] {
  const sections: Section[] = []
  // Split on 【...】 headers, keeping the delimiter
  const parts = content.split(/(【[^】]+】)/)
  let currentTitle = ''
  for (const part of parts) {
    if (/^【[^】]+】$/.test(part)) {
      currentTitle = part.replace(/[【】]/g, '').trim()
    } else if (currentTitle) {
      const body = part.trim()
      if (body) sections.push({ title: currentTitle, body })
      currentTitle = ''
    }
  }
  // Fallback: if no 【】 markers, render as plain text
  if (sections.length === 0 && content.trim()) {
    sections.push({ title: '', body: content.trim() })
  }
  return sections
}

const SECTION_STYLE: Record<string, { border: string; label: string; icon: string }> = {
  // Legacy LLM section names
  '故障概要':       { border: 'border-[#e5e7eb]',  label: 'text-[#0e639c]', icon: '🗒️' },
  '问题现象':       { border: 'border-blue-200',   label: 'text-[#0e639c]', icon: '🔍' },
  '根因分析':       { border: 'border-red-200',    label: 'text-[#0e639c]', icon: '🎯' },
  '实例状态变化':   { border: 'border-yellow-200', label: 'text-[#0e639c]', icon: '📊' },
  '具体技术问题':   { border: 'border-purple-200', label: 'text-[#0e639c]', icon: '🔧' },
  '业务影响评估':   { border: 'border-orange-200', label: 'text-[#0e639c]', icon: '⚡' },
  '解决方案':       { border: 'border-green-200',  label: 'text-[#0e639c]', icon: '✅' },
  '预防措施':       { border: 'border-teal-200',   label: 'text-[#0e639c]', icon: '🛡️' },
  '经验总结':       { border: 'border-[#e5e7eb]',  label: 'text-[#0e639c]', icon: '📌' },
  // Spec section names (frontend_spec §9)
  '故障结论':         { border: 'border-[#e5e7eb]',  label: 'text-[#0e639c]', icon: '📋' },
  '异常现象':         { border: 'border-blue-200',   label: 'text-[#0e639c]', icon: '🔍' },
  '根因定位':         { border: 'border-red-200',    label: 'text-[#0e639c]', icon: '🎯' },
  '实例与资源状态':   { border: 'border-yellow-200', label: 'text-[#0e639c]', icon: '📊' },
  '影响面分析':       { border: 'border-orange-200', label: 'text-[#0e639c]', icon: '⚡' },
  '处置建议':         { border: 'border-green-200',  label: 'text-[#0e639c]', icon: '✅' },
  '长期优化建议':     { border: 'border-teal-200',   label: 'text-[#0e639c]', icon: '🛡️' },
  '诊断依据与可信度': { border: 'border-[#e5e7eb]',  label: 'text-[#0e639c]', icon: '📌' },
}

function defaultStyle() {
  return { border: 'border-[#e5e7eb]', label: 'text-[#0e639c]', icon: '📋' }
}

function renderBody(body: string) {
  const lines = body.split('\n').filter(l => l.trim())
  return lines.map((line, i) => {
    const text = line.replace(/^[-•›\s]+/, '').trim()
    return (
      <div key={i} className="flex items-start gap-1.5 text-xs leading-relaxed text-[#374151]">
        <span className="text-[#9ca3af] flex-shrink-0 mt-0.5">›</span>
        <span>{text}</span>
      </div>
    )
  })
}

interface Props {
  content: string
  entityData?: EntitySummaryData | null
}

function EntitySummaryCard({ data }: { data: EntitySummaryData }) {
  const total = data.services.length + data.instances.length + data.interfaces.length
  return (
    <div className="rounded-lg border border-[#dbeafe] bg-[#eff6ff] p-3 mb-3">
      <div className="text-xs font-semibold text-[#1d4ed8] mb-2">📋 实体概览</div>
      <div className="flex flex-wrap gap-2 text-[11px] text-[#374151]">
        {data.services.length > 0 && (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-[#dbeafe] text-[#1d4ed8] font-medium">
            <span className="text-[10px]">☑</span> {data.services.length} 服务
          </span>
        )}
        {data.instances.length > 0 && (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-[#dbeafe] text-[#1d4ed8] font-medium">
            <span className="text-[10px]">☑</span> {data.instances.length} 实例
          </span>
        )}
        {data.interfaces.length > 0 && (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-[#dbeafe] text-[#1d4ed8] font-medium">
            <span className="text-[10px]">☑</span> {data.interfaces.length} 接口
          </span>
        )}
        <span className="text-[#6b7280] ml-1">共 {total} 个实体</span>
      </div>
      {data.services.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {data.services.slice(0, 10).map(s => (
            <span key={s} className="inline-block px-1.5 py-0.5 text-[10px] rounded bg-white border border-[#d1d5db] text-[#4b5563] font-medium">{s}</span>
          ))}
          {data.services.length > 10 && (
            <span className="text-[10px] text-[#9ca3af]">+{data.services.length - 10} 更多</span>
          )}
        </div>
      )}
    </div>
  )
}

export function DiagnosisReportView({ content, entityData }: Props) {
  const sections = parseReport(content)

  return (
    <div className="space-y-3">
      {entityData && <EntitySummaryCard data={entityData} />}
      {sections.map((sec, i) => {
        const style = SECTION_STYLE[sec.title] ?? defaultStyle()
        return (
          <div
            key={i}
            className={`rounded-lg border ${style.border} bg-white p-3`}
          >
            {sec.title && (
              <div className={`text-xs font-semibold mb-2 ${style.label}`}>
                {style.icon} {sec.title}
              </div>
            )}
            <div className="space-y-1">
              {renderBody(sec.body)}
            </div>
          </div>
        )
      })}
    </div>
  )
}
