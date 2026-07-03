import os
import sys


REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
BACKEND_ROOT = os.path.join(REPO_ROOT, "backend")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)


from app.models.context import DiagnosisContext
from app.skills.report_skill import ReportSkill


class _FakeLLM:
    def generate_explanation(self, context: dict) -> str:
        return "diagnosis report"

    def generate_undetermined_report(self, context: dict) -> str:
        return "undetermined diagnosis report"


def _make_ctx() -> DiagnosisContext:
    ctx = DiagnosisContext(api="/api/checkout", time="2026-06-01T10:00:00Z", symptom="HTTP 500")
    ctx.trace_result = {
        "trace_id": "trace-1",
        "call_path": ["frontend:/api/checkout", "checkout:/checkout", "payment:/charge"],
        "root_candidates": [{"service": "payment", "type": "service_exception"}],
        "abnormal_spans": [{"service": "payment", "api": "/charge"}],
    }
    ctx.log_result = {
        "upstream_error_type": "FeignException",
        "root_candidates": [{"service": "payment", "type": "service_exception"}],
        "propagation_logs": [{"service": "checkout", "exception_type": "FeignException"}],
    }
    ctx.metric_result = {
        "conclusion": "payment error rate elevated",
        "metric_root_candidates": [{"service": "payment", "type": "service_exception"}],
        "red_metrics": [{"service_name": "payment", "overall_anomaly_score": 0.81}],
    }
    ctx.graph_result = {
        "nodes": [
            {"id": "frontend", "node_type": "Service"},
            {"id": "checkout", "node_type": "Service"},
            {"id": "payment", "node_type": "Service"},
        ],
        "edges": [
            {"source": "frontend", "target": "checkout", "label": "calls"},
            {"source": "checkout", "target": "payment", "label": "calls"},
        ],
    }
    return ctx


def _run_report(ctx: DiagnosisContext, monkeypatch):
    monkeypatch.setattr("app.skills.report_skill.get_llm_provider", lambda: _FakeLLM())
    return ReportSkill().run(ctx)


def test_object_centered_explain_visible_when_dcc_context_complete(monkeypatch):
    ctx = _make_ctx()
    ctx.dcc_context = {
        "alert": {"api": "/api/checkout"},
        "objects": {
            "entities": [{"entity_id": "checkout", "entity_type": "service"}, {"entity_id": "payment", "entity_type": "service"}],
            "topology": {
                "nodes": [{"id": "checkout"}, {"id": "payment"}],
                "edges": [{"source": "checkout", "target": "payment", "relation": "calls"}],
            },
        },
        "candidates": {
            "root_cause": [{"entity_id": "payment", "candidate_source": "dependency_graph"}],
            "impact_scope": [{"entity_id": "checkout", "node_type": "directly_affected_node"}],
        },
    }
    ctx.root_cause_result = {
        "root_cause_service": "payment",
        "root_cause_api": "/charge",
        "root_cause_type": "service_exception",
        "confidence": "high",
        "is_confirmed": True,
        "candidate_source": "dcc_candidates",
        "entry_entity": "/api/checkout",
        "object_centered_mode": True,
        "candidates": [{"service": "payment", "score": 0.91}],
        "scoring_reason": "dcc candidates + evidence confirmation",
    }
    ctx.impact_result = {
        "affected_services": ["checkout", "frontend"],
        "candidate_source": "topology_propagation",
        "object_centered_mode": True,
        "impact_nodes_by_type": {
            "propagation_nodes": ["checkout"],
            "directly_affected_nodes": ["checkout"],
            "indirectly_affected_nodes": ["frontend"],
            "merely_observed_nodes": [],
        },
    }

    result = _run_report(ctx, monkeypatch)
    explain = result.output["object_centered_explain"]

    assert explain["object_selection"]["object_context_mode"] is True
    assert explain["object_selection"]["entry_entity"] == "/api/checkout"
    assert explain["distinctive_signals"]["used_dcc"] is True
    assert explain["distinctive_signals"]["not_plain_trace_log_metric_scan"] is True


