from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.repositories import TraceRepository
from app.repositories.contracts import RepositoryResult
from app.repositories.default_repositories import (
    DefaultBusinessImpactRepository,
    DefaultMetricRepository,
    DefaultServiceMapRepository,
    DefaultTraceRepository,
)
from app.models.context import DiagnosisContext
from app.skills.entity_binding_skill import EntityBindingSkill
from app.skills.graph_analysis_skill import GraphAnalysisSkill
from app.skills.impact_analysis_skill import ImpactAnalysisSkill
from app.skills.report_skill import ReportSkill
from app.skills.root_cause_skill import RootCauseSkill
from app.adapters.llm_provider import MockLLMProvider


class FakeObservabilityAdapter:
    def __init__(self):
        self.calls: list[dict] = []

    def get_data_source(self) -> str:
        return "opensearch"

    def get_traces(self, query_context=None, data_dir=None, case_id=None):
        self.calls.append(dict(query_context or {}))
        return [
            {
                "traceId": "trace-1",
                "spanId": "span-1",
                "serviceName": "checkout-service",
                "name": "POST:/checkout/pay",
                "status.code": 2,
                "events": [{"attributes": {"error@kind": "TimeoutError"}}],
            },
            {
                "traceId": "trace-1",
                "spanId": "span-2",
                "serviceName": "payment-service",
                "name": "POST:/payment/charge",
                "status.code": 1,
                "events": [],
            },
        ]


class StubTraceRepository(TraceRepository):
    def __init__(self, spans: list[dict]):
        self.spans = spans

    def get_traces(self, query=None, *, data_dir=None, case_id=None):
        return RepositoryResult(source="test", query_context=query or {}, items=self.spans, raw_refs=[{"kind": "trace", "ref": "test:trace"}])

    def get_trace_by_id(self, trace_id, query=None, *, data_dir=None, case_id=None):
        return RepositoryResult(source="test", query_context=query or {}, items=[span for span in self.spans if span.get("traceId") == trace_id])

    def get_error_spans(self, service_name=None, time_range=None, *, data_dir=None, case_id=None):
        return RepositoryResult(source="test", query_context={}, items=[])

    def get_span_attributes(self, trace_id, *, data_dir=None, case_id=None):
        return RepositoryResult(source="test", query_context={}, items=[])


class StubLogRepository:
    def __init__(self, logs: list[dict]):
        self.logs = logs

    def get_logs(self, query=None, *, data_dir=None, case_id=None):
        return RepositoryResult(source="test", query_context=query or {}, items=self.logs)


class StubMetricRepository:
    def __init__(self, metrics: list[dict]):
        self.metrics = metrics

    def get_red_metrics(self, service_name=None, time_range=None, *, data_dir=None, case_id=None):
        return RepositoryResult(source="test", query_context={}, items=self.metrics)


class RecordingServiceMapRepository:
    def __init__(self, spans: list[dict]):
        self.spans = spans
        self.queries: list[dict] = []

    def get_service_map(self, time_range=None, *, query=None, data_dir=None, case_id=None):
        self.queries.append(dict(query or {}))
        result = DefaultServiceMapRepository(trace_repository=StubTraceRepository(self.spans)).get_service_map(query=query)
        return result


class FakeMetricAdapter:
    def __init__(self, metrics: list[dict]):
        self.metrics = metrics

    def get_data_source(self) -> str:
        return "test"

    def get_metrics(self, query_context=None, data_dir=None, case_id=None):
        return self.metrics


def test_trace_repository_wraps_adapter_and_exposes_domain_methods():
    fake_adapter = FakeObservabilityAdapter()
    repository = DefaultTraceRepository(adapter_module=fake_adapter)

    result = repository.get_error_spans("checkout-service", {"start": "2026-05-22T10:00:00Z", "end": "2026-05-22T10:05:00Z"})

    assert result.source == "opensearch"
    assert result.availability == "available"
    assert result.raw_refs == [{"kind": "trace", "ref": "opensearch:trace"}]
    assert result.items[0]["serviceName"] == "checkout-service"
    assert fake_adapter.calls[0]["service"] == "checkout-service"
    assert fake_adapter.calls[0]["time_window"]["start"] == "2026-05-22T10:00:00Z"


