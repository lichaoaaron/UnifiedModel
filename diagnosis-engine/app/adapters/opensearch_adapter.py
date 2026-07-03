"""
OpenSearchAdapter: queries OpenSearch for trace/log/metric observability data.
"""
import base64
import json
import logging
import os
import time as _time
from typing import Any
from urllib import request
from urllib.error import HTTPError, URLError
from urllib.parse import quote

from app.models.query_context import QueryContext

logger = logging.getLogger(__name__)


class _UrllibTransport:
    def __init__(self, base_url: str, username: str | None = None, password: str | None = None, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout

    def search(self, index: str, body: dict) -> dict:
        url = f"{self.base_url}/{quote(index, safe='*,-_.')}/_search"
        data = json.dumps(body).encode("utf-8")
        req = request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        if self.username and self.password:
            token = base64.b64encode(f"{self.username}:{self.password}".encode("utf-8")).decode("ascii")
            req.add_header("Authorization", f"Basic {token}")
        with request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))


class OpenSearchAdapter:
    def __init__(
        self,
        transport: Any | None = None,
        trace_index: str | None = None,
        log_index: str | None = None,
        metric_index: str | None = None,
    ):
        self.trace_index = trace_index or os.environ.get("OPENSEARCH_TRACE_INDEX", "otel-v1-apm-span-*")
        self.log_index = log_index or os.environ.get("OPENSEARCH_LOG_INDEX", "otel-logs-*")
        self.metric_index = metric_index or os.environ.get("OPENSEARCH_METRIC_INDEX", "otel-metrics-*")
        self._transport: Any | None = transport
        self._transport_built: bool = transport is not None

    def _get_transport(self) -> Any | None:
        """Lazily build transport so env vars loaded after import are visible."""
        if not self._transport_built:
            self._transport = self._build_transport()
            self._transport_built = True
        return self._transport

    def _build_transport(self) -> Any | None:
        base_url = os.environ.get("OPENSEARCH_URL", "").strip()
        if not base_url:
            return None
        timeout = float(os.environ.get("OPENSEARCH_TIMEOUT_SECONDS", "10"))
        return _UrllibTransport(
            base_url=base_url,
            username=os.environ.get("OPENSEARCH_USERNAME"),
            password=os.environ.get("OPENSEARCH_PASSWORD"),
            timeout=timeout,
        )

    def check_connectivity(self) -> dict[str, Any]:
        """Lightweight connectivity check against the configured OpenSearch endpoint.

        Returns:
            dict with keys: connected (bool), url (str), latency_ms (float | None),
            error (str | None), configured (bool).
        """
        base_url = os.environ.get("OPENSEARCH_URL", "").strip()
        if not base_url:
            return {
                "connected": False,
                "url": "",
                "latency_ms": None,
                "error": "OPENSEARCH_URL is not configured",
                "configured": False,
            }
        t0 = _time.monotonic()
        try:
            url = base_url.rstrip("/") + "/"
            req = request.Request(url, method="GET")
            username = os.environ.get("OPENSEARCH_USERNAME")
            password = os.environ.get("OPENSEARCH_PASSWORD")
            if username and password:
                token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
                req.add_header("Authorization", f"Basic {token}")
            timeout = float(os.environ.get("OPENSEARCH_TIMEOUT_SECONDS", "5"))
            with request.urlopen(req, timeout=timeout) as resp:
                latency_ms = (_time.monotonic() - t0) * 1000
                body = json.loads(resp.read().decode("utf-8"))
                return {
                    "connected": True,
                    "url": base_url,
                    "latency_ms": round(latency_ms, 1),
                    "error": None,
                    "configured": True,
                    "version": body.get("version", {}).get("number", "") if isinstance(body, dict) else "",
                }
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            latency_ms = (_time.monotonic() - t0) * 1000
            logger.warning("[OpenSearchAdapter] Connectivity check failed: %s", exc)
            return {
                "connected": False,
                "url": base_url,
                "latency_ms": round(latency_ms, 1),
                "error": f"{type(exc).__name__}: {exc}",
                "configured": True,
            }

    def _warning_response(self, warning: str) -> dict[str, Any]:
        return {
            "source": "opensearch",
            "total_hits": 0,
            "items": [],
            "aggregations": {},
            "warning": warning,
        }

    def query_trace(self, query_context: QueryContext | None = None) -> dict[str, Any]:
        body = self._build_search_body(query_context, time_field="startTime", api_fields=[
            "name",
            "span.attributes.url",
            "span.attributes.http@url",
            "span.attributes.url@full",
        ])
        return self._search(self.trace_index, body, self._normalize_trace)

    def query_log(self, query_context: QueryContext | None = None) -> dict[str, Any]:
        body = self._build_search_body(query_context, time_field="@timestamp", message_fields=[
            "body",
            "log.attributes.message",
        ], include_trace_id=True)
        return self._search(self.log_index, body, self._normalize_log)

    def query_metric(self, query_context: QueryContext | None = None) -> dict[str, Any]:
        body = self._build_search_body(query_context, time_field="time", message_fields=["name"], include_trace_id=False)
        return self._search(self.metric_index, body, self._normalize_metric)

    # Compatibility wrappers for current skill call style.
    def get_traces(self, query_context: QueryContext | None = None) -> list[dict]:
        return self.query_trace(query_context).get("items", [])

    def get_logs(self, query_context: QueryContext | None = None) -> list[dict]:
        return self.query_log(query_context).get("items", [])

    def get_metrics(self, query_context: QueryContext | None = None) -> list[dict]:
        return self.query_metric(query_context).get("items", [])

    def _search(self, index: str, body: dict, normalizer) -> dict[str, Any]:
        transport = self._get_transport()
        if transport is None:
            return self._warning_response("OPENSEARCH_URL is not configured")
        try:
            response = transport.search(index, body)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            return self._warning_response(f"OpenSearch query failed: {type(exc).__name__}")

        hits = response.get("hits", {}) if isinstance(response, dict) else {}
        total = hits.get("total", 0)
        if isinstance(total, dict):
            total_hits = total.get("value", 0)
        else:
            total_hits = total
        items = [normalizer(hit.get("_source", hit)) for hit in hits.get("hits", [])]
        return {
            "source": "opensearch",
            "total_hits": total_hits,
            "items": items,
            "aggregations": response.get("aggregations", {}) if isinstance(response, dict) else {},
        }

    def _build_search_body(
        self,
        query_context: QueryContext | None,
        time_field: str,
        api_fields: list[str] | None = None,
        message_fields: list[str] | None = None,
        include_trace_id: bool = True,
    ) -> dict:
        qc = query_context or QueryContext()
        limit = qc.limit or int(os.environ.get("OPENSEARCH_QUERY_LIMIT", "200"))
        filters: list[dict] = []
        must: list[dict] = []

        time_range: dict[str, str] = {}
        if qc.time_start:
            time_range["gte"] = qc.time_start
        if qc.time_end:
            time_range["lte"] = qc.time_end
        if time_range:
            filters.append({"range": {time_field: time_range}})
        if include_trace_id and qc.trace_id:
            filters.append({"term": {"traceId": qc.trace_id}})
        if qc.service:
            filters.append({"bool": {"should": [
                {"term": {"serviceName": qc.service}},
                {"term": {"resource.attributes.service@name": qc.service}},
            ], "minimum_should_match": 1}})
        if qc.level:
            filters.append({"term": {"severityText": qc.level}})

        # API wildcards → should (scoring boost, NOT a hard filter).
        # Alert APIs may not appear verbatim in real span names (e.g. an alert
        # references a user-facing path while spans use internal RPC names).
        # Treating them as must would silently exclude all data.
        api_should: list[dict] = []
        for field in api_fields or []:
            if qc.api:
                api_should.append({"wildcard": {field: f"*{qc.api}*"}})

        # Keyword matches → must (required when keyword is explicitly provided).
        keyword_should: list[dict] = []
        for field in message_fields or []:
            if qc.keyword:
                keyword_should.append({"match": {field: qc.keyword}})
        if keyword_should:
            must.append({"bool": {"should": keyword_should, "minimum_should_match": 1}})

        return {
            "size": limit,
            "sort": [{time_field: {"order": "desc"}}],
            "query": {"bool": {"filter": filters, "must": must, "should": api_should}},
        }

    def _normalize_trace(self, src: dict) -> dict:
        span_attrs = self._get(src, "span.attributes", {}) or {}
        resource_attrs = self._get(src, "resource.attributes", {}) or {}
        status = self._get(src, "status", {}) or {}
        item = dict(src)
        item["resource.attributes.service@name"] = (
            src.get("serviceName")
            or src.get("resource.attributes.service@name")
            or resource_attrs.get("service@name", "")
        )
        item["resource.attributes.service@instance@id"] = (
            src.get("resource.attributes.service@instance@id")
            or resource_attrs.get("service@instance@id", "")
        )
        item["span.attributes.http@status_code"] = (
            src.get("span.attributes.http@status_code")
            or src.get("span.attributes.http@response@status_code")
            or span_attrs.get("http@status_code")
            or span_attrs.get("http@response@status_code")
            or ""
        )
        item["span.attributes.url"] = (
            src.get("span.attributes.url")
            or src.get("span.attributes.http@url")
            or src.get("span.attributes.url@full")
            or span_attrs.get("url")
            or span_attrs.get("http@url")
            or span_attrs.get("url@full")
            or ""
        )
        if isinstance(status, dict):
            item["status.code"] = src.get("status.code") or status.get("code")
            item["status.message"] = src.get("status.message") or status.get("message", "")
        item["events"] = [self._normalize_event(event) for event in src.get("events", []) or []]
        return item

    def _normalize_event(self, event: dict) -> dict:
        attrs = dict(event.get("attributes", {}) or {})
        attrs["error@kind"] = attrs.get("error@kind") or attrs.get("exception@type") or ""
        attrs["message"] = attrs.get("message") or attrs.get("exception@message") or ""
        attrs["stack"] = attrs.get("stack") or attrs.get("exception@stacktrace") or ""
        return {**event, "attributes": attrs}

    def _normalize_log(self, src: dict) -> dict:
        attrs = self._get(src, "log.attributes", {}) or {}
        resource_attrs = self._get(src, "resource.attributes", {}) or {}
        item = dict(src)
        item["time"] = src.get("@timestamp") or src.get("time")
        item["resource.attributes.service@name"] = (
            src.get("serviceName")
            or src.get("resource.attributes.service@name")
            or resource_attrs.get("service@name", "")
        )
        item["log.attributes.message"] = src.get("log.attributes.message") or attrs.get("message") or src.get("body", "")
        item["log.attributes.log@level"] = src.get("log.attributes.log@level") or attrs.get("log@level") or src.get("severityText", "")
        item["log.attributes.error"] = src.get("log.attributes.error") or attrs.get("error") or attrs.get("err") or ""
        item["log.attributes.otelTraceID"] = src.get("log.attributes.otelTraceID") or attrs.get("otelTraceID") or src.get("traceId", "")
        item["log.attributes.otelSpanID"] = src.get("log.attributes.otelSpanID") or attrs.get("otelSpanID") or src.get("spanId", "")
        return item

    def _normalize_metric(self, src: dict) -> dict:
        resource_attrs = self._get(src, "resource.attributes", {}) or {}
        item = dict(src)
        item["resource.attributes.compose_service"] = (
            src.get("resource.attributes.compose_service")
            or resource_attrs.get("compose_service")
            or src.get("resource.attributes.service@name")
            or resource_attrs.get("service@name")
            or src.get("serviceName")
            or ""
        )
        item["resource.attributes.container@name"] = src.get("resource.attributes.container@name") or resource_attrs.get("container@name", "")
        item["resource.attributes.container@id"] = src.get("resource.attributes.container@id") or resource_attrs.get("container@id", "")
        item["resource.attributes.container@hostname"] = src.get("resource.attributes.container@hostname") or resource_attrs.get("container@hostname", "")
        if item.get("value") is None:
            item["value"] = src.get("sum")
        return item

    def _get(self, data: dict, path: str, default: Any = None) -> Any:
        current: Any = data
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                return default
            current = current[part]
        return current

    # ── Entity-centered RED metrics aggregation ──────────────────────────────
    # Instead of sampling N documents per service and computing RED client-side,
    # this method pushes the aggregation to OpenSearch using the entity key field
    # (resource.attributes.service@name) defined by the otel.service entity model.
    #
    # Entity model reference (UnifiedModel):
    #   entity_set: otel.service
    #   field_mapping: display_name ↔ serviceName ↔ resource.attributes.service@name
    #   evidence: trace_set, log_set, metric_set (linked via serviceName)
    # ──────────────────────────────────────────────────────────────────────────

    # Entity key field — the OpenSearch field that identifies an otel.service entity.
    ENTITY_SERVICE_FIELD = "resource.attributes.service@name"

    # Span status codes considered as errors.
    _ERROR_STATUS_CODES = {2}  # status.code=2 = Error (OTel semantic convention)

    def query_entity_red_metrics(
        self,
        query_context: QueryContext | None = None,
        time_range: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Compute per-entity RED metrics using OpenSearch native aggregations.

        Groups spans by the entity key field and computes request_count,
        error_count, error_rate, P50/P95/P99 latency per entity (service).
        Also queries logs for per-entity error log counts.

        Args:
            query_context: Optional QueryContext with time_start/time_end.
            time_range: Optional {"gte": ..., "lte": ...} dict (takes precedence).

        Returns:
            dict with keys: source, items (list of per-entity RED dicts),
            total_entities, warnings.
        """
        qc = query_context or QueryContext()
        time_filter = self._build_time_filter(qc, time_range, time_field="startTime")
        log_time_filter = self._build_time_filter(qc, time_range, time_field="observedTimestamp")

        # ── Span aggregation: per-entity request count, error count, latency ─
        span_agg_body = {
            "size": 0,
            "query": {"bool": {"filter": [time_filter]} if time_filter else {}},
            "aggs": {
                "by_entity": {
                    "terms": {
                        "field": self.ENTITY_SERVICE_FIELD,
                        "size": 100,
                        "order": {"_count": "desc"},
                    },
                    "aggs": {
                        "error_spans": {
                            "filter": {"terms": {"status.code": list(self._ERROR_STATUS_CODES)}},
                        },
                        "p50_latency_ns": {
                            "percentiles": {"field": "durationInNanos", "percents": [50]},
                        },
                        "p95_latency_ns": {
                            "percentiles": {"field": "durationInNanos", "percents": [95]},
                        },
                        "p99_latency_ns": {
                            "percentiles": {"field": "durationInNanos", "percents": [99]},
                        },
                        "latest_span": {
                            "top_hits": {
                                "size": 1,
                                "sort": [{"startTime": "desc"}],
                                "_source": ["name", "status.code", "startTime", "durationInNanos"],
                            },
                        },
                    },
                },
                "total_error_spans": {
                    "filter": {"terms": {"status.code": list(self._ERROR_STATUS_CODES)}},
                },
            },
        }

        # ── Log aggregation: per-entity error log count ─
        log_agg_body = {
            "size": 0,
            "query": {"bool": {"filter": [
                *([log_time_filter] if log_time_filter else []),
                {"terms": {"severityText": ["ERROR", "FATAL", "CRITICAL", "WARN"]}},
            ]}},
            "aggs": {
                "by_entity": {
                    "terms": {
                        "field": self.ENTITY_SERVICE_FIELD,
                        "size": 100,
                    },
                },
            },
        }

        warnings: list[str] = []
        span_result: dict[str, Any] = {}
        log_result: dict[str, Any] = {}

        # Execute span aggregation
        try:
            span_result = self._search_aggregation(self.trace_index, span_agg_body)
        except Exception as exc:
            warnings.append(f"Trace aggregation failed: {type(exc).__name__}: {exc}")
            logger.warning("[OpenSearchAdapter] Entity RED trace aggregation failed: %s", exc)

        # Execute log aggregation
        try:
            log_result = self._search_aggregation(self.log_index, log_agg_body)
        except Exception as exc:
            warnings.append(f"Log aggregation failed: {type(exc).__name__}: {exc}")
            logger.warning("[OpenSearchAdapter] Entity RED log aggregation failed: %s", exc)

        # ── Merge span + log results per entity ─────────────────────────────
        span_buckets = self._extract_buckets(span_result, "by_entity")
        log_buckets = self._extract_buckets(log_result, "by_entity")

        # Build lookup: service_name → log_error_count
        log_error_by_service: dict[str, int] = {}
        for bucket in log_buckets:
            svc = str(bucket.get("key", ""))
            if svc:
                log_error_by_service[svc] = int(bucket.get("doc_count", 0))

        # Total error spans across all entities (for global anomaly context)
        total_error_span_count = 0
        total_agg = span_result.get("aggregations", {}) if isinstance(span_result, dict) else {}
        total_error = total_agg.get("total_error_spans", {})
        if isinstance(total_error, dict):
            total_error_span_count = int(total_error.get("doc_count", 0))

        items: list[dict[str, Any]] = []
        for bucket in span_buckets:
            service_name = str(bucket.get("key", ""))
            if not service_name:
                continue

            request_count = int(bucket.get("doc_count", 0))
            if request_count == 0:
                continue

            error_agg = bucket.get("error_spans", {})
            error_count = int(error_agg.get("doc_count", 0)) if isinstance(error_agg, dict) else 0
            error_rate = round(error_count / request_count, 4) if request_count > 0 else 0.0

            p50_ns = self._extract_percentile(bucket, "p50_latency_ns", 50)
            p95_ns = self._extract_percentile(bucket, "p95_latency_ns", 95)
            p99_ns = self._extract_percentile(bucket, "p99_latency_ns", 99)

            log_error_count = log_error_by_service.get(service_name, 0)

            # Latest span sample for context
            latest_hits = (bucket.get("latest_span", {}) or {}).get("hits", {}).get("hits", [])
            latest_span_sample: dict[str, Any] | None = None
            if latest_hits:
                src = latest_hits[0].get("_source", {})
                latest_span_sample = {
                    "name": src.get("name", ""),
                    "status_code": src.get("status", {}).get("code") if isinstance(src.get("status"), dict) else src.get("status.code"),
                    "start_time": src.get("startTime", ""),
                    "duration_ms": round((src.get("durationInNanos", 0) or 0) / 1_000_000, 2),
                }

            # ── Compute anomaly_score (entity-centered heuristic) ────────────
            # Weighted combination of error_rate, error_count, and latency deviation.
            # error_rate dominates (weight 0.6), latency contributes 0.25, error_count 0.15.
            error_score = min(error_rate * 3, 1.0)  # error_rate 0.33 → score 1.0
            latency_score = min((p95_ns or 0) / 5_000_000_000, 1.0)  # 5s P95 → score 1.0
            count_score = min(error_count / 100, 1.0)  # 100 errors → score 1.0
            anomaly_score = round(
                error_score * 0.6 + latency_score * 0.25 + count_score * 0.15,
                4,
            )

            items.append({
                "entity_type": "otel.service",
                "entity_key_field": self.ENTITY_SERVICE_FIELD,
                "service_name": service_name,
                "request_count": request_count,
                "error_count": error_count,
                "error_rate": error_rate,
                "p50_latency_ms": round((p50_ns or 0) / 1_000_000, 2),
                "p95_latency_ms": round((p95_ns or 0) / 1_000_000, 2),
                "p99_latency_ms": round((p99_ns or 0) / 1_000_000, 2),
                "log_error_count": log_error_count,
                "anomaly_score": anomaly_score,
                "latest_span_sample": latest_span_sample,
            })

        return {
            "source": "opensearch",
            "items": items,
            "total_entities": len(items),
            "total_error_span_count": total_error_span_count,
            "warnings": warnings,
        }

    def _search_aggregation(self, index: str, body: dict) -> dict[str, Any]:
        """Execute an aggregation-only query (size=0) against an index."""
        transport = self._get_transport()
        if transport is None:
            raise RuntimeError("OPENSEARCH_URL is not configured")
        return transport.search(index, body)

    @staticmethod
    def _build_time_filter(
        qc: QueryContext,
        time_range: dict[str, str] | None,
        time_field: str,
    ) -> dict[str, Any] | None:
        """Build a range filter dict for the given time field."""
        gte = (time_range or {}).get("gte") or qc.time_start
        lte = (time_range or {}).get("lte") or qc.time_end
        if gte or lte:
            range_filter: dict[str, str] = {}
            if gte:
                range_filter["gte"] = gte
            if lte:
                range_filter["lte"] = lte
            return {"range": {time_field: range_filter}}
        return None

    @staticmethod
    def _extract_buckets(result: dict[str, Any], agg_name: str) -> list[dict[str, Any]]:
        """Safely extract term-aggregation buckets from an aggregation response."""
        if not isinstance(result, dict):
            return []
        agg = result.get("aggregations", {})
        if not isinstance(agg, dict):
            return []
        bucket_agg = agg.get(agg_name, {})
        if not isinstance(bucket_agg, dict):
            return []
        buckets = bucket_agg.get("buckets", [])
        return buckets if isinstance(buckets, list) else []

    @staticmethod
    def _extract_percentile(bucket: dict[str, Any], agg_name: str, percent: int) -> float | None:
        """Extract a percentile value from a nested percentiles aggregation."""
        pct_agg = bucket.get(agg_name, {})
        if not isinstance(pct_agg, dict):
            return None
        values = pct_agg.get("values", {})
        if not isinstance(values, dict):
            return None
        val = values.get(str(float(percent)))
        return float(val) if val is not None else None
