from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.context import DiagnosisContext
from app.skills.trace_analysis_skill import TraceAnalysisSkill
from app.adapters import observability_adapter as adapter


def _span(
    trace_id: str,
    span_id: str,
    service: str,
    name: str,
    start_time: str,
    *,
    parent_span_id: str = "",
    kind: str = "SPAN_KIND_SERVER",
    http_status: str = "",
    status_code: int | None = None,
    rpc_service: str = "",
    rpc_method: str = "",
    status_message: str = "",
    events: list[dict] | None = None,
) -> dict:
    item = {
        "traceId": trace_id,
        "spanId": span_id,
        "parentSpanId": parent_span_id,
        "serviceName": service,
        "name": name,
        "kind": kind,
        "startTime": start_time,
        "durationInNanos": 5_000_000,
        "events": events or [],
    }
    if http_status:
        item["span.attributes.http@status_code"] = http_status
        item["span.attributes.url"] = f"http://frontend-proxy:9080{name}" if name.startswith("GET /api/") else ""
    if status_code is not None:
        item["status.code"] = status_code
    if status_message:
        item["status.message"] = status_message
    if rpc_service:
        item["span.attributes.rpc@service"] = rpc_service
    if rpc_method:
        item["span.attributes.rpc@method"] = rpc_method
    return item


def test_trace_skill_refetches_selected_trace_and_prefers_downstream_rpc(monkeypatch):
    selected_trace_id = "trace-rich"
    initial_spans = [
        _span(
            "trace-nearby-proxy",
            "proxy-1",
            "frontend-proxy",
            "GET",
            "2026-05-21T02:22:24.100Z",
            http_status="500",
            status_code=2,
        ),
        _span(
            selected_trace_id,
            "web-1",
            "frontend-web",
            "GET",
            "2026-05-21T02:22:24.300Z",
            kind="SPAN_KIND_CLIENT",
            http_status="500",
        ),
        _span(
            selected_trace_id,
            "proxy-2",
            "frontend-proxy",
            "GET",
            "2026-05-21T02:22:24.320Z",
            parent_span_id="web-1",
            http_status="500",
            status_code=2,
        ),
        _span(
            selected_trace_id,
            "frontend-1",
            "frontend",
            "GET /api/recommendations",
            "2026-05-21T02:22:24.340Z",
            parent_span_id="proxy-2",
            http_status="500",
            status_code=2,
        ),
        _span(
            selected_trace_id,
            "frontend-2",
            "frontend",
            "executing api route (pages) /api/recommendations",
            "2026-05-21T02:22:24.350Z",
            parent_span_id="frontend-1",
            status_code=2,
            events=[{
                "attributes": {
                    "exception@type": "13",
                    "exception@message": "13 INTERNAL: Error: Product Catalog Fail Feature Flag Enabled",
                }
            }],
        ),
    ]
    full_trace_spans = initial_spans[1:] + [
        _span(
            selected_trace_id,
            "frontend-3",
            "frontend",
            "oteldemo.ProductCatalogService/GetProduct",
            "2026-05-21T02:22:24.360Z",
            parent_span_id="frontend-2",
            kind="SPAN_KIND_CLIENT",
            status_code=2,
            rpc_service="oteldemo.ProductCatalogService",
            rpc_method="GetProduct",
        ),
    ]
    calls: list[dict] = []

    def fake_get_traces(query_context=None, data_dir=None, case_id=None):
        payload = dict(query_context or {})
        calls.append(payload)
        if payload.get("trace_id") == selected_trace_id:
            return full_trace_spans
        return initial_spans

    monkeypatch.setattr(adapter, "get_data_source", lambda: "opensearch")
    monkeypatch.setattr(adapter, "get_traces", fake_get_traces)

    ctx = DiagnosisContext(api="/api/recommendations", time="2026-05-21T02:22:24Z", symptom="HTTP 500")
    ctx.query_context = {
        "alert_api": "/api/recommendations",
        "time_window": {
            "start": "2026-05-21T02:17:24Z",
            "end": "2026-05-21T02:27:24Z",
        },
    }

    TraceAnalysisSkill().run(ctx)

    assert calls[0]["limit"] == 1000
    assert calls[1]["trace_id"] == selected_trace_id
    assert calls[1]["alert_api"] is None
    assert ctx.trace_result["trace_id"] == selected_trace_id
    assert ctx.trace_result["first_error_service"] == "product-catalog"
    assert ctx.trace_result["first_error_api"] == "oteldemo.ProductCatalogService/GetProduct"
    assert any(
        candidate["service"] == "product-catalog" and not candidate["is_propagation"]
        for candidate in ctx.trace_result["root_candidates"]
    )
    assert all(
        candidate["is_propagation"]
        for candidate in ctx.trace_result["root_candidates"]
        if candidate["service"] in {"frontend-web", "frontend-proxy", "frontend"}
    )