def test_service_map_repository_preserves_observed_call_direction():
    spans = [
        {"traceId": "trace-1", "spanId": "root", "parentSpanId": "", "serviceName": "frontend", "name": "GET:/checkout", "durationInNanos": 100_000_000},
        {"traceId": "trace-1", "spanId": "child", "parentSpanId": "root", "serviceName": "checkout-service", "name": "POST:/checkout/pay", "durationInNanos": 2_000_000_000, "status.code": 2},
        {"traceId": "trace-1", "spanId": "leaf", "parentSpanId": "child", "serviceName": "payment-service", "name": "POST:/payment/charge", "durationInNanos": 500_000_000},
    ]
    repository = DefaultServiceMapRepository(trace_repository=StubTraceRepository(spans))

    service_map = repository.get_service_map()
    edges = service_map.items[0]["edges"]
    downstream = repository.get_downstream_services("checkout-service").items[0]["downstream_services"]
    impacted = repository.get_impacted_services("payment-service").items[0]["impacted_services"]

    assert {edge["source"] + "->" + edge["target"] for edge in edges} == {
        "frontend->checkout-service",
        "checkout-service->payment-service",
    }
    assert downstream == ["payment-service"]
    assert impacted == ["checkout-service", "frontend"]
    checkout_edge = next(edge for edge in edges if edge["target"] == "checkout-service")
    assert checkout_edge["call_count"] == 1
    assert checkout_edge["error_count"] == 1
    assert checkout_edge["error_rate"] == 1.0
    assert checkout_edge["avg_duration_ms"] == 2000.0


def test_metric_repository_aggregates_red_metrics_from_trace_log_and_metric_series():
    spans = [
        {"traceId": "trace-1", "spanId": "s1", "serviceName": "checkout-service", "status.code": 1, "durationInNanos": 500_000_000},
        {"traceId": "trace-1", "spanId": "s2", "serviceName": "checkout-service", "status.code": 2, "durationInNanos": 2_500_000_000},
        {"traceId": "trace-1", "spanId": "s3", "serviceName": "payment-service", "status.code": 1, "durationInNanos": 100_000_000},
    ]
    logs = [
        {"traceId": "trace-1", "serviceName": "checkout-service", "log.attributes.log@level": "ERROR", "log.attributes.message": "checkout failed"}
    ]
    metrics = [
        {"resource.attributes.compose_service": "checkout-service", "name": "http.server.duration.p95", "value": "1500", "unit": "ms"},
        {"resource.attributes.compose_service": "checkout-service", "name": "http.server.error.rate", "value": "10", "unit": "%"},
    ]
    repository = DefaultMetricRepository(
        adapter_module=FakeMetricAdapter(metrics),
        trace_repository=StubTraceRepository(spans),
        log_repository=StubLogRepository(logs),
    )

    result = repository.get_all_services_red_metrics({"start": "2026-05-22T10:00:00Z", "end": "2026-05-22T10:10:00Z"})
    checkout = next(item for item in result.items if item["service_name"] == "checkout-service")
    error_rate = repository.get_service_error_rate("checkout-service").items[0]

    assert checkout["rate"]["request_count"] == 2
    assert checkout["rate"]["rate_per_minute"] == 0.2
    assert checkout["error"]["error_count"] == 1
    assert checkout["error"]["log_error_count"] == 1
    assert checkout["error"]["error_rate"] == 0.5
    assert checkout["error_signal"] == "elevated"
    assert checkout["duration_signal"] == "elevated"
    assert checkout["overall_anomaly_score"] >= 0.8
    assert error_rate["service_name"] == "checkout-service"
    assert error_rate["error_rate"] == 0.5


def test_business_impact_repository_derives_fields_from_observability_data():
    spans = [
        {
            "traceId": "trace-1",
            "spanId": "span-1",
            "serviceName": "checkout-service",
            "status.code": 2,
            "span.attributes": {
                "order.id": "order-1001",
                "user.id": "user-7",
                "amount": "88.50",
                "payment.status": "failed",
            },
            "events": [{"attributes": {"message": "payment transaction failed"}}],
        }
    ]
    logs = [
        {
            "traceId": "trace-1",
            "serviceName": "checkout-service",
            "log.attributes.log@level": "ERROR",
            "log.attributes.message": "payment transaction failed for order_id=order-1001",
        }
    ]
    repository = DefaultBusinessImpactRepository(
        trace_repository=StubTraceRepository(spans),
        log_repository=StubLogRepository(logs),
        metric_repository=StubMetricRepository([]),
    )

    result = repository.get_business_impact("checkout-service")
    summary = result.items[0]

    assert result.availability == "available"
    assert summary["affected_order_count"] == 1
    assert summary["affected_user_count"] == 1
    assert summary["failed_transaction_count"] == 1
    assert summary["estimated_gmv_loss"] == 88.5
    assert summary["estimated_revenue_impact"] == 88.5
    assert summary["confidence"] == "high"
    assert summary["business_events"]
    assert summary["evidence_links"]["trace_ids"] == ["trace-1"]


