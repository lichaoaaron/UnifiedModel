"""
Minimal automated tests for reasoning_chain / root_cause_explanation.

Run from project root with PYTHONPATH set:
    $env:PYTHONPATH = "$PWD;$PWD\backend"
    python backend/tests/test_reasoning_chain.py

Or with pytest (if installed):
    pytest backend/tests/test_reasoning_chain.py -v
"""
import sys
import os
import types

# ---------------------------------------------------------------------------
# Path bootstrap so tests can run both standalone and under pytest
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
_BACKEND = os.path.join(_REPO_ROOT, "backend")
for _p in [_REPO_ROOT, _BACKEND]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------
from app.models.context import DiagnosisContext
from app.skills.reasoning_chain_builder import build_reasoning_chain
from app.orchestrator.diagnosis_orchestrator import _build_call_graph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(override: dict | None = None) -> DiagnosisContext:
    """Create a minimal DiagnosisContext with synthetic (non-hardcoded) skill outputs."""
    ctx = DiagnosisContext(api="/entry/someApi", time="2026-05-11 10:00:00", symptom="HTTP 500")
    ctx.trace_result = {
        "trace_id": "trace-abc123",
        "first_error_service": "svc-downstream",
        "first_error_api": "/downstream/action",
        "first_error_exception": "java.lang.SomeException",
        "extracted_bad_parameter": "badval",
        "call_path": ["svc-entry: GET:/entry/someApi", "svc-downstream: GET:/downstream/action"],
        "abnormal_spans": [{"service": "svc-downstream", "api": "/downstream/action"}],
    }
    ctx.log_result = {
        "upstream_service": "svc-entry",
        "upstream_error_type": "FeignException",
        "downstream_url": "http://svc-downstream/downstream/action?param=badval",
        "log_evidence": ["error at svc-entry: FeignException"],
        "error_param": "badval",
    }
    ctx.metric_result = {
        "conclusion": "未发现资源异常",
        "checked_metrics": [{"metric_name": "cpu", "value": 30}],
    }
    ctx.graph_result = {
        "nodes": [
            {"id": "svc-entry", "is_root_cause": False},
            {"id": "svc-downstream", "is_root_cause": True},
        ],
        "edges": [
            {"source": "svc-entry", "target": "svc-downstream", "label": "calls"},
            {"source": "svc-downstream", "target": "svc-entry", "label": "impacts"},
        ],
    }
    ctx.root_cause_result = {
        "root_cause_service": "svc-downstream",
        "root_cause_api": "/downstream/action",
        "root_cause_type": "业务参数异常",
        "exception_type": "java.lang.SomeException",
        "bad_param": "badval",
        "root_cause_reason": "svc-downstream 产生非传播性原始异常",
        "confidence": "high",
        "applied_rule": "rule_downstream_specific_exception",
        "is_confirmed": True,
        "evidence_conflicts": [],
    }
    ctx.impact_result = {
        "affected_services": ["svc-entry"],
        "affected_apis": ["/entry/someApi"],
        "impact_path": [{"source": "svc-downstream", "target": "svc-entry", "type": "impacts"}],
    }
    ctx.evidence_consistency = {"has_conflict": False, "conflicts": []}
    if override:
        for k, v in override.items():
            setattr(ctx, k, v)
    return ctx


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_reasoning_chain_top_level_keys():
    """reasoning_chain must contain all required top-level keys."""
    ctx = _make_ctx()
    chain = build_reasoning_chain(ctx)
    for key in ("symptom", "evidence", "root_cause_candidates", "selected_root_cause", "propagation_path"):
        assert key in chain, f"reasoning_chain missing key: {key}"


def test_reasoning_chain_evidence_statuses():
    """Each evidence source must have a status field."""
    ctx = _make_ctx()
    chain = build_reasoning_chain(ctx)
    for src in ("trace", "log", "metric", "graph"):
        ev = chain["evidence"].get(src, {})
        assert "status" in ev, f"evidence.{src} missing 'status'"
        assert ev["status"] in ("available", "unavailable", "insufficient"), \
            f"evidence.{src}.status has unexpected value: {ev['status']}"


def test_reasoning_chain_evidence_available_with_data():
    """When skill outputs contain findings, evidence status should be 'available'."""
    ctx = _make_ctx()
    chain = build_reasoning_chain(ctx)
    assert chain["evidence"]["trace"]["status"] == "available"
    assert chain["evidence"]["log"]["status"] == "available"
    assert chain["evidence"]["metric"]["status"] == "available"
    assert chain["evidence"]["graph"]["status"] == "available"


