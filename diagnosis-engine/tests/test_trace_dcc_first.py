"""Tests for Step 4: Trace DCC-first input resolution and Skill integration."""
import os
import sys

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
BACKEND_ROOT = os.path.join(REPO_ROOT, "backend")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

import pytest

from app.models.context import DiagnosisContext
from app.runtime.trace_input_resolver import TraceInputResolution, resolve_trace_input


# ─── helpers ─────────────────────────────────────────────────────────────────

def _make_ctx(dcc: dict | None = None) -> DiagnosisContext:
    ctx = DiagnosisContext(
        api="/pay/submit",
        time="2026-05-30 12:00:00",
        symptom="HTTP 500",
    )
    ctx.query_context = {}
    if dcc is not None:
        ctx.dcc_context = dcc
    return ctx


def _dcc_with_traces(items: list[dict], availability: str = "available") -> dict:
    return {
        "protocol_version": "dcc.v0.1",
        "context_id": "dcc-trace-test",
        "generated_at": "2026-05-30T12:00:00Z",
        "workspace": {"workspace_id": "test-workspace"},
        "alert": {
            "api": "/pay/submit",
            "time": "2026-05-30 12:00:00",
            "symptom": "HTTP 500",
        },
        "evidence": {
            "trace": {
                "availability": availability,
                "items": items,
                "warnings": [],
            },
            "log": {"availability": "empty", "items": []},
            "metric": {"availability": "empty", "items": []},
        },
        "objects": {
            "entities": [{"entity_id": "svc-1", "entity_type": "service", "entity_name": "payment-service", "domain": "devops", "attrs": {}}],
            "relations": [],
            "topology": {
                "nodes": [{"id": "payment-service", "node_type": "service", "label": "payment-service"}],
                "edges": [],
            },
        },
        "candidates": {"root_cause": [], "impact_scope": []},
        "provenance": {"producer": "unit-test"},
        "meta": {"availability": "available"},
    }


_SAMPLE_SPAN = {
    "traceId": "trace-dcc-001",
    "spanId": "span-001",
    "parentSpanId": "",
    "serviceName": "payment-service",
    "name": "/pay/submit",
    "kind": "SPAN_KIND_SERVER",
    "startTime": "2026-05-30T12:00:00Z",
    "status.code": 0,
    "status.message": "",
    "events": [],
}


# ─── resolver unit tests ─────────────────────────────────────────────────────

def test_resolver_returns_dcc_spans_when_available() -> None:
    ctx = _make_ctx(_dcc_with_traces([_SAMPLE_SPAN]))
    res = resolve_trace_input(ctx)
    assert res.skipped_adapter is True
    assert res.spans == [_SAMPLE_SPAN]
    assert res.data_source_label == "dcc:evidence.trace.items"
    assert not res.warnings


def test_resolver_fallback_when_items_empty() -> None:
    ctx = _make_ctx(_dcc_with_traces([], availability="available"))
    res = resolve_trace_input(ctx)
    assert res.skipped_adapter is False
    assert res.spans == []
    assert any("empty" in w for w in res.warnings)


def test_resolver_fallback_when_unavailable() -> None:
    ctx = _make_ctx(_dcc_with_traces([], availability="unavailable"))
    res = resolve_trace_input(ctx)
    assert res.skipped_adapter is False
    assert any("unavailable" in w for w in res.warnings)


def test_resolver_fallback_when_insufficient() -> None:
    ctx = _make_ctx(_dcc_with_traces([_SAMPLE_SPAN], availability="insufficient"))
    res = resolve_trace_input(ctx)
    assert res.skipped_adapter is False
    assert any("insufficient" in w for w in res.warnings)


def test_resolver_no_dcc_returns_adapter_path() -> None:
    ctx = _make_ctx()  # no dcc_context
    res = resolve_trace_input(ctx)
    assert res.skipped_adapter is False
    assert res.data_source_label == "adapter"
    assert res.spans == []


def test_resolver_extracts_topology_seed() -> None:
    ctx = _make_ctx(_dcc_with_traces([_SAMPLE_SPAN]))
    res = resolve_trace_input(ctx)
    assert res.topology_seed.get("nodes") is not None
    assert res.entity_seed[0]["entity_name"] == "payment-service"