def test_business_impact_repository_keeps_unknown_when_business_fields_missing():
    spans = [
        {"traceId": "trace-1", "spanId": "span-1", "serviceName": "payment-service", "status.code": 2, "name": "oteldemo.PaymentService/Charge"},
    ]
    repository = DefaultBusinessImpactRepository(
        trace_repository=StubTraceRepository(spans),
        log_repository=StubLogRepository([]),
        metric_repository=StubMetricRepository([]),
    )

    result = repository.get_business_impact("payment-service")
    summary = result.items[0]

    assert result.availability == "available"
    assert summary["affected_order_count"] == "unknown"
    assert summary["affected_user_count"] == "unknown"
    assert summary["estimated_revenue_impact"] == "unknown"
    assert summary["failed_transaction_count"] == 1
    assert summary["failed_transaction_count_estimated"] is True
    assert summary["confidence"] == "medium"


def test_business_impact_repository_parses_log_business_failure_and_metric_links():
    logs = [
        {
            "_id": "log-1",
            "traceId": "trace-log-1",
            "serviceName": "checkout-service",
            "severityText": "ERROR",
            "log.attributes.message": "checkout failed order_id=order-9 user_id=user-3 amount=42.75 payment_status=failed",
        }
    ]
    metrics = [
        {"service_name": "checkout-service", "overall_anomaly_score": 0.8, "error_signal": "elevated", "error": {"error_rate": 0.5}, "rate": {"request_count": 2}},
    ]
    repository = DefaultBusinessImpactRepository(
        trace_repository=StubTraceRepository([]),
        log_repository=StubLogRepository(logs),
        metric_repository=StubMetricRepository(metrics),
    )

    result = repository.get_business_impact_for_services(["checkout-service"])
    summary = result.items[0]

    assert summary["affected_order_count"] == 1
    assert summary["affected_user_count"] == 1
    assert summary["failed_transaction_count"] == 1
    assert summary["estimated_revenue_impact"] == 42.75
    assert summary["business_events"][0]["event_type"] == "payment_failure"
    assert summary["evidence_links"]["log_ids"] == ["log-1"]
    assert summary["related_red_metrics"][0]["overall_anomaly_score"] == 0.8


def test_root_cause_result_contains_red_and_service_map_evidence():
    ctx = DiagnosisContext(api="/checkout/pay", time="2026-05-22T10:00:00Z", symptom="HTTP 500")
    ctx.trace_result = {
        "root_candidates": [{
            "source": "trace",
            "service": "checkout-service",
            "api": "/checkout/pay",
            "type": "service_exception",
            "exception_type": "TimeoutError",
            "evidence": "checkout timeout",
            "score": 0.6,
            "is_propagation": False,
        }],
        "first_error_service": "checkout-service",
        "first_error_api": "/checkout/pay",
        "first_error_exception": "TimeoutError",
    }
    ctx.log_result = {"root_candidates": []}
    ctx.metric_result = {
        "red_metrics": [{
            "service_name": "checkout-service",
            "rate_signal": "normal",
            "error_signal": "elevated",
            "duration_signal": "elevated",
            "overall_anomaly_score": 0.9,
            "evidence_summary": ["error_rate=0.5", "p95_duration_ms=1500"],
        }],
        "metric_root_candidates": [],
    }
    ctx.graph_result = {
        "call_edges": [{
            "source": "frontend",
            "target": "checkout-service",
            "source_service": "frontend",
            "target_service": "checkout-service",
            "call_count": 3,
            "error_count": 2,
            "error_rate": 0.667,
        }],
        "upstream_services": {"checkout-service": ["frontend"]},
        "downstream_services": {"frontend": ["checkout-service"]},
        "impacted_services": ["frontend"],
        "service_map_evidence": {"impacted_services": ["frontend"]},
    }

    RootCauseSkill().run(ctx)

    candidate = ctx.root_cause_result["candidates"][0]
    assert ctx.root_cause_result["evidence_by_source"]["red_metrics"]
    assert ctx.root_cause_result["evidence_by_source"]["service_map"]
    assert candidate["red_metrics_evidence"]["overall_anomaly_score"] == 0.9
    assert candidate["related_upstream_services"] == ["frontend"]