def test_reasoning_chain_surfaces_red_metrics_and_service_map_call_edges():
    """Reasoning chain should expose RED anomaly score and structured call_edges."""
    ctx = _make_ctx()
    red_item = {
        "service_name": "svc-downstream",
        "overall_anomaly_score": 0.88,
        "rate_signal": "normal",
        "error_signal": "elevated",
        "duration_signal": "elevated",
    }
    call_edges = [
        {"source_service": "svc-entry", "target_service": "svc-downstream", "call_count": 4, "error_count": 2},
    ]
    ctx.metric_result["red_metrics"] = [red_item]
    ctx.graph_result["call_edges"] = call_edges
    ctx.root_cause_result["evidence_by_source"] = {
        "red_metrics": [red_item],
        "service_map": {"call_edges": call_edges},
    }

    chain = build_reasoning_chain(ctx)
    metric_findings = "\n".join(chain["evidence"]["metric"]["findings"])
    graph_findings = "\n".join(chain["evidence"]["graph"]["findings"])

    assert "RED Metrics：svc-downstream 异常评分=0.88" in metric_findings
    assert "svc-entry → svc-downstream" in graph_findings


def test_reasoning_chain_unavailable_when_empty():
    """When skill results are empty, evidence must be marked unavailable/insufficient, not raise."""
    ctx = DiagnosisContext(api="/api/x", time="2026-01-01", symptom="error")
    # all skill results remain default empty dicts
    chain = build_reasoning_chain(ctx)
    # Should not raise; evidence must be marked
    for src in ("trace", "log", "metric", "graph"):
        assert chain["evidence"][src]["status"] in ("unavailable", "insufficient")


def test_reasoning_chain_candidates_present():
    """At least one root cause candidate must be present."""
    ctx = _make_ctx()
    chain = build_reasoning_chain(ctx)
    candidates = chain["root_cause_candidates"]
    assert len(candidates) >= 1
    c = candidates[0]
    for field in ("candidate_id", "candidate_type", "entity_ref", "score", "supporting_reasons", "weakening_reasons", "evidence_refs"):
        assert field in c, f"candidate missing field: {field}"


def test_reasoning_chain_no_hardcoded_sample_values():
    """reasoning_chain must not reference hardcoded sample values from project demo data."""
    ctx = _make_ctx()
    chain = build_reasoning_chain(ctx)
    chain_str = str(chain)
    # These are the known demo-specific hardcoded values that must not appear
    forbidden = ["xiaozhou-product", "xiaozhou-order", "172.16.8.6", "172.16.8.9",
                 "/product/getOrderById", "getOrderById"]
    for forbidden_val in forbidden:
        assert forbidden_val not in chain_str, \
            f"reasoning_chain contains hardcoded sample value: {forbidden_val}"


def test_reasoning_chain_selected_root_cause():
    """selected_root_cause must contain entity_ref and selection_reason."""
    ctx = _make_ctx()
    chain = build_reasoning_chain(ctx)
    sel = chain["selected_root_cause"]
    assert sel.get("entity_ref"), "selected_root_cause.entity_ref must not be empty"
    assert sel.get("selection_reason"), "selected_root_cause.selection_reason must not be empty"
    assert "is_confirmed" in sel


def test_reasoning_chain_propagation_path():
    """propagation_path must have status and path list."""
    ctx = _make_ctx()
    chain = build_reasoning_chain(ctx)
    prop = chain["propagation_path"]
    assert "status" in prop
    assert "path" in prop
    assert "explanation" in prop


def test_reasoning_chain_with_evidence_conflict():
    """When evidence conflicts exist, weakening_reasons should contain conflict description."""
    ctx = _make_ctx()
    ctx.root_cause_result["evidence_conflicts"] = [
        {
            "field": "bad_param",
            "source_a": "trace",
            "source_a_value": "aa",
            "source_b": "log",
            "source_b_value": "bb",
        }
    ]
    ctx.root_cause_result["is_confirmed"] = False
    ctx.evidence_consistency = {"has_conflict": True, "conflicts": []}
    chain = build_reasoning_chain(ctx)
    candidates = chain["root_cause_candidates"]
    weakening = candidates[0]["weakening_reasons"]
    assert any("证据冲突" in w for w in weakening), "expected conflict in weakening_reasons"
    assert not chain["selected_root_cause"]["is_confirmed"]


