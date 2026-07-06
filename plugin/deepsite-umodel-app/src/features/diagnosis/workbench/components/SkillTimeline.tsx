import React, { useState } from 'react'
import type { SkillResult } from '../types/diagnosis'
import { CheckCircle, Loader, Clock, ChevronDown, ChevronUp } from 'lucide-react'

interface Props {
  skills: SkillResult[]
  activeIndex: number
}

const statusIcon = (status: string) => {
  if (status === 'success') {return <CheckCircle size={16} className="text-green-500 flex-shrink-0" />}
  if (status === 'running') {return <Loader size={16} className="text-blue-500 flex-shrink-0 animate-spin" />}
  return <Clock size={16} className="text-gray-300 flex-shrink-0" />
}

const statusColor = (status: string) => {
  if (status === 'success') {return 'border-green-400 bg-green-50'}
  if (status === 'running') {return 'border-blue-400 bg-blue-50 animate-pulse'}
  return 'border-gray-200 bg-gray-50'
}

export default function SkillTimeline({ skills, activeIndex }: Props) {
  const [expanded, setExpanded] = useState<number | null>(null)

  return (
    <div className="space-y-2">
      {skills.map((skill, i) => {
        const isExpanded = expanded === i
        const canExpand = skill.status === 'success'
        return (
          <div
            key={i}
            className={`border rounded-xl transition-all duration-300 ${statusColor(skill.status)}`}
          >
            <div
              className={`flex items-center gap-3 px-4 py-3 ${canExpand ? 'cursor-pointer' : ''}`}
              onClick={() => canExpand && setExpanded(isExpanded ? null : i)}
            >
              {statusIcon(skill.status)}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-gray-500">Step {i + 1}</span>
                  <span className="text-sm font-semibold text-gray-800">{skill.title}</span>
                </div>
                {skill.status === 'running' && (
                  <p className="text-xs text-blue-600 mt-0.5">执行中…</p>
                )}
                {skill.status === 'success' && (
                  <p className="text-xs text-gray-600 mt-0.5 truncate">{skill.summary}</p>
                )}
                {skill.status === 'pending' && (
                  <p className="text-xs text-gray-400 mt-0.5">等待中</p>
                )}
              </div>
              {canExpand && (
                isExpanded ? <ChevronUp size={14} className="text-gray-400" /> : <ChevronDown size={14} className="text-gray-400" />
              )}
            </div>

            {isExpanded && (
              <div className="px-4 pb-4 border-t border-green-200 mt-0 pt-3 space-y-3">
                <p className="text-xs text-gray-600 leading-relaxed">{skill.explanation}</p>
                {skill.evidence.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-gray-700 mb-1">📌 证据</p>
                    <ul className="space-y-1">
                      {skill.evidence.map((e, j) => (
                        <li key={j} className="text-xs text-gray-600 bg-white rounded px-2 py-1 border border-green-100">
                          {e}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {Object.keys(skill.output).length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-gray-700 mb-1">📤 输出</p>
                    <pre className="text-xs bg-gray-900 text-green-300 rounded-lg p-3 overflow-auto max-h-40">
                      {JSON.stringify(skill.output, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