def test_graph_skill_uses_entry_trace_id_for_complete_service_map_edges():
    spans = [
        {"traceId": "entry-trace", "spanId": "root", "parentSpanId": "", "serviceName": "frontend", "name": "GET:/api/checkout", "kind": "SPAN_KIND_SERVER"},
        {"traceId": "entry-trace", "spanId": "checkout", "parentSpanId": "root", "serviceName": "checkout", "name": "oteldemo.CheckoutService/PlaceOrder"},
        {"traceId": "entry-trace", "spanId": "payment", "parentSpanId": "checkout", "serviceName": "payment", "name": "oteldemo.PaymentService/Charge", "status.code": 2},
    ]
    service_map_repository = RecordingServiceMapRepository(spans)
    ctx = DiagnosisContext(api="/api/checkout", time="2026-05-21 10:00:00", symptom="HTTP 500")
    ctx.query_context = {"trace_id": "downstream-trace", "time_window": {"start": "2026-05-21T01:55:00Z", "end": "2026-05-21T02:05:00Z"}}
    ctx.trace_result = {
        "service_map_trace_id": "entry-trace",
        "first_error_service": "payment",
        "first_error_api": "oteldemo.PaymentService/Charge",
    }

    GraphAnalysisSkill(
        service_map_repository=service_map_repository,
        metric_repository=StubMetricRepository([]),
    ).run(ctx)

    assert service_map_repository.queries[0]["trace_id"] == "entry-trace"
    call_edge_pairs = {(edge["source"], edge["target"]) for edge in ctx.graph_result["call_edges"]}
    graph_call_pairs = {(edge["source"], edge["target"]) for edge in ctx.graph_result["edges"] if edge.get("label") == "calls"}
    assert call_edge_pairs == {("frontend", "checkout"), ("checkout", "payment")}
    assert {("frontend", "checkout"), ("checkout", "payment")} <= graph_call_pairs
    assert ctx.graph_result["impacted_services"] == ["checkout", "frontend"]


def test_entity_binding_extracts_grpc_interfaces_from_span_names():
    spans = [
        {"serviceName": "checkout", "name": "oteldemo.CheckoutService/PlaceOrder"},
        {"serviceName": "payment", "name": "oteldemo.PaymentService/Charge"},
    ]
    ctx = DiagnosisContext(
        api="/oteldemo.CheckoutService/PlaceOrder",
        time="2026-06-27 08:00:00",
        symptom="HTTP 500",
    )
    ctx.query_context = {"time_window": {"start": "2026-06-27T07:55:00Z", "end": "2026-06-27T08:05:00Z"}}

    EntityBindingSkill(
        trace_repository=StubTraceRepository(spans),
        log_repository=StubLogRepository([]),
        metric_repository=StubMetricRepository([]),
    ).run(ctx)

    assert ctx.entity_result["services"] == ["checkout", "payment"]
    assert ctx.entity_result["interfaces"] == [
        "oteldemo.CheckoutService/PlaceOrder",
        "oteldemo.PaymentService/Charge",
    ]