def test_report_skill_output_contains_reasoning_chain():
    """ReportSkill.run() must produce ctx.report_result with reasoning_chain key."""
    from app.skills.report_skill import ReportSkill
    ctx = _make_ctx()
    skill = ReportSkill()
    skill_result = skill.run(ctx)
    assert "reasoning_chain" in ctx.report_result, "ctx.report_result must contain reasoning_chain"
    chain = ctx.report_result["reasoning_chain"]
    for key in ("symptom", "evidence", "root_cause_candidates", "selected_root_cause", "propagation_path"):
        assert key in chain, f"reasoning_chain missing key: {key}"


def test_report_contains_reasoning_section_markdown():
    """Final report text must contain the '根因判定依据' section header."""
    from app.skills.report_skill import ReportSkill
    ctx = _make_ctx()
    skill = ReportSkill()
    skill.run(ctx)
    report_text = ctx.report_result.get("report", "")
    assert "根因判定依据" in report_text, \
        f"Final report missing '根因判定依据' section. Report starts with: {report_text[:200]}"


def test_call_graph_completes_runtime_topology_from_trace_and_root_cause():
    """Runtime call_graph should include trace service chain + root-cause service/api exposes edge."""
    ctx = DiagnosisContext(api="/api/checkout", time="2026-05-21 10:00:00", symptom="grpc unavailable")
    ctx.trace_result = {
        "trace_id": "trace-xyz",
        "entry_api": "/api/checkout",
        "call_path": [
            "load-generator: /api/checkout",
            "checkout: checkout call",
            "cart: cart call",
            "currency: currency call",
        ],
        "service_call": "load-generator → checkout → cart → currency",
    }
    ctx.root_cause_result = {
        "root_cause_service": "payment",
        "root_cause_api": "oteldemo.PaymentService/Charge",
        "is_confirmed": True,
    }
    ctx.impact_result = {
        "affected_services": ["checkout", "cart", "currency", "payment"],
        "affected_apis": ["/api/checkout", "oteldemo.PaymentService/Charge"],
    }
    ctx.graph_result = {"nodes": [], "edges": []}

    call_graph = _build_call_graph(ctx)
    node_ids = {node.id for node in call_graph.nodes}
    edge_set = {(edge.source, edge.target, edge.label) for edge in call_graph.edges}

    for service in ["load-generator", "checkout", "cart", "currency", "payment"]:
        assert service in node_ids
    assert "/api/checkout" in node_ids
    assert "oteldemo.PaymentService/Charge" in node_ids

    assert ("load-generator", "checkout", "calls") in edge_set
    assert ("checkout", "cart", "calls") in edge_set
    assert ("cart", "currency", "calls") in edge_set
    assert ("payment", "oteldemo.PaymentService/Charge", "exposes") in edge_set

    incoming_to_root_api = [edge for edge in call_graph.edges if edge.target == "oteldemo.PaymentService/Charge"]
    assert incoming_to_root_api, "root cause api should not be isolated"


def test_call_graph_marks_only_one_root_cause_interface_when_single_root_cause_api():
    """Only root_cause_api should be marked as root-cause interface."""
    ctx = DiagnosisContext(api="/api/checkout", time="2026-05-21 10:00:00", symptom="grpc unavailable")
    ctx.trace_result = {
        "trace_id": "trace-one-root-api",
        "entry_api": "/api/checkout",
        "first_error_api": "oteldemo.CheckoutService/PlaceOrder",
        "call_path": [
            "frontend: /api/checkout",
            "checkout: oteldemo.CheckoutService/PlaceOrder",
            "payment: oteldemo.PaymentService/Charge",
        ],
    }
    ctx.root_cause_result = {
        "root_cause_service": "payment",
        "root_cause_api": "oteldemo.PaymentService/Charge",
        "is_confirmed": True,
    }
    ctx.impact_result = {
        "affected_services": ["checkout", "payment"],
        "affected_apis": ["/api/checkout", "oteldemo.PaymentService/Charge"],
    }
    ctx.graph_result = {
        "nodes": [],
        "edges": [],
        "interface_edges": [
            {
                "source": "/api/checkout",
                "target": "oteldemo.CheckoutService/PlaceOrder",
                "label": "downstream call",
            }
        ],
    }

    call_graph = _build_call_graph(ctx)
    root_cause_interfaces = [
        node.id for node in call_graph.nodes
        if node.node_type == "Interface" and node.is_root_cause
    ]

    assert root_cause_interfaces == ["oteldemo.PaymentService/Charge"]


