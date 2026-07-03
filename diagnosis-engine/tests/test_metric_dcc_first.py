"""Tests for Step 6: Metric DCC-first input resolution, Skill integration,
legacy/replay fallback, and combined Trace+Log+Metric DCC path."""
import os
import sys

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
BACKEND_ROOT = os.path.join(REPO_ROOT, "backend")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

import pytest

from app.models.context import DiagnosisContext
from app.runtime.metric_input_resolver import MetricInputResolution, resolve_metric_input


# ─── helpers ─────────────────────────────────────────────────────────────────

def _make_ctx(dcc: dict | None = None) -> DiagnosisContext:
    ctx = DiagnosisContext(
        api="/order/create",
        time="2026-05-30 12:00:00",
        symptom="HTTP 500",
    )
    ctx.query_context = {}
    ctx.trace_result = {}
    if dcc is not None:
        ctx.dcc_context = dcc
    return ctx


def _full_dcc(
    metric_items: list[dict],
    metric_availability: str = "available",
    trace_items: list[dict] | None = None,
    log_items: list[dict] | None = None,
) -> dict:
    return {
        "protocol_version": "dcc.v0.1",
        "context_id": "dcc-metric-test",
        "generated_at": "2026-05-30T12:00:00Z",
        "workspace": {"workspace_id": "test-ws"},
        "alert": {
            "api": "/order/create",
            "time": "2026-05-30 12:00:00",
            "symptom": "HTTP 500",
        },
        "evidence": {
            "trace": {
                "availability": "available" if trace_items else "empty",
                "items": trace_items or [],
                "warnings": [],
            },
            "log": {
                "availability": "available" if log_items else "empty",
                "items": log_items or [],
                "warnings": [],
            },
            "metric": {
                "availability": metric_availability,
                "items": metric_items,
                "warnings": [],
            },
        },
        "objects": {
            "entities": [
                {
                    "entity_id": "svc-order",
                    "entity_type": "service",
                    "entity_name": "order-service",
                    "domain": "devops",
                    "attrs": {},
                }
            ],
            "relations": [],
            "topology": {
                "nodes": [{"id": "order-service", "node_type": "service", "label": "order-service"}],
                "edges": [],
            },
        },
        "candidates": {"root_cause": [], "impact_scope": []},
        "provenance": {"producer": "unit-test"},
        "meta": {"availability": "available"},
    }


_SAMPLE_METRIC = {
    "name": "cpu_usage_percent",
    "serviceName": "order-service",
    "resource.attributes.compose_service": "order-service",
    "resource.attributes.container@name": "order-service-pod",
    "value": 92.5,
    "unit": "%",
}

_SAMPLE_SPAN = {
    "traceId": "trace-dcc-001",
    "spanId": "span-001",
    "parentSpanId": "",
    "serviceName": "order-service",
    "name": "/order/create",
    "kind": "SPAN_KIND_SERVER",
    "startTime": "2026-05-30T12:00:00Z",
    "status.code": 0,
    "status.message": "",
    "events": [],
}

_SAMPLE_LOG = {
    "serviceName": "order-service",
    "severityText": "ERROR",
    "log.attributes.message": "NullPointerException: orderId cannot be null",
    "log.attributes.stack_trace": "",
}


# ─── resolver unit tests ─────────────────────────────────────────────────────

def test_resolver_returns_dcc_metrics_when_available() -> None:
    ctx = _make_ctx(_full_dcc([_SAMPLE_METRIC]))
    res = resolve_metric_input(ctx)
    assert res.skipped_adapter is True
    assert res.metrics == [_SAMPLE_METRIC]
    assert res.data_source_label == "dcc:evidence.metric.items"
    assert not res.warnings


def test_resolver_fallback_when_metric_items_empty() -> None:
    ctx = _make_ctx(_full_dcc([], metric_availability="available"))
    res = resolve_metric_input(ctx)
    assert res.skipped_adapter is False
    assert any("empty" in w for w in res.warnings)


def test_resolver_fallback_when_metric_unavailable() -> None:
    ctx = _make_ctx(_full_dcc([], metric_availability="unavailable"))
    res = resolve_metric_input(ctx)
    assert res.skipped_adapter is False
    assert any("unavailable" in w for w in res.warnings)