def test_root_cause_outputs_evidence_chain_for_propagation_and_root():
    ctx = DiagnosisContext(
        api="/oteldemo.CheckoutService/PlaceOrder",
        time="2026-06-27 08:00:00",
        symptom="HTTP 500",
    )
    ctx.trace_result = {
        "trace_id": "trace-1",
        "entry_api": "/oteldemo.CheckoutService/PlaceOrder",
        "entry_service": "checkout",
        "service_call": "checkout -> payment",
        "interface_call": "/oteldemo.CheckoutService/PlaceOrder -> oteldemo.PaymentService/Charge",
        "first_error_service": "payment",
        "first_error_api": "oteldemo.PaymentService/Charge",
        "first_error_exception": "PaymentError",
        "root_candidates": [
            {
                "source": "trace",
                "service": "checkout",
                "api": "/oteldemo.CheckoutService/PlaceOrder",
                "type": "service_exception",
                "exception_type": "HTTPError",
                "evidence": "checkout returned HTTP 500 after downstream payment failed",
                "score": 0.2,
                "is_propagation": True,
            },
            {
                "source": "trace",
                "service": "payment",
                "api": "oteldemo.PaymentService/Charge",
                "type": "service_exception",
                "exception_type": "PaymentError",
                "evidence": "Payment request failed. Invalid token.",
                "score": 0.8,
                "is_propagation": False,
            },
        ],
    }
    ctx.log_result = {"root_candidates": [], "log_evidence": []}
    ctx.metric_result = {"metric_root_candidates": [], "red_metrics": []}
    ctx.graph_result = {
        "call_edges": [{"source": "checkout", "target": "payment"}],
        "service_map_evidence": {"call_edges": [{"source": "checkout", "target": "payment"}]},
        "upstream_services": {"payment": ["checkout"]},
        "downstream_services": {"checkout": ["payment"]},
        "impacted_services": ["checkout"],
    }

    RootCauseSkill().run(ctx)

    chain = ctx.root_cause_result.get("evidence_chain")
    assert chain
    assert chain["entry_service"] == "checkout"
    assert chain["root_cause_service"] == "payment"
    assert chain["propagation_services"] == ["checkout"]
    assert any(step["service"] == "checkout" and step["role"] == "propagation" for step in chain["steps"])
    assert any(step["service"] == "payment" and step["role"] == "root_cause" for step in chain["steps"])


def test_report_renders_red_metrics_and_service_map_evidence(monkeypatch):
    monkeypatch.setattr("app.skills.report_skill.get_llm_provider", lambda: MockLLMProvider())

    ctx = DiagnosisContext(api="/api/checkout", time="2026-05-21 10:00:00", symptom="paymentFailure HTTP 500")
    red_payment = {
        "service_name": "payment",
        "rate_signal": "normal",
        "error_signal": "elevated",
        "duration_signal": "elevated",
        "overall_anomaly_score": 0.9,
        "rate": {"request_count": 3},
        "error": {"error_rate": 0.667},
        "duration": {"p95_duration_ms": 1500},
    }
    call_edges = [
        {"source": "frontend", "target": "checkout", "source_service": "frontend", "target_service": "checkout", "call_count": 3, "error_count": 0, "error_rate": 0.0, "p95_duration_ms": 120},
        {"source": "checkout", "target": "payment", "source_service": "checkout", "target_service": "payment", "call_count": 3, "error_count": 2, "error_rate": 0.667, "p95_duration_ms": 1500},
    ]
    ctx.trace_result = {"trace_id": "trace-1", "call_path": ["frontend:/api/checkout", "checkout:PlaceOrder", "payment:Charge"]}
    ctx.log_result = {"log_evidence": [], "root_candidates": []}
    ctx.metric_result = {
        "resource_status": "no_threshold",
        "conclusion": "部分指标未配置阈值，无法单独判断资源状态。",
        "red_metrics": [red_payment],
    }
    ctx.graph_result = {
        "call_edges": call_edges,
        "service_map_evidence": {"call_edges": call_edges, "impacted_services": ["checkout", "frontend"]},
        "edges": [{"source": edge["source"], "target": edge["target"], "label": "calls"} for edge in call_edges],
    }
    ctx.root_cause_result = {
        "root_cause_service": "payment",
        "root_cause_api": "oteldemo.PaymentService/Charge",
        "root_cause_type": "service_exception",
        "exception_type": "HTTPError",
        "confidence": "high",
        "is_confirmed": True,
        "evidence_by_source": {"red_metrics": [red_payment], "service_map": {"call_edges": call_edges}},
    }
    ctx.impact_result = {
        "affected_services": ["frontend", "checkout", "payment"],
        "affected_apis": ["/api/checkout", "oteldemo.PaymentService/Charge"],
        "impact_scale": "unavailable",
    }

    ReportSkill().run(ctx)
    report = ctx.report_result["report"]

    assert "RED Metrics 证据：payment RED 异常评分=0.9" in report
    assert "error=elevated" in report
    assert "Service Map 证据：checkout→payment" in report
    assert "当前根因结论置信度为 high" in report


