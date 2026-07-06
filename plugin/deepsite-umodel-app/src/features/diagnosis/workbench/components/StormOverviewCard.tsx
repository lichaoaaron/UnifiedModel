import React from 'react'
import type { StormOverview } from '../types/diagnosis'
import { Activity, GitBranch, Timer, Waves } from 'lucide-react'

interface Props {
  overview: StormOverview
}

function Field({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="min-w-0">
      <div className="text-[11px] text-[#6b7280] mb-0.5">{label}</div>
      <div className="text-sm text-[#111827] font-medium truncate" title={String(value)}>{value}</div>
    </div>
  )
}

export default function StormOverviewCard({ overview }: Props) {
  const confidencePercent = overview.confidence === null ? null : Math.round(overview.confidence * 100)

  return (
    <div className="bg-white rounded-xl border border-[#e5e7eb] p-4 shadow-[0_1px_5px_rgba(15,23,42,0.06)]">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm font-semibold text-[#0e639c]">
            <Waves size={15} />
            风暴任务总览
          </div>
          <p className="mt-1 text-xs text-[#6b7280] leading-relaxed max-w-3xl">
            {overview.symptom}
          </p>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Field label="告警对象" value={overview.alert_api} />
        <Field label="时间窗口" value={overview.time_window} />
        <Field label="租户" value={overview.tenant} />
        <Field label="业务流" value={overview.business_flow} />
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-md border border-[#e5e7eb] bg-[#f9fafb] px-3 py-2">
          <div className="flex items-center gap-1.5 text-[11px] text-[#6b7280]">
            <Activity size={12} />
            Error Trace 数量
          </div>
          <div className="mt-1 text-lg font-semibold text-[#111827]">{overview.error_trace_count}</div>
        </div>
        <div className="rounded-md border border-[#e5e7eb] bg-[#f9fafb] px-3 py-2">
          <div className="flex items-center gap-1.5 text-[11px] text-[#6b7280]">
            <GitBranch size={12} />
            诊断分支数量
          </div>
          <div className="mt-1 text-lg font-semibold text-[#111827]">{overview.diagnosis_branch_count}</div>
        </div>
        <div className="rounded-md border border-[#e5e7eb] bg-[#f9fafb] px-3 py-2">
          <div className="flex items-center gap-1.5 text-[11px] text-[#6b7280]">
            <Timer size={12} />
            当前轮次 / 证据进度
          </div>
          <div className="mt-1 text-sm font-semibold text-[#111827]">{overview.current_round} · {overview.evidence_progress}</div>
        </div>
        <div className="rounded-md border border-[#bfdbfe] bg-[#eff6ff] px-3 py-2">
          <div className="text-[11px] text-[#0e639c]">收敛状态 / 置信度</div>
          <div className="mt-1 flex items-center gap-2">
            <span className="text-sm text-[#0e639c] font-semibold">{confidencePercent === null ? '--' : `${confidencePercent}%`}</span>
          </div>
          <div className="mt-2 h-1.5 rounded-full bg-white border border-[#bfdbfe] overflow-hidden">
            <div className="h-full bg-[#0e639c]" style={{ width: `${confidencePercent ?? 0}%` }} />
          </div>
        </div>
      </div>
    </div>
  )
}
