import { Wifi, WifiOff, AlertTriangle, Database, Zap } from 'lucide-react'
import type { DataSourceStatus } from '../types/diagnosis'

interface Props {
  status: DataSourceStatus | null
}

const SOURCE_LABELS: Record<string, string> = {
  opensearch: 'OpenSearch 直连',
  local_json: '本地 Case',
  local_fallback: '本地 Case（降级）',
  unifiedmodel: 'UnifiedModel',
}

const KIND_LABELS: Record<string, string> = {
  trace: 'Trace',
  log: 'Log',
  metric: 'Metric',
}

export default function DataSourceIndicator({ status }: Props) {
  if (!status) {
    return (
      <div className="px-3 py-2 border-b border-[#333] bg-[#1e1e1e]">
        <div className="flex items-center gap-2 text-[#858585] text-xs">
          <Database size={12} />
          <span>数据源状态加载中…</span>
        </div>
      </div>
    )
  }

  const { active_source, opensearch_connectivity, fallback_occurred, per_kind_source, warnings } = status
  const isOpenSearch = active_source === 'opensearch'
  const isConnected = isOpenSearch && opensearch_connectivity?.connected

  let statusColor = 'text-[#858585]'
  let bgColor = 'bg-[#1e1e1e]'
  let borderColor = 'border-[#333]'
  let Icon = Database
  let label = SOURCE_LABELS[active_source] || active_source

  if (isOpenSearch && isConnected && !fallback_occurred) {
    statusColor = 'text-[#4ec9b0]'
    bgColor = 'bg-[#1a2e22]'
    borderColor = 'border-[#2a5a3a]'
    Icon = Wifi
  } else if (isOpenSearch && !isConnected) {
    statusColor = 'text-[#f48771]'
    bgColor = 'bg-[#2e1a1a]'
    borderColor = 'border-[#5a2a2a]'
    Icon = WifiOff
    label = 'OpenSearch 不可达'
  } else if (fallback_occurred) {
    statusColor = 'text-[#dcdcaa]'
    bgColor = 'bg-[#2e2a1a]'
    borderColor = 'border-[#5a4a2a]'
    Icon = AlertTriangle
  }

  const kindBadges = Object.entries(per_kind_source)
    .filter(([, source]) => source !== active_source)
  void kindBadges // referenced for future use

  return (
    <div className={`px-3 py-2 border-b ${borderColor} ${bgColor} text-xs`}>
      {/* Main status row */}
      <div className={`flex items-center gap-2 ${statusColor} font-medium`}>
        <Icon size={12} />
        <span>{label}</span>
        {isOpenSearch && opensearch_connectivity?.connected && (
          <span className="text-[#858585] font-normal">
            {opensearch_connectivity.latency_ms != null
              ? `${opensearch_connectivity.latency_ms}ms`
              : ''}
          </span>
        )}
      </div>

      {/* Per-kind status */}
      <div className="flex flex-wrap gap-1.5 mt-1.5">
        {Object.entries(per_kind_source).map(([kind, source]) => {
          const isFellBack = source === 'local_fallback'
          return (
            <span
              key={kind}
              className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px]
                ${isFellBack
                  ? 'bg-[#5a4a2a] text-[#dcdcaa]'
                  : isOpenSearch && isConnected
                    ? 'bg-[#2a5a3a] text-[#4ec9b0]'
                    : 'bg-[#333] text-[#858585]'
                }`}
            >
              {isFellBack ? <AlertTriangle size={10} /> : <Zap size={10} />}
              {KIND_LABELS[kind] || kind}
              {isFellBack ? ' 降级' : ''}
            </span>
          )
        })}
      </div>

      {/* Warnings */}
      {warnings.length > 0 && (
        <div className="mt-1.5 space-y-0.5">
          {warnings.slice(0, 2).map((warning, i) => (
            <div key={i} className="text-[#dcdcaa] text-[10px] leading-tight truncate" title={warning}>
              ⚠ {warning}
            </div>
          ))}
          {warnings.length > 2 && (
            <div className="text-[#858585] text-[10px]">
              …共 {warnings.length} 条警告
            </div>
          )}
        </div>
      )}

      {/* Connectivity detail tooltip */}
      {isOpenSearch && opensearch_connectivity && !opensearch_connectivity.connected && opensearch_connectivity.error && (
        <div className="mt-1 text-[#f48771] text-[10px] leading-tight truncate" title={opensearch_connectivity.error}>
          {opensearch_connectivity.error}
        </div>
      )}
    </div>
  )
}
