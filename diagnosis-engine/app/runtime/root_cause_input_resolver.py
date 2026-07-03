"""
Object-centered root cause input resolver.

Priority order:
1. DCC candidates.root_cause  — pre-computed by UnifiedModel / upstream runtime
2. DCC objects.topology entry_points / candidate_paths  — topology-inferred
3. Evidence-based with DCC context — DCC present but no explicit candidates or topo hints
4. Pure evidence-based — no DCC, legacy trace/log/metric construction

Resolver output is consumed by RootCauseSkill to replace or supplement _collect_candidates().
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.context import DiagnosisContext


@dataclass
class RootCauseInputResolution:
    """Resolved root-cause candidate context from DCC or evidence sources."""

    candidates: list[dict] = field(default_factory=list)
    """Normalized candidate list ready for _score_candidates()."""

    entry_entity: str = ""
    """Hint entity (api / service) from DCC alert, used for api fallback."""

    topology_context: dict = field(default_factory=dict)
    """Raw topology sub-dict from DCC objects.topology (nodes, edges, entry_points, ...)."""

    entity_context: list[dict] = field(default_factory=list)
    """Entity objects from DCC objects.entities."""

    candidate_source: str = "evidence_based"
    """Where candidates came from. Values:
      dcc_candidates          — DCC candidates.root_cause used directly
      topology_inferred       — inferred from DCC topology entry_points / candidate_paths
      evidence_based_with_dcc_context — DCC present but no candidates / topo hints
      evidence_based          — no DCC; pure trace/log/metric construction
    """

    dcc_used: bool = False
    """True when DCC context was found and influenced candidate resolution."""

    warnings: list[str] = field(default_factory=list)
    """Non-fatal advisory messages logged to execution_log."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize_dcc_candidate(item: dict, entry_api: str) -> dict:
    """Normalize one DCC candidates.root_cause item to the internal candidate format."""
    service = (
        item.get("service")
        or item.get("entity_name")
        or item.get("entity_id")
        or item.get("root_cause_service")
        or ""
    )
    score = float(item.get("confidence") or item.get("score") or 0.85)
    root_type = (
        item.get("type")
        or item.get("root_cause_type")
        or item.get("entity_type")
        or "service_exception"
    )
    # Avoid bare entity types like "service" being used as root_cause_type
    if root_type in {"service", "Service", "microservice"}:
        root_type = "service_exception"
    reason = (
        item.get("reason")
        or item.get("evidence")
        or item.get("message")
        or f"DCC candidate: {service}"
    )
    return {
        "service": str(service),
        "component": item.get("component") or item.get("container") or str(service),
        "api": item.get("api") or item.get("root_cause_api") or entry_api,
        "type": root_type,
        "exception_type": item.get("exception_type"),
        "score": min(0.99, max(0.0, score)),
        "source": "dcc_candidate",
        "sources": ["dcc_candidate"],
        "evidence": [reason],
        "is_propagation": bool(item.get("is_propagation", False)),
        "_candidate_origin": "dcc_candidates",
    }


def _infer_candidates_from_topology(
    topology: dict, entry_api: str
) -> list[dict]:
    """Infer candidate list from DCC topology entry_points and candidate_paths.

    Returns an empty list when no useful topology hints are found.
    """
    candidates: list[dict] = []

    # entry_points: explicit anomaly / propagation entry nodes
    for ep in (topology.get("entry_points") or []):
        if not isinstance(ep, dict):
            continue
        node_id = ep.get("entity_id") or ep.get("id") or ep.get("service") or ""
        if not node_id:
            continue
        candidates.append(
            {
                "service": str(node_id),
                "component": str(node_id),
                "api": entry_api,
                "type": "service_exception",
                "exception_type": None,
                "score": 0.45,
                "source": "dcc_topology",
                "sources": ["dcc_topology"],
                "evidence": [f"DCC topology entry_point: {node_id}"],
                "is_propagation": False,
                "_candidate_origin": "topology_inferred",
            }
        )

    # candidate_paths: propagation paths where the terminal node is likely root
    for path in (topology.get("candidate_paths") or []):
        if not isinstance(path, (dict, list)):
            continue
        # Support both {nodes: [...]} and flat list formats
        nodes_in_path = path.get("nodes") if isinstance(path, dict) else path
        if not nodes_in_path:
            continue
        last = nodes_in_path[-1]
        node_id = (
            last
            if isinstance(last, str)
            else (last.get("entity_id") or last.get("id") or last.get("service") or "")
        )
        if not node_id:
            continue
        # Avoid duplicating an entry_point already added
        if any(c["service"] == str(node_id) for c in candidates):
            continue
        candidates.append(
            {
                "service": str(node_id),
                "component": str(node_id),
                "api": entry_api,
                "type": "service_exception",
                "exception_type": None,
                "score": 0.40,
                "source": "dcc_topology",
                "sources": ["dcc_topology"],
                "evidence": [f"DCC topology candidate_path terminal: {node_id}"],
                "is_propagation": False,
                "_candidate_origin": "topology_inferred",
            }
        )

    return candidates


