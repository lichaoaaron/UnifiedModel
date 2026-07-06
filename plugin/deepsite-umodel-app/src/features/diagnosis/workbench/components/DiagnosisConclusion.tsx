import React from 'react'
import type { DiagnosisSummary } from '../types/diagnosis'
import { Target, ArrowRight } from 'lucide-react'

interface Props {
  summary: DiagnosisSummary
  report: string
}

export default function DiagnosisConclusion({ summary, report }: Props) {
  return (
    <div className="space-y-4">
      {/* Root Cause Card */}
      <div className="bg-gradient-to-br from-red-50 to-rose-50 rounded-2xl shadow-lg border border-red-200 p-6">
        <div className="flex items-center gap-2 mb-4">
          <Target size={18} className="text-red-500" />
          <h3 className="text-sm font-semibold text-red-800">根因定位</h3>
          <span className="ml-auto text-xs bg-red-100 text-red-600 px-2 py-0.5 rounded-full font-semibold">
            高置信度
          </span>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-white rounded-xl p-3 border border-red-100">
            <p className="text-xs text-gray-500 mb-1">根因服务</p>
            <p className="text-sm font-bold text-red-700">{summary.root_cause_service}</p>
          </div>
          <div className="bg-white rounded-xl p-3 border border-red-100">
            <p className="text-xs text-gray-500 mb-1">根因接口</p>
            <p className="text-sm font-bold text-red-700">{summary.root_cause_api}</p>
          </div>
          <div className="bg-white rounded-xl p-3 border border-red-100">
            <p className="text-xs text-gray-500 mb-1">根因类型</p>
            <p className="text-sm font-bold text-orange-600">{summary.root_cause_type}</p>
          </div>
          <div className="bg-white rounded-xl p-3 border border-red-100">
            <p className="text-xs text-gray-500 mb-1">异常参数</p>
            <p className="text-sm font-bold text-orange-600">id = &quot;{summary.bad_parameter}&quot;</p>
          </div>
          <div className="bg-white rounded-xl p-3 border border-red-100 col-span-2">
            <p className="text-xs text-gray-500 mb-1">异常类型</p>
            <p className="text-xs font-mono font-bold text-red-600">{summary.exception_type}</p>
          </div>
        </div>
      </div>

      {/* Impact Card */}
      <div className="bg-gradient-to-br from-orange-50 to-amber-50 rounded-2xl shadow-lg border border-orange-200 p-6">
        <div className="flex items-center gap-2 mb-4">
          <ArrowRight size={18} className="text-orange-500" />
          <h3 className="text-sm font-semibold text-orange-800">影响面分析</h3>
        </div>
        <div className="space-y-2">
          <div className="bg-white rounded-xl p-3 border border-orange-100">
            <p className="text-xs text-gray-500 mb-1">影响接口</p>
            <p className="text-sm font-bold text-orange-700">{summary.impact_api}</p>
          </div>
          <div className="bg-white rounded-xl p-3 border border-orange-100">
            <p className="text-xs text-gray-500 mb-2">业务影响</p>
            <div className="space-y-1">
              {summary.business_impact.map((b, i) => (
                <div key={i} className="flex items-center gap-2">
                  <div className="w-1.5 h-1.5 bg-orange-400 rounded-full flex-shrink-0" />
                  <p className="text-xs font-medium text-orange-700">{b}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Final Report */}
      {report && (
        <div className="bg-white rounded-2xl shadow-lg border border-gray-100 p-6">
          <h3 className="text-sm font-semibold text-gray-800 mb-3">📋 完整诊断报告</h3>
          <div className="prose prose-sm max-w-none">
            <pre className="text-xs text-gray-700 whitespace-pre-wrap leading-relaxed font-sans bg-gray-50 rounded-xl p-4 border border-gray-100 max-h-96 overflow-y-auto">
              {report}
            </pre>
          </div>
        </div>
      )}
    </div>
  )
}
