"""Default repository implementations backed by the current observability adapter."""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

from app.adapters import observability_adapter
from app.adapters.local_json_adapter import resolve_data_dir
from app.models.query_context import QueryContext
from app.repositories.contracts import (
    BusinessImpactRepository,
    LogRepository,
    MetricRepository,
    RepositoryResult,
    ServiceMapRepository,
    TraceRepository,
)

logger = logging.getLogger(__name__)

_ERROR_LEVELS = {"ERROR", "FATAL", "CRITICAL", "WARN"}
_FAILURE_TOKENS = ("fail", "failed", "failure", "error", "exception", "timeout", "cancel", "decline", "unavailable")
_BUSINESS_TOKENS = ("order", "payment", "transaction", "checkout")


def _query_to_dict(query: dict[str, Any] | Any | None) -> dict[str, Any]:
    if query is None:
        return {}
    if hasattr(query, "to_dict"):
        return dict(query.to_dict())
    if isinstance(query, dict):
        return dict(query)
    return {}


def _with_time_range(query: dict[str, Any] | None, time_range: dict[str, Any] | None) -> dict[str, Any]:
    merged = _query_to_dict(query)
    if time_range:
        merged.setdefault("time_window", dict(time_range))
        if time_range.get("start"):
            merged.setdefault("time_start", time_range.get("start"))
        if time_range.get("end"):
            merged.setdefault("time_end", time_range.get("end"))
    return merged


def _availability(items: list[dict[str, Any]]) -> str:
    return "available" if items else "empty"


def _record_source(adapter_module: Any) -> str:
    get_data_source = getattr(adapter_module, "get_data_source", None)
    if callable(get_data_source):
        return str(get_data_source())
    return "local_json"


def _adapter_warnings(adapter_module: Any) -> list[str]:
    """Collect warnings from the adapter module's fallback tracking."""
    get_warnings = getattr(adapter_module, "get_data_source_status", None)
    if callable(get_warnings):
        status = get_warnings()
        if isinstance(status, dict):
            return list(status.get("warnings", []))
    return []


def _raw_ref(kind: str, source: str, data_dir: str | None, case_id: str | None) -> list[dict[str, str]]:
    if source == "opensearch":
        return [{"kind": kind, "ref": f"opensearch:{kind}"}]
    try:
        resolved_dir = resolve_data_dir(data_dir=data_dir, case_id=case_id)
    except Exception:
        return []
    return [{"kind": kind, "ref": f"{resolved_dir}/{kind}.json"}]


def _result(
    *,
    source: str,
    kind: str,
    query: dict[str, Any],
    items: list[dict[str, Any]],
    data_dir: str | None,
    case_id: str | None,
    availability: str | None = None,
    warnings: list[str] | None = None,
    adapter_module: Any = None,
) -> RepositoryResult:
    merged_warnings = list(warnings or [])
    if adapter_module is not None:
        merged_warnings.extend(_adapter_warnings(adapter_module))
    return RepositoryResult(
        source=source,
        query_context=query,
        items=items,
        availability=availability or _availability(items),
        warnings=merged_warnings,
        raw_refs=_raw_ref(kind, source, data_dir, case_id),
    )


def _service_of(record: dict[str, Any]) -> str:
    return str(
        record.get("serviceName")
        or record.get("resource.attributes.service@name")
        or record.get("resource.attributes.compose_service")
        or record.get("resource.attributes.container@name")
        or ""
    )


def _trace_id_of(record: dict[str, Any]) -> str:
    return str(record.get("traceId") or record.get("log.attributes.otelTraceID") or record.get("resource.attributes.sw8@trace_id") or "")


def _is_error_span(span: dict[str, Any]) -> bool:
    status_code = span.get("status.code") or (span.get("status") or {}).get("code")
    http_status_raw = span.get("span.attributes.http@status_code") or span.get("span.attributes.http@response@status_code")
    try:
        http_status = int(http_status_raw)
    except (TypeError, ValueError):
        http_status = 0
    events = span.get("events") or []
    has_error_event = any(
        (event.get("attributes") or {}).get("error@kind")
        or str((event.get("attributes") or {}).get("event", "")).lower() == "error"
        or "exception" in str((event.get("attributes") or {}).get("message", "")).lower()
        for event in events
        if isinstance(event, dict)
    )
    return str(status_code) == "2" or http_status >= 500 or has_error_event or str(span.get("derived.error", "")) == "1"


def _is_error_log(log_record: dict[str, Any]) -> bool:
    severity = str(
        log_record.get("severityText")
        or log_record.get("severity_text")
        or log_record.get("log.attributes.log@level")
        or ""
    ).upper()
    message = str(log_record.get("log.attributes.message") or log_record.get("body") or "")
    stack_trace = str(log_record.get("log.attributes.stack_trace") or "")
    return severity in _ERROR_LEVELS or "exception" in (message + stack_trace).lower() or "error" in (message + stack_trace).lower()


def _value_as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    token = str(value).strip().replace(",", "")
    if not token:
        return None
    try:
        return float(token)
    except ValueError:
        match = re.search(r"-?\d+(?:\.\d+)?", token)
        if not match:
            return None
        try:
            return float(match.group(0))
        except ValueError:
            return None


def _duration_ms_of_span(span: dict[str, Any]) -> float | None:
    nanos = _value_as_float(span.get("durationInNanos") or span.get("duration_in_nanos"))
    if nanos is not None:
        return nanos / 1_000_000
    millis = _value_as_float(span.get("duration_ms") or span.get("durationMs"))
    return millis


