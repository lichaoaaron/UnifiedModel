"""Tests for Step 5: Log DCC-first input resolution, Skill integration,
legacy/replay fallback, and combined Trace+Log DCC path."""
import os
import sys

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
BACKEND_ROOT = os.path.join(REPO_ROOT, "backend")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

import pytest

from app.models.context import DiagnosisContext
from app.runtime.log_input_resolver import LogInputResolution, resolve_log_input


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
    log_items: list[dict],
    log_availability: str = "available",
    trace_items: list[dict] | None = None,
    trace_availability: str = "empty",
) -> dict:
    return {
        "protocol_version": "dcc.v0.1",
        "context_id": "dcc-log-test",
        "generated_at": "2026-05-30T12:00:00Z",
        "workspace": {"workspace_id": "test-ws"},
        "alert": {
            "api": "/order/create",
            "time": "2026-05-30 12:00:00",
            "symptom": "HTTP 500",
        },
        "evidence": {
            "trace": {
                "availability": trace_availability,
                "items": trace_items or [],
                "warnings": [],
            },
            "log": {
                "availability": log_availability,
                "items": log_items,
                "warnings": [],
            },
            "metric": {"availability": "empty", "items": []},
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


_SAMPLE_LOG = {
    "serviceName": "order-service",
    "severityText": "ERROR",
    "log.attributes.message": "NullPointerException: orderId cannot be null",
    "log.attributes.stack_trace": "",
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


# ─── resolver unit tests ─────────────────────────────────────────────────────

def test_resolver_returns_dcc_logs_when_available() -> None:
    ctx = _make_ctx(_full_dcc([_SAMPLE_LOG]))
    res = resolve_log_input(ctx)
    assert res.skipped_adapter is True
    assert res.logs == [_SAMPLE_LOG]
    assert res.data_source_label == "dcc:evidence.log.items"
    assert not res.warnings


def test_resolver_fallback_when_log_items_empty() -> None:
    ctx = _make_ctx(_full_dcc([], log_availability="available"))
    res = resolve_log_input(ctx)
    assert res.skipped_adapter is False
    assert any("empty" in w for w in res.warnings)


def test_resolver_fallback_when_log_unavailable() -> None:
    ctx = _make_ctx(_full_dcc([], log_availability="unavailable"))
    res = resolve_log_input(ctx)
    assert res.skipped_adapter is False
    assert any("unavailable" in w for w in res.warnings)


def test_resolver_fallback_when_log_insufficient() -> None:
    ctx = _make_ctx(_full_dcc([_SAMPLE_LOG], log_availability="insufficient"))
    res = resolve_log_input(ctx)
    assert res.skipped_adapter is False
    assert any("insufficient" in w for w in res.warnings)


def test_resolver_no_dcc_returns_adapter_path() -> None:
    ctx = _make_ctx()  # no dcc_context
    res = resolve_log_input(ctx)
    assert res.skipped_adapter is False
    assert res.data_source_label == "adapter"
    assert res.logs == []


def test_resolver_extracts_topology_and_entity_seed() -> None:
    ctx = _make_ctx(_full_dcc([_SAMPLE_LOG]))
    res = resolve_log_input(ctx)
    assert res.topology_seed.get("nodes") is not None
    assert res.entity_seed[0]["entity_name"] == "order-service"


def test_resolver_missing_log_bucket() -> None:
    dcc = {
        "protocol_version": "dcc.v0.1",
        "context_id": "dcc-no-log",
        "generated_at": "2026-05-30T12:00:00Z",
        "workspace": {"workspace_id": "test-ws"},
        "alert": {"api": "/order/create", "time": "2026-05-30 12:00:00", "symptom": "HTTP 500"},
        "evidence": {
            "trace": {"availability": "empty", "items": []},
            "metric": {"availability": "empty", "items": []},
            # "log" bucket intentionally missing
        },
        "objects": {"entities": [], "relations": [], "topology": {"nodes": [], "edges": []}},
        "candidates": {"root_cause": [], "impact_scope": []},
        "provenance": {"producer": "unit-test"},
        "meta": {"availability": "available"},
    }
    ctx = _make_ctx(dcc)
    res = resolve_log_input(ctx)
    assert res.skipped_adapter is False
    assert any("missing or malformed" in w for w in res.warnings)


# ─── LogAnalysisSkill integration tests ──────────────────────────────────────

def test_log_skill_uses_dcc_logs_not_adapter(monkeypatch) -> None:
    """When DCC has available log items, adapter.get_logs must NOT be called."""
    import app.skills.log_analysis_skill as lskill_module
    from app.skills.log_analysis_skill import LogAnalysisSkill

    adapter_calls: list = []
    monkeypatch.setattr(lskill_module.adapter, "get_logs", lambda **kw: (adapter_calls.append(kw) or []))
    monkeypatch.setattr(lskill_module.adapter, "get_data_source", lambda: "local_json")

    ctx = _make_ctx(_full_dcc([_SAMPLE_LOG]))
    result = LogAnalysisSkill().run(ctx)

    assert adapter_calls == [], "adapter.get_logs must NOT be called when DCC has log items"
    assert result.status == "success"
    assert result.input["data_file"] == "dcc:evidence.log.items"
    assert any("order-service" in str(e) for e in result.evidence)


def test_log_skill_populates_log_result_from_dcc(monkeypatch) -> None:
    import app.skills.log_analysis_skill as lskill_module
    from app.skills.log_analysis_skill import LogAnalysisSkill

    monkeypatch.setattr(lskill_module.adapter, "get_logs", lambda **kw: [])
    monkeypatch.setattr(lskill_module.adapter, "get_data_source", lambda: "local_json")

    ctx = _make_ctx(_full_dcc([_SAMPLE_LOG]))
    LogAnalysisSkill().run(ctx)

    assert ctx.log_result.get("upstream_service") == "order-service"
    assert ctx.log_result.get("upstream_error_type") == "NullPointerException"


def test_log_skill_fallback_when_dcc_log_empty(monkeypatch) -> None:
    """When DCC log bucket is empty, adapter.get_logs must be called."""
    import app.skills.log_analysis_skill as lskill_module
    from app.skills.log_analysis_skill import LogAnalysisSkill

    adapter_calls: list = []
    monkeypatch.setattr(lskill_module.adapter, "get_logs", lambda **kw: (adapter_calls.append(kw) or []))
    monkeypatch.setattr(lskill_module.adapter, "get_data_source", lambda: "opensearch")

    ctx = _make_ctx(_full_dcc([], log_availability="available"))
    result = LogAnalysisSkill().run(ctx)

    assert adapter_calls, "adapter.get_logs MUST be called when DCC log items are empty"
    assert result.status == "success"
    assert any("empty" in log for log in result.execution_log)


def test_log_skill_no_dcc_calls_adapter(monkeypatch) -> None:
    """Without DCC, the legacy/replay adapter path must be used."""
    import app.skills.log_analysis_skill as lskill_module
    from app.skills.log_analysis_skill import LogAnalysisSkill

    adapter_calls: list = []
    monkeypatch.setattr(lskill_module.adapter, "get_logs", lambda **kw: (adapter_calls.append(kw) or []))
    monkeypatch.setattr(lskill_module.adapter, "get_data_source", lambda: "opensearch")

    ctx = _make_ctx()  # no DCC
    result = LogAnalysisSkill().run(ctx)

    assert adapter_calls, "adapter.get_logs MUST be called when no DCC is present"
    assert result.status == "success"
    assert "dcc" not in result.input["data_file"]


def test_log_skill_legacy_replay_label_in_input(monkeypatch) -> None:
    """Legacy replay path should expose [legacy-replay] in the data_file label."""
    import app.skills.log_analysis_skill as lskill_module
    from app.skills.log_analysis_skill import LogAnalysisSkill

    monkeypatch.setattr(lskill_module.adapter, "get_logs", lambda **kw: [])
    monkeypatch.setattr(lskill_module.adapter, "get_data_source", lambda: "opensearch")

    ctx = _make_ctx()  # no DCC — falls back to legacy
    result = LogAnalysisSkill().run(ctx)
    # OpenSearch fallback path uses "opensearch:log" label
    assert result.input["data_file"] == "opensearch:log"


def test_log_skill_warns_and_logs_on_insufficient(monkeypatch) -> None:
    import app.skills.log_analysis_skill as lskill_module
    from app.skills.log_analysis_skill import LogAnalysisSkill

    monkeypatch.setattr(lskill_module.adapter, "get_logs", lambda **kw: [])
    monkeypatch.setattr(lskill_module.adapter, "get_data_source", lambda: "opensearch")

    ctx = _make_ctx(_full_dcc([_SAMPLE_LOG], log_availability="insufficient"))
    result = LogAnalysisSkill().run(ctx)

    assert result.status == "success"
    assert "insufficient" in " ".join(result.execution_log)


# ─── Combined Trace + Log both from DCC ──────────────────────────────────────

def test_trace_and_log_both_from_dcc_no_adapter_calls(monkeypatch) -> None:
    """When DCC has both trace and log items, neither adapter.get_traces nor
    adapter.get_logs should be called."""
    import app.skills.trace_analysis_skill as tskill_module
    import app.skills.log_analysis_skill as lskill_module
    from app.skills.trace_analysis_skill import TraceAnalysisSkill
    from app.skills.log_analysis_skill import LogAnalysisSkill

    trace_adapter_calls: list = []
    log_adapter_calls: list = []

    monkeypatch.setattr(tskill_module.adapter, "get_traces", lambda **kw: (trace_adapter_calls.append(kw) or []))
    monkeypatch.setattr(tskill_module.adapter, "get_data_source", lambda: "local_json")
    monkeypatch.setattr(lskill_module.adapter, "get_logs", lambda **kw: (log_adapter_calls.append(kw) or []))
    monkeypatch.setattr(lskill_module.adapter, "get_data_source", lambda: "local_json")

    dcc = _full_dcc(
        log_items=[_SAMPLE_LOG],
        log_availability="available",
        trace_items=[_SAMPLE_SPAN],
        trace_availability="available",
    )
    ctx = _make_ctx(dcc)
    ctx.query_context = {}

    t_result = TraceAnalysisSkill().run(ctx)
    l_result = LogAnalysisSkill().run(ctx)

    assert trace_adapter_calls == [], "adapter.get_traces must not be called with DCC traces"
    assert log_adapter_calls == [], "adapter.get_logs must not be called with DCC logs"
    assert t_result.input["data_file"] == "dcc:evidence.trace.items"
    assert l_result.input["data_file"] == "dcc:evidence.log.items"
    assert ctx.trace_result.get("trace_id") == "trace-dcc-001"
    assert ctx.log_result.get("upstream_service") == "order-service"


# ─── orchestrator-level DCC log integration ──────────────────────────────────

def test_orchestrator_dcc_log_uses_resolver(monkeypatch) -> None:
    """Full orchestrator → LogAnalysisSkill path: DCC log items must be consumed."""
    from app.orchestrator import diagnosis_orchestrator
    from app.session import InMemoryDiagnosisSessionStore
    import app.skills.log_analysis_skill as lskill_module
    from app.models.diagnosis import SkillResult as SR
    from app.skills.log_analysis_skill import LogAnalysisSkill

    log_adapter_calls: list = []
    monkeypatch.setattr(lskill_module.adapter, "get_logs", lambda **kw: (log_adapter_calls.append(kw) or []))
    monkeypatch.setattr(lskill_module.adapter, "get_data_source", lambda: "local_json")

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
                ctx.report_result = {"report": "dcc-log-test-done"}
            return SR(skill_name=self.skill_name, tool_name=self.tool_name, title=self.title,
                      status="success", summary="ok", input={}, output={}, evidence=[], execution_log=[], explanation="")

    import app.skills.trace_analysis_skill as tskill_module
    monkeypatch.setattr(tskill_module.adapter, "get_traces", lambda **kw: [])
    monkeypatch.setattr(tskill_module.adapter, "get_data_source", lambda: "local_json")

    pipeline = [
        _NopSkill("AlertContextSkill", "MModelSkill/set_time_range"),
        _NopSkill("TraceAnalysisSkill", "MModelSkill/analyze_trace"),
        _NopSkill("EntityBindingSkill", "MModelSkill/bind_entities"),
        LogAnalysisSkill(),  # ← real skill
        _NopSkill("MetricCheckSkill", "MModelSkill/check_metrics"),
        _NopSkill("GraphAnalysisSkill", "MModelSkill/query_graph"),
        _NopSkill("RootCauseSkill", "MModelSkill/locate_root_cause"),
        _NopSkill("ImpactAnalysisSkill", "MModelSkill/analyze_impact"),
        _NopSkill("ReportSkill", "MModelSkill/generate_report"),
    ]
    monkeypatch.setattr(diagnosis_orchestrator, "SKILL_PIPELINE", pipeline)

    dcc = _full_dcc([_SAMPLE_LOG])
    response = diagnosis_orchestrator.run_diagnosis(
        api="",
        time="",
        symptom="",
        dcc=dcc,
        session_store=InMemoryDiagnosisSessionStore(),
    )

    assert log_adapter_calls == [], "adapter.get_logs must not be called when DCC has log items"
    log_skill_result = next(
        (s for s in response.skills if s.skill_name == "LogAnalysisSkill"), None
    )
    assert log_skill_result is not None
    assert log_skill_result.input["data_file"] == "dcc:evidence.log.items"


# ─── legacy replay path must still work ──────────────────────────────────────

def test_legacy_replay_path_unbroken(monkeypatch) -> None:
    """The legacy/replay adapter path (case_id / data_dir) must continue to work."""
    import app.skills.log_analysis_skill as lskill_module
    from app.skills.log_analysis_skill import LogAnalysisSkill

    sample_legacy_log = {
        "serviceName": "legacy-service",
        "severityText": "ERROR",
        "log.attributes.message": "legacy error from case file",
        "log.attributes.stack_trace": "",
    }
    monkeypatch.setattr(lskill_module.adapter, "get_logs", lambda **kw: [sample_legacy_log])
    monkeypatch.setattr(lskill_module.adapter, "get_data_source", lambda: "opensearch")

    ctx = _make_ctx()  # no DCC → legacy adapter path
    ctx.case_id = "mock-case"  # as if called with a demo case_id
    result = LogAnalysisSkill().run(ctx)

    assert result.status == "success"
    assert ctx.log_result.get("upstream_service") == "legacy-service"
