import type { StormRoundSummary as StormRoundSummaryData } from '../types/diagnosis'
import { CheckCircle2, Layers } from 'lucide-react'

interface Props {
  summary: StormRoundSummaryData
}

export default function StormRoundSummary({ summary }: Props) {
  return (
    <div className="w-full rounded-lg border border-[#dbe7f3] bg-[#f8fafc] px-3 py-2.5 text-sm shadow-[0_1px_5px_rgba(15,23,42,0.04)]">
      <div className="flex flex-wrap items-center gap-2 text-[#0e639c] font-semibold mb-1.5">
        <CheckCircle2 size={14} />
        <span>第 {summary.round_id} 轮证据小结：{summary.intent}</span>
        {summary.is_extra_round && (
          <span className="rounded border border-[#fed7aa] bg-[#fff7ed] px-1.5 py-0.5 text-[11px] text-[#9a3412] font-medium">
            追加补证据
          </span>
        )}
      </div>
      <div className="flex items-start gap-1.5 text-xs text-[#6b7280] mb-1.5">
        <Layers size={12} className="mt-0.5 flex-shrink-0" />
        <span>{summary.goal}</span>
      </div>
      <p className="text-[#1f2937] leading-relaxed">{summary.summary}</p>
    </div>
  )
}