from __future__ import annotations

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.diagnosis import SkillResult
from app.orchestrator import diagnosis_orchestrator
from app.orchestrator import intent_router
from app.orchestrator.llm_diagnosis_orchestrator import stream_agentic_diagnosis
from app.repositories.contracts import RepositoryResult
from app.session import (
    InMemoryDiagnosisSessionStore,
    resolve_context_reference,
    update_session_from_observability_query,
    update_session_from_context,
)


def _fake_ctx() -> SimpleNamespace:
    return SimpleNamespace(
        api="/api/checkout",
        time="2026-05-22 10:00:00",
        symptom="HTTP 500 spike",
        case_id="case-a",
        data_dir=None,
        query_context={"alert_api": "/api/checkout", "time_window": {"start": "t1", "end": "t2"}},
        trace_result={"trace_id": "trace-1", "entry_trace_id": "trace-entry", "service_map_trace_id": "trace-entry"},
        log_result={},
        metric_result={"red_metrics": [{"service_name": "payment-service", "overall_anomaly_score": 0.92}]},
        graph_result={
            "call_edges": [
                {"source_service": "checkout-service", "target_service": "payment-service", "error_rate": 1.0},
                {"source_service": "payment-service", "target_service": "bank-service", "error_rate": 1.0},
            ]
        },
        root_cause_result={
            "root_cause_service": "payment-service",
            "root_cause_api": "/payment/charge",
            "root_cause_type": "service_exception",
            "confidence": "high",
            "candidates": [
                {"service": "payment-service", "score": 0.91, "evidence": "RED error and duration elevated"},
                {"service": "checkout-service", "score": 0.42, "evidence": "Upstream propagation"},
            ],
        },
        impact_result={
            "affected_services": ["checkout-service", "payment-service"],
            "business_impact": {
                "affected_order_count": "unknown",
                "failed_transaction_count": 1,
                "affected_user_count": "unknown",
                "estimated_revenue_impact": "unknown",
                "confidence": "medium",
                "evidence_links": {
                    "trace_ids": ["trace-1"],
                    "log_ids": ["log-9"],
                    "metric_refs": ["payment-service:red"],
                    "service_map_edges": [{"source_service": "checkout-service", "target_service": "payment-service"}],
                },
            },
        },
    )


def test_session_memory_updates_from_completed_context() -> None:
    store = InMemoryDiagnosisSessionStore()
    session = store.create_session()

    updated = update_session_from_context(
        session,
        _fake_ctx(),
        user_message="请分析 /api/checkout 的 HTTP 500 spike",
        assistant_message="payment-service 是首要根因候选。",
        store=store,
    )

    assert updated.current_focus.service_name == "payment-service"
    assert updated.business_impact_summary["failed_transaction_count"] == 1
    assert "checkout-service" in updated.impacted_services
    assert "trace-1" in updated.related_trace_ids
    assert "log-9" in updated.related_log_ids
    assert "payment-service:red" in updated.related_metric_refs
    assert updated.root_cause_candidates[0]["service_name"] == "payment-service"


def test_resolver_uses_current_focus_for_pronouns_and_business_impact() -> None:
    store = InMemoryDiagnosisSessionStore()
    session = update_session_from_context(
        store.create_session(),
        _fake_ctx(),
        user_message="先看根因",
        assistant_message="payment-service 异常。",
        store=store,
    )

    log_resolution = resolve_context_reference("继续看它的日志", session)
    impact_resolution = resolve_context_reference("影响了多少订单？", session)

    assert log_resolution["resolved_type"] == "service"
    assert log_resolution["resolved_value"] == "payment-service"
    assert impact_resolution["resolved_type"] == "business_impact"
    assert impact_resolution["service_name"] == "payment-service"


def test_resolver_switches_focus_when_service_is_explicit() -> None:
    store = InMemoryDiagnosisSessionStore()
    session = update_session_from_context(
        store.create_session(),
        _fake_ctx(),
        user_message="先看根因",
        assistant_message="payment-service 异常。",
        store=store,
    )

    resolution = resolve_context_reference("那 checkout 呢？", session)

    assert resolution["resolved_type"] == "service"
    assert resolution["resolved_value"] == "checkout-service"
    assert session.current_focus.service_name == "checkout-service"


def test_resolver_requests_clarification_when_pronoun_has_no_focus() -> None:
    store = InMemoryDiagnosisSessionStore()
    session = store.create_session()

    resolution = resolve_context_reference("继续看它的日志", session)

    assert resolution["needs_clarification"] is True
    assert "请指定" in resolution["clarification_question"]