def _parse_iso_time(raw: Any) -> datetime | None:
    token = str(raw or "").strip()
    if not token:
        return None
    if token.endswith("Z"):
        token = token[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(token)
    except ValueError:
        return None


def _time_window_minutes(time_range: dict[str, Any] | None) -> float:
    if not time_range:
        return 1.0
    start = _parse_iso_time(time_range.get("start") or time_range.get("time_start"))
    end = _parse_iso_time(time_range.get("end") or time_range.get("time_end"))
    if not start or not end:
        return 1.0
    minutes = abs((end - start).total_seconds()) / 60
    return max(minutes, 1.0)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * percentile
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _metric_name(metric: dict[str, Any]) -> str:
    return str(metric.get("name") or metric.get("metric_name") or "")


def _metric_service(metric: dict[str, Any]) -> str:
    return _service_of(metric)


def _signal_score(signal: str, weight: float) -> float:
    return weight if signal in {"elevated", "increased", "decreased"} else 0.0


class DefaultTraceRepository(TraceRepository):
    def __init__(self, adapter_module: Any = observability_adapter):
        self.adapter = adapter_module

    def get_traces(self, query: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        query_dict = _query_to_dict(query)
        items = self.adapter.get_traces(query_context=query_dict, data_dir=data_dir, case_id=case_id)
        source = _record_source(self.adapter)
        return _result(source=source, kind="trace", query=query_dict, items=items, data_dir=data_dir, case_id=case_id, adapter_module=self.adapter)

    def get_trace_by_id(self, trace_id: str, query: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        query_dict = _query_to_dict(query)
        query_dict["trace_id"] = trace_id
        result = self.get_traces(query_dict, data_dir=data_dir, case_id=case_id)
        result.items = [span for span in result.items if _trace_id_of(span.get("_source", span)) == trace_id]
        result.availability = _availability(result.items)
        return result

    def get_error_spans(self, service_name: str | None = None, time_range: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        query_dict = _with_time_range({"service": service_name} if service_name else None, time_range)
        result = self.get_traces(query_dict, data_dir=data_dir, case_id=case_id)
        result.items = [span for span in result.items if (not service_name or _service_of(span.get("_source", span)) == service_name) and _is_error_span(span.get("_source", span))]
        result.availability = _availability(result.items)
        return result

    def get_span_attributes(self, trace_id: str, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        result = self.get_trace_by_id(trace_id, data_dir=data_dir, case_id=case_id)
        attribute_items: list[dict[str, Any]] = []
        for span in result.items:
            source_span = span.get("_source", span)
            attributes: dict[str, Any] = {}
            nested_attributes = source_span.get("span.attributes") or {}
            if isinstance(nested_attributes, dict):
                attributes.update(nested_attributes)
            for key, value in source_span.items():
                if key.startswith("span.attributes."):
                    attributes[key.removeprefix("span.attributes.")] = value
            attribute_items.append({
                "trace_id": _trace_id_of(source_span),
                "span_id": source_span.get("spanId", ""),
                "service": _service_of(source_span),
                "attributes": attributes,
            })
        result.items = attribute_items
        result.availability = _availability(attribute_items)
        return result


class DefaultLogRepository(LogRepository):
    def __init__(self, adapter_module: Any = observability_adapter):
        self.adapter = adapter_module

    def get_logs(self, query: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        query_dict = _query_to_dict(query)
        items = self.adapter.get_logs(query_context=query_dict, data_dir=data_dir, case_id=case_id)
        source = _record_source(self.adapter)
        return _result(source=source, kind="log", query=query_dict, items=items, data_dir=data_dir, case_id=case_id, adapter_module=self.adapter)

    def get_error_logs(self, service_name: str | None = None, time_range: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        query_dict = _with_time_range({"service": service_name} if service_name else None, time_range)
        result = self.get_logs(query_dict, data_dir=data_dir, case_id=case_id)
        result.items = [log_record for log_record in result.items if (not service_name or _service_of(log_record) == service_name) and _is_error_log(log_record)]
        result.availability = _availability(result.items)
        return result

    def search_logs_by_trace_id(self, trace_id: str, query: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        query_dict = _query_to_dict(query)
        query_dict["trace_id"] = trace_id
        result = self.get_logs(query_dict, data_dir=data_dir, case_id=case_id)
        result.items = [log_record for log_record in result.items if _trace_id_of(log_record) == trace_id]
        result.availability = _availability(result.items)
        return result

    def search_logs_by_keyword(self, keyword: str, time_range: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        query_dict = _with_time_range({"keyword": keyword}, time_range)
        result = self.get_logs(query_dict, data_dir=data_dir, case_id=case_id)
        lowered_keyword = keyword.lower()
        result.items = [
            log_record for log_record in result.items
            if lowered_keyword in str(log_record.get("log.attributes.message") or log_record.get("body") or "").lower()
        ]
        result.availability = _availability(result.items)
        return result


class DefaultMetricRepository(MetricRepository):
    def __init__(
        self,
        adapter_module: Any = observability_adapter,
        trace_repository: TraceRepository | None = None,
        log_repository: LogRepository | None = None,
    ):
        self.adapter = adapter_module
        self.trace_repository = trace_repository or DefaultTraceRepository(adapter_module)
        self.log_repository = log_repository or DefaultLogRepository(adapter_module)

    def _get_metrics(self, query: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        query_dict = _query_to_dict(query)
        items = self.adapter.get_metrics(query_context=query_dict, data_dir=data_dir, case_id=case_id)
        source = _record_source(self.adapter)
        return _result(source=source, kind="metric", query=query_dict, items=items, data_dir=data_dir, case_id=case_id, adapter_module=self.adapter)

    def _filter_metric_series(self, service_name: str | None, time_range: dict[str, Any] | None, name_tokens: tuple[str, ...], *, data_dir: str | None, case_id: str | None) -> RepositoryResult:
        query_dict = _with_time_range({"service": service_name} if service_name else None, time_range)
        result = self._get_metrics(query_dict, data_dir=data_dir, case_id=case_id)
        filtered_items = []
        for metric in result.items:
            metric_service = _metric_service(metric)
            metric_name = _metric_name(metric).lower()
            if service_name and metric_service != service_name:
                continue
            if name_tokens and not any(token in metric_name for token in name_tokens):
                continue
            filtered_items.append(metric)
        result.items = filtered_items
        result.availability = _availability(filtered_items)
        return result

    def get_service_rate(self, service_name: str, time_range: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        result = self.get_red_metrics(service_name, time_range, data_dir=data_dir, case_id=case_id)
        result.items = [item.get("rate", {}) | {"service_name": item.get("service_name")} for item in result.items]
        result.availability = _availability(result.items)
        return result

    def get_service_error_rate(self, service_name: str, time_range: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        result = self.get_red_metrics(service_name, time_range, data_dir=data_dir, case_id=case_id)
        result.items = [item.get("error", {}) | {"service_name": item.get("service_name")} for item in result.items]
        result.availability = _availability(result.items)
        return result

    def get_service_duration(self, service_name: str, time_range: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        result = self.get_red_metrics(service_name, time_range, data_dir=data_dir, case_id=case_id)
        result.items = [item.get("duration", {}) | {"service_name": item.get("service_name")} for item in result.items]
        result.availability = _availability(result.items)
        return result

    def get_red_metrics(self, service_name: str | None = None, time_range: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        query_dict = _with_time_range({"service": service_name} if service_name else None, time_range)
        metric_result = self._get_metrics(query_dict, data_dir=data_dir, case_id=case_id)
        try:
            trace_result = self.trace_repository.get_traces(query_dict, data_dir=data_dir, case_id=case_id)
        except Exception as exc:
            trace_result = RepositoryResult(source=metric_result.source, query_context=query_dict, items=[], availability="unavailable", warnings=[f"trace unavailable: {type(exc).__name__}"])
        try:
            log_result = self.log_repository.get_logs(query_dict, data_dir=data_dir, case_id=case_id)
        except Exception as exc:
            log_result = RepositoryResult(source=metric_result.source, query_context=query_dict, items=[], availability="unavailable", warnings=[f"log unavailable: {type(exc).__name__}"])

        service_names = self._collect_service_names(service_name, trace_result.items, log_result.items, metric_result.items)
        red_items = [
            self._build_service_red_metrics(service, time_range, trace_result.items, log_result.items, metric_result.items)
            for service in service_names
        ]
        warnings = metric_result.warnings + trace_result.warnings + log_result.warnings
        return RepositoryResult(
            source=metric_result.source,
            query_context=query_dict,
            items=red_items,
            availability=_availability(red_items),
            warnings=warnings,
            raw_refs=metric_result.raw_refs + trace_result.raw_refs + log_result.raw_refs,
        )

    def get_all_services_red_metrics(self, time_range: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        return self.get_red_metrics(None, time_range, data_dir=data_dir, case_id=case_id)

    def get_entity_red_metrics(
        self,
        time_range: dict[str, Any] | None = None,
        *,
        data_dir: str | None = None,
        case_id: str | None = None,
    ) -> RepositoryResult:
        """Entity-centered RED metrics using OpenSearch native aggregations.

        Instead of sampling N documents per service and computing RED client-side,
        this method pushes aggregation to OpenSearch using the entity key field
        (resource.attributes.service@name) defined by the otel.service entity model.

        Falls back to get_all_services_red_metrics when OpenSearch is not the
        active data source.
        """
        data_source = _record_source(self.adapter)
        if data_source == "mmodel_api":
            return self._get_entity_red_metrics_via_mmodel(time_range)
        if data_source != "opensearch":
            return self.get_all_services_red_metrics(time_range, data_dir=data_dir, case_id=case_id)

        from app.adapters.opensearch_adapter import OpenSearchAdapter

        adapter = OpenSearchAdapter()
        time_start = (time_range or {}).get("gte") or (time_range or {}).get("start") or ""
        time_end = (time_range or {}).get("lte") or (time_range or {}).get("end") or ""
        query_context = QueryContext(time_start=time_start, time_end=time_end) if (time_start or time_end) else None

        try:
            agg_result = adapter.query_entity_red_metrics(
                query_context=query_context,
                time_range=time_range,
            )
        except Exception as exc:
            logger.warning(
                "[MetricRepository] Entity RED aggregation failed (%s), falling back to sampled RED",
                exc,
            )
            return self.get_all_services_red_metrics(time_range, data_dir=data_dir, case_id=case_id)

        entity_items: list[dict[str, Any]] = agg_result.get("items", [])
        warnings: list[str] = list(agg_result.get("warnings", []))

        # Transform entity RED items into the format expected by intent_router
        red_items: list[dict[str, Any]] = []
        for entity in entity_items:
            svc = entity.get("service_name", "")
            error_rate = entity.get("error_rate", 0)
            error_count = entity.get("error_count", 0)
            p95 = entity.get("p95_latency_ms")
            p50 = entity.get("p50_latency_ms")
            p99 = entity.get("p99_latency_ms")
            log_errors = entity.get("log_error_count", 0)
            anomaly = entity.get("anomaly_score", 0)
            request_count = entity.get("request_count", 0)

            red_items.append({
                "service_name": svc,
                "entity_type": entity.get("entity_type", "otel.service"),
                "request_count": request_count,
                "error": {
                    "error_rate": error_rate,
                    "error_count": error_count,
                    "log_error_count": log_errors,
                },
                "duration": {
                    "p50_duration_ms": p50,
                    "p95_duration_ms": p95,
                    "p99_duration_ms": p99,
                },
                "overall_anomaly_score": anomaly,
                "evidence_summary": [
                    f"[entity={svc}] requests={request_count} errors={error_count} "
                    f"error_rate={error_rate} p95={p95}ms p99={p99}ms "
                    f"log_errors={log_errors} anomaly={anomaly}"
                ],
                "_entity_source": "opensearch_aggregation",
            })

        return RepositoryResult(
            source="opensearch",
            query_context={"time_range": time_range, "mode": "entity_centered_aggregation"},
            items=red_items,
            availability=_availability(red_items),
            warnings=warnings,
            raw_refs=[{"kind": "entity_red_metrics", "ref": "opensearch:aggregation:entity_red_metrics"}],
        )

    def _get_entity_red_metrics_via_mmodel(
        self,
        time_range: dict[str, Any] | None = None,
    ) -> RepositoryResult:
        """Entity-centered RED metrics via MModel API evidence() queries.

        Fetches the entity list from MModel and queries metric evidence per entity,
        then computes RED (Rate/Error/Duration) from the returned metric data.
        """
        try:
            from app.adapters.unifiedmodel_adapter import _mmodel_api_adapter
        except ImportError:
            return RepositoryResult(
                source="mmodel_api",
                query_context={"time_range": time_range, "mode": "entity_centered_mmodel"},
                items=[],
                availability="unavailable",
                warnings=["MModel API adapter not available"],
                raw_refs=[],
            )

        time_start = (time_range or {}).get("gte") or (time_range or {}).get("start") or ""
        time_end = (time_range or {}).get("lte") or (time_range or {}).get("end") or ""
        from_ts = time_start if time_start else None
        to_ts = time_end if time_end else None

        try:
            entities = _mmodel_api_adapter.query_entities(limit=50)
        except Exception as exc:
            logger.warning("[MetricRepository] MModel entity query failed: %s", exc)
            return RepositoryResult(
                source="mmodel_api",
                query_context={"time_range": time_range},
                items=[],
                availability="unavailable",
                warnings=[f"MModel entity query failed: {exc}"],
                raw_refs=[],
            )

        red_items: list[dict[str, Any]] = []
        warnings: list[str] = []

        for entity in entities[:20]:  # Cap at 20 entities for performance
            entity_id = entity.get("__entity_id__", "")
            entity_name = str(entity.get("display_name", "") or entity.get("entity_name", "") or entity_id)
            entity_type = str(entity.get("__entity_type__", "unknown"))

            try:
                metric_items = _mmodel_api_adapter._client.query_evidence(
                    entity_id=entity_id,
                    kind="metric_set",
                    from_ts=from_ts,
                    to_ts=to_ts,
                    limit=50,
                )
            except Exception:
                continue  # Skip entities with no metric data

            if not metric_items:
                continue

            # Compute RED from metric items — extract rate, error, duration signals
            request_count = len(metric_items)
            error_count = sum(
                1 for m in metric_items
                if any(t in str(m.get("name", "")).lower()
                       for t in ("error", "fail", "exception"))
            )
            error_rate = round(error_count / request_count, 4) if request_count else 0.0

            durations: list[float] = []
            for m in metric_items:
                duration_val = _value_as_float(m.get("value"))
                if duration_val is not None and duration_val > 0:
                    durations.append(duration_val)
            p95 = round(_percentile(durations, 0.95), 3) if durations else None
            p50 = round(_percentile(durations, 0.50), 3) if durations else None
            p99 = round(_percentile(durations, 0.99), 3) if durations else None

            anomaly_score = min(1.0, error_rate * 10.0 + (0.3 if p95 and p95 > 1000 else 0.0))

            red_items.append({
                "service_name": entity_name,
                "entity_type": entity_type,
                "request_count": request_count,
                "error": {
                    "error_rate": error_rate,
                    "error_count": error_count,
                    "log_error_count": 0,  # Not available via metric evidence alone
                },
                "duration": {
                    "p50_duration_ms": p50,
                    "p95_duration_ms": p95,
                    "p99_duration_ms": p99,
                },
                "overall_anomaly_score": round(anomaly_score, 3),
                "evidence_summary": [
                    f"[entity={entity_name}] requests={request_count} errors={error_count} "
                    f"error_rate={error_rate} p95={p95}ms p99={p99}ms anomaly={round(anomaly_score, 3)}"
                ],
                "_entity_source": "mmodel_api",
            })

        return RepositoryResult(
            source="mmodel_api",
            query_context={"time_range": time_range, "mode": "entity_centered_mmodel"},
            items=red_items,
            availability=_availability(red_items),
            warnings=warnings,
            raw_refs=[{"kind": "entity_red_metrics", "ref": "mmodel_api:evidence:metric_set"}],
        )

    def _collect_service_names(
        self,
        requested_service: str | None,
        spans: list[dict[str, Any]],
        logs: list[dict[str, Any]],
        metrics: list[dict[str, Any]],
    ) -> list[str]:
        if requested_service:
            return [requested_service]
        names = []
        for record in [*(span.get("_source", span) for span in spans), *logs, *metrics]:
            service = _service_of(record)
            if service and service not in names:
                names.append(service)
        return names

    def _build_service_red_metrics(
        self,
        service_name: str,
        time_range: dict[str, Any] | None,
        spans: list[dict[str, Any]],
        logs: list[dict[str, Any]],
        metrics: list[dict[str, Any]],
    ) -> dict[str, Any]:
        service_spans = [span.get("_source", span) for span in spans if _service_of(span.get("_source", span)) == service_name]
        service_logs = [log_record for log_record in logs if _service_of(log_record) == service_name]
        service_metrics = [metric for metric in metrics if _metric_service(metric) == service_name]

        request_count = len([span for span in service_spans if span.get("kind") in {"", "SPAN_KIND_SERVER", "SPAN_KIND_CLIENT"}]) or len(service_spans)
        minutes = _time_window_minutes(time_range)
        rate_per_minute = round(request_count / minutes, 3) if request_count else 0.0

        error_spans = [span for span in service_spans if _is_error_span(span)]
        error_logs = [log_record for log_record in service_logs if _is_error_log(log_record)]
        error_metric_values = [
            _value_as_float(metric.get("value"))
            for metric in service_metrics
            if any(token in _metric_name(metric).lower() for token in ("error", "errors", "fail", "failure"))
        ]
        error_metric_values = [value for value in error_metric_values if value is not None]
        error_count = len(error_spans)
        total_count = request_count or len(service_spans)
        error_rate = round(error_count / total_count, 4) if total_count else 0.0
        max_error_metric = max(error_metric_values) if error_metric_values else None

        durations = [duration for duration in (_duration_ms_of_span(span) for span in service_spans) if duration is not None]
        duration_metric_values = [
            _value_as_float(metric.get("value"))
            for metric in service_metrics
            if any(token in _metric_name(metric).lower() for token in ("duration", "latency", "p95", "p99"))
        ]
        duration_metric_values = [value for value in duration_metric_values if value is not None]
        avg_duration = round(sum(durations) / len(durations), 3) if durations else None
        p95_duration = _percentile(durations, 0.95)
        p99_duration = _percentile(durations, 0.99)
        max_duration = max(durations) if durations else None
        metric_p95 = max(duration_metric_values) if duration_metric_values else None

        rate_signal = "normal" if request_count else "unknown"
        error_signal = "elevated" if error_count > 0 or bool(error_logs) or (max_error_metric is not None and max_error_metric > 0) else ("normal" if total_count else "unknown")
        effective_p95 = metric_p95 if metric_p95 is not None else p95_duration
        effective_avg = avg_duration or 0
        duration_signal = "elevated" if (effective_p95 is not None and effective_p95 >= 1000) or effective_avg >= 1000 else ("normal" if durations or duration_metric_values else "unknown")
        overall_score = min(1.0, _signal_score(error_signal, 0.45) + _signal_score(duration_signal, 0.35) + (0.1 if request_count else 0.0))

        evidence_summary = []
        evidence_summary.append(f"request_count={request_count}, rate_per_minute={rate_per_minute}")
        evidence_summary.append(f"error_count={error_count}, error_rate={error_rate}, error_logs={len(error_logs)}")
        if avg_duration is not None or effective_p95 is not None:
            evidence_summary.append(f"avg_duration_ms={avg_duration}, p95_duration_ms={round(effective_p95, 3) if effective_p95 is not None else None}")
        if max_error_metric is not None:
            evidence_summary.append(f"metric_error_signal={max_error_metric}")

        return {
            "service_name": service_name,
            "rate": {
                "service_name": service_name,
                "request_count": request_count,
                "rate_per_minute": rate_per_minute,
                "baseline_rate_per_minute": None,
                "change_ratio": None,
                "time_range": time_range or {},
            },
            "error": {
                "service_name": service_name,
                "error_count": error_count,
                "log_error_count": len(error_logs),
                "total_count": total_count,
                "error_rate": error_rate,
                "metric_error_rate": max_error_metric,
                "baseline_error_rate": None,
                "change_ratio": None,
                "time_range": time_range or {},
            },
            "duration": {
                "service_name": service_name,
                "avg_duration_ms": avg_duration,
                "p95_duration_ms": round(p95_duration, 3) if p95_duration is not None else None,
                "p99_duration_ms": round(p99_duration, 3) if p99_duration is not None else None,
                "max_duration_ms": round(max_duration, 3) if max_duration is not None else None,
                "metric_p95_duration_ms": metric_p95,
                "baseline_p95_duration_ms": None,
                "change_ratio": None,
            },
            "rate_signal": rate_signal,
            "error_signal": error_signal,
            "duration_signal": duration_signal,
            "overall_anomaly_score": round(overall_score, 3),
            "evidence_summary": evidence_summary,
            "metric_series": service_metrics,
            "source_counts": {
                "span_count": len(service_spans),
                "log_count": len(service_logs),
                "metric_count": len(service_metrics),
            },
        }


class DefaultServiceMapRepository(ServiceMapRepository):
    def __init__(self, trace_repository: TraceRepository | None = None):
        self.trace_repository = trace_repository or DefaultTraceRepository()

    def get_service_map(self, time_range: dict[str, Any] | None = None, *, query: dict[str, Any] | None = None, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        query_dict = _with_time_range(query, time_range)
        trace_result = self.trace_repository.get_traces(query_dict, data_dir=data_dir, case_id=case_id)
        spans = [span.get("_source", span) for span in trace_result.items]
        services = list(dict.fromkeys(_service_of(span) for span in spans if _service_of(span)))
        call_edges = self._build_call_edges(spans)
        item = {
            "nodes": [{"id": service, "type": "Service"} for service in services],
            "edges": call_edges,
            "call_edges": call_edges,
            "services": services,
            "spans": spans,
        }
        return RepositoryResult(
            source=trace_result.source,
            query_context=query_dict,
            items=[item],
            availability="available" if spans else "empty",
            warnings=trace_result.warnings,
            raw_refs=trace_result.raw_refs,
        )

    def get_call_edges(self, time_range: dict[str, Any] | None = None, *, query: dict[str, Any] | None = None, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        service_map = self.get_service_map(time_range, query=query, data_dir=data_dir, case_id=case_id)
        item = service_map.items[0] if service_map.items else {}
        service_map.items = list(item.get("call_edges", []))
        service_map.availability = _availability(service_map.items)
        return service_map

    def get_upstream_services(self, service_name: str, time_range: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        service_map = self.get_service_map(time_range, data_dir=data_dir, case_id=case_id)
        edges = service_map.items[0].get("edges", []) if service_map.items else []
        upstream = sorted({edge["source"] for edge in edges if edge.get("target") == service_name})
        service_map.items = [{"service": service_name, "upstream_services": upstream}]
        service_map.availability = _availability(service_map.items if upstream else [])
        return service_map

    def get_downstream_services(self, service_name: str, time_range: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        service_map = self.get_service_map(time_range, data_dir=data_dir, case_id=case_id)
        edges = service_map.items[0].get("edges", []) if service_map.items else []
        downstream = sorted({edge["target"] for edge in edges if edge.get("source") == service_name})
        service_map.items = [{"service": service_name, "downstream_services": downstream}]
        service_map.availability = _availability(service_map.items if downstream else [])
        return service_map

    def get_impacted_services(self, service_name: str, time_range: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        service_map = self.get_service_map(time_range, data_dir=data_dir, case_id=case_id)
        edges = service_map.items[0].get("edges", []) if service_map.items else []
        reverse_edges: dict[str, set[str]] = {}
        for edge in edges:
            reverse_edges.setdefault(edge.get("target", ""), set()).add(edge.get("source", ""))
        impacted: list[str] = []
        queue = [service_name]
        seen = {service_name}
        while queue:
            current_service = queue.pop(0)
            for upstream_service in sorted(reverse_edges.get(current_service, set())):
                if upstream_service and upstream_service not in seen:
                    seen.add(upstream_service)
                    impacted.append(upstream_service)
                    queue.append(upstream_service)
        service_map.items = [{"service": service_name, "impacted_services": impacted}]
        service_map.availability = _availability(service_map.items if impacted else [])
        return service_map

    def _build_call_edges(self, spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
        service_by_span = {
            str(span.get("spanId")): _service_of(span)
            for span in spans
            if span.get("spanId") and _service_of(span)
        }
        buckets: dict[tuple[str, str], dict[str, Any]] = {}
        for span in spans:
            source_service = service_by_span.get(str(span.get("parentSpanId") or ""), "")
            target_service = _service_of(span)
            if not source_service or not target_service or source_service == target_service:
                continue
            key = (source_service, target_service)
            bucket = buckets.setdefault(key, {
                "source": source_service,
                "target": target_service,
                "source_service": source_service,
                "target_service": target_service,
                "type": "calls",
                "call_count": 0,
                "error_count": 0,
                "durations": [],
            })
            bucket["call_count"] += 1
            if _is_error_span(span):
                bucket["error_count"] += 1
            duration = _duration_ms_of_span(span)
            if duration is not None:
                bucket["durations"].append(duration)

        edges = []
        for bucket in buckets.values():
            durations = bucket.pop("durations", [])
            call_count = int(bucket.get("call_count") or 0)
            error_count = int(bucket.get("error_count") or 0)
            avg_duration = round(sum(durations) / len(durations), 3) if durations else None
            p95_duration = _percentile(durations, 0.95)
            edges.append({
                **bucket,
                "error_rate": round(error_count / call_count, 4) if call_count else 0.0,
                "avg_duration_ms": avg_duration,
                "p95_duration_ms": round(p95_duration, 3) if p95_duration is not None else None,
            })
        return edges


class DefaultBusinessImpactRepository(BusinessImpactRepository):
    _FIELD_ALIASES = {
        "order_id": ("order_id", "orderid", "app_order_id"),
        "transaction_id": ("transaction_id", "transactionid", "payment_transaction_id", "app_payment_transaction_id"),
        "user_id": ("user_id", "userid", "app_user_id", "enduser_id"),
        "amount": ("amount", "order_amount", "payment_amount", "app_order_amount", "app_payment_amount", "gmv", "revenue", "price", "total"),
        "payment_status": ("payment_status", "app_payment_status", "checkout_status"),
        "payment_charged": ("payment_charged", "app_payment_charged"),
        "currency": ("currency", "app_order_currency", "app_payment_currency"),
    }

    def __init__(
        self,
        trace_repository: TraceRepository | None = None,
        log_repository: LogRepository | None = None,
        metric_repository: MetricRepository | None = None,
    ):
        self.trace_repository = trace_repository or DefaultTraceRepository()
        self.log_repository = log_repository or DefaultLogRepository()
        self.metric_repository = metric_repository or DefaultMetricRepository()

    def get_business_impact(self, service_name: str | None = None, time_range: dict[str, Any] | None = None, *, query: dict[str, Any] | None = None, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        service_names = [service_name] if service_name else []
        return self._get_business_impact(service_names, time_range, query=query, data_dir=data_dir, case_id=case_id)

    def get_business_impact_for_services(self, service_names: list[str], time_range: dict[str, Any] | None = None, *, query: dict[str, Any] | None = None, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        return self._get_business_impact(service_names, time_range, query=query, data_dir=data_dir, case_id=case_id)

    def _get_business_impact(self, service_names: list[str], time_range: dict[str, Any] | None = None, *, query: dict[str, Any] | None = None, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        query_dict = _with_time_range(query, time_range)
        normalized_services = [service for service in dict.fromkeys(service_names) if service]
        warnings: list[str] = []
        try:
            trace_result = self.trace_repository.get_traces(query_dict, data_dir=data_dir, case_id=case_id)
        except Exception as exc:
            warnings.append(f"trace unavailable: {type(exc).__name__}")
            trace_result = RepositoryResult(source="unavailable", query_context=query_dict, items=[], availability="unavailable")
        try:
            log_result = self.log_repository.get_logs(query_dict, data_dir=data_dir, case_id=case_id)
        except Exception as exc:
            warnings.append(f"log unavailable: {type(exc).__name__}")
            log_result = RepositoryResult(source="unavailable", query_context=query_dict, items=[], availability="unavailable")
        try:
            metric_result = self.metric_repository.get_red_metrics(normalized_services[0] if len(normalized_services) == 1 else None, time_range, data_dir=data_dir, case_id=case_id)
        except Exception as exc:
            warnings.append(f"metric unavailable: {type(exc).__name__}")
            metric_result = RepositoryResult(source="unavailable", query_context=query_dict, items=[], availability="unavailable")

        business_events = self._collect_business_events(normalized_services, trace_result.items, log_result.items)
        metric_candidates = [metric for item in metric_result.items for metric in item.get("metric_series", [])] or metric_result.items
        metric_hints = self._business_metric_hints(metric_candidates, normalized_services)
        impacted_services = self._summarize_by_service(business_events, metric_hints)
        summary = self._summarize_business_events(normalized_services, time_range, business_events, metric_hints, impacted_services)
        if not business_events:
            warnings.append("business impact fields or business failure events were not found in trace/log evidence")
        if metric_hints and not business_events:
            warnings.append("business impact is supported only by metric hints; counts remain unknown")
        return RepositoryResult(
            source=trace_result.source if trace_result.source == log_result.source else "mixed_observability",
            query_context=query_dict,
            items=[summary],
            availability="available" if business_events else ("insufficient" if metric_hints else "empty"),
            warnings=warnings,
            raw_refs=trace_result.raw_refs + log_result.raw_refs + metric_result.raw_refs,
        )

    def get_affected_orders(self, service_name: str | None = None, time_range: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        result = self.get_business_impact(service_name, time_range, data_dir=data_dir, case_id=case_id)
        summary = result.items[0] if result.items else {}
        result.items = [{"order_id": order_id} for order_id in summary.get("affected_orders", [])]
        result.availability = _availability(result.items)
        return result

    def get_failed_transactions(self, service_name: str | None = None, time_range: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        result = self.get_business_impact(service_name, time_range, data_dir=data_dir, case_id=case_id)
        summary = result.items[0] if result.items else {}
        result.items = list(summary.get("failed_transactions", []))
        result.availability = _availability(result.items)
        return result

    def get_affected_users(self, service_name: str | None = None, time_range: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        result = self.get_business_impact(service_name, time_range, data_dir=data_dir, case_id=case_id)
        summary = result.items[0] if result.items else {}
        result.items = [{"user_id": user_id} for user_id in summary.get("affected_users", [])]
        result.availability = _availability(result.items)
        return result

    def get_estimated_revenue_impact(self, service_name: str | None = None, time_range: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        result = self.get_business_impact(service_name, time_range, data_dir=data_dir, case_id=case_id)
        summary = result.items[0] if result.items else {}
        revenue = summary.get("estimated_revenue_impact", "unknown")
        result.items = [{"estimated_revenue_impact": revenue, "estimated_gmv_loss": revenue, "currency": summary.get("currency")}]
        result.availability = "available" if revenue != "unknown" else "insufficient"
        return result

    def _summarize_business_events(self, service_names: list[str], time_range: dict[str, Any] | None, business_events: list[dict[str, Any]], metric_hints: list[dict[str, Any]], impacted_services: list[dict[str, Any]]) -> dict[str, Any]:
        affected_orders = sorted({event["order_id"] for event in business_events if event.get("order_id")})
        affected_users = sorted({event["user_id"] for event in business_events if event.get("user_id")})
        failed_events = [event for event in business_events if event.get("is_failure")]
        transaction_ids = sorted({event["transaction_id"] for event in failed_events if event.get("transaction_id")})
        failed_order_ids = sorted({event["order_id"] for event in failed_events if event.get("order_id")})
        failed_transaction_estimated = False
        if transaction_ids:
            failed_transaction_count: int | str = len(transaction_ids)
        elif failed_order_ids:
            failed_transaction_count = len(failed_order_ids)
            failed_transaction_estimated = True
        elif failed_events:
            failed_transaction_count = len({self._event_identity(event) for event in failed_events})
            failed_transaction_estimated = True
        else:
            failed_transaction_count = "unknown"
        revenue_values = [event["amount"] for event in failed_events if isinstance(event.get("amount"), (int, float))]
        estimated_revenue: float | str = round(sum(revenue_values), 2) if revenue_values else "unknown"
        related_trace_ids = sorted({event["trace_id"] for event in business_events if event.get("trace_id")})
        related_span_ids = sorted({event["span_id"] for event in business_events if event.get("span_id")})
        related_log_ids = sorted({event["log_id"] for event in business_events if event.get("log_id")})
        related_services = sorted({event["service_name"] for event in business_events if event.get("service_name")})
        related_red_metrics = self._summarize_metric_links(metric_hints)
        confidence = self._business_confidence(business_events, metric_hints)
        evidence_summary = self._business_evidence_summary(business_events, metric_hints)
        currency = next((event.get("currency") for event in failed_events if event.get("currency")), None)
        return {
            "service_name": service_names[0] if len(service_names) == 1 else None,
            "service_names": service_names,
            "time_range": time_range or {},
            "affected_order_count": len(affected_orders) if affected_orders else "unknown",
            "failed_transaction_count": failed_transaction_count,
            "failed_transaction_count_estimated": failed_transaction_estimated,
            "affected_user_count": len(affected_users) if affected_users else "unknown",
            "estimated_revenue_impact": estimated_revenue,
            "estimated_gmv_loss": estimated_revenue,
            "currency": currency,
            "affected_orders": affected_orders,
            "affected_users": affected_users,
            "failed_transactions": failed_events,
            "business_events": business_events,
            "impacted_services": impacted_services,
            "related_trace_ids": related_trace_ids,
            "related_span_ids": related_span_ids,
            "related_log_ids": related_log_ids,
            "related_services": related_services,
            "related_red_metrics": related_red_metrics,
            "metric_hints": metric_hints,
            "evidence_links": {
                "trace_ids": related_trace_ids,
                "span_ids": related_span_ids,
                "log_ids": related_log_ids,
                "metric_refs": [metric.get("name") or metric.get("service_name") for metric in metric_hints if metric.get("name") or metric.get("service_name")],
                "related_services": related_services,
                "related_red_metrics": related_red_metrics,
            },
            "confidence": confidence,
            "evidence_summary": evidence_summary,
            "source": "observability_derived",
        }

    def _summarize_by_service(self, business_events: list[dict[str, Any]], metric_hints: list[dict[str, Any]]) -> list[dict[str, Any]]:
        services = sorted({event.get("service_name") for event in business_events if event.get("service_name")} | {metric.get("service_name") for metric in metric_hints if metric.get("service_name")})
        impacted_services: list[dict[str, Any]] = []
        for service in services:
            service_events = [event for event in business_events if event.get("service_name") == service]
            service_metrics = [metric for metric in metric_hints if metric.get("service_name") == service]
            service_summary = self._summarize_business_events([service], None, service_events, service_metrics, [])
            impacted_services.append({
                "service_name": service,
                "affected_order_count": service_summary["affected_order_count"],
                "failed_transaction_count": service_summary["failed_transaction_count"],
                "failed_transaction_count_estimated": service_summary["failed_transaction_count_estimated"],
                "affected_user_count": service_summary["affected_user_count"],
                "estimated_revenue_impact": service_summary["estimated_revenue_impact"],
                "currency": service_summary.get("currency"),
                "confidence": service_summary["confidence"],
                "evidence_summary": service_summary["evidence_summary"],
            })
        return impacted_services

    def _collect_business_events(self, service_names: list[str], spans: list[dict[str, Any]], logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        service_filter = set(service_names)
        events: list[dict[str, Any]] = []
        for span in spans:
            source_span = span.get("_source", span)
            service = _service_of(source_span)
            if service_filter and service not in service_filter:
                continue
            fields = self._extract_business_fields(source_span)
            is_failure = self._is_business_failure(source_span)
            if fields or is_failure:
                events.append(self._build_business_event("trace", source_span, fields, is_failure))
        for log_record in logs:
            service = _service_of(log_record)
            if service_filter and service not in service_filter:
                continue
            fields = self._extract_business_fields(log_record)
            is_failure = self._is_business_failure(log_record)
            if fields or is_failure:
                events.append(self._build_business_event("log", log_record, fields, is_failure))
        return events

    def _build_business_event(self, source: str, record: dict[str, Any], fields: dict[str, Any], is_failure: bool) -> dict[str, Any]:
        message = self._message_of(record)
        event = {
            "event_type": self._classify_business_event(record, fields, is_failure),
            "service_name": _service_of(record),
            "timestamp": self._timestamp_of(record),
            "trace_id": _trace_id_of(record),
            "span_id": str(record.get("spanId") or record.get("span_id") or ""),
            "log_id": self._log_id_of(record) if source == "log" else "",
            "order_id": fields.get("order_id"),
            "transaction_id": fields.get("transaction_id"),
            "user_id": fields.get("user_id"),
            "amount": fields.get("amount"),
            "currency": fields.get("currency"),
            "payment_status": fields.get("payment_status"),
            "payment_charged": fields.get("payment_charged"),
            "source": source,
            "message": message[:500],
            "is_failure": is_failure,
            "technical_evidence": {
                "status_error": _is_error_span(record) if source == "trace" else _is_error_log(record),
                "failure_text": self._has_failure_text(record),
                "service_name": _service_of(record),
                "trace_id": _trace_id_of(record),
            },
        }
        return {key: value for key, value in event.items() if value not in (None, "")}

    def _extract_business_fields(self, record: dict[str, Any]) -> dict[str, Any]:
        flattened = self._flatten(record)
        fields: dict[str, Any] = {}
        for key, value in flattened.items():
            normalized_key = key.lower().replace("-", "_").replace("@", "_").replace(".", "_")
            if not fields.get("order_id") and self._matches_alias(normalized_key, "order_id"):
                fields["order_id"] = str(value)
            if not fields.get("transaction_id") and self._matches_alias(normalized_key, "transaction_id"):
                fields["transaction_id"] = str(value)
            if not fields.get("user_id") and self._matches_alias(normalized_key, "user_id"):
                fields["user_id"] = str(value)
            if not fields.get("payment_status") and self._matches_alias(normalized_key, "payment_status"):
                fields["payment_status"] = str(value)
            if fields.get("payment_charged") is None and self._matches_alias(normalized_key, "payment_charged"):
                fields["payment_charged"] = str(value).lower() in {"true", "1", "yes", "charged", "success"}
            if not fields.get("currency") and self._matches_alias(normalized_key, "currency"):
                fields["currency"] = str(value)
            if fields.get("amount") is None and self._matches_alias(normalized_key, "amount"):
                amount = self._to_number(value)
                if amount is not None:
                    fields["amount"] = amount
        fields.update({key: value for key, value in self._extract_business_fields_from_text(self._message_of(record)).items() if value and not fields.get(key)})
        for url_key in ("span.attributes.url", "resource.attributes.http@url", "url", "http.url"):
            raw_url = record.get(url_key)
            if raw_url:
                fields.update({key: value for key, value in self._extract_business_fields_from_url(str(raw_url)).items() if value and not fields.get(key)})
        return fields

    def _matches_alias(self, normalized_key: str, canonical_field: str) -> bool:
        if normalized_key in self._FIELD_ALIASES.get(canonical_field, ()):
            return True
        if canonical_field == "order_id":
            return "order" in normalized_key and "id" in normalized_key
        if canonical_field == "transaction_id":
            return "transaction" in normalized_key and "id" in normalized_key
        if canonical_field == "user_id":
            return "user" in normalized_key and "id" in normalized_key
        if canonical_field == "amount":
            return any(token in normalized_key for token in ("amount", "gmv", "revenue", "price", "total"))
        if canonical_field == "payment_status":
            return ("payment" in normalized_key and "status" in normalized_key) or "checkout_status" in normalized_key
        if canonical_field == "payment_charged":
            return "payment" in normalized_key and "charged" in normalized_key
        if canonical_field == "currency":
            return "currency" in normalized_key
        return False

    def _extract_business_fields_from_url(self, raw_url: str) -> dict[str, Any]:
        query_values = parse_qs(urlparse(raw_url).query)
        fields: dict[str, Any] = {}
        for key, values in query_values.items():
            if not values:
                continue
            normalized_key = key.lower().replace("-", "_")
            value = values[0]
            if "order" in normalized_key and "id" in normalized_key:
                fields["order_id"] = value
            elif "transaction" in normalized_key and "id" in normalized_key:
                fields["transaction_id"] = value
            elif "user" in normalized_key and "id" in normalized_key:
                fields["user_id"] = value
            elif "payment" in normalized_key and "status" in normalized_key:
                fields["payment_status"] = value
            elif any(token in normalized_key for token in ("amount", "gmv", "revenue", "price", "total")):
                amount = self._to_number(value)
                if amount is not None:
                    fields["amount"] = amount
        return fields

    def _extract_business_fields_from_text(self, text: str) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        patterns = {
            "order_id": r"(?:order[_\s.-]?id|order)[:=\s]+([A-Za-z0-9_-]+)",
            "transaction_id": r"(?:transaction[_\s.-]?id|txn[_\s.-]?id|transaction)[:=\s]+([A-Za-z0-9_-]+)",
            "user_id": r"(?:user[_\s.-]?id|user)[:=\s]+([A-Za-z0-9_-]+)",
        }
        for field_name, pattern in patterns.items():
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                fields[field_name] = match.group(1)
        amount_match = re.search(r"(?:amount|gmv|revenue|price|total)[:=\s]+([+-]?\d+(?:\.\d+)?)", text, flags=re.IGNORECASE)
        if amount_match:
            fields["amount"] = self._to_number(amount_match.group(1))
        status_match = re.search(r"(?:payment|checkout)[_\s.-]?status[:=\s]+([A-Za-z0-9_-]+)", text, flags=re.IGNORECASE)
        if status_match:
            fields["payment_status"] = status_match.group(1)
        return fields

    def _flatten(self, record: dict[str, Any], prefix: str = "") -> dict[str, Any]:
        flattened: dict[str, Any] = {}
        for key, value in record.items():
            child_key = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, dict):
                flattened.update(self._flatten(value, child_key))
            else:
                flattened[child_key] = value
        return flattened

    def _to_number(self, value: Any) -> float | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        match = re.search(r"-?\d+(?:\.\d+)?", str(value))
        if not match:
            return None
        try:
            return float(match.group(0))
        except ValueError:
            return None

    def _timestamp_of(self, record: dict[str, Any]) -> str:
        return str(record.get("startTime") or record.get("time") or record.get("timestamp") or record.get("@timestamp") or record.get("observedTimestamp") or "")

    def _message_of(self, record: dict[str, Any]) -> str:
        events = record.get("events") or []
        event_messages = []
        for event in events:
            if isinstance(event, dict):
                attrs = event.get("attributes") or {}
                event_messages.extend(str(attrs.get(key) or "") for key in ("message", "exception.message", "error@kind"))
        return " ".join([
            str(record.get("name") or ""),
            str(record.get("status.message") or ""),
            str(record.get("log.attributes.message") or record.get("body") or ""),
            str(record.get("log.attributes.stack_trace") or ""),
            " ".join(event_messages),
        ]).strip()

    def _log_id_of(self, record: dict[str, Any]) -> str:
        return str(record.get("_id") or record.get("log_id") or record.get("id") or ":".join(token for token in [_trace_id_of(record), self._timestamp_of(record), _service_of(record)] if token))

    def _is_business_failure(self, record: dict[str, Any]) -> bool:
        fields = self._extract_business_fields(record)
        payment_status = str(fields.get("payment_status") or "").lower()
        if payment_status in {"failed", "failure", "declined", "error", "cancelled", "canceled"}:
            return True
        if fields.get("payment_charged") is False:
            return True
        return (_is_error_span(record) or _is_error_log(record) or self._has_failure_text(record)) and self._has_business_text(record)

    def _classify_business_event(self, record: dict[str, Any], fields: dict[str, Any], is_failure: bool) -> str:
        text = " ".join([str(record), self._message_of(record), str(fields)]).lower()
        if "fraud" in text:
            return "fraud_check_failure" if is_failure else "unknown_business_failure"
        if "inventory" in text or "stock" in text:
            return "inventory_failure" if is_failure else "unknown_business_failure"
        if "payment" in text or "charge" in text or "transaction" in text:
            return "payment_failure" if is_failure else "unknown_business_failure"
        if "checkout" in text:
            return "checkout_failure" if is_failure else "unknown_business_failure"
        if "order" in text:
            return "order_failure" if is_failure else "unknown_business_failure"
        return "unknown_business_failure"

    def _business_metric_hints(self, metrics: list[dict[str, Any]], service_names: list[str]) -> list[dict[str, Any]]:
        service_filter = set(service_names)
        hints: list[dict[str, Any]] = []
        for metric in metrics:
            service = str(metric.get("service_name") or metric.get("service") or metric.get("resource.attributes.compose_service") or "")
            if service_filter and service and service not in service_filter:
                continue
            text = str(metric.get("name") or metric.get("service_name") or metric).lower()
            has_business_name = any(token in text for token in _BUSINESS_TOKENS)
            has_error_signal = any(token in text for token in ("error", "fail", "transaction")) or metric.get("error_signal") == "elevated" or metric.get("overall_anomaly_score")
            if has_business_name or has_error_signal:
                hints.append(metric)
        return hints

    def _summarize_metric_links(self, metric_hints: list[dict[str, Any]]) -> list[dict[str, Any]]:
        links: list[dict[str, Any]] = []
        for metric in metric_hints[:10]:
            links.append({
                "service_name": metric.get("service_name") or metric.get("service"),
                "name": metric.get("name"),
                "overall_anomaly_score": metric.get("overall_anomaly_score"),
                "error_signal": metric.get("error_signal"),
                "error_rate": (metric.get("error") or {}).get("error_rate") if isinstance(metric.get("error"), dict) else metric.get("error_rate"),
                "request_count": (metric.get("rate") or {}).get("request_count") if isinstance(metric.get("rate"), dict) else metric.get("request_count"),
            })
        return links

    def _business_confidence(self, business_events: list[dict[str, Any]], metric_hints: list[dict[str, Any]]) -> str:
        if any(event.get("order_id") or event.get("user_id") or event.get("amount") is not None for event in business_events):
            return "high"
        if business_events:
            return "medium"
        if metric_hints:
            return "low"
        return "none"

    def _business_evidence_summary(self, business_events: list[dict[str, Any]], metric_hints: list[dict[str, Any]]) -> list[str]:
        summary: list[str] = []
        trace_events = [event for event in business_events if event.get("source") == "trace"]
        log_events = [event for event in business_events if event.get("source") == "log"]
        if trace_events:
            summary.append(f"trace 中识别业务失败事件 {len(trace_events)} 条")
        if log_events:
            summary.append(f"log 中识别业务失败事件 {len(log_events)} 条")
        if any(event.get("order_id") for event in business_events):
            summary.append("已从可观测字段提取 order_id，可统计受影响订单")
        if any(event.get("user_id") for event in business_events):
            summary.append("已从可观测字段提取 user_id，可统计受影响用户")
        if any(event.get("amount") is not None for event in business_events):
            summary.append("已从可观测字段提取金额，可估算金额影响")
        if metric_hints:
            summary.append(f"RED/metric 异常信号 {len(metric_hints)} 条，仅用于辅助影响程度判断")
        return summary or ["未识别到可证明业务受损的 trace/log/metric 字段"]

    def _event_identity(self, event: dict[str, Any]) -> str:
        for key in ("transaction_id", "order_id", "span_id", "log_id"):
            value = event.get(key)
            if value:
                return f"{key}:{value}"
        return f"{event.get('source')}:{event.get('service_name')}:{event.get('trace_id')}:{event.get('event_type')}:{event.get('timestamp')}"

    def _has_failure_text(self, record: dict[str, Any]) -> bool:
        text = str(record).lower()
        return any(token in text for token in _FAILURE_TOKENS) and any(token in text for token in _BUSINESS_TOKENS)

    def _has_business_text(self, record: dict[str, Any]) -> bool:
        text = str(record).lower()
        return any(token in text for token in _BUSINESS_TOKENS)


def get_trace_repository() -> TraceRepository:
    return DefaultTraceRepository()


def get_log_repository() -> LogRepository:
    return DefaultLogRepository()


def get_metric_repository() -> MetricRepository:
    return DefaultMetricRepository()


def get_service_map_repository() -> ServiceMapRepository:
    return DefaultServiceMapRepository()


def get_business_impact_repository() -> BusinessImpactRepository:
    return DefaultBusinessImpactRepository()
