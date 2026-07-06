import React, { useState, useRef, useEffect, useMemo } from 'react'
import type { DiagnoseRequest, DiagnosisMessage, DiagnosisMode, DiagnosisSummary, CallGraph } from './types/diagnosis'
import { streamAgenticDiagnosis } from './api/diagnosisApi'
import { streamStormDemoDiagnosis } from './api/stormDemoAdapter'
import EventStream from './components/EventStream'
import ServiceCallGraph from './components/ServiceCallGraph'
import EmptyState from './components/EmptyState'
import HistoryPanel, { loadHistory, updateHistoryRecord } from './components/HistoryPanel'
import { parseUserInput } from './utils/parseUserInput'
import { buildNormalEventStream } from './utils/diagnosisEventMapper'
import { buildStormEventStream } from './utils/stormEventMapper'
import { matchNodeToEvent, resolveNodeLabelToId, enrichRelatedNodesWithIds } from './utils/nodeEventMatcher'
import { ArrowUp, Search, Stethoscope, StopCircle, Tornado } from 'lucide-react'
import './diagnosisWorkbench.css'

const UI_VERSION = 'v2.0.0'

const MODE_LABELS: Record<DiagnosisMode, string> = {
  observability: '观测问答',
  diagnosis: '故障诊断',
  storm: '风暴模式',
}

const MODE_PLACEHOLDERS: Record<DiagnosisMode, string> = {
  observability: '询问服务、日志、指标、Trace 或业务影响...',
  diagnosis: '描述故障现象，例如 API、时间、错误码、症状...',
  storm: '描述复杂故障，Mobile Ops 将持续分析并主动补查证据...',
}

const MODE_OPTIONS: Array<{ value: DiagnosisMode; label: string; Icon: typeof Search }> = [
  { value: 'diagnosis', label: MODE_LABELS.diagnosis, Icon: Stethoscope },
  { value: 'storm', label: MODE_LABELS.storm, Icon: Tornado },
  { value: 'observability', label: MODE_LABELS.observability, Icon: Search },
]

type DoneSession = { session_id?: string }

// ── Utility helpers ────────────────────────────────────────────────────────

function inferModeFromMessages(messages: DiagnosisMessage[]): DiagnosisMode {
  const hasStormMessages = messages.some(message =>
    message.type === 'storm_overview'
    || message.type === 'storm_round_summary'
    || message.report_title === '风暴诊断报告'
  )
  if (hasStormMessages) {return 'storm'}
  const sessionLine = messages.find(message => message.role === 'assistant' && message.type === 'text' && message.content?.includes('模式：'))
  if (sessionLine?.content?.includes(MODE_LABELS.diagnosis)) {return 'diagnosis'}
  if (sessionLine?.content?.includes(MODE_LABELS.storm)) {return 'storm'}
  return 'diagnosis'
}

function hasExplicitApi(text: string): boolean {
  return /\bapi\s*[:=]/i.test(text) || /\/[A-Za-z0-9_/?=&%.-]+/.test(text)
}

function hasExplicitTime(text: string): boolean {
  return /\btime\s*[:=]/i.test(text) || /\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}/.test(text)
}

function hasExplicitSymptom(text: string): boolean {
  return /\bsymptom\s*[:=]/i.test(text)
    || /接口(?:出现|发生|报出|报)/.test(text)
    || /HTTP\s*\d{3}|超时|timeout|响应慢|slow|报错|异常|exception|error|不可用|down|挂了|宕机/i.test(text)
}

function compactMessagesForHistory(messages: DiagnosisMessage[]): DiagnosisMessage[] {
  return messages.map(message => {
    if (message.type === 'skill_call') {
      return {
        role: message.role,
        type: message.type,
        skill_name: message.skill_name,
        tool_name: message.tool_name,
        status: message.status,
        summary: message.summary,
        duration_ms: message.duration_ms,
        evidence: message.evidence?.slice(0, 8),
        execution_log: message.execution_log?.slice(0, 12),
        explanation: message.explanation,
        root_cause_status: message.root_cause_status,
        confidence: message.confidence,
        recovery_action: message.recovery_action,
        run_id: message.run_id,
        stream_id: message.stream_id,
      }
    }
    if (message.type === 'call_graph') {
      return {
        role: message.role,
        type: message.type,
        run_id: message.run_id,
        call_graph: message.call_graph
          ? {
              ...message.call_graph,
              nodes: message.call_graph.nodes.slice(0, 30),
              edges: message.call_graph.edges.slice(0, 60),
            }
          : undefined,
      }
    }
    return message
  })
}