def test_resolver_fallback_when_metric_insufficient() -> None:
    ctx = _make_ctx(_full_dcc([_SAMPLE_METRIC], metric_availability="insufficient"))
    res = resolve_metric_input(ctx)
    assert res.skipped_adapter is False
    assert any("insufficient" in w for w in res.warnings)


def test_resolver_no_dcc_returns_adapter_path() -> None:
    ctx = _make_ctx()
    res = resolve_metric_input(ctx)
    assert res.skipped_adapter is False
    assert res.data_source_label == "adapter"
    assert res.metrics == []


def test_resolver_extracts_topology_and_entity_seed() -> None:
    ctx = _make_ctx(_full_dcc([_SAMPLE_METRIC]))
    res = resolve_metric_input(ctx)
    assert res.topology_seed.get("nodes") is not None
    assert res.entity_seed[0]["entity_name"] == "order-service"


def test_resolver_missing_metric_bucket() -> None:
    dcc = {
        "protocol_version": "dcc.v0.1",
        "context_id": "dcc-no-metric",
        "generated_at": "2026-05-30T12:00:00Z",
        "workspace": {"workspace_id": "test-ws"},
        "alert": {"api": "/order/create", "time": "2026-05-30 12:00:00", "symptom": "HTTP 500"},
        "evidence": {
            "trace": {"availability": "empty", "items": []},
            "log": {"availability": "empty", "items": []},
            # "metric" bucket intentionally missing
        },
        "objects": {"entities": [], "relations": [], "topology": {"nodes": [], "edges": []}},
        "candidates": {"root_cause": [], "impact_scope": []},
        "provenance": {"producer": "unit-test"},
        "meta": {"availability": "available"},
    }
    ctx = _make_ctx(dcc)
    res = resolve_metric_input(ctx)
    assert res.skipped_adapter is False
    assert any("missing or malformed" in w for w in res.warnings)


# ─── MetricCheckSkill integration tests ──────────────────────────────────────

def test_metric_skill_uses_dcc_metrics_not_adapter(monkeypatch) -> None:
    """When DCC has available metric items, adapter.get_metrics must NOT be called."""
    import app.skills.metric_check_skill as mskill_module
    from app.skills.metric_check_skill import MetricCheckSkill

    adapter_calls: list = []
    monkeypatch.setattr(mskill_module.adapter, "get_metrics", lambda **kw: (adapter_calls.append(kw) or []))
    monkeypatch.setattr(mskill_module.adapter, "get_data_source", lambda: "local_json")

    ctx = _make_ctx(_full_dcc([_SAMPLE_METRIC]))
    result = MetricCheckSkill().run(ctx)

    assert adapter_calls == [], "adapter.get_metrics must NOT be called when DCC has metric items"
    assert result.status == "success"
    assert result.input["data_file"] == "dcc:evidence.metric.items"
    assert "order-service" in ctx.metric_result.get("services_checked", [])


def test_metric_skill_populates_metric_result_from_dcc(monkeypatch) -> None:
    import app.skills.metric_check_skill as mskill_module
    from app.skills.metric_check_skill import MetricCheckSkill

    monkeypatch.setattr(mskill_module.adapter, "get_metrics", lambda **kw: [])
    monkeypatch.setattr(mskill_module.adapter, "get_data_source", lambda: "local_json")

    ctx = _make_ctx(_full_dcc([_SAMPLE_METRIC]))
    MetricCheckSkill().run(ctx)

    checked = ctx.metric_result.get("checked_metrics", [])
    assert any(m["metric_name"] == "cpu_usage_percent" for m in checked)


def test_metric_skill_fallback_when_dcc_metric_empty(monkeypatch) -> None:
    """When DCC metric bucket is empty, adapter.get_metrics must be called."""
    import app.skills.metric_check_skill as mskill_module
    from app.skills.metric_check_skill import MetricCheckSkill

    adapter_calls: list = []
    monkeypatch.setattr(mskill_module.adapter, "get_metrics", lambda **kw: (adapter_calls.append(kw) or []))
    monkeypatch.setattr(mskill_module.adapter, "get_data_source", lambda: "opensearch")

    ctx = _make_ctx(_full_dcc([], metric_availability="available"))
    result = MetricCheckSkill().run(ctx)

    assert adapter_calls, "adapter.get_metrics MUST be called when DCC metric items are empty"
    assert result.status == "success"
    assert any("empty" in log for log in result.execution_log)