def test_call_graph_does_not_mark_entry_or_propagation_api_as_root_cause():
    """entry_api and propagation api are call-chain interfaces, not root-cause interfaces."""
    ctx = DiagnosisContext(api="/api/checkout", time="2026-05-21 10:00:00", symptom="grpc unavailable")
    ctx.trace_result = {
        "trace_id": "trace-entry-prop",
        "entry_api": "/api/checkout",
        "first_error_api": "oteldemo.CheckoutService/PlaceOrder",
        "call_path": [
            "frontend: /api/checkout",
            "checkout: oteldemo.CheckoutService/PlaceOrder",
            "payment: oteldemo.PaymentService/Charge",
        ],
    }
    ctx.root_cause_result = {
        "root_cause_service": "payment",
        "root_cause_api": "oteldemo.PaymentService/Charge",
        "is_confirmed": True,
    }
    ctx.impact_result = {
        "affected_services": ["checkout", "payment"],
        "affected_apis": ["/api/checkout", "oteldemo.PaymentService/Charge"],
    }
    ctx.graph_result = {
        "nodes": [],
        "edges": [],
        "interface_edges": [
            {
                "source": "/api/checkout",
                "target": "oteldemo.CheckoutService/PlaceOrder",
                "label": "downstream call",
            }
        ],
    }

    call_graph = _build_call_graph(ctx)
    node_by_id = {node.id: node for node in call_graph.nodes}

    assert node_by_id["oteldemo.PaymentService/Charge"].is_root_cause is True
    assert node_by_id["/api/checkout"].is_root_cause is False
    assert node_by_id["oteldemo.CheckoutService/PlaceOrder"].is_root_cause is False


def test_call_graph_emits_interface_downstream_edges_for_topology():
    """Interface-level downstream calls should be present in the frontend call graph."""
    ctx = DiagnosisContext(
        api="/oteldemo.CheckoutService/PlaceOrder",
        time="2026-06-27 08:00:00",
        symptom="HTTP 500",
    )
    ctx.trace_result = {
        "trace_id": "trace-1",
        "entry_api": "/oteldemo.CheckoutService/PlaceOrder",
        "first_error_api": "oteldemo.PaymentService/Charge",
        "call_path": [
            "checkout: oteldemo.CheckoutService/PlaceOrder",
            "payment: oteldemo.PaymentService/Charge",
        ],
    }
    ctx.root_cause_result = {
        "root_cause_service": "payment",
        "root_cause_api": "oteldemo.PaymentService/Charge",
        "root_cause_type": "service_exception",
        "is_confirmed": True,
    }
    ctx.impact_result = {
        "affected_services": ["checkout", "payment"],
        "affected_apis": [
            "/oteldemo.CheckoutService/PlaceOrder",
            "oteldemo.PaymentService/Charge",
        ],
    }
    ctx.graph_result = {
        "nodes": [],
        "edges": [],
        "interface_edges": [{
            "source": "/oteldemo.CheckoutService/PlaceOrder",
            "target": "oteldemo.PaymentService/Charge",
            "label": "downstream call",
        }],
    }

    call_graph = _build_call_graph(ctx)
    edge_set = {(edge.source, edge.target, edge.label) for edge in call_graph.edges}

    assert (
        "/oteldemo.CheckoutService/PlaceOrder",
        "oteldemo.PaymentService/Charge",
        "downstream call",
    ) in edge_set


# ---------------------------------------------------------------------------
# Standalone runner (no pytest required)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_fns = [
        test_reasoning_chain_top_level_keys,
        test_reasoning_chain_evidence_statuses,
        test_reasoning_chain_evidence_available_with_data,
        test_reasoning_chain_surfaces_red_metrics_and_service_map_call_edges,
        test_reasoning_chain_unavailable_when_empty,
        test_reasoning_chain_candidates_present,
        test_reasoning_chain_no_hardcoded_sample_values,
        test_reasoning_chain_selected_root_cause,
        test_reasoning_chain_propagation_path,
        test_reasoning_chain_with_evidence_conflict,
        test_report_skill_output_contains_reasoning_chain,
        test_report_contains_reasoning_section_markdown,
        test_call_graph_completes_runtime_topology_from_trace_and_root_cause,
    ]
    passed = 0
    failed = 0
    for fn in test_fns:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
            passed += 1
        except Exception as exc:
            print(f"  FAIL  {fn.__name__}: {exc}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
