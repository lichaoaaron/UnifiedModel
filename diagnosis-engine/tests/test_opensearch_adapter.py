from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.adapters.opensearch_adapter import OpenSearchAdapter
from app.models.query_context import QueryContext


class FakeTransport:
    def __init__(self, response: dict):
        self.response = response
        self.calls: list[dict] = []

    def search(self, index: str, body: dict) -> dict:
        self.calls.append({"index": index, "body": body})
        return self.response


def _hit(source: dict) -> dict:
    return {"_source": source}


def test_query_trace_uses_context_and_normalizes_span_fields():
    transport = FakeTransport({
        "hits": {
            "total": {"value": 1},
            "hits": [
                _hit({
                    "traceId": "trace-1",
                    "spanId": "span-1",
                    "parentSpanId": "root",
                    "serviceName": "service-a",
                    "name": "/api/example",
                    "startTime": "2026-05-20T01:00:00Z",
                    "status": {"code": 2, "message": "error"},
                    "span": {"attributes": {"http@response@status_code": "500", "url@full": "/api/example"}},
                    "resource": {"attributes": {"service@name": "service-a"}},
                    "events": [
                        {
                            "attributes": {
                                "exception@type": "RuntimeError",
                                "exception@message": "boom",
                                "exception@stacktrace": "stack",
                            }
                        }
                    ],
                })
            ],
        }
    })
    adapter = OpenSearchAdapter(transport=transport, trace_index="trace-index")

    result = adapter.query_trace(QueryContext(
        time_start="2026-05-20T00:55:00Z",
        time_end="2026-05-20T01:05:00Z",
        api="/api/example",
        service="service-a",
        trace_id="trace-1",
        limit=10,
    ))

    assert transport.calls[0]["index"] == "trace-index"
    body = transport.calls[0]["body"]
    assert body["size"] == 10
    assert {"term": {"traceId": "trace-1"}} in body["query"]["bool"]["filter"]
    assert {"bool": {"should": [
        {"term": {"serviceName": "service-a"}},
        {"term": {"resource.attributes.service@name": "service-a"}},
    ], "minimum_should_match": 1}} in body["query"]["bool"]["filter"]
    assert body["query"]["bool"]["filter"][0]["range"]["startTime"]["gte"] == "2026-05-20T00:55:00Z"
    item = result["items"][0]
    assert item["resource.attributes.service@name"] == "service-a"
    assert item["span.attributes.http@status_code"] == "500"
    assert item["span.attributes.url"] == "/api/example"
    assert item["events"][0]["attributes"]["error@kind"] == "RuntimeError"
    assert item["events"][0]["attributes"]["message"] == "boom"


def test_query_log_uses_context_and_normalizes_message_fields():
    transport = FakeTransport({
        "hits": {
            "total": {"value": 1},
            "hits": [
                _hit({
                    "@timestamp": "2026-05-20T01:00:00Z",
                    "traceId": "trace-1",
                    "spanId": "span-1",
                    "serviceName": "service-a",
                    "severityText": "ERROR",
                    "body": "request failed",
                    "log": {"attributes": {"message": "detailed failure", "err": "boom"}},
                    "resource": {"attributes": {"service@name": "service-a"}},
                })
            ],
        }
    })
    adapter = OpenSearchAdapter(transport=transport, log_index="log-index")

    result = adapter.query_log(QueryContext(
        time_start="2026-05-20T00:55:00Z",
        time_end="2026-05-20T01:05:00Z",
        service="service-a",
        trace_id="trace-1",
        level="ERROR",
    ))

    assert transport.calls[0]["index"] == "log-index"
    filters = transport.calls[0]["body"]["query"]["bool"]["filter"]
    assert {"term": {"traceId": "trace-1"}} in filters
    assert {"bool": {"should": [
        {"term": {"serviceName": "service-a"}},
        {"term": {"resource.attributes.service@name": "service-a"}},
    ], "minimum_should_match": 1}} in filters
    assert {"term": {"severityText": "ERROR"}} in filters
    item = result["items"][0]
    assert item["time"] == "2026-05-20T01:00:00Z"
    assert item["resource.attributes.service@name"] == "service-a"
    assert item["log.attributes.message"] == "detailed failure"
    assert item["log.attributes.error"] == "boom"


def test_query_metric_uses_context_and_normalizes_value_fields():
    transport = FakeTransport({
        "hits": {
            "total": {"value": 1},
            "hits": [
                _hit({
                    "time": "2026-05-20T01:00:00Z",
                    "name": "metric.name",
                    "sum": 12.5,
                    "unit": "ms",
                    "serviceName": "service-a",
                    "resource": {"attributes": {"compose_service": "service-a", "container@name": "container-a"}},
                })
            ],
        }
    })
    adapter = OpenSearchAdapter(transport=transport, metric_index="metric-index")

    result = adapter.query_metric(QueryContext(
        time_start="2026-05-20T00:55:00Z",
        time_end="2026-05-20T01:05:00Z",
        service="service-a",
        keyword="metric.name",
        trace_id="trace-1",
    ))

    assert transport.calls[0]["index"] == "metric-index"
    filters = transport.calls[0]["body"]["query"]["bool"]["filter"]
    assert {"term": {"traceId": "trace-1"}} not in filters
    item = result["items"][0]
    assert item["resource.attributes.compose_service"] == "service-a"
    assert item["resource.attributes.container@name"] == "container-a"
    assert item["value"] == 12.5
