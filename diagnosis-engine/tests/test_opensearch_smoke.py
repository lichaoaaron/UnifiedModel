from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.adapters.opensearch_adapter import OpenSearchAdapter
from app.models.query_context import QueryContext


def _load_backend_env_if_present() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def _require_opensearch_env() -> None:
    _load_backend_env_if_present()
    if not os.environ.get("OPENSEARCH_URL"):
        pytest.skip("OpenSearch smoke skipped: OPENSEARCH_URL is not configured")


def _lookback_query_context() -> QueryContext:
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=24)
    return QueryContext(
        time_start=start.isoformat().replace("+00:00", "Z"),
        time_end=end.isoformat().replace("+00:00", "Z"),
        limit=3,
    )


def _assert_base_result_shape(result: dict) -> None:
    assert result["source"] == "opensearch"
    assert "total_hits" in result
    assert isinstance(result["items"], list)
    assert "aggregations" in result


def _require_item(result: dict, source_name: str) -> dict:
    _assert_base_result_shape(result)
    if not result["items"]:
        pytest.skip(f"OpenSearch smoke skipped: no {source_name} items found in the default lookback window")
    return result["items"][0]


def test_live_opensearch_adapter_returns_normalized_structures():
    _require_opensearch_env()
    adapter = OpenSearchAdapter()
    query_context = _lookback_query_context()

    trace_result = adapter.query_trace(query_context)
    log_result = adapter.query_log(query_context)
    metric_result = adapter.query_metric(query_context)

    trace_item = _require_item(trace_result, "trace")
    assert "traceId" in trace_item
    assert "resource.attributes.service@name" in trace_item
    assert "span.attributes.http@status_code" in trace_item
    assert "span.attributes.url" in trace_item
    assert "events" in trace_item

    log_item = _require_item(log_result, "log")
    assert "time" in log_item
    assert "resource.attributes.service@name" in log_item
    assert "log.attributes.message" in log_item
    assert "log.attributes.error" in log_item

    metric_item = _require_item(metric_result, "metric")
    assert "name" in metric_item
    assert "value" in metric_item
    assert "resource.attributes.compose_service" in metric_item
    assert "resource.attributes.container@name" in metric_item