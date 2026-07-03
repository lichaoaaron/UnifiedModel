import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import type { CallGraph, CallNode, CallEdge } from '../types/diagnosis'

interface Props {
  graph: CallGraph
  onNodeClick?: (nodeId: string) => void
  selectedNodeId?: string | null
}

// ── Layout constants ────────────────────────────────────────────────────────
const NODE_W = 128
const NODE_H = 44
const H_GAP = 28       // gap between nodes in the same row
const ROW_H = 96       // vertical pitch between rows (node + space for edges)
const V_PAD = 16       // top / bottom padding
const H_PAD = 16       // left / right padding
const ROW_LABEL_W = 72 // fixed-width column for row labels on the left

// ── Row ordering: lower index = higher up in the graph ─────────────────────
const TYPE_ROW: Record<string, number> = {
  BusinessFlow: 0,
  Business:     1,
  Service:      2,
  Interface:    3,
  Dependency:   4,
  Instance:     5,
  // legacy lowercase fallbacks
  service:   2,
  interface: 3,
  dependency: 4,
}

const ROW_LABEL: Record<number, string> = {
  0: 'BusinessFlow',
  1: 'Business',
  2: 'Service',
  3: 'Interface',
  4: 'Dependency',
  5: 'Instance',
}

// ── Node colouring ──────────────────────────────────────────────────────────
// Priority: visual_role > storm_role > legacy fields
function nodeStyle(node: CallNode, _showMiddle: boolean) {
  // Extended visual roles (object-centered topology)
  if (node.visual_role === 'confirmed_root')
    return { fill: '#fee2e2', stroke: '#ef4444', text: '#991b1b', opacity: 1, strokeWidth: 2.5 }
  if (node.visual_role === 'candidate_root')
    return { fill: '#fef3c7', stroke: '#f59e0b', text: '#92400e', opacity: 1, strokeWidth: 2 }
  if (node.visual_role === 'entry')
    return { fill: '#dbeafe', stroke: '#3b82f6', text: '#1d4ed8', opacity: 1, strokeWidth: 2 }
  // direct_impact, indirect_impact, propagated → unified "affected" (amber)
  if (node.visual_role === 'direct_impact' || node.visual_role === 'indirect_impact' || node.visual_role === 'propagated')
    return { fill: '#fef9c3', stroke: '#eab308', text: '#854d0e', opacity: 1, strokeWidth: 1.5 }
  if (node.visual_role === 'observed')
  if (node.visual_role === 'observed')
    return { fill: '#f8fafc', stroke: '#94a3b8', text: '#475569', opacity: 0.82, strokeWidth: 1 }
  if (node.visual_role === 'normal')
    return { fill: '#f9fafb', stroke: '#d1d5db', text: '#4b5563', opacity: 0.95 }

  // Legacy storm roles
  if (node.storm_role === 'common_root')
    return { fill: '#fee2e2', stroke: '#ef4444', text: '#991b1b', opacity: 1 }
  if (node.storm_role === 'secondary_local_issue')
    return { fill: '#fef3c7', stroke: '#d97706', text: '#92400e', opacity: 1 }
  if (node.storm_role === 'propagated_impact')
    return { fill: '#fef9c3', stroke: '#eab308', text: '#854d0e', opacity: 1 }
  if (node.storm_role === 'noise')
    return { fill: '#f8fafc', stroke: '#94a3b8', text: '#475569', opacity: 0.72 }

  // Legacy fields
  if (node.is_root_cause)
    return { fill: '#fee2e2', stroke: '#ef4444', text: '#991b1b', opacity: 1 }
  if (node.is_entry)
    return { fill: '#dbeafe', stroke: '#3b82f6', text: '#1d4ed8', opacity: 1 }
  if (node.is_call_chain)
    return { fill: '#fef9c3', stroke: '#eab308', text: '#854d0e', opacity: 1 }
  // not in call chain — subdued but readable
  return   { fill: '#f9fafb',   stroke: '#d1d5db', text: '#4b5563', opacity: 0.95 }
}

// ── Edge colouring ──────────────────────────────────────────────────────────
function edgeStyle(edge: CallEdge) {
  return edge.is_call_chain
    ? { stroke: '#6b7280', width: 1.5, opacity: 1,    labelFill: '#4b5563' }
    : { stroke: '#cbd5e1', width: 1.05, opacity: 0.9,  labelFill: '#64748b' }
}