function splitMarkdownBlocks(content: string): string[] {
  const lines = content.replace(/\r\n/g, '\n').split('\n')
  const blocks: string[] = []
  let index = 0
  while (index < lines.length) {
    if (!lines[index].trim()) { index += 1; continue }
    if (lines[index].trim().startsWith('```')) {
      const block = [lines[index]]; index += 1
      while (index < lines.length) { block.push(lines[index]); const done = lines[index].trim().startsWith('```'); index += 1; if (done) {break} }
      blocks.push(`${block.join('\n')}\n\n`); continue
    }
    if (lines[index].trim().startsWith('|')) {
      const block: string[] = []
      while (index < lines.length && lines[index].trim().startsWith('|')) { block.push(lines[index]); index += 1 }
      blocks.push(`${block.join('\n')}\n\n`); continue
    }
    if (lines[index].trim().startsWith('- ') || /^\d+\.\s+/.test(lines[index].trim())) {
      const block: string[] = []
      while (index < lines.length && (lines[index].trim().startsWith('- ') || /^\d+\.\s+/.test(lines[index].trim()))) { block.push(lines[index]); index += 1 }
      blocks.push(`${block.join('\n')}\n\n`); continue
    }
    const block: string[] = []
    while (index < lines.length && lines[index].trim() && !lines[index].trim().startsWith('|') && !lines[index].trim().startsWith('- ') && !/^\d+\.\s+/.test(lines[index].trim()) && !lines[index].trim().startsWith('```')) { block.push(lines[index]); index += 1 }
    blocks.push(`${block.join('\n')}\n\n`)
  }
  return blocks.length ? blocks : [content]
}