def test_report_preserves_high_confidence_and_single_sample_edge_guard(monkeypatch):
    monkeypatch.setattr("app.skills.report_skill.get_llm_provider", lambda: MockLLMProvider())

    ctx = DiagnosisContext(api="/api/checkout", time="2026-05-21 10:00:00", symptom="paymentFailure HTTP 500")
    call_edges = [
        {"source": "load-generator", "target": "frontend-proxy", "source_service": "load-generator", "target_service": "frontend-proxy", "call_count": 1, "error_count": 1, "error_rate": 1.0},
        {"source": "frontend-proxy", "target": "frontend", "source_service": "frontend-proxy", "target_service": "frontend", "call_count": 1, "error_count": 1, "error_rate": 1.0},
        {"source": "frontend", "target": "checkout", "source_service": "frontend", "target_service": "checkout", "call_count": 1, "error_count": 1, "error_rate": 1.0},
        {"source": "checkout", "target": "payment", "source_service": "checkout", "target_service": "payment", "call_count": 1, "error_count": 1, "error_rate": 1.0},
    ]
    ctx.trace_result = {"trace_id": "trace-1", "call_path": ["checkout:PlaceOrder", "payment:Charge"]}
    ctx.log_result = {"log_evidence": [], "root_candidates": []}
    ctx.metric_result = {
        "resource_status": "no_threshold",
        "conclusion": "部分指标未配置阈值，无法单独判断资源状态。",
    }
    ctx.graph_result = {
        "call_edges": call_edges,
        "service_map_evidence": {"call_edges": call_edges},
    }
    ctx.root_cause_result = {
        "root_cause_service": "payment",
        "root_cause_api": "oteldemo.PaymentService/Charge",
        "root_cause_type": "service_exception",
        "exception_type": "HTTPError",
        "confidence": "high",
        "is_confirmed": True,
        "evidence_by_source": {"service_map": {"call_edges": call_edges}},
    }
    ctx.impact_result = {
        "affected_services": ["checkout", "payment"],
        "affected_apis": ["/api/checkout", "oteldemo.PaymentService/Charge"],
        "impact_scale": "unavailable",
    }

    ReportSkill().run(ctx)
    report = ctx.report_result["report"]

    assert "当前根因结论置信度为 high" in report
    assert "中等置信度" not in report
    assert "核心受影响服务为 checkout, payment" in report
    assert "上游传播链路涉及 load-generator, frontend-proxy, frontend, checkout, payment" in report
    assert "单样本观测，不外推全局错误率" in report
    assert "error_rate=1.0" not in report
    assert "错误率 100%" not in report
    assert "错误率高达100%" not in report


def test_impact_skill_attaches_business_impact_to_root_cause_and_service_map():
    spans = [
        {
            "traceId": "trace-1",
            "spanId": "payment-span",
            "serviceName": "payment",
            "status.code": 2,
            "name": "oteldemo.PaymentService/Charge",
            "span.attributes": {
                "app.order.id": "order-100",
                "app.user.id": "user-100",
                "app.payment.amount": "19.99",
                "app.payment.status": "failed",
            },
        }
    ]
    repository = DefaultBusinessImpactRepository(
        trace_repository=StubTraceRepository(spans),
        log_repository=StubLogRepository([]),
        metric_repository=StubMetricRepository([]),
    )
    ctx = DiagnosisContext(api="/api/checkout", time="2026-05-21 10:00:00", symptom="paymentFailure HTTP 500")
    ctx.query_context = {"time_window": {"start": "2026-05-21T01:55:00Z", "end": "2026-05-21T02:05:00Z"}}
    ctx.trace_result = {"call_path": ["checkout:/api/checkout", "payment:oteldemo.PaymentService/Charge"]}
    ctx.root_cause_result = {
        "root_cause_service": "payment",
        "root_cause_api": "oteldemo.PaymentService/Charge",
    }
    ctx.graph_result = {
        "call_edges": [
            {"source_service": "checkout", "target_service": "payment", "call_count": 1, "error_count": 1, "error_rate": 1.0}
        ],
        "edges": [],
    }

    ImpactAnalysisSkill(business_impact_repository=repository).run(ctx)
    business_impact = ctx.impact_result["business_impact"]

    assert business_impact["affected_order_count"] == 1
    assert business_impact["failed_transaction_count"] == 1
    assert business_impact["affected_user_count"] == 1
    assert business_impact["estimated_revenue_impact"] == 19.99
    assert business_impact["root_cause_service"] == "payment"
    assert business_impact["evidence_links"]["service_map_edges"][0]["source"] == "checkout"