class _FakeSkill:
    def __init__(self, skill_name: str):
        self.skill_name = skill_name
        self.tool_name = f"MModelSkill/{skill_name}"
        self.title = skill_name

    def run(self, ctx):
        if self.skill_name == "AlertContextSkill":
            ctx.query_context = {"alert_api": ctx.api, "time_window": {"start": ctx.time, "end": ctx.time}}
            output = ctx.query_context
        elif self.skill_name == "TraceAnalysisSkill":
            ctx.trace_result = {"trace_id": "trace-1", "call_path": ["checkout-service:/api/checkout", "payment-service:/payment/charge"]}
            output = ctx.trace_result
        elif self.skill_name == "EntityBindingSkill":
            ctx.entity_binding_result = {"services": ["checkout-service", "payment-service"], "binding_count": 2}
            output = ctx.entity_binding_result
        elif self.skill_name == "LogAnalysisSkill":
            ctx.log_result = {"root_candidates": []}
            output = ctx.log_result
        elif self.skill_name == "MetricCheckSkill":
            ctx.metric_result = {"red_metrics": [{"service_name": "payment-service", "overall_anomaly_score": 0.9}], "conclusion": "RED 异常"}
            output = ctx.metric_result
        elif self.skill_name == "GraphAnalysisSkill":
            ctx.graph_result = {
                "nodes": [{"id": "checkout-service"}, {"id": "payment-service"}],
                "edges": [{"source": "checkout-service", "target": "payment-service", "label": "calls"}],
                "call_edges": [{"source_service": "checkout-service", "target_service": "payment-service"}],
            }
            output = ctx.graph_result
        elif self.skill_name == "RootCauseSkill":
            ctx.root_cause_result = {
                "root_cause_service": "payment-service",
                "root_cause_api": "/payment/charge",
                "root_cause_type": "service_exception",
                "exception_type": "TimeoutError",
                "bad_param": "",
                "confidence": "high",
                "candidates": [{"service": "payment-service", "score": 0.9, "evidence": "RED 异常"}],
                "scoring_reason": "payment-service score=0.9",
                "is_confirmed": True,
            }
            output = ctx.root_cause_result
        elif self.skill_name == "ImpactAnalysisSkill":
            ctx.impact_result = {
                "affected_services": ["checkout-service"],
                "affected_apis": ["/api/checkout"],
                "affected_business": ["checkout"],
                "business_impact": {"failed_transaction_count": 1, "confidence": "medium", "evidence_links": {"trace_ids": ["trace-1"]}},
            }
            output = ctx.impact_result
        else:
            ctx.report_result = {"report": "payment-service 是首要根因候选。"}
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


class _FakeLogRepository:
    def get_error_logs(self, service_name=None, time_range=None, *, data_dir=None, case_id=None):
        return RepositoryResult(source="test", query_context={"service": service_name}, items=[{
            "serviceName": service_name or "payment-service",
            "severityText": "ERROR",
            "log.attributes.message": "payment timeout while charging order",
        }])


class _FakeMetricRepository:
    def get_red_metrics(self, service_name=None, time_range=None, *, data_dir=None, case_id=None):
        return RepositoryResult(source="test", query_context={"service": service_name}, items=[{
            "service_name": service_name or "payment-service",
            "error": {"error_count": 3, "log_error_count": 1, "total_count": 10, "error_rate": 0.3},
            "duration": {"p95_duration_ms": 1500},
            "overall_anomaly_score": 0.9,
            "evidence_summary": ["error_rate=0.3"],
        }])

    def get_all_services_red_metrics(self, time_range=None, *, data_dir=None, case_id=None):
        return RepositoryResult(source="test", query_context={}, items=[
            {
                "service_name": "payment-service",
                "error": {"error_count": 0, "log_error_count": 52, "total_count": 10, "error_rate": 0.0},
                "duration": {"p95_duration_ms": None},
                "overall_anomaly_score": 0.45,
                "evidence_summary": ["payment log errors"],
            },
            {
                "service_name": "checkout-service",
                "error": {"error_count": 1, "log_error_count": 0, "total_count": 20, "error_rate": 0.05},
                "duration": {"p95_duration_ms": 300},
                "overall_anomaly_score": 0.2,
                "evidence_summary": ["checkout minor errors"],
            },
        ])


class _FakeBusinessImpactRepository:
    def get_business_impact(self, service_name=None, time_range=None, *, query=None, data_dir=None, case_id=None):
        return RepositoryResult(source="test", query_context={"service": service_name}, items=[{
            "affected_order_count": "unknown",
            "failed_transaction_count": 2,
            "affected_user_count": "unknown",
            "estimated_revenue_impact": "unknown",
            "confidence": "medium",
            "evidence_links": {"trace_ids": ["trace-1"]},
        }])


