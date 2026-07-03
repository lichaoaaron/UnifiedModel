import { useState } from 'react'
import { ChevronDown, ChevronRight, CheckCircle2, XCircle, Clock } from 'lucide-react'
import type { SkillResult } from '../../api/types'
import { Badge, Panel } from '../../design/components'

/** Map skill names to Chinese display names. */
function skillLabel(name: string): string {
  const map: Record<string, string> = {
    AlertContextSkill: '告警上下文解析',
    EntityBindingSkill: '实体绑定',
    TraceAnalysisSkill: 'Trace 分析',
    LogAnalysisSkill: '日志分析',
    MetricCheckSkill: '指标检查',
    GraphAnalysisSkill: '拓扑图分析',
    RootCauseSkill: '根因推断',
    ImpactAnalysisSkill: '影响面分析',
    ReportSkill: '报告生成',
  }
  return map[name] ?? name
}

export function DiagnosisSkillCard({ skill }: { skill: SkillResult }) {
  const [open, setOpen] = useState(false)

  const icon =
    skill.status === 'success' ? (
      <CheckCircle2 size={16} style={{ color: 'var(--color-success)' }} />
    ) : skill.status === 'error' ? (
      <XCircle size={16} style={{ color: 'var(--color-danger)' }} />
    ) : (
      <Clock size={16} style={{ color: 'var(--color-warning)' }} />
    )

  return (
    <Panel>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          width: '100%',
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          padding: '8px 0',
          fontSize: '0.9em',
          textAlign: 'left',
        }}
      >
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        {icon}
        <span style={{ fontWeight: 600 }}>{skillLabel(skill.skill_name)}</span>
        {skill.duration_ms != null && (
          <span className="muted" style={{ fontSize: '0.8em', marginLeft: 'auto' }}>
            {(skill.duration_ms / 1000).toFixed(1)}s
          </span>
        )}
        {skill.status === 'success' && (
          <Badge tone="success">成功</Badge>
        )}
        {skill.status === 'error' && (
          <Badge tone="danger">失败</Badge>
        )}
      </button>

      {skill.summary && (
        <p style={{ margin: '4px 0 0 24px', fontSize: '0.85em', lineHeight: 1.5 }}>
          {skill.summary}
        </p>
      )}

      {open && (
        <div style={{ margin: '8px 0 0 24px', fontSize: '0.82em' }}>
          {/* Evidence */}
          {skill.evidence && skill.evidence.length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <strong>证据:</strong>
              <ul style={{ margin: '4px 0', paddingLeft: 18 }}>
                {skill.evidence.map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Execution log */}
          {skill.execution_log && skill.execution_log.length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <strong>执行日志:</strong>
              <div className="muted" style={{ fontSize: '0.85em' }}>
                {skill.execution_log.map((line, i) => (
                  <div key={i}>{line}</div>
                ))}
              </div>
            </div>
          )}

          {/* Explanation */}
          {skill.explanation && (
            <div style={{ marginBottom: 8 }}>
              <strong>说明:</strong>
              <p className="muted" style={{ margin: '4px 0' }}>
                {skill.explanation}
              </p>
            </div>
          )}
        </div>
      )}
    </Panel>
  )
}
