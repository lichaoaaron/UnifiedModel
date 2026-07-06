import React, { useEffect, useRef, useMemo } from 'react'
import type { EventStreamItem, CallGraph, EntitySummaryData } from '../types/diagnosis'
import EventRow from './EventRow'
import { Terminal } from 'lucide-react'

interface Props {
  events: EventStreamItem[]
  loading?: boolean
  /** The current call graph to show in the topology panel */
  currentGraph?: CallGraph | null
  highlightedNodeId?: string
  onNodeClick?: (nodeId: string) => void
  focusedEventId?: string | null
}

/** Extract entity summary data from bind_entities event in the stream. */
function extractEntityData(events: EventStreamItem[]): EntitySummaryData | null {
  const bindEvent = events.find(e => e.details?.output && (e.title === 'bind_entities' || (e.raw as Record<string, unknown>)?.skill_name === 'entity_binding'))
  if (!bindEvent?.details?.output) {return null}
  const output = bindEvent.details.output as Record<string, unknown>
  const services = Array.isArray(output.services) ? output.services as string[] : []
  const instances = Array.isArray(output.instances) ? output.instances as string[] : []
  const interfaces = Array.isArray(output.interfaces) ? output.interfaces as string[] : []
  if (!services.length && !instances.length) {return null}
  return { services, instances, interfaces }
}

export default function EventStream({ events, loading, highlightedNodeId, onNodeClick, focusedEventId }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const eventRowRefs = useRef<Map<string, HTMLDivElement>>(new Map())
  const autoScrollRef = useRef(true)

  // Extract entity data from bind_entities event for the report
  const entityData = useMemo(() => extractEntityData(events), [events])

  // Auto-scroll to bottom when new events arrive (unless user is reading)
  useEffect(() => {
    const el = scrollRef.current
    if (!el || !autoScrollRef.current) {return}
    el.scrollTop = el.scrollHeight
  }, [events])

  // Scroll to focused event when it changes
  useEffect(() => {
    if (!focusedEventId) {return}
    const rowEl = eventRowRefs.current.get(focusedEventId)
    if (rowEl) {
      rowEl.scrollIntoView({ block: 'center', behavior: 'smooth' })
    }
  }, [focusedEventId])

  const handleScroll = () => {
    const el = scrollRef.current
    if (!el) {return}
    const threshold = 50
    autoScrollRef.current = el.scrollHeight - el.scrollTop - el.clientHeight <= threshold
  }

  if (events.length === 0) {return null}

  return (
    <div className="flex-1 min-h-0 flex flex-col overflow-hidden bg-white">
      <div className="event-stream-header flex-shrink-0 flex items-center gap-2 px-3 py-1.5 border-b border-[#f0f0f0] bg-[#fafafa]">
        <Terminal size={12} className="text-[#9ca3af]" />
        <span className="text-[10px] font-medium text-[#9ca3af] uppercase tracking-wider">诊断事件流</span>
        {events.length > 0 && (
          <span className="text-[10px] text-[#c4c4c4] ml-auto">
            {events.length} 条事件
          </span>
        )}
      </div>

      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 min-h-0 overflow-y-auto py-1"
      >
        {events.map((event) => (
          <div
            key={event.id}
            ref={(el) => {
              if (el) {eventRowRefs.current.set(event.id, el)}
              else {eventRowRefs.current.delete(event.id)}
            }}
            data-event-id={event.id}
          >
            <EventRow
              event={event}
              highlightedNodeId={highlightedNodeId}
              onNodeClick={onNodeClick}
              isFocused={focusedEventId === event.id}
              entityData={entityData}
            />
          </div>
        ))}
      </div>
    </div>
  )
}
