"""
Object-centered impact input resolver.

Priority order:
1. DCC candidates.impact_scope  — pre-computed by UnifiedModel / upstream runtime
2. DCC objects.topology + confirmed root cause  — topology-propagation inferred
3. Evidence-based with DCC entity context — DCC present but no explicit candidates/topology
4. Pure evidence-based — no DCC; graph adjacency + trace construction

Key node_type classification semantics:
  root_cause_node          — the confirmed root cause service / entity
  propagation_node         — intermediate node on propagation path (between entry and root cause)
  directly_affected_node   — node that directly calls root cause (receives failure upstream)
  indirectly_affected_node — node further up the call chain from directly_affected
  merely_observed_node     — appeared in trace/evidence but no topological impact path confirmed

Resolver output consumed by ImpactAnalysisSkill to replace or constrain affected_services
construction and to populate node_classifications metadata.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.context import DiagnosisContext


# ---------------------------------------------------------------------------
# Data contract
# ---------------------------------------------------------------------------

@dataclass
class ImpactInputResolution:
    """Resolved impact candidate context, ready for ImpactAnalysisSkill consumption."""

    impact_candidates: list[dict] = field(default_factory=list)
    """Normalized candidate list with node_type classification.
    Format:
      {service, entity_id, node_type, confidence, source, reason, _candidate_origin}
    """

    root_cause_service: str = ""
    """Root cause service resolved from ctx.root_cause_result or DCC alert."""

    entry_api: str = ""
    """Entry API from DCC alert or ctx.api."""

    topology_context: dict = field(default_factory=dict)
    """Raw topology sub-dict from DCC objects.topology."""

    entity_context: list[dict] = field(default_factory=list)
    """Entity objects from DCC objects.entities."""

    candidate_source: str = "evidence_based"
    """Indicates which priority path was used. Values:
      dcc_impact_candidates          — DCC candidates.impact_scope used directly
      topology_propagation           — inferred from DCC topology + confirmed root cause
      evidence_based_with_dcc_context — DCC present but no impact candidates / topology
      evidence_based                 — no DCC; pure graph / trace construction
    """

    dcc_used: bool = False
    """True when DCC context was found and influenced candidate resolution."""

    warnings: list[str] = field(default_factory=list)
    """Non-fatal advisory messages, intended for execution_log."""


# ---------------------------------------------------------------------------
# Node type helpers
# ---------------------------------------------------------------------------

_VALID_NODE_TYPES = {
    "root_cause_node",
    "propagation_node",
    "directly_affected_node",
    "indirectly_affected_node",
    "merely_observed_node",
}

_NODE_TYPE_ALIASES = {
    # root cause
    "root_cause": "root_cause_node",
    "root": "root_cause_node",
    "fault_source": "root_cause_node",
    "fault": "root_cause_node",
    # propagation
    "propagation": "propagation_node",
    "propagated": "propagation_node",
    "intermediate": "propagation_node",
    # directly affected
    "directly_affected": "directly_affected_node",
    "direct": "directly_affected_node",
    "caller": "directly_affected_node",
    "upstream": "directly_affected_node",
    "impacted": "directly_affected_node",
    # indirectly affected
    "indirectly_affected": "indirectly_affected_node",
    "indirect": "indirectly_affected_node",
    "secondary": "indirectly_affected_node",
    # merely observed
    "observed": "merely_observed_node",
    "seen": "merely_observed_node",
    "trace_only": "merely_observed_node",
    "unsupported": "merely_observed_node",
    "no_evidence": "merely_observed_node",
}


def _normalize_node_type(raw: str) -> str:
    """Normalize raw impact node type string to canonical value."""
    token = (raw or "").lower().strip().replace("-", "_").replace(" ", "_")
    if token in _VALID_NODE_TYPES:
        return token
    return _NODE_TYPE_ALIASES.get(token, "directly_affected_node")


# ---------------------------------------------------------------------------
# Edge extraction helpers
# ---------------------------------------------------------------------------

def _edge_src(e: dict) -> str:
    return e.get("source") or e.get("source_service") or ""


def _edge_tgt(e: dict) -> str:
    return e.get("target") or e.get("target_service") or ""


# ---------------------------------------------------------------------------
# Priority 1: Normalize DCC impact_scope candidates
# ---------------------------------------------------------------------------

def _normalize_dcc_impact_candidate(item: dict) -> dict:
    """Normalize one DCC candidates.impact_scope item to the internal format."""
    service = (
        item.get("service")
        or item.get("entity_name")
        or item.get("entity_id")
        or ""
    )
    node_type = _normalize_node_type(
        item.get("node_type") or item.get("impact_type") or item.get("type") or ""
    )
    confidence = float(item.get("confidence") or item.get("score") or 0.70)
    reason = (
        item.get("reason")
        or item.get("evidence")
        or item.get("message")
        or f"DCC impact candidate: {service}"
    )
    return {
        "service": str(service),
        "entity_id": item.get("entity_id") or str(service),
        "node_type": node_type,
        "confidence": min(0.99, max(0.0, confidence)),
        "source": "dcc_impact_candidates",
        "reason": reason,
        "_candidate_origin": "dcc_impact_candidates",
    }


# ---------------------------------------------------------------------------
# Priority 2: Topology-propagation inference
# ---------------------------------------------------------------------------

def _infer_from_topology(
    topology: dict, root_cause_service: str, entry_api: str
) -> list[dict]:
    """Infer classified impact candidates from DCC topology edges and confirmed root cause.

    Traversal direction: edges represent "A calls B" (source → target).
    - directly_affected_node: services whose target == root_cause (direct callers)
    - indirectly_affected_node: callers of directly_affected services
    - root_cause_node: root_cause_service itself
    """
    candidates: list[dict] = []
    if not root_cause_service:
        return candidates

    edges = [e for e in (topology.get("edges") or []) if isinstance(e, dict)]

    # Root cause node
    candidates.append({
        "service": root_cause_service,
        "entity_id": root_cause_service,
        "node_type": "root_cause_node",
        "confidence": 0.95,
        "source": "topology_propagation",
        "reason": f"Confirmed root cause service: {root_cause_service}",
        "_candidate_origin": "topology_inferred",
    })

    # Direct callers (services that call root_cause → directly_affected)
    direct_callers = {
        _edge_src(e)
        for e in edges
        if _edge_tgt(e) == root_cause_service
        and _edge_src(e)
        and _edge_src(e) != root_cause_service
    }
    for svc in sorted(direct_callers):
        candidates.append({
            "service": svc,
            "entity_id": svc,
            "node_type": "directly_affected_node",
            "confidence": 0.80,
            "source": "topology_propagation",
            "reason": f"Direct caller of root cause {root_cause_service}",
            "_candidate_origin": "topology_inferred",
        })

    # Indirect callers (callers of direct_callers → indirectly_affected)
    indirect_callers = {
        _edge_src(e)
        for e in edges
        if _edge_tgt(e) in direct_callers
        and _edge_src(e)
        and _edge_src(e) not in direct_callers
        and _edge_src(e) != root_cause_service
    }
    for svc in sorted(indirect_callers):
        candidates.append({
            "service": svc,
            "entity_id": svc,
            "node_type": "indirectly_affected_node",
            "confidence": 0.55,
            "source": "topology_propagation",
            "reason": (
                f"Indirect caller via directly_affected: {sorted(direct_callers)}"
            ),
            "_candidate_origin": "topology_inferred",
        })

    return candidates


# ---------------------------------------------------------------------------
# Priority 3 / 4: Evidence-based graph classification
# ---------------------------------------------------------------------------

def _classify_services_from_graph(
    root_cause_service: str, graph_result: dict
) -> list[dict]:
    """Classify impact candidates using graph adjacency.

    Used for evidence-based paths (Priority 3 / 4) to provide node_type
    metadata even when DCC is absent or lacks explicit candidates.

    Services in the graph but not reachable from root_cause are marked
    'merely_observed_node' — they appeared in evidence but have no
    confirmed topological impact path.
    """
    edges = [
        e for e in (
            graph_result.get("call_edges")
            or graph_result.get("edges")
            or []
        )
        if isinstance(e, dict)
    ]
    nodes_raw = graph_result.get("nodes") or []

    # Collect all services mentioned in graph
    all_services: set[str] = set()
    for e in edges:
        s, t = _edge_src(e), _edge_tgt(e)
        if s:
            all_services.add(s)
        if t:
            all_services.add(t)
    for n in nodes_raw:
        if isinstance(n, dict):
            nid = n.get("id") or n.get("service") or ""
            if nid:
                all_services.add(nid)

    candidates: list[dict] = []

    if not root_cause_service:
        # No root cause known — label all as directly_affected (conservative)
        for svc in sorted(all_services):
            candidates.append({
                "service": svc,
                "entity_id": svc,
                "node_type": "directly_affected_node",
                "confidence": 0.40,
                "source": "legacy_call_chain",
                "reason": "Root cause unknown; service present in call graph",
                "_candidate_origin": "evidence_based",
            })
        return candidates

    # Root cause node
    if root_cause_service in all_services:
        candidates.append({
            "service": root_cause_service,
            "entity_id": root_cause_service,
            "node_type": "root_cause_node",
            "confidence": 0.90,
            "source": "root_cause_adjacency",
            "reason": "Identified root cause service",
            "_candidate_origin": "evidence_based",
        })

    # Direct callers of root_cause
    direct_callers = {
        _edge_src(e)
        for e in edges
        if _edge_tgt(e) == root_cause_service
        and _edge_src(e)
        and _edge_src(e) != root_cause_service
    }

    # Callers of direct callers (indirect)
    indirect_callers = {
        _edge_src(e)
        for e in edges
        if _edge_tgt(e) in direct_callers
        and _edge_src(e)
        and _edge_src(e) not in direct_callers
        and _edge_src(e) != root_cause_service
    }

    classified = {root_cause_service} | direct_callers | indirect_callers

    for svc in sorted(direct_callers):
        candidates.append({
            "service": svc,
            "entity_id": svc,
            "node_type": "directly_affected_node",
            "confidence": 0.75,
            "source": "root_cause_adjacency",
            "reason": f"Direct caller of root cause {root_cause_service} (from call graph)",
            "_candidate_origin": "evidence_based",
        })

    for svc in sorted(indirect_callers):
        candidates.append({
            "service": svc,
            "entity_id": svc,
            "node_type": "indirectly_affected_node",
            "confidence": 0.50,
            "source": "root_cause_adjacency",
            "reason": f"Caller of directly_affected: present in call graph upstream",
            "_candidate_origin": "evidence_based",
        })

    # Merely observed: in graph but not in propagation path
    for svc in sorted(all_services - classified):
        candidates.append({
            "service": svc,
            "entity_id": svc,
            "node_type": "merely_observed_node",
            "confidence": 0.25,
            "source": "trace_evidence",
            "reason": (
                "Appeared in call graph but no confirmed topological path to root cause"
            ),
            "_candidate_origin": "evidence_based",
        })

    return candidates


# ---------------------------------------------------------------------------
# Public resolver
# ---------------------------------------------------------------------------

def resolve_impact_input(ctx: "DiagnosisContext") -> ImpactInputResolution:
    """Resolve object-level impact candidate context using priority order.

    Priority:
    1. DCC candidates.impact_scope (pre-computed by UnifiedModel)
    2. DCC topology + confirmed root cause (topology-propagation)
    3. DCC entity context + graph classification (evidence_based_with_dcc_context)
    4. No DCC — pure graph / trace classification (evidence_based)

    Returns ImpactInputResolution with impact_candidates always classified
    by node_type, and candidate_source indicating which path was used.
    """
    dcc: dict | None = None
    raw_dcc = getattr(ctx, "dcc_context", None)
    if isinstance(raw_dcc, dict) and raw_dcc:
        dcc = raw_dcc

    root_cause_service: str = (getattr(ctx, "root_cause_result", None) or {}).get(
        "root_cause_service"
    ) or ""
    graph_result: dict = getattr(ctx, "graph_result", None) or {}

    if dcc is None:
        # ── Priority 4: No DCC ────────────────────────────────────────────────
        candidates = _classify_services_from_graph(root_cause_service, graph_result)
        return ImpactInputResolution(
            impact_candidates=candidates,
            root_cause_service=root_cause_service,
            entry_api=getattr(ctx, "api", "") or "",
            candidate_source="evidence_based",
            dcc_used=False,
        )

    warnings: list[str] = []

    # Extract structural context from DCC
    objects: dict = dcc.get("objects") or {}
    topology: dict = objects.get("topology") or {}
    entity_context = [e for e in (objects.get("entities") or []) if isinstance(e, dict)]
    alert: dict = dcc.get("alert") or {}
    entry_api = alert.get("api") or getattr(ctx, "api", "") or ""

    # ── Priority 1: DCC explicit impact_scope candidates ─────────────────────
    impact_raw = (dcc.get("candidates") or {}).get("impact_scope") or []
    impact_raw = [c for c in impact_raw if isinstance(c, dict)]

    if impact_raw:
        normalizable = [
            _normalize_dcc_impact_candidate(c)
            for c in impact_raw
            if (c.get("service") or c.get("entity_name") or c.get("entity_id"))
        ]
        if normalizable:
            return ImpactInputResolution(
                impact_candidates=normalizable,
                root_cause_service=root_cause_service,
                entry_api=entry_api,
                topology_context=topology,
                entity_context=entity_context,
                candidate_source="dcc_impact_candidates",
                dcc_used=True,
                warnings=warnings,
            )
        warnings.append(
            "[ImpactInputResolver] DCC candidates.impact_scope present but no items had "
            "normalizable service/entity_name/entity_id; falling through to topology"
        )

    # ── Priority 2: DCC topology propagation ─────────────────────────────────
    topo_edges = [e for e in (topology.get("edges") or []) if isinstance(e, dict)]
    if topo_edges and root_cause_service:
        topo_candidates = _infer_from_topology(topology, root_cause_service, entry_api)
        if topo_candidates:
            return ImpactInputResolution(
                impact_candidates=topo_candidates,
                root_cause_service=root_cause_service,
                entry_api=entry_api,
                topology_context=topology,
                entity_context=entity_context,
                candidate_source="topology_propagation",
                dcc_used=True,
                warnings=warnings,
            )

    # ── Priority 3: DCC context but no explicit impact candidates/topology ────
    graph_candidates = _classify_services_from_graph(root_cause_service, graph_result)
    if topology or entity_context:
        # Constrain by DCC entity set when available: services outside DCC entity
        # context are downgraded to merely_observed
        known_entity_ids: set[str] = set()
        for ent in entity_context:
            eid = ent.get("id") or ent.get("entity_name") or ent.get("entity_id") or ""
            if eid:
                known_entity_ids.add(eid)
        if known_entity_ids:
            for c in graph_candidates:
                if (
                    c.get("node_type") != "root_cause_node"
                    and c.get("service") not in known_entity_ids
                ):
                    c["node_type"] = "merely_observed_node"
                    c["reason"] += " [not in DCC entity context]"
                    c["confidence"] = min(c.get("confidence", 0.3), 0.30)
        warnings.append(
            "[ImpactInputResolver] DCC present but no explicit impact_scope or topology edges; "
            "using graph classification enriched with DCC entity context"
        )
        return ImpactInputResolution(
            impact_candidates=graph_candidates,
            root_cause_service=root_cause_service,
            entry_api=entry_api,
            topology_context=topology,
            entity_context=entity_context,
            candidate_source="evidence_based_with_dcc_context",
            dcc_used=True,
            warnings=warnings,
        )

    # ── Priority 4 (DCC present but empty shell) ─────────────────────────────
    warnings.append(
        "[ImpactInputResolver] DCC present but missing impact_scope, topology, and entity "
        "context; falling through to pure evidence-based construction"
    )
    return ImpactInputResolution(
        impact_candidates=graph_candidates,
        root_cause_service=root_cause_service,
        entry_api=entry_api,
        topology_context={},
        entity_context=[],
        candidate_source="evidence_based",
        dcc_used=False,
        warnings=warnings,
    )