def test_orchestrator_returns_session_memory_metadata(monkeypatch) -> None:
    store = InMemoryDiagnosisSessionStore()
    monkeypatch.setattr(
        diagnosis_orchestrator,
        "SKILL_PIPELINE",
        [
            _FakeSkill("AlertContextSkill"),
            _FakeSkill("TraceAnalysisSkill"),
            _FakeSkill("EntityBindingSkill"),
            _FakeSkill("LogAnalysisSkill"),
            _FakeSkill("MetricCheckSkill"),
            _FakeSkill("GraphAnalysisSkill"),
            _FakeSkill("RootCauseSkill"),
            _FakeSkill("ImpactAnalysisSkill"),
            _FakeSkill("ReportSkill"),
        ],
    )
    monkeypatch.setattr(diagnosis_orchestrator, "resolve_request_context", lambda **kwargs: (kwargs.get("case_id"), kwargs.get("data_dir")))
    monkeypatch.setattr(intent_router, "get_log_repository", lambda: _FakeLogRepository())

    response = diagnosis_orchestrator.run_diagnosis(
        api="/api/checkout",
        time="2026-05-22 10:00:00",
        symptom="HTTP 500 spike",
        case_id="case-a",
        session_store=store,
    )

    assert response.session_id
    assert response.current_focus["service_name"] == "payment-service"
    assert response.memory_summary["business_impact_summary"]["failed_transaction_count"] == 1
    assert store.get_session(response.session_id).current_focus.service_name == "payment-service"  # type: ignore[union-attr]

    follow_up = diagnosis_orchestrator.run_diagnosis(
        api="/unknown",
        time="",
        symptom="",
        case_id="case-a",
        session_id=response.session_id,
        message="继续看它的日志",
        session_store=store,
    )

    assert follow_up.resolved_context["resolved_type"] == "service"
    assert follow_up.resolved_context["resolved_value"] == "payment-service"
    assert follow_up.session_id == response.session_id
    assert follow_up.intent == "followup_inspect_logs"
    assert follow_up.executed_skills == ["analyze_log"]


def test_followup_metrics_and_business_impact_only_run_needed_skill(monkeypatch) -> None:
    store = InMemoryDiagnosisSessionStore()
    session = update_session_from_context(
        store.create_session(),
        _fake_ctx(),
        user_message="首轮诊断",
        assistant_message="payment-service 是首要根因候选。",
        store=store,
    )
    monkeypatch.setattr(intent_router, "get_metric_repository", lambda: _FakeMetricRepository())
    monkeypatch.setattr(intent_router, "get_business_impact_repository", lambda: _FakeBusinessImpactRepository())

    metrics = diagnosis_orchestrator.run_diagnosis(
        api="",
        time="",
        symptom="",
        session_id=session.session_id,
        message="继续看它的指标",
        mode="diagnosis",
        session_store=store,
    )
    impact = diagnosis_orchestrator.run_diagnosis(
        api="",
        time="",
        symptom="",
        session_id=session.session_id,
        message="影响了多少订单？",
        session_store=store,
    )

    assert metrics.intent == "followup_inspect_metrics"
    assert metrics.executed_skills == ["check_metrics"]
    assert impact.intent == "followup_inspect_business_impact"
    assert impact.executed_skills == ["analyze_impact"]


def test_observability_query_sets_top1_focus_and_followup_rank(monkeypatch) -> None:
    store = InMemoryDiagnosisSessionStore()
    monkeypatch.setattr(intent_router, "get_metric_repository", lambda: _FakeMetricRepository())
    monkeypatch.setattr(intent_router, "get_log_repository", lambda: _FakeLogRepository())

    query = diagnosis_orchestrator.run_diagnosis(
        api="",
        time="",
        symptom="",
        case_id="case-a",
        message="过去15分钟哪些服务出现最多的异常？",
        session_store=store,
    )

    assert query.intent == "observability_query"
    assert query.executed_skills == ["observability_query"]
    assert query.current_focus["service_name"] == "payment-service"
    assert query.answer.startswith("过去 15 分钟内，payment-service 的异常最突出。")
    assert "日志异常数量明显高于其他服务" in query.answer
    assert "RED error_rate 暂未显示异常" in query.answer
    assert "| 排名 | 服务 | 日志异常数 | Error Rate | P95 | 评分 | 判断 |" in query.answer
    assert "暂无数据" in query.answer
    assert "None" not in query.answer
    assert "unknown" not in query.answer
    assert "看第一名的日志" in query.answer

    follow_up = diagnosis_orchestrator.run_diagnosis(
        api="",
        time="",
        symptom="",
        case_id="case-a",
        session_id=query.session_id,
        message="看第一名的日志",
        session_store=store,
    )

    assert follow_up.intent == "followup_inspect_logs"
    assert follow_up.resolved_context["resolved_value"] == "payment-service"
    assert follow_up.executed_skills == ["analyze_log"]
    assert "这次只查询了 payment-service 的日志" in follow_up.answer
    assert "完整诊断链路" in follow_up.answer


