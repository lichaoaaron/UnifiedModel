import { Bot, History, Settings } from 'lucide-react'

export default function Sidebar() {
  return (
    <div className="w-12 flex flex-col items-center bg-[#333333] border-r border-[#252526] py-3 gap-1 flex-shrink-0">
      {/* Logo */}
      <div className="w-8 h-8 rounded-md bg-[#0e639c] flex items-center justify-center mb-3">
        <Bot size={16} className="text-white" />
      </div>

      <NavIcon icon={<Bot size={20} />} active tooltip="诊断" />
      <NavIcon icon={<History size={20} />} tooltip="历史" />
      <NavIcon icon={<Settings size={20} />} tooltip="设置" />
    </div>
  )
}

function NavIcon({
  icon, active = false, tooltip
}: {
  icon: React.ReactNode
  active?: boolean
  tooltip: string
}) {
  return (
    <div
      title={tooltip}
      className={`w-10 h-10 flex items-center justify-center rounded-md cursor-pointer transition-colors
        ${active
          ? 'text-white bg-[#37373d]'
          : 'text-[#858585] hover:text-[#cccccc] hover:bg-[#2a2d2e]'
        }`}
    >
      {icon}
    </div>
  )
}

// React import needed for ReactNode type
import React from 'react'