// ── Cubic-bezier path between two points ───────────────────────────────────
function curvePath(
  x1: number, y1: number, exitDown: boolean,
  x2: number, y2: number, _enterDown: boolean,
): string {
  const midY = (y1 + y2) / 2
  if (exitDown) {
    return `M${x1},${y1} C${x1},${midY} ${x2},${midY} ${x2},${y2}`
  }
  if (!exitDown && !_enterDown) {
    // same row: gentle arc above
    const bulge = -42
    return `M${x1},${y1} C${x1 + (x2 - x1) * 0.25},${y1 + bulge} ${x2 - (x2 - x1) * 0.25},${y2 + bulge} ${x2},${y2}`
  }
  return `M${x1},${y1} C${x1},${midY} ${x2},${midY} ${x2},${y2}`
}

function labelWidth(label: string) {
  return Math.max(28, label.length * 5.6 + 10)
}

function avg(values: number[]) {
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

function nodeRoleText(node: CallNode) {
  const type = node.node_type ?? 'service'

  // Simplified: 4 user-facing roles — root / entry include type context
  if (node.visual_role === 'confirmed_root') {
    if (type === 'Dependency' || type === 'dependency') return '根因依赖'
    if (type === 'Interface' || type === 'interface') return '根因接口'
    return '根因服务'
  }
  if (node.visual_role === 'candidate_root') return '候选'
  if (node.visual_role === 'entry') {
    if (type === 'Interface' || type === 'interface') return '入口接口'
    return '入口服务'
  }
  if (node.visual_role === 'direct_impact' || node.visual_role === 'indirect_impact' || node.visual_role === 'propagated') return '受影响'
  if (node.visual_role === 'observed') return '仅观测'
  // Legacy storm roles
  if (node.storm_role === 'common_root') return '根因'
  if (node.storm_role === 'secondary_local_issue') return '次要'
  if (node.storm_role === 'propagated_impact') return '受影响'
  if (node.storm_role === 'noise') return '背景'
  // Legacy fields — also include type context
  if (node.is_root_cause) {
    if (type === 'Dependency' || type === 'dependency') return '根因依赖'
    if (type === 'Interface' || type === 'interface') return '根因接口'
    return '根因服务'
  }
  if (node.is_entry) {
    if (type === 'Interface' || type === 'interface') return '入口接口'
    return '入口服务'
  }
  return ''
}

function formatNodeDisplayLabel(node: CallNode): string {
  const raw = node.label || node.id
  const type = node.node_type ?? ''
  if (type === 'Interface' || type === 'interface') {
    if (raw.startsWith('/')) {
      return raw.length > 24 ? `${raw.slice(0, 23)}...` : raw
    }
    if (raw.includes('/') && !raw.includes(' ')) {
      const parts = raw.split('/')
      const tail = parts.slice(-2).join('/')
      const shown = tail || raw
      return shown.length > 24 ? `${shown.slice(0, 23)}...` : shown
    }
  }
  return raw.length > 16 ? `${raw.slice(0, 15)}...` : raw
}

export default function ServiceCallGraph({ graph, onNodeClick, selectedNodeId }: Props) {
  const [collapsed, setCollapsed] = useState(false)

  if (!graph || graph.nodes.length === 0) return null
  if (collapsed) {
    return (
      <div className="bg-white rounded-xl border border-[#e5e7eb] p-4 shadow-[0_1px_5px_rgba(15,23,42,0.06)]">
        <button
          type="button"
          onClick={() => setCollapsed(false)}
          className="flex w-full items-center justify-between gap-3 text-left"
          aria-expanded="false"
          title="展开本体层拓扑"
        >
          <span className="flex items-center gap-2 text-xs font-semibold text-[#0e639c]">
            <ChevronRight size={14} />
            <span>&#x1F578; 本体层拓扑</span>
          </span>
          <span className="text-[10px] font-medium text-[#6b7280]">
            {graph.nodes.length} 节点 · {graph.edges.length} 边
          </span>
        </button>
      </div>
    )
  }

  const hasStormRoles = graph.nodes.some(node => node.storm_role)

  // ── Group nodes by row ──────────────────────────────────────────────────
  const rowBuckets = new Map<number, CallNode[]>()
  for (const node of graph.nodes) {
    const r = TYPE_ROW[node.node_type ?? 'service'] ?? 2
    if (!rowBuckets.has(r)) rowBuckets.set(r, [])
    rowBuckets.get(r)!.push(node)
  }
  const activeRows = [...rowBuckets.keys()].sort((a, b) => a - b)
  const nodeById = new Map(graph.nodes.map(node => [node.id, node]))
  const neighbors = new Map<string, string[]>()
  for (const edge of graph.edges) {
    const srcList = neighbors.get(edge.source) ?? []
    srcList.push(edge.target)
    neighbors.set(edge.source, srcList)

    const tgtList = neighbors.get(edge.target) ?? []
    tgtList.push(edge.source)
    neighbors.set(edge.target, tgtList)
  }

  const maxCount = Math.max(...[...rowBuckets.values()].map(n => n.length), 1)
  const nodeAreaW = maxCount * NODE_W + (maxCount - 1) * H_GAP
  const svgW = H_PAD + ROW_LABEL_W + nodeAreaW + H_PAD
  const svgH = V_PAD + activeRows.length * ROW_H - (ROW_H - NODE_H) + V_PAD

  // ── Assign pixel positions ───────────────────────────────────────────────
  const activeRowIndex = new Map<number, number>()
  activeRows.forEach((r, idx) => activeRowIndex.set(r, idx))

  const rowTopY = (rowNum: number) =>
    V_PAD + (activeRowIndex.get(rowNum) ?? 0) * ROW_H

  const rowOrders = new Map<number, CallNode[]>()
  for (const [rowNum, nodes] of rowBuckets) {
    const ordered = [...nodes].sort((left, right) => {
      const degreeDiff = (neighbors.get(right.id)?.length ?? 0) - (neighbors.get(left.id)?.length ?? 0)
      if (degreeDiff !== 0) return degreeDiff
      const highlightDiff = Number(!!right.is_call_chain) - Number(!!left.is_call_chain)
      if (highlightDiff !== 0) return highlightDiff
      return left.label.localeCompare(right.label)
    })
    rowOrders.set(rowNum, ordered)
  }

  const indexInRow = (rowNum: number, nodeId: string) =>
    rowOrders.get(rowNum)?.findIndex(node => node.id === nodeId) ?? -1

  const anchorForNode = (rowNum: number, nodeId: string) => {
    const linked = neighbors.get(nodeId) ?? []
    const anchors: number[] = []
    for (const relatedId of linked) {
      const relatedNode = nodeById.get(relatedId)
      if (!relatedNode) continue
      const relatedRow = TYPE_ROW[relatedNode.node_type ?? 'service'] ?? 2
      if (relatedRow === rowNum) continue
      const relatedIndex = indexInRow(relatedRow, relatedId)
      if (relatedIndex >= 0) anchors.push(relatedIndex)
    }
    return anchors.length ? avg(anchors) : null
  }

  for (let pass = 0; pass < 6; pass += 1) {
    for (const rowNum of activeRows) {
      const existing = rowOrders.get(rowNum) ?? []
      rowOrders.set(rowNum, [...existing].sort((left, right) => {
        const leftAnchor = anchorForNode(rowNum, left.id)
        const rightAnchor = anchorForNode(rowNum, right.id)
        if (leftAnchor !== null && rightAnchor !== null && leftAnchor !== rightAnchor) {
          return leftAnchor - rightAnchor
        }
        if (leftAnchor !== null && rightAnchor === null) return -1
        if (leftAnchor === null && rightAnchor !== null) return 1

        const highlightDiff = Number(!!right.is_call_chain) - Number(!!left.is_call_chain)
        if (highlightDiff !== 0) return highlightDiff

        const degreeDiff = (neighbors.get(right.id)?.length ?? 0) - (neighbors.get(left.id)?.length ?? 0)
        if (degreeDiff !== 0) return degreeDiff

        return left.label.localeCompare(right.label)
      }))
    }
  }

  const rowAnchorOffset = (rowNum: number, nodes: CallNode[]) => {
    const rowW = nodes.length * NODE_W + (nodes.length - 1) * H_GAP
    const centeredStart = H_PAD + ROW_LABEL_W + Math.floor((nodeAreaW - rowW) / 2)
    const linkedAnchors = nodes
      .map(node => anchorForNode(rowNum, node.id))
      .filter((value): value is number => value !== null)

    if (!linkedAnchors.length) return centeredStart

    const slotW = NODE_W + H_GAP
    const targetCenter = H_PAD + ROW_LABEL_W + avg(linkedAnchors) * slotW + NODE_W / 2
    const minStart = H_PAD + ROW_LABEL_W
    const maxStart = H_PAD + ROW_LABEL_W + nodeAreaW - rowW
    return Math.max(minStart, Math.min(maxStart, Math.round(targetCenter - rowW / 2)))
  }

  const posMap = new Map<string, { x: number; y: number; row: number }>()
  for (const rowNum of activeRows) {
    const nodes = rowOrders.get(rowNum) ?? []
    const startX = rowAnchorOffset(rowNum, nodes)
    const y = rowTopY(rowNum)
    nodes.forEach((node, i) => {
      posMap.set(node.id, { x: startX + i * (NODE_W + H_GAP), y, row: rowNum })
    })
  }

  // ── Resolve edges ────────────────────────────────────────────────────────
  interface ResolvedEdge {
    d: string; label: string
    style: ReturnType<typeof edgeStyle>
    labelX: number; labelY: number; labelW: number
    isCallChain: boolean
  }
  const resolvedEdges: ResolvedEdge[] = []

  for (const e of graph.edges) {
    const src = posMap.get(e.source)
    const tgt = posMap.get(e.target)
    if (!src || !tgt) continue
    const style = edgeStyle(e)

    let x1: number, y1: number, x2: number, y2: number
    let exitDown: boolean, enterDown: boolean

    if (src.row === tgt.row) {
      x1 = src.x + (src.x < tgt.x ? NODE_W : 0)
      y1 = src.y + NODE_H / 2
      x2 = tgt.x + (src.x < tgt.x ? 0 : NODE_W)
      y2 = tgt.y + NODE_H / 2
      exitDown = false; enterDown = false
    } else if (src.row < tgt.row) {
      x1 = src.x + NODE_W / 2; y1 = src.y + NODE_H
      x2 = tgt.x + NODE_W / 2; y2 = tgt.y
      exitDown = true; enterDown = true
    } else {
      x1 = src.x + NODE_W / 2; y1 = src.y
      x2 = tgt.x + NODE_W / 2; y2 = tgt.y + NODE_H
      exitDown = false; enterDown = false
    }

    const isSameRow = src.row === tgt.row
    const edgeLabel = e.label || e.source || e.target
    const labelX = isSameRow
      ? (x1 + x2) / 2
      : (x1 + x2) / 2 + (src.x < tgt.x ? 10 : -10)
    const labelY = isSameRow
      ? y1 - 26
      : (y1 + y2) / 2 - 6

    resolvedEdges.push({
      d: curvePath(x1, y1, exitDown, x2, y2, enterDown),
      label: edgeLabel,
      style,
      labelX,
      labelY,
      labelW: labelWidth(edgeLabel),
      isCallChain: !!e.is_call_chain,
    })
  }

  // Draw non-call-chain edges first so call-chain edges appear on top
  resolvedEdges.sort((a, b) => Number(a.isCallChain) - Number(b.isCallChain))

  return (
    <div className="bg-white rounded-xl border border-[#e5e7eb] p-4 shadow-[0_1px_5px_rgba(15,23,42,0.06)]">
      <button
        type="button"
        onClick={() => setCollapsed(true)}
        className="mb-3 flex w-full items-center justify-between gap-3 text-left"
        aria-expanded="true"
        title="收起本体层拓扑"
      >
        <span className="flex items-center gap-2 text-xs font-semibold text-[#0e639c]">
          <ChevronDown size={14} />
          <span>&#x1F578; 本体层拓扑</span>
        </span>
        <span className="text-[10px] font-medium text-[#6b7280]">
          {graph.nodes.length} 节点 · {graph.edges.length} 边
        </span>
      </button>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-3 mb-3 text-[10px]">
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-3 rounded-sm border border-[#3b82f6] bg-[#dbeafe]" />
          <span className="text-[#1d4ed8]">入口</span>
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-3 rounded-sm border-2 border-[#ef4444] bg-[#fee2e2]" />
          <span className="text-[#991b1b]">根因</span>
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-3 rounded-sm border border-[#eab308] bg-[#fef9c3]" />
          <span className="text-[#854d0e]">受影响</span>
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-3 rounded-sm border border-[#d1d5db] bg-[#f9fafb]" />
          <span className="text-[#4b5563]">本体节点</span>
        </span>
        {hasStormRoles && (
          <>
            <span className="flex items-center gap-1">
              <span className="inline-block w-3 h-3 rounded-sm border border-[#d97706] bg-[#fef3c7]" />
              <span className="text-[#92400e]">次要</span>
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block w-3 h-3 rounded-sm border border-[#9ca3af] bg-[#f8fafc] opacity-75" />
              <span className="text-[#6b7280]">背景</span>
            </span>
          </>
        )}
      </div>

      {/* Scrollable SVG */}
      <div className="overflow-auto" style={{ maxHeight: 520 }}>
        <div className="min-w-max flex justify-center">
          <svg
            width={svgW}
            height={svgH}
            viewBox={`0 0 ${svgW} ${svgH}`}
            style={{ display: 'block' }}
          >
          <defs>
            <marker id="arr-chain" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
              <polygon points="0 0,7 3.5,0 7" fill="#6b7280" />
            </marker>
            <marker id="arr-dim" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
              <polygon points="0 0,6 3,0 6" fill="#cbd5e1" />
            </marker>
          </defs>

          {/* Row labels */}
          {activeRows.map(rowNum => (
            <text
              key={`lbl-${rowNum}`}
              x={H_PAD + ROW_LABEL_W - 8}
              y={rowTopY(rowNum) + NODE_H / 2 + 4}
              textAnchor="end"
              fontSize="9"
              fill="#9ca3af"
              fontWeight="500"
            >
              {ROW_LABEL[rowNum] ?? ''}
            </text>
          ))}

          {/* Edges */}
          {resolvedEdges.map((e, i) => (
            <g key={`e-${i}`} opacity={e.style.opacity}>
              <path
                d={e.d}
                fill="none"
                stroke={e.style.stroke}
                strokeWidth={e.style.width}
                markerEnd={e.isCallChain ? 'url(#arr-chain)' : 'url(#arr-dim)'}
              />
              {e.label && (
                <g>
                  <rect
                    x={e.labelX - e.labelW / 2}
                    y={e.labelY - 8}
                    width={e.labelW}
                    height={12}
                    rx="4"
                    fill="#ffffff"
                    stroke="#d1d5db"
                    strokeWidth="0.6"
                    opacity="0.97"
                  />
                  <text
                    x={e.labelX}
                    y={e.labelY}
                    textAnchor="middle"
                    fontSize="7.5"
                    fill={e.style.labelFill}
                  >
                    {e.label}
                  </text>
                </g>
              )}
            </g>
          ))}

          {/* Nodes */}
          {graph.nodes.map(node => {
            const pos = posMap.get(node.id)
            if (!pos) return null
            const s = nodeStyle(node, false)
            const disp = formatNodeDisplayLabel(node)
            const roleText = nodeRoleText(node)
            return (
              <g key={node.id} opacity={s.opacity}
                onClick={() => onNodeClick?.(node.id)}
                style={{ cursor: onNodeClick ? 'pointer' : undefined }}
              >
                <title>{roleText ? `${node.label} · ${roleText}` : node.label}</title>
                <rect
                  x={pos.x} y={pos.y}
                  width={NODE_W} height={NODE_H} rx="6"
                  fill={s.fill} stroke={s.stroke} strokeWidth={selectedNodeId === node.id ? 3 : (s as { strokeWidth?: number }).strokeWidth ?? 1.5}
                />
                {/* Selected ring */}
                {selectedNodeId === node.id && (
                  <rect
                    x={pos.x - 2} y={pos.y - 2}
                    width={NODE_W + 4} height={NODE_H + 4} rx="8"
                    fill="none" stroke="#0e639c" strokeWidth="2" opacity="0.7"
                  />
                )}
                <text
                  x={pos.x + NODE_W / 2} y={pos.y + (roleText ? 17 : NODE_H / 2 + 1)}
                  textAnchor="middle" dominantBaseline="middle"
                  fontSize="10" fontWeight="600" fill={s.text}
                >
                  {disp}
                </text>
                {roleText && (
                  <text
                    x={pos.x + NODE_W / 2} y={pos.y + 31}
                    textAnchor="middle" dominantBaseline="middle"
                    fontSize="8" fontWeight="500" fill={s.text}
                  >
                    {roleText}
                  </text>
                )}
              </g>
            )
          })}
          </svg>
        </div>
      </div>

    </div>
  )
}