def test_observability_mode_does_not_auto_run_full_diagnosis_for_failure_text(monkeypatch) -> None:
    store = InMemoryDiagnosisSessionStore()
    monkeypatch.setattr(intent_router, "get_metric_repository", lambda: _FakeMetricRepository())

    response = diagnosis_orchestrator.run_diagnosis(
        api="/api/checkout",
        time="2026-05-21 10:00:00",
        symptom="paymentFailure HTTP 500，支付 charge 请求失败",
        case_id="case-a",
        message="api: /api/checkout time: 2026-05-21 10:00:00 symptom: paymentFailure HTTP 500，支付 charge 请求失败",
        mode="observability",
        session_store=store,
    )

    assert response.mode == "observability"
    assert response.intent == "observability_query"
    assert response.executed_skills == ["observability_query"]


def test_diagnosis_mode_runs_initial_diagnosis_for_fault_context(monkeypatch) -> None:
    store = InMemoryDiagnosisSessionStore()
    monkeypatch.setattr(
        diagnosis_orchestrator,
        "SKILL_PIPELINE",
        [
            _FakeSkill("AlertContextSkill"),
            _FakeSkill("TraceAnalysisSkill"),
            _FakeSkill("EntityBindingSkill"),
            _FakeSkill("LogAnalysisSkill"),
            _FakeSkill("MetricCheckSkill"),
            _FakeSkill("GraphAnalysisSkill"),
            _FakeSkill("RootCauseSkill"),
            _FakeSkill("ImpactAnalysisSkill"),
            _FakeSkill("ReportSkill"),
        ],
    )
    monkeypatch.setattr(diagnosis_orchestrator, "resolve_request_context", lambda **kwargs: (kwargs.get("case_id"), kwargs.get("data_dir")))

    response = diagnosis_orchestrator.run_diagnosis(
        api="/api/checkout",
        time="2026-05-21 10:00:00",
        symptom="paymentFailure HTTP 500，支付 charge 请求失败",
        case_id="case-a",
        message="api: /api/checkout time: 2026-05-21 10:00:00 symptom: paymentFailure HTTP 500，支付 charge 请求失败",
        mode="diagnosis",
        session_store=store,
    )

    assert response.mode == "diagnosis"
    assert response.intent == "initial_diagnosis"
    assert response.executed_skills == [
        "set_time_range",
        "analyze_trace",
        "bind_entities",
        "analyze_log",
        "check_metrics",
        "analyze_graph",
        "infer_root_cause",
        "analyze_impact",
        "generate_report",
    ]


def test_clarify_when_pronoun_has_no_focus() -> None:
    store = InMemoryDiagnosisSessionStore()
    response = diagnosis_orchestrator.run_diagnosis(
        api="",
        time="",
        symptom="",
        message="继续看它",
        session_store=store,
    )

    assert response.intent == "clarify"
    assert response.executed_skills == []
    assert "指定" in response.answer or "日志" in response.answer


def test_agentic_stream_followup_uses_intent_router_without_full_react(monkeypatch) -> None:
    store = InMemoryDiagnosisSessionStore()
    session = update_session_from_context(
        store.create_session(),
        _fake_ctx(),
        user_message="首轮诊断",
        assistant_message="payment-service 是首要根因候选。",
        store=store,
    )
    monkeypatch.setattr(intent_router, "get_log_repository", lambda: _FakeLogRepository())

    events = list(stream_agentic_diagnosis(
        api="",
        time="",
        symptom="",
        session_id=session.session_id,
        message="继续看它的日志",
        session_store=store,
    ))

    assert events[0]["type"] == "session"
    assert events[0]["intent"] == "followup_inspect_logs"
    assert [event.get("skill") for event in events if event.get("type") == "skill_start"] == ["analyze_log"]
    assert events[-1]["type"] == "done"
    assert events[-1]["executed_skills"] == ["analyze_log"]
