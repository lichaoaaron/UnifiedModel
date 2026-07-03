import React from 'react'
import { Shield } from 'lucide-react'

interface Props {
  evidenceChain: string[]
}

export default function EvidenceChain({ evidenceChain }: Props) {
  if (!evidenceChain || evidenceChain.length === 0) return null

  const categories = [
    { prefix: 'Trace', color: 'blue', bg: 'bg-blue-50', border: 'border-blue-200', text: 'text-blue-700', badge: 'bg-blue-100 text-blue-600' },
    { prefix: 'Log', color: 'purple', bg: 'bg-purple-50', border: 'border-purple-200', text: 'text-purple-700', badge: 'bg-purple-100 text-purple-600' },
    { prefix: 'Metric', color: 'green', bg: 'bg-green-50', border: 'border-green-200', text: 'text-green-700', badge: 'bg-green-100 text-green-600' },
  ]

  return (
    <div className="bg-white rounded-2xl shadow-lg border border-gray-100 p-6">
      <div className="flex items-center gap-2 mb-4">
        <Shield size={18} className="text-indigo-500" />
        <h3 className="text-sm font-semibold text-gray-800">证据链</h3>
      </div>
      <div className="space-y-3">
        {evidenceChain.map((ev, i) => {
          const cat = categories.find(c => ev.startsWith(c.prefix)) || categories[0]
          return (
            <div key={i} className={`flex items-start gap-3 ${cat.bg} border ${cat.border} rounded-xl px-3 py-2.5`}>
              <span className={`text-xs font-semibold px-2 py-0.5 rounded-full flex-shrink-0 ${cat.badge}`}>
                {ev.split('证据：')[0].trim()}
              </span>
              <span className={`text-xs ${cat.text} leading-relaxed`}>
                {ev.includes('证据：') ? ev.split('证据：')[1] : ev}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
