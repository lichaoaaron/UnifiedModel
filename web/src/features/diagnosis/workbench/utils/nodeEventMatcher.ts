import type { CallNode, CallGraph, EventStreamItem } from '../types/diagnosis'

/**
 * Resolve a text label to a topology node ID using the call graph.
 * Returns the matching node ID or null.
 */
export function resolveNodeLabelToId(label: string, graph: CallGraph | null | undefined): string | null {
  if (!graph || !label) return null
  const l = label.toLowerCase()
  // Exact match on id or label
  for (const n of graph.nodes) {
    if (n.id.toLowerCase() === l || n.label.toLowerCase() === l) return n.id
  }
  // Contains match
  for (const n of graph.nodes) {
    if (n.label.toLowerCase().includes(l) || l.includes(n.label.toLowerCase())) return n.id
  }
  return null
}

/**
 * Enrich event related_nodes by cross-referencing label strings with call_graph node IDs.
 * Only keeps entries that can be resolved to actual topology nodes.
 */
export function enrichRelatedNodesWithIds(
  relatedNodes: string[] | undefined,
  graph: CallGraph | null | undefined
): string[] {
  if (!relatedNodes?.length) return []
  // When graph is not yet available, keep original labels as-is for display
  if (!graph) return relatedNodes.slice(0, 8)
  const resolved: string[] = []
  const seen = new Set<string>()
  for (const label of relatedNodes) {
    const nodeId = resolveNodeLabelToId(label, graph)
    if (nodeId && !seen.has(nodeId.toLowerCase())) {
      seen.add(nodeId.toLowerCase())
      resolved.push(nodeId)
    }
  }
  return resolved
}

/**
 * Match a topology node to the most relevant event stream item.
 * Returns the event ID or null if no match.
 *
 * Priority:
 * 1. event.related_nodes contains nodeId
 * 2. Role-based matching (entry → object_selection, root_cause → root_cause_decision, etc.)
 * 3. Text fallback: node label appears in event title/summary
 *
 * Falls back to first event of matching kind if no exact match.
 */
export function matchNodeToEvent(nodeId: string, node: CallNode, events: EventStreamItem[]): string | null {
  if (!events.length) return null

  const nodeLabel = (node.label || node.id).toLowerCase()

  // 1. Direct related_nodes match — exact entity_id match first
  for (const evt of events) {
    if (!evt.related_nodes?.length) continue
    if (evt.related_nodes.includes(nodeId)) return evt.id
    // Fuzzy: related_nodes entry contains the node label
    for (const rn of evt.related_nodes) {
      if (rn.toLowerCase().includes(nodeLabel) || nodeLabel.includes(rn.toLowerCase())) {
        return evt.id
      }
    }
  }

  // 2. Match via evidence_refs in details
  for (const evt of events) {
    if (evt.evidence_refs?.includes(nodeId)) return evt.id
  }

  // 3. Match via details evidence/explanation — search for node label in evidence strings
  for (const evt of events) {
    const evd = evt.details?.evidence
    if (evd) {
      for (const line of evd) {
        if (line.toLowerCase().includes(nodeLabel)) return evt.id
      }
    }
    if (evt.details?.explanation?.toLowerCase().includes(nodeLabel)) return evt.id
  }

  // 4. Text fallback in title/summary
  for (const evt of events) {
    if (evt.title?.toLowerCase().includes(nodeLabel) ||
        evt.summary?.toLowerCase().includes(nodeLabel)) {
      return evt.id
    }
  }

  // 5. Role + node_type based fallback (type-aware, not generic)
  const role = resolveNodeRole(node)
  const nodeType = (node.node_type ?? 'service').toLowerCase()
  const typeKindMap = typeToPreferredKinds(nodeType, role)

  for (const kind of typeKindMap) {
    const match = events.find(e => e.kind === kind)
    if (match) return match.id
  }

  // 6. Final graceful fallback — only for root/entry, not generic object_selection
  if (role === 'confirmed_root' || role === 'candidate_root' || role === 'common_root') {
    return events.find(e => e.kind === 'root_cause_decision')?.id ??
           events.find(e => e.kind === 'evidence_confirmation')?.id ?? null
  }
  if (role === 'entry') {
    return events.find(e => e.kind === 'object_selection')?.id ??
           events.find(e => e.kind === 'evidence_confirmation')?.id ?? null
  }
  if (role === 'propagated' || role === 'propagated_impact' ||
      role === 'direct_impact' || role === 'indirect_impact') {
    return events.find(e => e.kind === 'impact_scope_decision')?.id ?? null
  }

  return null
}

/** Type-aware preferred event kinds: combines node_type + role for precision. */
function typeToPreferredKinds(nodeType: string, role: string): EventStreamItem['kind'][] {
  // Root cause nodes → specific evidence that found them
  if (role === 'confirmed_root' || role === 'candidate_root' || role === 'common_root') {
    if (nodeType === 'dependency' || nodeType === 'Dependency') return ['evidence_confirmation', 'root_cause_decision']
    if (nodeType === 'instance' || nodeType === 'Instance') return ['evidence_confirmation', 'root_cause_decision']
    return ['root_cause_decision', 'evidence_confirmation']
  }
  // Entry point nodes
  if (role === 'entry') {
    if (nodeType === 'interface' || nodeType === 'Interface') return ['evidence_confirmation', 'object_selection']
    return ['object_selection', 'evidence_confirmation']
  }
  // Propagated / impacted nodes
  if (role === 'propagated' || role === 'propagated_impact' ||
      role === 'direct_impact' || role === 'indirect_impact') {
    return ['impact_scope_decision']
  }
  // Observed noise nodes
  if (role === 'observed' || role === 'noise') {
    return ['impact_scope_decision', 'object_selection']
  }
  // Type-based fallback for normal nodes
  if (nodeType === 'service' || nodeType === 'Service') return ['object_selection', 'evidence_confirmation', 'impact_scope_decision']
  if (nodeType === 'interface' || nodeType === 'Interface') return ['evidence_confirmation', 'root_cause_decision']
  if (nodeType === 'dependency' || nodeType === 'Dependency') return ['evidence_confirmation', 'root_cause_decision']
  if (nodeType === 'instance' || nodeType === 'Instance') return ['evidence_confirmation', 'object_selection']
  return ['object_selection', 'evidence_confirmation', 'root_cause_decision']
}

function resolveNodeRole(node: CallNode): string {
  if (node.visual_role) return node.visual_role
  if (node.storm_role) return node.storm_role
  if (node.is_root_cause) return 'confirmed_root'
  if (node.is_entry) return 'entry'
  return 'normal'
}
