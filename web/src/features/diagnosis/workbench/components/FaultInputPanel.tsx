import React from 'react'
import { AlertTriangle } from 'lucide-react'

interface Props {
  api: string
  time: string
  symptom: string
  onApiChange: (v: string) => void
  onTimeChange: (v: string) => void
  onSymptomChange: (v: string) => void
  onStart: () => void
  loading: boolean
}

export default function FaultInputPanel({
  api, time, symptom, onApiChange, onTimeChange, onSymptomChange, onStart, loading
}: Props) {
  return (
    <div className="bg-white rounded-2xl shadow-lg border border-gray-100 p-6">
      <div className="flex items-center gap-2 mb-5">
        <AlertTriangle className="text-orange-500" size={20} />
        <h2 className="text-base font-semibold text-gray-800">故障输入</h2>
      </div>
      <div className="space-y-4">
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">故障接口</label>
          <input
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 bg-gray-50"
            value={api}
            onChange={e => onApiChange(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">故障时间</label>
          <input
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 bg-gray-50"
            value={time}
            onChange={e => onTimeChange(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">故障现象</label>
          <input
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 bg-gray-50"
            value={symptom}
            onChange={e => onSymptomChange(e.target.value)}
          />
        </div>
        <button
          onClick={onStart}
          disabled={loading}
          className={`w-full py-2.5 rounded-lg text-sm font-semibold transition-all
            ${loading
              ? 'bg-blue-300 text-white cursor-not-allowed'
              : 'bg-blue-600 hover:bg-blue-700 text-white shadow-sm hover:shadow-md'
            }`}
        >
          {loading ? '诊断中…' : '开始诊断'}
        </button>
      </div>
    </div>
  )
}
