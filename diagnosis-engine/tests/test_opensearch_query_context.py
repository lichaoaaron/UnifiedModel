from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.adapters import observability_adapter
from app.models.context import DiagnosisContext
from app.models.query_context import QueryContext
from app.skills.alert_context_skill import AlertContextSkill


def test_alert_context_builds_time_window_from_request_time(monkeypatch):
    monkeypatch.delenv("DATA_SOURCE", raising=False)
    ctx = DiagnosisContext(api="/api/example", time="2026-05-20 10:00:00", symptom="HTTP 500")

    AlertContextSkill().run(ctx)

    assert ctx.query_context["time_window"]["start"] == "2026-05-20T09:55:00"
    assert ctx.query_context["time_window"]["end"] == "2026-05-20T10:05:00"


def test_alert_context_normalizes_naive_time_to_utc_for_opensearch(monkeypatch):
    monkeypatch.setenv("DATA_SOURCE", "opensearch")
    ctx = DiagnosisContext(api="/api/example", time="2026-05-21 10:00:00", symptom="HTTP 500")

    AlertContextSkill().run(ctx)

    parsed = datetime(2026, 5, 21, 10, 0, 0).astimezone(timezone.utc)
    expected_start = (parsed - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    expected_end = (parsed + timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    assert ctx.query_context["time_window"]["start"] == expected_start
    assert ctx.query_context["time_window"]["end"] == expected_end


def test_alert_context_normalizes_offset_time_to_utc_for_opensearch(monkeypatch):
    monkeypatch.setenv("DATA_SOURCE", "opensearch")
    ctx = DiagnosisContext(api="/api/example", time="2026-05-21T10:00:00+08:00", symptom="HTTP 500")

    AlertContextSkill().run(ctx)

    assert ctx.query_context["time_window"]["start"] == "2026-05-21T01:55:00Z"
    assert ctx.query_context["time_window"]["end"] == "2026-05-21T02:05:00Z"


class FakeOpenSearchAdapter:
    def __init__(self):
        self.query_context = None

    def query_trace(self, query_context):
        self.query_context = query_context
        return {"source": "opensearch", "total_hits": 0, "items": [], "aggregations": {}}


def test_observability_adapter_coerces_dict_to_query_context(monkeypatch):
    fake = FakeOpenSearchAdapter()
    monkeypatch.setenv("DATA_SOURCE", "opensearch")
    monkeypatch.setattr(observability_adapter, "_opensearch_adapter", fake)

    observability_adapter.get_traces(query_context={
        "alert_api": "/api/example",
        "trace_id": "trace-1",
        "service": "service-a",
        "time_window": {
            "start": "2026-05-20T09:55:00",
            "end": "2026-05-20T10:05:00",
        },
    })

    assert isinstance(fake.query_context, QueryContext)
    assert fake.query_context.api == "/api/example"
    assert fake.query_context.trace_id == "trace-1"
    assert fake.query_context.service == "service-a"
    assert fake.query_context.time_start == "2026-05-20T09:55:00"