def test_trace_skill_hops_to_downstream_unavailable_trace(monkeypatch):
    entry_trace_id = "trace-entry"
    downstream_trace_id = "trace-downstream"
    initial_spans = [
        _span(
            entry_trace_id,
            "frontend-1",
            "frontend",
            "POST /api/checkout",
            "2026-05-21T02:39:30.532Z",
            status_code=2,
            http_status="500",
        ),
        _span(
            entry_trace_id,
            "frontend-2",
            "frontend",
            "executing api route (pages) /api/checkout",
            "2026-05-21T02:39:30.533Z",
            parent_span_id="frontend-1",
            status_code=2,
            events=[{
                "attributes": {
                    "exception@type": "13",
                    "exception@message": "13 INTERNAL: failed to charge card: could not charge the card: rpc error: code = Unavailable desc = name resolver error: produced zero addresses",
                }
            }],
        ),
        _span(
            entry_trace_id,
            "frontend-3",
            "frontend",
            "oteldemo.CheckoutService/PlaceOrder",
            "2026-05-21T02:39:30.533Z",
            parent_span_id="frontend-2",
            kind="SPAN_KIND_CLIENT",
            status_code=2,
            rpc_service="oteldemo.CheckoutService",
            rpc_method="oteldemo.CheckoutService/PlaceOrder",
        ),
    ]
    downstream_lookup_spans = [
        _span(
            downstream_trace_id,
            "checkout-1",
            "checkout",
            "oteldemo.CheckoutService/PlaceOrder",
            "2026-05-21T02:38:23.843Z",
            status_code=2,
            events=[{
                "attributes": {
                    "exception@type": "*errors.errorString",
                    "exception@message": "could not charge the card: rpc error: code = Unavailable desc = name resolver error: produced zero addresses",
                }
            }],
        ),
    ]
    downstream_full_trace = downstream_lookup_spans + [
        _span(
            downstream_trace_id,
            "checkout-2",
            "checkout",
            "oteldemo.PaymentService/Charge",
            "2026-05-21T02:38:23.888Z",
            parent_span_id="checkout-1",
            kind="SPAN_KIND_CLIENT",
            status_code=2,
            rpc_method="oteldemo.PaymentService/Charge",
            status_message="name resolver error: produced zero addresses",
        ),
    ]
    calls: list[dict] = []

    def fake_get_traces(query_context=None, data_dir=None, case_id=None):
        payload = dict(query_context or {})
        calls.append(payload)
        if payload.get("trace_id") == entry_trace_id:
            return initial_spans
        if payload.get("trace_id") == downstream_trace_id:
            return downstream_full_trace
        if payload.get("api") == "oteldemo.CheckoutService/PlaceOrder":
            return downstream_lookup_spans
        return initial_spans

    monkeypatch.setattr(adapter, "get_data_source", lambda: "opensearch")
    monkeypatch.setattr(adapter, "get_traces", fake_get_traces)

    ctx = DiagnosisContext(api="/api/checkout", time="2026-05-21T02:39:30.532Z", symptom="HTTP 500")
    ctx.query_context = {
        "alert_api": "/api/checkout",
        "time_window": {
            "start": "2026-05-21T02:34:30Z",
            "end": "2026-05-21T02:44:30Z",
        },
    }

    TraceAnalysisSkill().run(ctx)

    assert calls[0]["limit"] == 1000
    assert calls[1]["trace_id"] == entry_trace_id
    assert calls[2]["api"] == "oteldemo.CheckoutService/PlaceOrder"
    assert calls[3]["trace_id"] == downstream_trace_id
    assert ctx.trace_result["trace_id"] == downstream_trace_id
    assert ctx.trace_result["first_error_service"] == "payment"
    assert ctx.trace_result["first_error_api"] == "oteldemo.PaymentService/Charge"
    assert any(
        candidate["service"] == "payment" and candidate["type"] == "dependency_unavailable" and not candidate["is_propagation"]
        for candidate in ctx.trace_result["root_candidates"]
    )


def test_trace_skill_prefers_downstream_service_over_entry_wrapper_error(monkeypatch):
    spans = [
        _span(
            "trace-1",
            "checkout-span",
            "checkout",
            "oteldemo.CheckoutService/PlaceOrder",
            "2026-06-27T08:00:00Z",
            status_code=2,
            status_message="failed to charge card: Payment request failed. Invalid token.",
        ),
        _span(
            "trace-1",
            "payment-span",
            "payment",
            "oteldemo.PaymentService/Charge",
            "2026-06-27T08:00:00.100Z",
            parent_span_id="checkout-span",
            status_code=2,
            status_message="Payment request failed. Invalid token.",
        ),
    ]

    monkeypatch.setattr(adapter, "get_data_source", lambda: "mmodel_api")
    monkeypatch.setattr(adapter, "get_traces", lambda query_context=None, data_dir=None, case_id=None: spans)

    ctx = DiagnosisContext(
        api="/oteldemo.CheckoutService/PlaceOrder",
        time="2026-06-27 08:00:00",
        symptom="HTTP 500",
    )
    ctx.query_context = {"alert_api": ctx.api, "time_window": {"start": "2026-06-27T07:55:00", "end": "2026-06-27T08:05:00"}}
    ctx.entity_result = {"services": ["checkout", "payment"]}

    TraceAnalysisSkill().run(ctx)

    assert ctx.trace_result["first_error_service"] == "payment"
    assert ctx.trace_result["first_error_api"] == "oteldemo.PaymentService/Charge"
    checkout_candidates = [
        candidate for candidate in ctx.trace_result["root_candidates"]
        if candidate["service"] == "checkout"
    ]
    assert checkout_candidates
    assert all(candidate["is_propagation"] for candidate in checkout_candidates)