def test_resolver_missing_trace_bucket() -> None:
    dcc = {
        "protocol_version": "dcc.v0.1",
        "context_id": "dcc-no-trace",
        "evidence": {
            "log": {"availability": "empty", "items": []},
            "metric": {"availability": "empty", "items": []},
        },
        "objects": {"entities": [], "relations": [], "topology": {"nodes": [], "edges": []}},
        "candidates": {"root_cause": [], "impact_scope": []},
        "provenance": {"producer": "unit-test"},
        "meta": {"availability": "available"},
    }
    ctx = _make_ctx(dcc)
    res = resolve_trace_input(ctx)
    assert res.skipped_adapter is False
    assert any("missing or malformed" in w for w in res.warnings)


# ─── Skill integration tests ─────────────────────────────────────────────────

def test_trace_skill_uses_dcc_spans_not_adapter(monkeypatch) -> None:
    """When DCC has available trace items, adapter.get_traces must NOT be called."""
    import app.skills.trace_analysis_skill as tskill_module
    from app.skills.trace_analysis_skill import TraceAnalysisSkill

    adapter_calls: list = []

    monkeypatch.setattr(tskill_module.adapter, "get_traces", lambda **kw: (adapter_calls.append(kw) or []))
    monkeypatch.setattr(tskill_module.adapter, "get_data_source", lambda: "local_json")

    ctx = _make_ctx(_dcc_with_traces([_SAMPLE_SPAN]))
    result = TraceAnalysisSkill().run(ctx)

    assert adapter_calls == [], "adapter.get_traces should NOT be called when DCC has trace items"
    assert result.status == "success"
    assert result.input["data_file"] == "dcc:evidence.trace.items"
    assert ctx.trace_result.get("trace_id") == "trace-dcc-001"


def test_trace_skill_populates_call_path_from_dcc_spans(monkeypatch) -> None:
    import app.skills.trace_analysis_skill as tskill_module
    from app.skills.trace_analysis_skill import TraceAnalysisSkill

    monkeypatch.setattr(tskill_module.adapter, "get_traces", lambda **kw: [])
    monkeypatch.setattr(tskill_module.adapter, "get_data_source", lambda: "local_json")

    ctx = _make_ctx(_dcc_with_traces([_SAMPLE_SPAN]))
    result = TraceAnalysisSkill().run(ctx)

    assert result.status == "success"
    call_path = ctx.trace_result.get("call_path", [])
    assert any("payment-service" in step for step in call_path)


def test_trace_skill_fallback_when_dcc_trace_empty(monkeypatch) -> None:
    """When DCC trace bucket is empty, adapter.get_traces must be called."""
    import app.skills.trace_analysis_skill as tskill_module
    from app.skills.trace_analysis_skill import TraceAnalysisSkill

    adapter_calls: list = []

    monkeypatch.setattr(tskill_module.adapter, "get_traces", lambda **kw: (adapter_calls.append(kw) or []))
    monkeypatch.setattr(tskill_module.adapter, "get_data_source", lambda: "opensearch")

    ctx = _make_ctx(_dcc_with_traces([], availability="available"))
    result = TraceAnalysisSkill().run(ctx)

    assert adapter_calls, "adapter.get_traces MUST be called when DCC trace items are empty"
    assert result.status == "success"
    assert any("empty" in log for log in result.execution_log)


def test_trace_skill_no_dcc_calls_adapter(monkeypatch) -> None:
    """Without DCC, the legacy adapter path must be used."""
    import app.skills.trace_analysis_skill as tskill_module
    from app.skills.trace_analysis_skill import TraceAnalysisSkill

    adapter_calls: list = []

    monkeypatch.setattr(tskill_module.adapter, "get_traces", lambda **kw: (adapter_calls.append(kw) or []))
    monkeypatch.setattr(tskill_module.adapter, "get_data_source", lambda: "opensearch")

    ctx = _make_ctx()  # no DCC
    result = TraceAnalysisSkill().run(ctx)

    assert adapter_calls, "adapter.get_traces MUST be called when no DCC is present"
    assert result.status == "success"
    # data_file should NOT reference dcc
    assert "dcc" not in result.input["data_file"]