def test_root_candidate_source_marked_as_unifiedmodel_object_context(monkeypatch):
    ctx = _make_ctx()
    ctx.dcc_context = {"alert": {"api": "/api/checkout"}, "objects": {}, "candidates": {}}
    ctx.root_cause_result = {
        "root_cause_service": "payment",
        "root_cause_api": "/charge",
        "root_cause_type": "service_exception",
        "confidence": "high",
        "is_confirmed": True,
        "candidate_source": "dcc_candidates",
        "object_centered_mode": True,
    }
    ctx.impact_result = {
        "affected_services": ["checkout"],
        "candidate_source": "topology_propagation",
        "impact_nodes_by_type": {},
    }

    result = _run_report(ctx, monkeypatch)
    root_decision = result.output["object_centered_explain"]["root_cause_decision"]

    assert root_decision["candidate_source"] == "dcc_candidates"
    assert root_decision["uses_unifiedmodel_object_candidates"] is True


def test_impact_scope_topology_propagation_is_explicit(monkeypatch):
    ctx = _make_ctx()
    ctx.dcc_context = {"alert": {"api": "/api/checkout"}, "objects": {}, "candidates": {}}
    ctx.root_cause_result = {
        "root_cause_service": "payment",
        "root_cause_api": "/charge",
        "root_cause_type": "service_exception",
        "confidence": "medium",
        "is_confirmed": True,
        "candidate_source": "topology_inferred",
    }
    ctx.impact_result = {
        "affected_services": ["checkout", "frontend"],
        "candidate_source": "topology_propagation",
        "impact_nodes_by_type": {
            "propagation_nodes": ["checkout"],
            "directly_affected_nodes": ["checkout"],
            "indirectly_affected_nodes": ["frontend"],
            "merely_observed_nodes": ["metrics-agent"],
        },
    }

    result = _run_report(ctx, monkeypatch)
    impact_decision = result.output["object_centered_explain"]["impact_scope_decision"]

    assert impact_decision["candidate_source"] == "topology_propagation"
    assert impact_decision["topology_driven_scope"] is True
    assert impact_decision["node_groups"]["directly_affected_nodes"] == ["checkout"]
    assert impact_decision["node_groups"]["merely_observed_nodes"] == ["metrics-agent"]


def test_legacy_fallback_path_explicitly_exposed(monkeypatch):
    ctx = _make_ctx()
    ctx.dcc_context = {}
    ctx.root_cause_result = {
        "root_cause_service": "payment",
        "root_cause_api": "/charge",
        "root_cause_type": "service_exception",
        "confidence": "medium",
        "is_confirmed": True,
        "candidate_source": "evidence_based",
        "object_centered_mode": False,
    }
    ctx.impact_result = {
        "affected_services": ["checkout"],
        "candidate_source": "evidence_based",
        "object_centered_mode": False,
        "impact_nodes_by_type": {
            "propagation_nodes": [],
            "directly_affected_nodes": ["checkout"],
            "indirectly_affected_nodes": [],
            "merely_observed_nodes": [],
        },
    }

    result = _run_report(ctx, monkeypatch)
    explain = result.output["object_centered_explain"]

    assert explain["fallback"]["legacy_path_used"] is True
    assert explain["fallback"]["root_cause_path"] == "legacy_evidence_based"
    assert explain["fallback"]["impact_path"] == "legacy_evidence_based"


def test_report_skill_backward_compatibility_kept(monkeypatch):
    ctx = _make_ctx()
    ctx.root_cause_result = {
        "root_cause_service": "payment",
        "root_cause_api": "/charge",
        "root_cause_type": "service_exception",
        "confidence": "high",
        "is_confirmed": True,
        "candidate_source": "dcc_candidates",
    }
    ctx.impact_result = {
        "affected_services": ["checkout"],
        "candidate_source": "dcc_impact_candidates",
        "impact_nodes_by_type": {},
    }

    result = _run_report(ctx, monkeypatch)

    assert result.status == "success"
    assert "reasoning_chain" in result.output
    assert "object_centered_explain" in result.output
    assert "根因判定依据" in result.output["report"]