def test_metric_skill_no_dcc_calls_adapter(monkeypatch) -> None:
    """Without DCC, the legacy/replay adapter path must be used."""
    import app.skills.metric_check_skill as mskill_module
    from app.skills.metric_check_skill import MetricCheckSkill

    adapter_calls: list = []
    monkeypatch.setattr(mskill_module.adapter, "get_metrics", lambda **kw: (adapter_calls.append(kw) or []))
    monkeypatch.setattr(mskill_module.adapter, "get_data_source", lambda: "opensearch")

    ctx = _make_ctx()
    result = MetricCheckSkill().run(ctx)

    assert adapter_calls, "adapter.get_metrics MUST be called when no DCC is present"
    assert result.status == "success"
    assert "dcc" not in result.input["data_file"]


def test_metric_skill_warns_and_logs_on_insufficient(monkeypatch) -> None:
    import app.skills.metric_check_skill as mskill_module
    from app.skills.metric_check_skill import MetricCheckSkill

    monkeypatch.setattr(mskill_module.adapter, "get_metrics", lambda **kw: [])
    monkeypatch.setattr(mskill_module.adapter, "get_data_source", lambda: "opensearch")

    ctx = _make_ctx(_full_dcc([_SAMPLE_METRIC], metric_availability="insufficient"))
    result = MetricCheckSkill().run(ctx)

    assert result.status == "success"
    assert "insufficient" in " ".join(result.execution_log)


def test_metric_skill_legacy_replay_label(monkeypatch) -> None:
    """OpenSearch fallback path uses correct label; local_json uses [legacy-replay]."""
    import app.skills.metric_check_skill as mskill_module
    from app.skills.metric_check_skill import MetricCheckSkill

    monkeypatch.setattr(mskill_module.adapter, "get_metrics", lambda **kw: [])
    monkeypatch.setattr(mskill_module.adapter, "get_data_source", lambda: "opensearch")

    ctx = _make_ctx()
    result = MetricCheckSkill().run(ctx)
    assert result.input["data_file"] == "opensearch:metric"


# ─── Combined Trace + Log + Metric all from DCC ──────────────────────────────

def test_trace_log_metric_all_from_dcc_no_adapter_calls(monkeypatch) -> None:
    """When DCC has trace, log, and metric items, no adapter calls should occur."""
    import app.skills.trace_analysis_skill as tskill_module
    import app.skills.log_analysis_skill as lskill_module
    import app.skills.metric_check_skill as mskill_module
    from app.skills.trace_analysis_skill import TraceAnalysisSkill
    from app.skills.log_analysis_skill import LogAnalysisSkill
    from app.skills.metric_check_skill import MetricCheckSkill

    trace_calls: list = []
    log_calls: list = []
    metric_calls: list = []

    monkeypatch.setattr(tskill_module.adapter, "get_traces", lambda **kw: (trace_calls.append(kw) or []))
    monkeypatch.setattr(tskill_module.adapter, "get_data_source", lambda: "local_json")
    monkeypatch.setattr(lskill_module.adapter, "get_logs", lambda **kw: (log_calls.append(kw) or []))
    monkeypatch.setattr(lskill_module.adapter, "get_data_source", lambda: "local_json")
    monkeypatch.setattr(mskill_module.adapter, "get_metrics", lambda **kw: (metric_calls.append(kw) or []))
    monkeypatch.setattr(mskill_module.adapter, "get_data_source", lambda: "local_json")

    dcc = _full_dcc(
        metric_items=[_SAMPLE_METRIC],
        metric_availability="available",
        trace_items=[_SAMPLE_SPAN],
        log_items=[_SAMPLE_LOG],
    )
    ctx = _make_ctx(dcc)
    ctx.query_context = {}

    t_result = TraceAnalysisSkill().run(ctx)
    l_result = LogAnalysisSkill().run(ctx)
    m_result = MetricCheckSkill().run(ctx)

    assert trace_calls == [], "adapter.get_traces must not be called with DCC traces"
    assert log_calls == [], "adapter.get_logs must not be called with DCC logs"
    assert metric_calls == [], "adapter.get_metrics must not be called with DCC metrics"
    assert t_result.input["data_file"] == "dcc:evidence.trace.items"
    assert l_result.input["data_file"] == "dcc:evidence.log.items"
    assert m_result.input["data_file"] == "dcc:evidence.metric.items"
    assert ctx.trace_result.get("trace_id") == "trace-dcc-001"
    assert ctx.log_result.get("upstream_service") == "order-service"
    assert "order-service" in ctx.metric_result.get("services_checked", [])


