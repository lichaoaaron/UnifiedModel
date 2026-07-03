"""
Tests for Step 8: Impact DCC-first (object-centered) input resolution.

Coverage:
  - ImpactInputResolution resolver: all four priority paths
  - Node type normalization helpers
  - Topology-propagation traversal
  - Evidence-based graph classification
  - ImpactAnalysisSkill.run(): DCC candidates / topology / legacy paths
  - Anti-overfitting: trace-observed-only nodes NOT marked as directly_affected
  - Backward compatibility: no-DCC legacy path unbroken
"""
import pytest
from unittest.mock import MagicMock, patch

from app.models.context import DiagnosisContext
from app.runtime.impact_input_resolver import (
    ImpactInputResolution,
    resolve_impact_input,
    _normalize_node_type,
    _normalize_dcc_impact_candidate,
    _infer_from_topology,
    _classify_services_from_graph,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_ctx(**kwargs) -> DiagnosisContext:
    ctx = DiagnosisContext(
        api=kwargs.get("api", "/api/checkout"),
        symptom=kwargs.get("symptom", "checkout timeout"),
        time="2024-01-01T10:00:00Z",
    )
    ctx.dcc_context = kwargs.get("dcc_context", {})
    ctx.trace_result = kwargs.get("trace_result", {})
    ctx.log_result = kwargs.get("log_result", {})
    ctx.metric_result = kwargs.get("metric_result", {})
    ctx.graph_result = kwargs.get("graph_result", {})
    ctx.root_cause_result = kwargs.get("root_cause_result", {})
    return ctx


def _full_dcc(extra: dict | None = None) -> dict:
    """Minimal valid DCC v0.1 payload."""
    base = {
        "protocol_version": "dcc-v0.1",
        "generated_at": "2024-01-01T10:00:00Z",
        "workspace": "demo",
        "alert": {
            "id": "alert-001",
            "symptom": "checkout timeout",
            "api": "/api/checkout",
            "alert_time": "2024-01-01T10:00:00Z",
            "severity": "critical",
        },
        "objects": {
            "entities": [],
            "relations": [],
            "topology": {"nodes": [], "edges": [], "entry_points": [], "candidate_paths": []},
        },
        "evidence": {
            "trace": {"availability": "none", "spans": []},
            "log": {"availability": "none", "records": []},
            "metric": {"availability": "none", "series": []},
        },
        "candidates": {
            "root_cause": [],
            "impact_scope": [],
        },
        "provenance": [],
        "meta": {},
    }
    if extra:
        for k, v in extra.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                base[k].update(v)
            else:
                base[k] = v
    return base


_SIMPLE_TOPO_EDGES = [
    {"source": "frontend-svc", "target": "order-svc", "label": "calls"},
    {"source": "order-svc", "target": "payment-svc", "label": "calls"},
]


# ---------------------------------------------------------------------------
# Unit tests: _normalize_node_type
# ---------------------------------------------------------------------------

class TestNormalizeNodeType:
    def test_valid_types_pass_through(self):
        for t in ["root_cause_node", "propagation_node", "directly_affected_node",
                  "indirectly_affected_node", "merely_observed_node"]:
            assert _normalize_node_type(t) == t

    def test_aliases_mapped_correctly(self):
        assert _normalize_node_type("root_cause") == "root_cause_node"
        assert _normalize_node_type("caller") == "directly_affected_node"
        assert _normalize_node_type("indirect") == "indirectly_affected_node"
        assert _normalize_node_type("observed") == "merely_observed_node"
        assert _normalize_node_type("propagation") == "propagation_node"

    def test_unknown_defaults_to_directly_affected(self):
        assert _normalize_node_type("something_unknown") == "directly_affected_node"

    def test_empty_defaults_to_directly_affected(self):
        assert _normalize_node_type("") == "directly_affected_node"


# ---------------------------------------------------------------------------
# Unit tests: _normalize_dcc_impact_candidate
# ---------------------------------------------------------------------------

class TestNormalizeDccImpactCandidate:
    def test_service_field_used(self):
        c = _normalize_dcc_impact_candidate({"service": "order-svc", "confidence": 0.8})
        assert c["service"] == "order-svc"
        assert c["confidence"] == 0.8
        assert c["_candidate_origin"] == "dcc_impact_candidates"

    def test_entity_name_fallback(self):
        c = _normalize_dcc_impact_candidate({"entity_name": "payment-svc"})
        assert c["service"] == "payment-svc"

    def test_node_type_normalized(self):
        c = _normalize_dcc_impact_candidate({"service": "svc", "node_type": "caller"})
        assert c["node_type"] == "directly_affected_node"

    def test_default_confidence(self):
        c = _normalize_dcc_impact_candidate({"service": "svc"})
        assert c["confidence"] == 0.70

    def test_score_capped_at_0_99(self):
        c = _normalize_dcc_impact_candidate({"service": "svc", "confidence": 1.5})
        assert c["confidence"] == 0.99


# ---------------------------------------------------------------------------
# Unit tests: _infer_from_topology
# ---------------------------------------------------------------------------

class TestInferFromTopology:
    def test_root_cause_node_always_included(self):
        topology = {"edges": _SIMPLE_TOPO_EDGES}
        result = _infer_from_topology(topology, "payment-svc", "/checkout")
        types = {c["service"]: c["node_type"] for c in result}
        assert types["payment-svc"] == "root_cause_node"

    def test_direct_callers_classified(self):
        topology = {"edges": _SIMPLE_TOPO_EDGES}
        result = _infer_from_topology(topology, "payment-svc", "/checkout")
        types = {c["service"]: c["node_type"] for c in result}
        assert types["order-svc"] == "directly_affected_node"

    def test_indirect_callers_classified(self):
        topology = {"edges": _SIMPLE_TOPO_EDGES}
        result = _infer_from_topology(topology, "payment-svc", "/checkout")
        types = {c["service"]: c["node_type"] for c in result}
        assert types["frontend-svc"] == "indirectly_affected_node"

    def test_no_root_cause_returns_empty(self):
        topology = {"edges": _SIMPLE_TOPO_EDGES}
        result = _infer_from_topology(topology, "", "/checkout")
        assert result == []

    def test_isolated_node_not_in_results(self):
        """A service that has no edge to root cause should NOT appear."""
        topo = {"edges": [{"source": "unrelated-svc", "target": "other-svc"}]}
        result = _infer_from_topology(topo, "payment-svc", "")
        services = [c["service"] for c in result]
        assert "unrelated-svc" not in services
        assert "other-svc" not in services


# ---------------------------------------------------------------------------
# Unit tests: _classify_services_from_graph
# ---------------------------------------------------------------------------

class TestClassifyServicesFromGraph:
    def test_root_cause_node_classified(self):
        graph = {"call_edges": _SIMPLE_TOPO_EDGES}
        result = _classify_services_from_graph("payment-svc", graph)
        types = {c["service"]: c["node_type"] for c in result}
        assert types["payment-svc"] == "root_cause_node"

    def test_direct_callers_classified(self):
        graph = {"call_edges": _SIMPLE_TOPO_EDGES}
        result = _classify_services_from_graph("payment-svc", graph)
        types = {c["service"]: c["node_type"] for c in result}
        assert types["order-svc"] == "directly_affected_node"

    def test_indirect_callers_classified(self):
        graph = {"call_edges": _SIMPLE_TOPO_EDGES}
        result = _classify_services_from_graph("payment-svc", graph)
        types = {c["service"]: c["node_type"] for c in result}
        assert types["frontend-svc"] == "indirectly_affected_node"

    def test_unrelated_service_merely_observed(self):
        edges = _SIMPLE_TOPO_EDGES + [{"source": "unrelated-svc", "target": "monitoring-svc"}]
        graph = {"call_edges": edges}
        result = _classify_services_from_graph("payment-svc", graph)
        types = {c["service"]: c["node_type"] for c in result}
        # unrelated-svc and monitoring-svc have no path to payment-svc
        assert types.get("unrelated-svc") == "merely_observed_node"
        assert types.get("monitoring-svc") == "merely_observed_node"

    def test_empty_graph_returns_empty(self):
        result = _classify_services_from_graph("payment-svc", {})
        assert result == [] or all(c["service"] == "payment-svc" for c in result)


# ---------------------------------------------------------------------------
# Unit tests: resolve_impact_input
# ---------------------------------------------------------------------------

class TestResolveImpactInput:
    def test_priority1_dcc_impact_scope(self):
        dcc = _full_dcc(extra={
            "candidates": {
                "root_cause": [],
                "impact_scope": [
                    {"service": "order-svc", "node_type": "directly_affected_node", "confidence": 0.85},
                    {"service": "frontend-svc", "node_type": "indirectly_affected_node", "confidence": 0.60},
                ],
            }
        })
        ctx = _make_ctx(dcc_context=dcc, root_cause_result={"root_cause_service": "payment-svc"})
        res = resolve_impact_input(ctx)
        assert res.candidate_source == "dcc_impact_candidates"
        assert res.dcc_used is True
        assert len(res.impact_candidates) == 2
        services = [c["service"] for c in res.impact_candidates]
        assert "order-svc" in services
        assert "frontend-svc" in services
        assert all(c["_candidate_origin"] == "dcc_impact_candidates" for c in res.impact_candidates)

    def test_priority2_topology_propagation(self):
        dcc = _full_dcc(extra={
            "objects": {
                "entities": [],
                "relations": [],
                "topology": {"nodes": [], "edges": _SIMPLE_TOPO_EDGES,
                              "entry_points": [], "candidate_paths": []},
            }
        })
        ctx = _make_ctx(dcc_context=dcc, root_cause_result={"root_cause_service": "payment-svc"})
        res = resolve_impact_input(ctx)
        assert res.candidate_source == "topology_propagation"
        assert res.dcc_used is True
        types = {c["service"]: c["node_type"] for c in res.impact_candidates}
        assert types["payment-svc"] == "root_cause_node"
        assert types["order-svc"] == "directly_affected_node"
        assert types["frontend-svc"] == "indirectly_affected_node"

    def test_priority3_dcc_context_with_graph(self):
        dcc = _full_dcc(extra={
            "objects": {
                "entities": [{"id": "order-svc"}, {"id": "payment-svc"}],
                "relations": [],
                "topology": {},
            }
        })
        ctx = _make_ctx(
            dcc_context=dcc,
            root_cause_result={"root_cause_service": "payment-svc"},
            graph_result={"call_edges": _SIMPLE_TOPO_EDGES},
        )
        res = resolve_impact_input(ctx)
        assert res.candidate_source == "evidence_based_with_dcc_context"
        assert res.dcc_used is True
        # frontend-svc not in DCC entities → should be merely_observed
        types = {c["service"]: c["node_type"] for c in res.impact_candidates}
        assert types.get("frontend-svc") == "merely_observed_node"

    def test_priority4_no_dcc(self):
        ctx = _make_ctx(
            dcc_context={},
            root_cause_result={"root_cause_service": "payment-svc"},
            graph_result={"call_edges": _SIMPLE_TOPO_EDGES},
        )
        res = resolve_impact_input(ctx)
        assert res.candidate_source == "evidence_based"
        assert res.dcc_used is False
        types = {c["service"]: c["node_type"] for c in res.impact_candidates}
        assert types["payment-svc"] == "root_cause_node"
        assert types["order-svc"] == "directly_affected_node"

    def test_warning_when_impact_scope_unnormalizable(self):
        dcc = _full_dcc(extra={
            "candidates": {
                "root_cause": [],
                "impact_scope": [{"no_service_field": "nothing"}],
            }
        })
        ctx = _make_ctx(dcc_context=dcc, root_cause_result={"root_cause_service": "svc-x"})
        res = resolve_impact_input(ctx)
        assert any("normalizable" in w for w in res.warnings)
        # Falls through to next priority
        assert res.candidate_source in {"topology_propagation", "evidence_based_with_dcc_context", "evidence_based"}


# ---------------------------------------------------------------------------
# Integration tests: ImpactAnalysisSkill with DCC candidates
# ---------------------------------------------------------------------------

import app.skills.impact_analysis_skill as _impact_module


def _run_impact_skill(ctx: DiagnosisContext, monkeypatch) -> object:
    """Run ImpactAnalysisSkill with external dependencies mocked."""
    # Mock OntologyConfigAdapter to return empty ontology
    mock_onto = MagicMock()
    mock_onto.load_demo_business_ontology.return_value = {
        "business_relations": [],
        "business_capabilities": [],
        "business_processes": [],
        "frontend_pages": [],
        "user_groups": [],
    }
    monkeypatch.setattr(_impact_module, "OntologyConfigAdapter", lambda: mock_onto)

    # Mock business impact repository
    mock_repo = MagicMock()
    mock_bi = MagicMock()
    mock_bi.items = []
    mock_repo.get_business_impact_for_services.return_value = mock_bi
    monkeypatch.setattr(_impact_module, "get_business_impact_repository", lambda: mock_repo)

    from app.skills.impact_analysis_skill import ImpactAnalysisSkill
    skill = ImpactAnalysisSkill(business_impact_repository=mock_repo)
    return skill.run(ctx)


class TestImpactSkillDCCFirst:
    def test_skill_uses_dcc_impact_candidates(self, monkeypatch):
        """DCC impact_scope candidates are used; affected_services comes from DCC."""
        dcc = _full_dcc(extra={
            "candidates": {
                "root_cause": [],
                "impact_scope": [
                    {"service": "order-svc", "node_type": "directly_affected_node", "confidence": 0.85},
                ],
            }
        })
        ctx = _make_ctx(
            dcc_context=dcc,
            root_cause_result={"root_cause_service": "payment-svc"},
        )
        result = _run_impact_skill(ctx, monkeypatch)
        assert result.status == "success"
        out = result.output
        assert out["dcc_candidates_used"] is True
        assert out["candidate_source"] == "dcc_impact_candidates"
        assert out["object_centered_mode"] is True
        assert "order-svc" in out["affected_services"]

    def test_skill_filters_merely_observed_when_dcc_authoritative(self, monkeypatch):
        """merely_observed_node services are NOT included in affected_services."""
        dcc = _full_dcc(extra={
            "candidates": {
                "root_cause": [],
                "impact_scope": [
                    {"service": "order-svc", "node_type": "directly_affected_node", "confidence": 0.85},
                    {"service": "monitoring-svc", "node_type": "merely_observed_node", "confidence": 0.20},
                ],
            }
        })
        ctx = _make_ctx(
            dcc_context=dcc,
            root_cause_result={"root_cause_service": "payment-svc"},
        )
        result = _run_impact_skill(ctx, monkeypatch)
        assert "order-svc" in result.output["affected_services"]
        assert "monitoring-svc" not in result.output["affected_services"]

    def test_skill_node_classifications_populated(self, monkeypatch):
        """ctx.impact_result contains node_classifications dict."""
        dcc = _full_dcc(extra={
            "objects": {
                "entities": [],
                "relations": [],
                "topology": {"nodes": [], "edges": _SIMPLE_TOPO_EDGES,
                              "entry_points": [], "candidate_paths": []},
            }
        })
        ctx = _make_ctx(
            dcc_context=dcc,
            root_cause_result={"root_cause_service": "payment-svc"},
        )
        result = _run_impact_skill(ctx, monkeypatch)
        out = result.output
        assert "node_classifications" in out
        assert "root_cause_nodes" in out["node_classifications"]
        assert "directly_affected_nodes" in out["node_classifications"]
        assert "merely_observed_nodes" in out["node_classifications"]
        assert "impact_nodes_by_type" in out

    def test_skill_topology_propagation_path(self, monkeypatch):
        """DCC topology edges used for propagation; correct node_type assigned."""
        dcc = _full_dcc(extra={
            "objects": {
                "entities": [],
                "relations": [],
                "topology": {"nodes": [], "edges": _SIMPLE_TOPO_EDGES,
                              "entry_points": [], "candidate_paths": []},
            }
        })
        ctx = _make_ctx(
            dcc_context=dcc,
            root_cause_result={"root_cause_service": "payment-svc"},
        )
        result = _run_impact_skill(ctx, monkeypatch)
        assert result.output["candidate_source"] == "topology_propagation"
        assert result.output["dcc_candidates_used"] is True
        by_type = result.output["impact_nodes_by_type"]
        assert "payment-svc" in by_type["root_cause_nodes"]
        assert "order-svc" in by_type["directly_affected_nodes"]
        assert "frontend-svc" in by_type["indirectly_affected_nodes"]

    def test_skill_trace_nodes_not_all_affected(self, monkeypatch):
        """Anti-overfitting: trace-observed services not automatically 'directly_affected'."""
        dcc = _full_dcc(extra={
            "candidates": {
                "root_cause": [],
                "impact_scope": [
                    # Only order-svc is explicitly marked as affected
                    {"service": "order-svc", "node_type": "directly_affected_node", "confidence": 0.85},
                ],
            }
        })
        # trace has many services that appeared in spans
        ctx = _make_ctx(
            dcc_context=dcc,
            root_cause_result={"root_cause_service": "payment-svc"},
            trace_result={
                "call_path": ["frontend-svc", "order-svc", "payment-svc", "logging-svc", "audit-svc"],
                "root_candidates": [],
            },
            graph_result={
                "call_edges": [
                    {"source": "frontend-svc", "target": "order-svc"},
                    {"source": "order-svc", "target": "payment-svc"},
                    # logging-svc and audit-svc in trace but no relevant edge
                    {"source": "logging-svc", "target": "audit-svc"},
                ]
            },
        )
        result = _run_impact_skill(ctx, monkeypatch)
        affected = result.output["affected_services"]
        # DCC-authoritative: only DCC-listed services (excluding merely_observed)
        assert "order-svc" in affected
        assert "logging-svc" not in affected
        assert "audit-svc" not in affected

    def test_skill_execution_log_shows_dcc_object_centered(self, monkeypatch):
        dcc = _full_dcc(extra={
            "candidates": {
                "root_cause": [],
                "impact_scope": [{"service": "svc-x", "confidence": 0.8}],
            }
        })
        ctx = _make_ctx(dcc_context=dcc, root_cause_result={"root_cause_service": "svc-root"})
        result = _run_impact_skill(ctx, monkeypatch)
        log_text = " ".join(result.execution_log)
        assert "DCC-object-centered" in log_text

    def test_skill_input_includes_candidate_source(self, monkeypatch):
        dcc = _full_dcc(extra={
            "candidates": {
                "root_cause": [],
                "impact_scope": [{"service": "svc-a", "confidence": 0.75}],
            }
        })
        ctx = _make_ctx(dcc_context=dcc, root_cause_result={"root_cause_service": "svc-root"})
        result = _run_impact_skill(ctx, monkeypatch)
        assert "candidate_source" in result.input
        assert result.input["dcc_candidates_count"] == 1

    def test_skill_evidence_shows_candidate_source(self, monkeypatch):
        dcc = _full_dcc(extra={
            "candidates": {
                "root_cause": [],
                "impact_scope": [{"service": "svc-b", "confidence": 0.70}],
            }
        })
        ctx = _make_ctx(dcc_context=dcc, root_cause_result={"root_cause_service": "svc-root"})
        result = _run_impact_skill(ctx, monkeypatch)
        evidence_text = " ".join(result.evidence)
        assert "dcc_impact_candidates" in evidence_text

    def test_skill_legacy_path_unbroken_no_dcc(self, monkeypatch):
        """No DCC: existing call-graph logic still works."""
        ctx = _make_ctx(
            dcc_context={},
            root_cause_result={"root_cause_service": "payment-svc"},
            graph_result={
                "call_edges": _SIMPLE_TOPO_EDGES,
                "edges": [],
            },
        )
        result = _run_impact_skill(ctx, monkeypatch)
        assert result.status == "success"
        out = result.output
        assert out["dcc_candidates_used"] is False
        assert out["candidate_source"] in {"evidence_based", "evidence_based+dcc_context"}
        assert "payment-svc" in out["affected_services"]

    def test_full_dcc_impact_pipeline(self, monkeypatch):
        """Full pipeline: DCC with topology + impact_scope + root_cause + trace."""
        dcc = _full_dcc(extra={
            "objects": {
                "entities": [{"id": "order-svc"}, {"id": "payment-svc"}],
                "relations": [],
                "topology": {"nodes": [], "edges": _SIMPLE_TOPO_EDGES,
                              "entry_points": [], "candidate_paths": []},
            },
            "candidates": {
                "root_cause": [{"service": "payment-svc", "confidence": 0.91}],
                "impact_scope": [
                    {"service": "order-svc", "node_type": "directly_affected_node", "confidence": 0.82},
                    {"service": "frontend-svc", "node_type": "indirectly_affected_node", "confidence": 0.60},
                ],
            },
        })
        ctx = _make_ctx(
            dcc_context=dcc,
            root_cause_result={"root_cause_service": "payment-svc"},
            trace_result={
                "root_candidates": [{"service": "payment-svc", "score": 0.8, "type": "service_exception"}],
                "call_path": ["frontend-svc", "order-svc", "payment-svc"],
            },
        )
        result = _run_impact_skill(ctx, monkeypatch)
        assert result.status == "success"
        out = result.output
        # DCC impact_scope takes Priority 1
        assert out["candidate_source"] == "dcc_impact_candidates"
        assert out["object_centered_mode"] is True
        assert "order-svc" in out["affected_services"]
        assert "frontend-svc" in out["affected_services"]
        # Classifications populated
        by_type = out["impact_nodes_by_type"]
        assert "order-svc" in by_type["directly_affected_nodes"]
        assert "frontend-svc" in by_type["indirectly_affected_nodes"]
        # Explanation mentions object-centered
        assert "object-centered" in result.explanation