export default function DiagnosisWorkbench({ workspaceId }: { workspaceId?: string }) {
  const [inputText, setInputText] = useState('')
  const [messages, setMessages] = useState<DiagnosisMessage[]>([])
  const [runningRunIds, setRunningRunIds] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [historyOpen, setHistoryOpen] = useState(true)
  const [historyVersion, setHistoryVersion] = useState(0)
  const [mode, setMode] = useState<DiagnosisMode>('diagnosis')
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [focusedEventId, setFocusedEventId] = useState<string | null>(null)

  const abortByRunRef = useRef<Record<string, () => void>>({})
  const sessionRef = useRef<{ userText: string }>({ userText: '' })
  const backendSessionIdRef = useRef<string | null>(null)
  const messagesRef = useRef<DiagnosisMessage[]>([])
  const visibleRunIdRef = useRef<string>('')
  const runMessagesRef = useRef<Record<string, DiagnosisMessage[]>>({})
  const runMetaRef = useRef<Record<string, { userText: string; createdAt: string }>>({})
  const runModeRef = useRef<Record<string, DiagnosisMode>>({})
  const runPlainAnswerRef = useRef<Record<string, boolean>>({})
  const plainAnswerQueueRef = useRef<Record<string, string[]>>({})
  const plainAnswerTypingRef = useRef<Record<string, boolean>>({})
  const plainAnswerDoneRef = useRef<Record<string, boolean>>({})
  const plainAnswerTimerRef = useRef<Record<string, number | null>>({})
  const pendingDoneRef = useRef<Record<string, { summary?: DiagnosisSummary; session?: DoneSession }>>({})
  const runStatusRef = useRef<Record<string, 'running' | 'complete'>>({})
  // id of the assistant bubble currently being streamed into
  const streamingIdByRunRef = useRef<Record<string, string | null>>({})
  // id of the report bubble currently being streamed into
  const reportStreamIdByRunRef = useRef<Record<string, string | null>>({})
  // wall-clock start time (ms) for each running skill, keyed by skill name
  const skillStartRef = useRef<Record<string, number>>({})
  // id of the current diagnosis run — scopes call_graph updates to the active run
  const currentRunLoading = visibleRunIdRef.current ? runningRunIds.includes(visibleRunIdRef.current) : false

  useEffect(() => {
    messagesRef.current = messages
  }, [messages])

  const persistRun = (
    runId: string,
    runMessages: DiagnosisMessage[],
    status: 'running' | 'complete',
    unread = false,
    summary?: Parameters<typeof updateHistoryRecord>[0]['summary'],
  ) => {
    const meta = runMetaRef.current[runId]
    if (!meta) {return}
    const existing = loadHistory().find(record => record.id === runId)
    const nextUnread = status === 'complete' && existing?.status === 'complete'
      ? Boolean(existing.unread)
      : unread
    updateHistoryRecord({
      id: runId,
      createdAt: meta.createdAt,
      userText: meta.userText,
      messages: compactMessagesForHistory(runMessages),
      status,
      unread: nextUnread,
      ...(summary ? { summary } : {}),
    })
  }

  const updateRunMessages = (runId: string, updater: (current: DiagnosisMessage[]) => DiagnosisMessage[]) => {
    setMessages(prev => {
      const isVisible = visibleRunIdRef.current === runId
      const base = isVisible ? prev : (runMessagesRef.current[runId] ?? [])
      const next = updater(base)
      runMessagesRef.current[runId] = next
      const status = runStatusRef.current[runId] ?? 'running'
      if (status === 'complete') {
        persistRun(runId, next, status, visibleRunIdRef.current !== runId)
      }
      return isVisible ? next : prev
    })
  }

  const sealReportStream = (runId: string) => {
    const rid = reportStreamIdByRunRef.current[runId]
    reportStreamIdByRunRef.current[runId] = null
    if (!rid) {return}
    updateRunMessages(runId, prev =>
      prev.map(m => m.stream_id === rid ? { ...m, type: 'report' as const } : m),
    )
    const pending = pendingDoneRef.current[runId]
    if (pending) {
      delete pendingDoneRef.current[runId]
      completeRun(runId, pending.summary)
    }
  }

  const completeRun = (runId: string, summary?: DiagnosisSummary) => {
    if (runStatusRef.current[runId] === 'complete') {return}
    runStatusRef.current[runId] = 'complete'
    setRunningRunIds(prev => prev.filter(id => id !== runId))
    const latest = runMessagesRef.current[runId] ?? []
    persistRun(runId, latest, 'complete', visibleRunIdRef.current !== runId, summary)
    setHistoryVersion(value => value + 1)
  }

  const pumpPlainAnswer = (runId: string) => {
    if (plainAnswerTypingRef.current[runId]) {return}
    plainAnswerTypingRef.current[runId] = true

    const tick = () => {
      const next = plainAnswerQueueRef.current[runId]?.shift()
      const rid = reportStreamIdByRunRef.current[runId]
      if (next && rid) {
        updateRunMessages(runId, prev => prev.map(m =>
          m.stream_id === rid ? { ...m, content: (m.content ?? '') + next } : m,
        ))
        plainAnswerTimerRef.current[runId] = window.setTimeout(tick, 140)
        return
      }

      plainAnswerTypingRef.current[runId] = false
      plainAnswerTimerRef.current[runId] = null
      if (plainAnswerDoneRef.current[runId]) {
        sealReportStream(runId)
      }
    }

    tick()
  }

  const handleSend = () => {
    if (currentRunLoading || !inputText.trim()) {return}

    const userText = inputText.trim()
    const requestMode = mode
    sessionRef.current.userText = userText
    const runId = crypto.randomUUID()
    const createdAt = new Date().toISOString()
    const userMessage: DiagnosisMessage = { role: 'user', type: 'text', content: userText }
    const initialMessages = visibleRunIdRef.current ? [...messagesRef.current, userMessage] : [userMessage]

    visibleRunIdRef.current = runId
    runMetaRef.current[runId] = { userText, createdAt }
    runModeRef.current[runId] = requestMode
    runPlainAnswerRef.current[runId] = requestMode === 'observability'
    runMessagesRef.current[runId] = initialMessages
    runStatusRef.current[runId] = 'running'
    persistRun(runId, initialMessages, 'running')
    setHistoryVersion(value => value + 1)
    setRunningRunIds(prev => prev.includes(runId) ? prev : [...prev, runId])

    setInputText('')
    setMessages(initialMessages)
    setError(null)
    streamingIdByRunRef.current[runId] = null
    reportStreamIdByRunRef.current[runId] = null
    plainAnswerQueueRef.current[runId] = []
    plainAnswerTypingRef.current[runId] = false
    plainAnswerDoneRef.current[runId] = false
    delete pendingDoneRef.current[runId]
    if (plainAnswerTimerRef.current[runId]) {
      window.clearTimeout(plainAnswerTimerRef.current[runId] ?? undefined)
      plainAnswerTimerRef.current[runId] = null
    }

    const parsedDiagnosisRequest = parseUserInput(userText)
    const baseRequest: DiagnoseRequest = {
      ...parsedDiagnosisRequest,
      message: userText,
      mode: requestMode,
      ...(backendSessionIdRef.current ? { session_id: backendSessionIdRef.current } : {}),
    }

    if (requestMode === 'storm') {
      updateRunMessages(runId, prev => [...prev, {
        role: 'assistant' as const,
        type: 'text' as const,
        content: `模式：${MODE_LABELS.storm} · 风暴初始化`,
      }])
      const abort = streamStormDemoDiagnosis(baseRequest, {
        onOverview: (overview) => {
          updateRunMessages(runId, prev => {
            const overviewIndex = prev.findIndex(message => message.type === 'storm_overview')
            if (overviewIndex < 0) {
              return [...prev, {
                role: 'assistant' as const,
                type: 'storm_overview' as const,
                storm_overview: overview,
              }]
            }
            return prev.map((message, index) => index === overviewIndex
              ? { ...message, storm_overview: overview }
              : message)
          })
        },
        onAssistantStatus: (content) => {
          const sid = crypto.randomUUID()
          streamingIdByRunRef.current[runId] = sid
          updateRunMessages(runId, prev => [...prev, {
            role: 'assistant' as const,
            type: 'assistant_streaming' as const,
            content,
            stream_id: sid,
          }])
        },
        onAssistantDone: () => {
          const sid = streamingIdByRunRef.current[runId]
          streamingIdByRunRef.current[runId] = null
          if (!sid) {return}
          updateRunMessages(runId, prev => prev.map(m =>
            m.stream_id === sid ? { ...m, type: 'text' as const } : m
          ))
        },
        onSkillStart: (message) => {
          updateRunMessages(runId, prev => [...prev, { ...message, run_id: runId }])
        },
        onSkillDone: (message) => {
          updateRunMessages(runId, prev => prev.map(m =>
            m.stream_id === message.stream_id ? message : m
          ))
        },
        onRoundSummary: (summary) => {
          updateRunMessages(runId, prev => [...prev, {
            role: 'assistant' as const,
            type: 'storm_round_summary' as const,
            storm_round_summary: summary,
          }])
        },
        onTopology: (callGraph) => {
          updateRunMessages(runId, prev => [...prev, {
            role: 'assistant' as const,
            type: 'call_graph' as const,
            call_graph: callGraph,
            run_id: runId,
          }])
        },
        onReportDelta: (content) => {
          const rid = reportStreamIdByRunRef.current[runId]
          if (rid) {
            updateRunMessages(runId, prev => prev.map(m =>
              m.stream_id === rid ? { ...m, content: (m.content ?? '') + content } : m
            ))
          } else {
            const newId = crypto.randomUUID()
            reportStreamIdByRunRef.current[runId] = newId
            updateRunMessages(runId, prev => [...prev, {
              role: 'assistant' as const,
              type: 'report_streaming' as const,
              content,
              stream_id: newId,
              report_title: '风暴诊断报告',
            }])
          }
        },
        onReportDone: () => {
          const rid = reportStreamIdByRunRef.current[runId]
          reportStreamIdByRunRef.current[runId] = null
          if (!rid) {return}
          updateRunMessages(runId, prev => prev.map(m =>
            m.stream_id === rid ? { ...m, type: 'report' as const } : m
          ))
        },
        onDone: (summary) => {
          runStatusRef.current[runId] = 'complete'
          setRunningRunIds(prev => prev.filter(id => id !== runId))
          const latest = runMessagesRef.current[runId] ?? []
          persistRun(runId, latest, 'complete', visibleRunIdRef.current !== runId, summary)
          setHistoryVersion(value => value + 1)
        },
        onError: (err) => {
          runStatusRef.current[runId] = 'complete'
          if (visibleRunIdRef.current === runId) {setError(err)}
          setRunningRunIds(prev => prev.filter(id => id !== runId))
          const latest = runMessagesRef.current[runId] ?? []
          persistRun(runId, latest, 'complete', visibleRunIdRef.current !== runId)
          setHistoryVersion(value => value + 1)
        },
      })

      abortByRunRef.current[runId] = abort
      return
    }

    const isFollowUp = Boolean(backendSessionIdRef.current)
    const diagnosisRequest: DiagnoseRequest = {
      ...baseRequest,
      ...(isFollowUp && !hasExplicitApi(userText) ? { api: '' } : {}),
      ...(isFollowUp && !hasExplicitTime(userText) ? { time: '' } : {}),
      ...(isFollowUp && !hasExplicitSymptom(userText) ? { symptom: '' } : {}),
    }

    const abort = streamAgenticDiagnosis(diagnosisRequest, {
      onSession: (session) => {
        if (session.session_id) {backendSessionIdRef.current = session.session_id}
        if (session.mode === 'observability' || session.intent === 'observability_query') {
          runPlainAnswerRef.current[runId] = true
        }
        if (session.intent) {
          const responseMode = (session.mode === 'observability' || session.mode === 'diagnosis' || session.mode === 'storm') ? session.mode : requestMode
          const modeText = `模式：${MODE_LABELS[responseMode]}`
          updateRunMessages(runId, prev => [...prev, {
            role: 'assistant' as const,
            type: 'text' as const,
            content: modeText,
          }])
        }
      },
      onAssistantDelta: (content) => {
        // Read/write the ref synchronously OUTSIDE the updater so that
        // onAssistantMessageDone always sees the current id when it runs.
        const sid = streamingIdByRunRef.current[runId]
        if (sid) {
          updateRunMessages(runId, prev =>
            prev.map(m =>
              m.stream_id === sid
                ? { ...m, content: (m.content ?? '') + content }
                : m
            )
          )
        } else {
          // Create new streaming bubble
          const newId = crypto.randomUUID()
          streamingIdByRunRef.current[runId] = newId
          updateRunMessages(runId, prev => [...prev, {
            role: 'assistant',
            type: 'assistant_streaming',
            content,
            stream_id: newId,
          }])
        }
      },
      onAssistantReplace: (content) => {
        const sid = streamingIdByRunRef.current[runId]
        if (sid) {
          updateRunMessages(runId, prev =>
            prev.map(m =>
              m.stream_id === sid
                ? { ...m, type: 'assistant_streaming', content }
                : m
            )
          )
        } else {
          const newId = crypto.randomUUID()
          streamingIdByRunRef.current[runId] = newId
          updateRunMessages(runId, prev => [...prev, {
            role: 'assistant',
            type: 'assistant_streaming',
            content,
            stream_id: newId,
          }])
        }
      },
      onAssistantMessageDone: () => {
        // Seal the streaming bubble → convert to plain text bubble
        const sid = streamingIdByRunRef.current[runId]
        streamingIdByRunRef.current[runId] = null
        if (sid) {
          updateRunMessages(runId, prev =>
            prev.map(m =>
              m.stream_id === sid ? { ...m, type: 'text' } : m
            )
          )
        }
      },
      onSkillStart: (skill, title, reason) => {
        if (skill === 'generate_report') {return}  // report is streamed directly, no tool card
        skillStartRef.current[`${runId}:${skill}`] = Date.now()
        updateRunMessages(runId, prev => [...prev, {
          role: 'assistant',
          type: 'skill_call',
          skill_name: skill,
          tool_name: `UModelSkill/${skill}`,
          run_id: runId,
          status: 'running',
          summary: '',
          content: title,
          explanation: reason,
          evidence: [],
          execution_log: [],
        }])
      },
      onSkillDone: (skill, result, callGraph) => {
        if (skill === 'generate_report') {return}  // no tool card was created for this skill
        updateRunMessages(runId, prev => {
          const updated = prev.map(m =>
            m.type === 'skill_call' && m.skill_name === skill && m.status === 'running'
              ? { ...m, status: 'success', summary: result.summary, evidence: result.evidence, execution_log: result.execution_log, duration_ms: result.duration_ms, root_cause_status: result.root_cause_status, confidence: result.confidence, output: result.output }
              : m
          )
          if (callGraph && callGraph.nodes.length > 0) {
            const callGraphIndex = updated.reduce((last: number, m: DiagnosisMessage, idx: number) =>
              m.type === 'call_graph' && m.run_id === runId ? idx : last, -1)
            if (callGraphIndex >= 0) {
              return updated.map((m, index) =>
                index === callGraphIndex
                  ? { ...m, call_graph: callGraph }
                  : m
              )
            }
            return [...updated, { role: 'assistant' as const, type: 'call_graph' as const, call_graph: callGraph, run_id: runId }]
          }
          return updated
        })
        delete skillStartRef.current[`${runId}:${skill}`]
      },
      onSkillError: (skill, err, result, recoveryAction) => {
        updateRunMessages(runId, prev => {
          const recovery = recoveryAction ?? result.recovery_action ?? '已记录失败并继续后续可执行分析'
          const updated = prev.map(m =>
            m.type === 'skill_call' && m.skill_name === skill && m.status === 'running'
              ? { ...m, status: 'failed', summary: result.summary, evidence: result.evidence, execution_log: result.execution_log, recovery_action: recovery, output: result.output }
              : m
          )
          // Append an inline error hint so user knows diagnosis continues
          return [...updated, {
            role: 'assistant' as const,
            type: 'text' as const,
            content: `${skill} 执行遇到问题：${err}。${recovery}。`,
          }]
        })
      },
      onReportDelta: (content) => {
        // Read/write the ref synchronously OUTSIDE the updater — same pattern as onAssistantDelta.
        // Writing the ref inside the updater causes a race: React may batch/delay updaters so
        // multiple deltas all see reportStreamIdRef.current === null and each create a new bubble.
        const rid = reportStreamIdByRunRef.current[runId]
        if (rid) {
          if (runPlainAnswerRef.current[runId]) {
            plainAnswerQueueRef.current[runId] = [
              ...(plainAnswerQueueRef.current[runId] ?? []),
              ...splitMarkdownBlocks(content),
            ]
            pumpPlainAnswer(runId)
          } else {
            updateRunMessages(runId, prev =>
              prev.map(m =>
                m.stream_id === rid ? { ...m, content: (m.content ?? '') + content } : m
              )
            )
          }
        } else {
          const newId = crypto.randomUUID()
          reportStreamIdByRunRef.current[runId] = newId
          updateRunMessages(runId, prev => [...prev, {
            role: 'assistant' as const,
            type: 'report_streaming' as const,
            content: runPlainAnswerRef.current[runId] ? '' : content,
            stream_id: newId,
            render_as: runPlainAnswerRef.current[runId] ? 'plain' as const : 'report' as const,
          }])
          if (runPlainAnswerRef.current[runId]) {
            plainAnswerQueueRef.current[runId] = [
              ...(plainAnswerQueueRef.current[runId] ?? []),
              ...splitMarkdownBlocks(content),
            ]
            pumpPlainAnswer(runId)
          }
        }
      },
      onReportDone: (_report) => {
        if (runPlainAnswerRef.current[runId]) {
          plainAnswerDoneRef.current[runId] = true
          if (!plainAnswerTypingRef.current[runId] && !(plainAnswerQueueRef.current[runId] ?? []).length) {
            sealReportStream(runId)
          }
        } else {
          sealReportStream(runId)
        }
      },
      onDone: (summary, session) => {
        if (session?.session_id) {backendSessionIdRef.current = session.session_id}
        if (runPlainAnswerRef.current[runId] && reportStreamIdByRunRef.current[runId]) {
          pendingDoneRef.current[runId] = { summary, session }
          return
        }
        completeRun(runId, summary)
      },
      onError: (err) => {
        runStatusRef.current[runId] = 'complete'
        if (visibleRunIdRef.current === runId) {setError(err)}
        setRunningRunIds(prev => prev.filter(id => id !== runId))
        const latest = runMessagesRef.current[runId] ?? []
        persistRun(runId, latest, 'complete', visibleRunIdRef.current !== runId)
        setHistoryVersion(value => value + 1)
      },
    })

    abortByRunRef.current[runId] = abort
  }

  const handleStop = () => {
    const runId = visibleRunIdRef.current
    abortByRunRef.current[runId]?.()
    delete abortByRunRef.current[runId]
    setRunningRunIds(prev => prev.filter(id => id !== runId))
    const latest = runMessagesRef.current[runId]
    if (runId && latest) {
      if (plainAnswerTimerRef.current[runId]) {
        window.clearTimeout(plainAnswerTimerRef.current[runId] ?? undefined)
        plainAnswerTimerRef.current[runId] = null
      }
      runStatusRef.current[runId] = 'complete'
      persistRun(runId, latest, 'complete', visibleRunIdRef.current !== runId)
      setHistoryVersion(value => value + 1)
    }
  }

  const handleNewChat = () => {
    if (visibleRunIdRef.current && messagesRef.current.length > 0) {
      runMessagesRef.current[visibleRunIdRef.current] = messagesRef.current
    }
    visibleRunIdRef.current = ''
    backendSessionIdRef.current = null
    setInputText('')
    setMessages([])
    messagesRef.current = []
    setError(null)
    setMode('diagnosis')
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // ── Derived data for the new split-pane layout ───────────────────────────
  const latestCallGraph: CallGraph | null | undefined = (() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].type === 'call_graph' && messages[i].call_graph) {
        return messages[i].call_graph
      }
    }
    return null
  })()

  const currentMode: 'normal' | 'storm' = mode === 'storm' ? 'storm' : 'normal'
  const rawEvents = useMemo(
    () => currentMode === 'storm'
      ? buildStormEventStream(messages)
      : buildNormalEventStream(messages),
    [currentMode, messages],
  )
  // Enrich related_nodes with actual topology node IDs where possible
  const events = useMemo(
    () => rawEvents.map(evt => ({
      ...evt,
      related_nodes: enrichRelatedNodesWithIds(evt.related_nodes, latestCallGraph),
    })),
    [rawEvents, latestCallGraph],
  )

  const isEmpty = messages.length === 0 && !currentRunLoading

  const handleTopologyNodeClick = (nodeId: string) => {
    setSelectedNodeId(nodeId)
    if (!latestCallGraph) {return}
    const node = latestCallGraph.nodes.find(n => n.id === nodeId)
    if (!node) {return}
    const matchedEventId = matchNodeToEvent(nodeId, node, events)
    if (matchedEventId) {
      setFocusedEventId(matchedEventId)
      // Clear focus after a short delay so user can re-click
      setTimeout(() => setFocusedEventId(null), 3000)
    }
  }

  return (
    <div className="diag-workbench-scope flex h-full bg-white text-[#1f2937] overflow-hidden">
      <HistoryPanel
        open={historyOpen}
        onOpen={() => setHistoryOpen(true)}
        onClose={() => setHistoryOpen(false)}
        onNewChat={handleNewChat}
        onReplay={(msgs, _label, id) => {
          visibleRunIdRef.current = id
          runMessagesRef.current[id] = msgs
          setMode(runModeRef.current[id] ?? inferModeFromMessages(msgs))
          setMessages(msgs)
          messagesRef.current = msgs
          setError(null)
          setHistoryVersion(value => value + 1)
        }}
        activeRunIds={runningRunIds}
        refreshKey={historyVersion}
      />
      <div className="flex flex-col flex-1 overflow-hidden">
        {/* ── Topology panel (upper half) ──────────────────────────────── */}
        {!isEmpty && (
          <div className="flex-shrink-0 border-b border-[#e5e7eb]">
            {latestCallGraph ? (
              <ServiceCallGraph graph={latestCallGraph} onNodeClick={handleTopologyNodeClick} selectedNodeId={selectedNodeId} />
            ) : (
              <div className="bg-white px-5 py-4 text-[13px] text-[#9ca3af] flex items-center gap-2">
                <div className="w-2.5 h-2.5 rounded-full border-2 border-[#d1d5db] border-t-[#6b7280] animate-spin" />
                <span>等待识别入口对象，正在构建故障相关拓扑…</span>
              </div>
            )}
          </div>
        )}

        {/* ── Event stream (lower half) / Empty state ──────────────────── */}
        {isEmpty ? (
          <div className="flex-1 flex flex-col">
            <EmptyState onSelectExample={(text) => setInputText(text)} />
          </div>
        ) : (
          <EventStream
            events={events}
            loading={currentRunLoading}
            currentGraph={latestCallGraph}
            focusedEventId={focusedEventId}
            onNodeClick={(label) => {
              // Token click — resolve label to topology node ID precisely
              const matchedId = resolveNodeLabelToId(label, latestCallGraph)
              if (matchedId) {setSelectedNodeId(matchedId)}
            }}
          />
        )}

        {/* Error bar */}
        {error && (
          <div className="px-4 py-2 bg-red-50 text-red-700 text-sm border-t border-red-200">
            {error}
          </div>
        )}

        {/* Input area */}
        <div className="px-5 py-2.5 border-t border-[#e5e7eb] bg-white flex-shrink-0">
          <div className="max-w-7xl mx-auto mb-2 flex items-center gap-2">
            <div className="inline-flex rounded-lg bg-transparent p-0.5 gap-1" role="tablist" aria-label="诊断模式">
              {MODE_OPTIONS.map(({ value, label, Icon }) => {
                const active = mode === value
                return (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setMode(value)}
                    disabled={currentRunLoading}
                    aria-pressed={active}
                    className={`inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors ${active
                      ? 'border-[#0e639c] bg-[#0e639c] text-white shadow-sm'
                      : 'border-[#d1d5db] text-[#6b7280] hover:bg-white hover:text-[#111827]'
                    } disabled:opacity-50`}
                    title={label}
                  >
                    <Icon size={13} />
                    {label}
                  </button>
                )
              })}
            </div>
          </div>
          <div className="max-w-7xl mx-auto flex items-end gap-2 bg-[#f9fafb] rounded-lg px-3 py-2 border border-[#d1d5db] shadow-[0_1px_8px_rgba(15,23,42,0.08)]">
            <textarea
              className="flex-1 bg-transparent text-sm text-[#111827] placeholder-[#9ca3af] resize-none outline-none leading-relaxed max-h-32 min-h-[2.5rem]"
              rows={2}
              value={inputText}
              onChange={e => setInputText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={MODE_PLACEHOLDERS[mode]}
              disabled={currentRunLoading}
            />
            {currentRunLoading ? (
              <button
                onClick={handleStop}
                className="diag-action-btn flex-shrink-0 w-8 h-8 flex items-center justify-center rounded-full border-none transition-colors"
                title="停止"
              >
                <StopCircle size={15} />
              </button>
            ) : (
              <button
                onClick={handleSend}
                disabled={!inputText.trim()}
                className="diag-action-btn flex-shrink-0 w-8 h-8 flex items-center justify-center rounded-full border-none transition-colors"
                title="发送 (Enter)"
              >
                <ArrowUp size={16} />
              </button>
            )}
          </div>
          <p className="max-w-7xl mx-auto text-[10px] text-[#9ca3af] mt-1.5 pl-1">
            Mobile Ops 可能会出错。请核实重要信息。
            <span className="ml-2 opacity-50">UI {UI_VERSION}</span>
          </p>
        </div>
      </div>
    </div>
  )
}
