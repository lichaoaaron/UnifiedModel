/**
 * HistoryPanel — Sidebar showing past diagnosis sessions from localStorage.
 * Clicking a record restores its messages to the main chat area (read-only replay).
 */
import { useEffect, useState } from 'react'
import type { HistoryRecord, DiagnosisMessage } from '../types/diagnosis'
import { Clock, LoaderCircle, MessageCircle, Network, PanelLeftClose, PanelLeftOpen, SquarePen } from 'lucide-react'

const STORAGE_KEY = 'mmodel_history_v2'
const MAX_RECORDS = 20

export function loadHistory(): HistoryRecord[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as HistoryRecord[]) : []
  } catch {
    return []
  }
}

export function saveHistoryRecord(record: HistoryRecord) {
  const list = loadHistory()
  const updated = [record, ...list.filter(item => item.id !== record.id)].slice(0, MAX_RECORDS)
  localStorage.setItem(STORAGE_KEY, JSON.stringify(updated))
}

export function updateHistoryRecord(record: HistoryRecord) {
  const list = loadHistory()
  const existingIndex = list.findIndex(item => item.id === record.id)
  if (existingIndex < 0) {
    saveHistoryRecord(record)
    return
  }
  const updated = list.map((item, index) => index === existingIndex ? record : item)
  localStorage.setItem(STORAGE_KEY, JSON.stringify(updated))
}

export function markHistoryViewed(id: string) {
  const updated = loadHistory().map(record =>
    record.id === id ? { ...record, unread: false } : record
  )
  localStorage.setItem(STORAGE_KEY, JSON.stringify(updated))
}

interface Props {
  open: boolean
  onOpen: () => void
  onClose: () => void
  onNewChat: () => void
  onReplay: (messages: DiagnosisMessage[], label: string, id: string) => void
  activeRunIds?: string[]
  refreshKey?: number
}

const iconButtonClass = 'w-9 h-9 flex items-center justify-center rounded-lg text-[#111827] hover:bg-[#f3f4f6] transition-colors'

export default function HistoryPanel({ open, onOpen, onClose, onNewChat, onReplay, activeRunIds = [], refreshKey = 0 }: Props) {
  const [records, setRecords] = useState<HistoryRecord[]>([])

  useEffect(() => {
    setRecords(loadHistory())
  }, [open, refreshKey])

  const formatTime = (iso: string) => {
    try {
      const d = new Date(iso)
      return d.toLocaleString('zh-CN', {
        month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit',
      })
    } catch {
      return iso
    }
  }

  if (!open) {
    return (
      <aside className="w-[45px] h-full bg-white border-r border-[#e5e7eb] flex flex-col items-center flex-shrink-0 py-3 gap-3">
        <button onClick={onOpen} className={iconButtonClass} title="展开边栏">
          <PanelLeftOpen size={19} />
        </button>
        <button onClick={onNewChat} className={iconButtonClass} title="新聊天">
          <SquarePen size={19} />
        </button>
        <button onClick={onOpen} className={iconButtonClass} title="最近">
          <MessageCircle size={19} />
        </button>
      </aside>
    )
  }

    return (
      <aside className="w-60 h-full bg-white border-r border-[#e5e7eb] flex flex-col flex-shrink-0">
        <div className="flex items-start justify-between gap-2 px-4 py-3">
          <div className="min-w-0">
            <div className="text-[15px] font-semibold text-[#111827] truncate">MModel 智能诊断</div>
            <span className="mt-1 inline-flex items-center gap-1 rounded bg-[#eff6ff] px-2 py-0.5 text-[11px] text-[#0e639c]">
              <Network size={11} />
              MModel 可观测本体
            </span>
          </div>
          <button
            onClick={onClose}
            className={`${iconButtonClass} flex-shrink-0`}
            title="关闭边栏"
          >
            <PanelLeftClose size={19} />
          </button>
        </div>

        <button
          onClick={onNewChat}
          className="mx-3 mt-2 mb-5 flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-[#111827] hover:bg-[#f3f4f6] transition-colors"
        >
          <SquarePen size={19} />
          新聊天
        </button>

        <div className="px-4 pb-2 text-sm font-semibold text-[#111827]">最近</div>

        <div className="flex-1 overflow-y-auto px-2 pb-3">
          {records.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full gap-2 text-[#9ca3af] select-none">
              <Clock size={28} />
              <p className="text-xs">暂无最近聊天</p>
            </div>
          ) : (
            records.map(rec => (
              <button
                key={rec.id}
                className="w-full min-w-0 flex items-center gap-2 rounded-lg px-3 py-2 text-left hover:bg-[#f3f4f6] transition-colors"
                onClick={() => {
                  const latest = loadHistory().find(item => item.id === rec.id) ?? rec
                  markHistoryViewed(rec.id)
                  setRecords(loadHistory())
                  onReplay(latest.messages, latest.userText, latest.id)
                }}
              >
                <span className="min-w-0 flex-1 truncate text-sm text-[#111827]" title={`${rec.userText} · ${formatTime(rec.createdAt)}`}>
                  {rec.userText}
                </span>
                {rec.status === 'running' && activeRunIds.includes(rec.id) && <LoaderCircle size={13} className="flex-shrink-0 animate-spin text-[#c7c7cc]" />}
                {rec.status === 'complete' && rec.unread && <span className="h-2 w-2 flex-shrink-0 rounded-full bg-[#0e639c]" />}
              </button>
            ))
          )}
        </div>

      </aside>
  )
}