# ─── orchestrator-level DCC metric integration ───────────────────────────────

def test_orchestrator_dcc_metric_uses_resolver(monkeypatch) -> None:
    """Full orchestrator → MetricCheckSkill path: DCC metric items must be consumed."""
    from app.orchestrator import diagnosis_orchestrator
    from app.session import InMemoryDiagnosisSessionStore
    import app.skills.metric_check_skill as mskill_module
    from app.models.diagnosis import SkillResult as SR
    from app.skills.metric_check_skill import MetricCheckSkill

    metric_adapter_calls: list = []
    monkeypatch.setattr(mskill_module.adapter, "get_metrics", lambda **kw: (metric_adapter_calls.append(kw) or []))
    monkeypatch.setattr(mskill_module.adapter, "get_data_source", lambda: "local_json")

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
                ctx.report_result = {"report": "dcc-metric-test-done"}
            return SR(skill_name=self.skill_name, tool_name=self.tool_name, title=self.title,
                      status="success", summary="ok", input={}, output={}, evidence=[], execution_log=[], explanation="")

    import app.skills.trace_analysis_skill as tskill_module
    import app.skills.log_analysis_skill as lskill_module
    monkeypatch.setattr(tskill_module.adapter, "get_traces", lambda **kw: [])
    monkeypatch.setattr(tskill_module.adapter, "get_data_source", lambda: "local_json")
    monkeypatch.setattr(lskill_module.adapter, "get_logs", lambda **kw: [])
    monkeypatch.setattr(lskill_module.adapter, "get_data_source", lambda: "local_json")

    pipeline = [
        _NopSkill("AlertContextSkill", "MModelSkill/set_time_range"),
        _NopSkill("TraceAnalysisSkill", "MModelSkill/analyze_trace"),
        _NopSkill("EntityBindingSkill", "MModelSkill/bind_entities"),
        _NopSkill("LogAnalysisSkill", "MModelSkill/analyze_log"),
        MetricCheckSkill(),  # ← real skill
        _NopSkill("GraphAnalysisSkill", "MModelSkill/query_graph"),
        _NopSkill("RootCauseSkill", "MModelSkill/locate_root_cause"),
        _NopSkill("ImpactAnalysisSkill", "MModelSkill/analyze_impact"),
        _NopSkill("ReportSkill", "MModelSkill/generate_report"),
    ]
    monkeypatch.setattr(diagnosis_orchestrator, "SKILL_PIPELINE", pipeline)

    dcc = _full_dcc([_SAMPLE_METRIC])
    response = diagnosis_orchestrator.run_diagnosis(
        api="",
        time="",
        symptom="",
        dcc=dcc,
        session_store=InMemoryDiagnosisSessionStore(),
    )

    assert metric_adapter_calls == [], "adapter.get_metrics must not be called when DCC has metric items"
    metric_skill_result = next(
        (s for s in response.skills if s.skill_name == "MetricCheckSkill"), None
    )
    assert metric_skill_result is not None
    assert metric_skill_result.input["data_file"] == "dcc:evidence.metric.items"


# ─── legacy replay path must still work ──────────────────────────────────────

def test_legacy_replay_path_unbroken(monkeypatch) -> None:
    """The legacy/replay adapter path (case_id / data_dir) must continue to work."""
    import app.skills.metric_check_skill as mskill_module
    from app.skills.metric_check_skill import MetricCheckSkill

    monkeypatch.setattr(mskill_module.adapter, "get_metrics", lambda **kw: [_SAMPLE_METRIC])
    monkeypatch.setattr(mskill_module.adapter, "get_data_source", lambda: "opensearch")

    ctx = _make_ctx()
    ctx.case_id = "mock-case"
    result = MetricCheckSkill().run(ctx)

    assert result.status == "success"
    checked = ctx.metric_result.get("checked_metrics", [])
    assert any(m["metric_name"] == "cpu_usage_percent" for m in checked)