def test_trace_skill_dcc_warns_and_logs_on_insufficient(monkeypatch) -> None:
    """Insufficient DCC trace data should produce a visible warning in execution_log."""
    import app.skills.trace_analysis_skill as tskill_module
    from app.skills.trace_analysis_skill import TraceAnalysisSkill

    monkeypatch.setattr(tskill_module.adapter, "get_traces", lambda **kw: [])
    monkeypatch.setattr(tskill_module.adapter, "get_data_source", lambda: "opensearch")

    ctx = _make_ctx(_dcc_with_traces([_SAMPLE_SPAN], availability="insufficient"))
    result = TraceAnalysisSkill().run(ctx)

    assert result.status == "success"
    combined_log = " ".join(result.execution_log)
    assert "insufficient" in combined_log


# ─── orchestrator-level DCC trace integration ────────────────────────────────

def test_orchestrator_with_dcc_trace_uses_resolver(monkeypatch) -> None:
    """Full orchestrator → TraceAnalysisSkill path: DCC spans must be consumed."""
    from app.orchestrator import diagnosis_orchestrator
    from app.session import InMemoryDiagnosisSessionStore
    import app.skills.trace_analysis_skill as tskill_module

    adapter_calls: list = []
    monkeypatch.setattr(tskill_module.adapter, "get_traces", lambda **kw: (adapter_calls.append(kw) or []))
    monkeypatch.setattr(tskill_module.adapter, "get_data_source", lambda: "local_json")

    # Replace only TraceAnalysisSkill in the pipeline; keep others fake (fast).
    from app.models.diagnosis import SkillResult as SR
    from app.skills.trace_analysis_skill import TraceAnalysisSkill

    class _NopSkill:
        def __init__(self, name: str, tool: str) -> None:
            self.skill_name = name
            self.tool_name = tool
            self.title = name

        def run(self, ctx):
            if self.skill_name == "AlertContextSkill":
                ctx.query_context = {"alert_api": ctx.api}
            elif self.skill_name == "RootCauseSkill":
                ctx.root_cause_result = {"root_cause_service": "", "is_confirmed": False}
            elif self.skill_name == "ImpactAnalysisSkill":
                ctx.impact_result = {"affected_services": [], "affected_apis": [], "affected_business": []}
            elif self.skill_name == "ReportSkill":
                ctx.report_result = {"report": "dcc-trace-test-done"}
            return SR(skill_name=self.skill_name, tool_name=self.tool_name, title=self.title,
                      status="success", summary="ok", input={}, output={}, evidence=[], execution_log=[], explanation="")

    pipeline = [
        _NopSkill("AlertContextSkill", "MModelSkill/set_time_range"),
        TraceAnalysisSkill(),  # ← real skill
        _NopSkill("EntityBindingSkill", "MModelSkill/bind_entities"),
        _NopSkill("LogAnalysisSkill", "MModelSkill/analyze_log"),
        _NopSkill("MetricCheckSkill", "MModelSkill/check_metrics"),
        _NopSkill("GraphAnalysisSkill", "MModelSkill/query_graph"),
        _NopSkill("RootCauseSkill", "MModelSkill/locate_root_cause"),
        _NopSkill("ImpactAnalysisSkill", "MModelSkill/analyze_impact"),
        _NopSkill("ReportSkill", "MModelSkill/generate_report"),
    ]
    monkeypatch.setattr(diagnosis_orchestrator, "SKILL_PIPELINE", pipeline)

    dcc = _dcc_with_traces([_SAMPLE_SPAN])
    response = diagnosis_orchestrator.run_diagnosis(
        api="",
        time="",
        symptom="",
        dcc=dcc,
        session_store=InMemoryDiagnosisSessionStore(),
    )

    # adapter.get_traces was NOT called — trace came from DCC
    assert adapter_calls == [], (
        "With a DCC that has trace items, adapter.get_traces should not be called"
    )
    assert response.skills is not None
    trace_skill_result = next(
        (s for s in response.skills if s.skill_name == "TraceAnalysisSkill"), None
    )
    assert trace_skill_result is not None
    assert trace_skill_result.input["data_file"] == "dcc:evidence.trace.items"
