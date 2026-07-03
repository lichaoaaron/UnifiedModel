import os
import sys


REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
BACKEND_ROOT = os.path.join(REPO_ROOT, "backend")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)


from app.models.diagnosis import SkillResult
from app.orchestrator import diagnosis_orchestrator
from app.session import InMemoryDiagnosisSessionStore


class _FakeSkill:
    def __init__(self, skill_name: str, tool_name: str) -> None:
        self.skill_name = skill_name
        self.tool_name = tool_name
        self.title = skill_name

    def run(self, ctx):
        output = {"skill": self.skill_name}
        if self.skill_name == "AlertContextSkill":
            ctx.query_context = {"alert_api": ctx.api, "time_window": {"start": ctx.time, "end": ctx.time}}
            output = ctx.query_context
        elif self.skill_name == "TraceAnalysisSkill":
            ctx.trace_result = {
                "trace_id": "trace-unit",
                "service_call": "source-service -> target-service",
                "call_path": ["source-service:/entry", "target-service:/work"],
                "root_candidates": [],
                "entry_api": ctx.api,
                "first_error_api": "/work",
            }
            output = ctx.trace_result
        elif self.skill_name == "EntityBindingSkill":
            ctx.entity_binding_result = {"services": ["source-service", "target-service"], "binding_count": 2}
            output = ctx.entity_binding_result
        elif self.skill_name == "LogAnalysisSkill":
            ctx.log_result = {"root_candidates": [], "propagation_logs": [], "upstream_service": "source-service"}
            output = ctx.log_result
        elif self.skill_name == "MetricCheckSkill":
            ctx.metric_result = {"metric_root_candidates": [], "conclusion": "metrics checked"}
            output = ctx.metric_result
        elif self.skill_name == "GraphAnalysisSkill":
            ctx.graph_result = {
                "nodes": [{"id": "source-service", "node_type": "Service"}, {"id": "target-service", "node_type": "Service"}],
                "edges": [{"source": "source-service", "target": "target-service", "label": "calls"}],
                "interface_edges": [],
            }
            output = ctx.graph_result
        elif self.skill_name == "RootCauseSkill":
            ctx.root_cause_result = {
                "root_cause_service": "target-service",
                "root_cause_api": "/work",
                "root_cause_type": "service_exception",
                "exception_type": "RuntimeError",
                "bad_param": "",
                "is_confirmed": True,
                "scoring_reason": "unit scoring reason",
            }
            output = ctx.root_cause_result
        elif self.skill_name == "ImpactAnalysisSkill":
            ctx.impact_result = {
                "affected_services": ["source-service"],
                "affected_apis": [ctx.api],
                "affected_business": ["generic business capability"],
            }
            output = ctx.impact_result
        elif self.skill_name == "ReportSkill":
            ctx.report_result = {"report": "target-service is the primary root-cause candidate."}
            output = ctx.report_result

        return SkillResult(
            skill_name=self.skill_name,
            tool_name=self.tool_name,
            title=self.title,
            status="success",
            summary=f"{self.skill_name} done",
            input={},
            output=output,
            evidence=[],
            execution_log=[],
            explanation="",
        )


def _fake_pipeline() -> list[_FakeSkill]:
    return [
        _FakeSkill("AlertContextSkill", "MModelSkill/set_time_range"),
        _FakeSkill("TraceAnalysisSkill", "MModelSkill/analyze_trace"),
        _FakeSkill("EntityBindingSkill", "MModelSkill/bind_entities"),
        _FakeSkill("LogAnalysisSkill", "MModelSkill/analyze_log"),
        _FakeSkill("MetricCheckSkill", "MModelSkill/check_metrics"),
        _FakeSkill("GraphAnalysisSkill", "MModelSkill/query_graph"),
        _FakeSkill("RootCauseSkill", "MModelSkill/locate_root_cause"),
        _FakeSkill("ImpactAnalysisSkill", "MModelSkill/analyze_impact"),
        _FakeSkill("ReportSkill", "MModelSkill/generate_report"),
    ]


def _minimal_dcc() -> dict:
    return {
        "protocol_version": "dcc.v0.1",
        "context_id": "dcc-test",
        "generated_at": "2026-01-01T00:00:00Z",
        "workspace": {"workspace_id": "demo"},
        "alert": {
            "api": "/dcc/entry",
            "time": "2026-05-25 10:00:00",
            "symptom": "HTTP 500 spike",
        },
        "objects": {
            "entities": [],
            "relations": [],
            "topology": {"nodes": [], "edges": []},
        },
        "evidence": {
            "trace": {"availability": "empty", "items": []},
            "log": {"availability": "empty", "items": []},
            "metric": {"availability": "empty", "items": []},
        },
        "candidates": {"root_cause": [], "impact_scope": []},
        "provenance": {"producer": "unit-test"},
        "meta": {"availability": "available", "warnings": []},
    }


def test_orchestrator_initial_diagnosis_uses_runbook_metadata(monkeypatch):
    monkeypatch.setattr(diagnosis_orchestrator, "SKILL_PIPELINE", _fake_pipeline())
    monkeypatch.setattr(diagnosis_orchestrator, "resolve_request_context", lambda **kwargs: (kwargs.get("case_id"), kwargs.get("data_dir")))

    response = diagnosis_orchestrator.run_diagnosis(
        api="/unit/entry",
        time="2026-05-25 10:00:00",
        symptom="HTTP 500 spike",
        case_id="unit-case",
        session_store=InMemoryDiagnosisSessionStore(),
    )

    assert [skill.skill_name for skill in response.skills] == diagnosis_orchestrator.DEFAULT_RUNBOOK.skill_names()
    for skill_result in response.skills:
        metadata = skill_result.input["runbook"]
        assert metadata["observation"]
        assert metadata["conclusion"]
        assert metadata["evidence"]
        assert metadata["skill_binding"]["skill_name"] == skill_result.skill_name

    skill_messages = [message for message in response.messages if message.type == "skill_call"]
    assert skill_messages
    assert skill_messages[0].input["runbook"]["observation"]
    assert response.final_report == "target-service is the primary root-cause candidate."


def test_orchestrator_uses_dcc_path_without_legacy_resolution(monkeypatch):
    monkeypatch.setattr(diagnosis_orchestrator, "SKILL_PIPELINE", _fake_pipeline())

    def _should_not_call_legacy(**kwargs):
        raise AssertionError("legacy resolve_request_context should not be called when dcc is provided")

    monkeypatch.setattr(diagnosis_orchestrator, "resolve_request_context", _should_not_call_legacy)

    response = diagnosis_orchestrator.run_diagnosis(
        api="",
        time="",
        symptom="",
        dcc=_minimal_dcc(),
        session_store=InMemoryDiagnosisSessionStore(),
    )

    assert response.summary.impact_api == "/dcc/entry"
    assert response.skills


def test_orchestrator_without_dcc_still_uses_legacy_resolution(monkeypatch):
    monkeypatch.setattr(diagnosis_orchestrator, "SKILL_PIPELINE", _fake_pipeline())
    called = {"value": False}

    def _legacy_resolver(**kwargs):
        called["value"] = True
        return kwargs.get("case_id") or "legacy-case", kwargs.get("data_dir")

    monkeypatch.setattr(diagnosis_orchestrator, "resolve_request_context", _legacy_resolver)

    response = diagnosis_orchestrator.run_diagnosis(
        api="/legacy/entry",
        time="2026-05-25 10:00:00",
        symptom="legacy flow",
        session_store=InMemoryDiagnosisSessionStore(),
    )

    assert called["value"] is True
    assert response.case_id == "legacy-case"