# ---------------------------------------------------------------------------
# Public resolver
# ---------------------------------------------------------------------------

def resolve_root_cause_input(ctx: "DiagnosisContext") -> RootCauseInputResolution:
    """Resolve object-level candidate context using priority order.

    Priority:
    1. DCC candidates.root_cause (pre-computed by UnifiedModel)
    2. DCC topology entry_points / candidate_paths (topology-inferred)
    3. DCC present but no explicit candidate hints (evidence_based_with_dcc_context)
    4. No DCC — pure evidence-based from trace/log/metric outputs
    """
    dcc: dict | None = None
    raw_dcc = getattr(ctx, "dcc_context", None)
    if isinstance(raw_dcc, dict) and raw_dcc:
        dcc = raw_dcc

    if dcc is None:
        return RootCauseInputResolution(
            candidates=[],
            candidate_source="evidence_based",
            dcc_used=False,
        )

    warnings: list[str] = []

    # Extract structural context
    objects: dict = dcc.get("objects") or {}
    topology: dict = objects.get("topology") or {}
    entity_context = [e for e in (objects.get("entities") or []) if isinstance(e, dict)]
    alert: dict = dcc.get("alert") or {}
    entry_api = alert.get("api") or ""

    # ── Priority 1: DCC explicit candidates ──────────────────────────────────
    dcc_candidates_raw = (dcc.get("candidates") or {}).get("root_cause") or []
    dcc_candidates_raw = [c for c in dcc_candidates_raw if isinstance(c, dict)]

    if dcc_candidates_raw:
        normalizable = [
            _normalize_dcc_candidate(c, entry_api)
            for c in dcc_candidates_raw
            if (c.get("service") or c.get("entity_name") or c.get("entity_id"))
        ]
        if normalizable:
            return RootCauseInputResolution(
                candidates=normalizable,
                entry_entity=entry_api,
                topology_context=topology,
                entity_context=entity_context,
                candidate_source="dcc_candidates",
                dcc_used=True,
                warnings=warnings,
            )
        warnings.append(
            "[RCInputResolver] DCC candidates.root_cause present but no items had "
            "normalizable service/entity_name/entity_id; falling through to topology"
        )

    # ── Priority 2: DCC topology-inferred ────────────────────────────────────
    topo_candidates = _infer_candidates_from_topology(topology, entry_api)
    if topo_candidates:
        return RootCauseInputResolution(
            candidates=topo_candidates,
            entry_entity=entry_api,
            topology_context=topology,
            entity_context=entity_context,
            candidate_source="topology_inferred",
            dcc_used=True,
            warnings=warnings,
        )

    # ── Priority 3: DCC present but no explicit candidates or topology hints ──
    if topology or entity_context:
        warnings.append(
            "[RCInputResolver] DCC present but no explicit candidates or topology hints; "
            "using evidence-based construction enriched with DCC entity/topology context"
        )
        return RootCauseInputResolution(
            candidates=[],
            entry_entity=entry_api,
            topology_context=topology,
            entity_context=entity_context,
            candidate_source="evidence_based_with_dcc_context",
            dcc_used=True,
            warnings=warnings,
        )

    # ── Priority 4: DCC present but empty shell ───────────────────────────────
    warnings.append(
        "[RCInputResolver] DCC present but missing candidates, topology, and entity context; "
        "falling through to pure evidence-based construction"
    )
    return RootCauseInputResolution(
        candidates=[],
        entry_entity=entry_api,
        topology_context={},
        entity_context=[],
        candidate_source="evidence_based",
        dcc_used=False,
        warnings=warnings,
    )