def test_report_renders_observability_business_impact(monkeypatch):
    monkeypatch.setattr("app.skills.report_skill.get_llm_provider", lambda: MockLLMProvider())

    ctx = DiagnosisContext(api="/api/checkout", time="2026-05-21 10:00:00", symptom="paymentFailure HTTP 500")
    ctx.trace_result = {"trace_id": "trace-1", "call_path": ["checkout:/api/checkout", "payment:Charge"]}
    ctx.log_result = {"log_evidence": [], "root_candidates": []}
    ctx.metric_result = {"resource_status": "no_threshold"}
    ctx.graph_result = {"call_edges": []}
    ctx.root_cause_result = {
        "root_cause_service": "payment",
        "root_cause_api": "oteldemo.PaymentService/Charge",
        "root_cause_type": "service_exception",
        "exception_type": "HTTPError",
        "confidence": "high",
        "is_confirmed": True,
    }
    ctx.impact_result = {
        "affected_services": ["checkout", "payment"],
        "affected_apis": ["/api/checkout", "oteldemo.PaymentService/Charge"],
        "impact_scale": "unavailable",
        "business_impact": {
            "affected_order_count": 2,
            "failed_transaction_count": 2,
            "affected_user_count": 1,
            "estimated_revenue_impact": 108.5,
            "confidence": "high",
            "related_trace_ids": ["trace-1"],
            "related_services": ["payment"],
            "evidence_links": {"trace_ids": ["trace-1"], "related_services": ["payment"]},
        },
    }

    ReportSkill().run(ctx)
    report = ctx.report_result["report"]

    assert "业务影响数据：payment 技术异常关联到可观测业务受损信号" in report
    assert "受影响订单数=2" in report
    assert "失败交易数=2" in report
    assert "估算金额影响=108.5" in report
    assert "业务影响关联 trace_ids：trace-1" in report


def test_report_renders_medium_confidence_failed_transaction_as_signal(monkeypatch):
    monkeypatch.setattr("app.skills.report_skill.get_llm_provider", lambda: MockLLMProvider())

    ctx = DiagnosisContext(api="/api/checkout", time="2026-05-21 10:00:00", symptom="paymentFailure HTTP 500")
    ctx.trace_result = {"trace_id": "trace-1", "call_path": ["checkout:/api/checkout", "payment:Charge"]}
    ctx.log_result = {"log_evidence": [], "root_candidates": []}
    ctx.metric_result = {"resource_status": "no_threshold"}
    ctx.graph_result = {"call_edges": []}
    ctx.root_cause_result = {
        "root_cause_service": "payment",
        "root_cause_api": "oteldemo.PaymentService/Charge",
        "root_cause_type": "service_exception",
        "exception_type": "HTTPError",
        "confidence": "high",
        "is_confirmed": True,
    }
    ctx.impact_result = {
        "affected_services": ["checkout", "payment"],
        "affected_apis": ["/api/checkout", "oteldemo.PaymentService/Charge"],
        "impact_scale": "unavailable",
        "business_impact": {
            "affected_order_count": "unknown",
            "failed_transaction_count": 1,
            "failed_transaction_count_estimated": True,
            "affected_user_count": "unknown",
            "estimated_revenue_impact": "unknown",
            "confidence": "medium",
            "evidence_links": {"trace_ids": ["trace-1"], "related_services": ["payment"]},
        },
    }

    ReportSkill().run(ctx)
    report = ctx.report_result["report"]

    assert "失败交易信号=1（可观测证据推导值，非最终业务交易事实）" in report
    assert "失败交易数=1" not in report
    assert "受影响订单数=unknown" in report
    assert "受影响用户数=unknown" in report
    assert "估算金额影响=unknown" in report


def test_observability_skills_depend_on_repositories_not_adapters():
    backend_root = Path(__file__).resolve().parents[1]
    skill_files = [
        backend_root / "app" / "skills" / "trace_analysis_skill.py",
        backend_root / "app" / "skills" / "log_analysis_skill.py",
        backend_root / "app" / "skills" / "metric_check_skill.py",
        backend_root / "app" / "skills" / "entity_binding_skill.py",
        backend_root / "app" / "skills" / "graph_analysis_skill.py",
    ]

    for skill_file in skill_files:
        source = skill_file.read_text(encoding="utf-8")
        assert "observability_adapter" not in source
        assert "local_json_adapter" not in source
