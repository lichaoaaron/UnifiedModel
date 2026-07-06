import React, { useState } from 'react'
import { ActivitySquare, Copy, Check } from 'lucide-react'

const EXAMPLE_INPUTS = [
  'api: /checkout/payment time: 2026-04-10 10:51:14 接口报 HTTP 500 异常',
  '检查 ais-amc 服务的 Redis 连接异常，分析根因和影响面',
]

interface Props {
  onSelectExample?: (text: string) => void
}

export default function EmptyState({ onSelectExample }: Props) {
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null)

  return (
    <div className="flex flex-col items-center justify-center h-full text-center gap-4 py-16 select-none px-4">
      <div className="relative w-14 h-14 rounded-2xl bg-[#0e639c] flex items-center justify-center shadow-[0_8px_24px_rgba(14,99,156,0.18)]">
        <ActivitySquare size={26} className="text-white" />
        <span className="absolute -right-0.5 -bottom-0.5 w-3 h-3 rounded-full bg-[#10b981] border-2 border-white" />
      </div>
      <div>
        <p className="text-[#111827] text-sm font-semibold">UModel 智能诊断</p>
        <p className="text-[#6b7280] text-[11px] max-w-sm leading-relaxed mt-1">
          基于可观测本体编排 Trace、Log、Metric 与实体关系 Skill，生成可解释的根因定位、证据链和影响面分析。
        </p>
      </div>

      {/* Example inputs */}
      <div className="flex flex-col gap-2 w-full max-w-md mt-2">
        {EXAMPLE_INPUTS.map((text, i) => {
          const copied = copiedIndex === i
          return (
            <button
              key={i}
              className="flex items-center gap-2 w-full text-left px-3 py-2 rounded-lg border border-[#e5e7eb] bg-[#f9fafb] hover:bg-[#f3f4f6] hover:border-[#d1d5db] transition-colors group"
              onClick={() => {
                if (onSelectExample) {
                  onSelectExample(text)
                } else {
                  navigator.clipboard?.writeText(text)
                  setCopiedIndex(i)
                  setTimeout(() => setCopiedIndex(null), 3000)
                }
              }}
              title="点击复制示例输入"
            >
              <span className="text-xs text-[#6b7280] flex-1 truncate">{text}</span>
              {copied
                ? <Check size={13} className="text-[#10b981] flex-shrink-0" />
                : <Copy size={13} className="text-[#c4c4c4] group-hover:text-[#6b7280] flex-shrink-0 transition-colors" />
              }
            </button>
          )
        })}
      </div>

      <p className="text-[10px] text-[#9ca3af] max-w-xs">
        在底部输入框中描述故障现象，或点击上方示例复制到输入框后发起诊断。
      </p>
    </div>
  )
}
