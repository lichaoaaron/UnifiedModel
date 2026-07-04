"""
UnifiedModelAdapter: reads versioned fault samples from UnifiedModel examples.

This adapter provides:
  - File-based mode (DATA_SOURCE=unifiedmodel): reads local JSON from
    UnifiedModel/examples/mmodel-fault-samples/
  - REST API mode (DATA_SOURCE=mmodel_api): calls MModel REST API
    (Query Service evidence(), .entity, .topo) to fetch runtime data.

Set DATA_SOURCE=mmodel_api and MMODEL_API_URL=http://localhost:8080
in backend/.env to use the REST API mode.
"""
import json
import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.adapters.mmodel_rest_client import get_mmodel_client
from app.models.query_context import QueryContext

logger = logging.getLogger(__name__)

_DEFAULT_SAMPLE_DIR = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "..",
        "examples",
        "mmodel-fault-samples",
    )
)


def _resolve_sample_dir(data_dir: str | None = None) -> str:
    configured = data_dir or os.environ.get("UNIFIEDMODEL_SAMPLE_DIR") or _DEFAULT_SAMPLE_DIR
    return os.path.normpath(configured)


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(int(raw), minimum)
    except ValueError:
        logger.warning("[UnifiedModelAdapter] invalid %s=%r, using default=%d", name, raw, default)
        return default


def _service_tokens_from_api(api: str | None) -> list[str]:
    text = (api or "").strip().strip("/")
    if not text:
        return []

    tokens: list[str] = []
    service_match = re.search(r"(?:^|[./])([A-Za-z0-9_]+)Service(?:[./]|$)", text)
    if service_match:
        base = service_match.group(1)
        tokens.extend([
            re.sub(r"(?<!^)(?=[A-Z])", "-", base).replace("_", "-").lower(),
            base.replace("_", "").lower(),
            base.lower(),
        ])
    tokens.extend(part.lower().replace("_", "-") for part in re.split(r"[/.:]+", text) if part)

    deduped: list[str] = []
    for token in tokens:
        if token and token not in deduped:
            deduped.append(token)
    return deduped


def _service_tokens_from_trace_items(items: list[dict[str, Any]]) -> list[str]:
    tokens: list[str] = []
    for item in items:
        text = " ".join(
            str(item.get(key) or "")
            for key in (
                "name",
                "status.message",
                "span.attributes.rpc@service",
                "span.attributes.rpc@method",
            )
        )
        tokens.extend(_service_tokens_from_api(text))
        for match in re.finditer(r"\b([A-Z][A-Za-z0-9_]+)(?:Service)?\s+request\s+failed\b", text):
            base = match.group(1)
            tokens.append(re.sub(r"(?<!^)(?=[A-Z])", "-", base).replace("_", "-").lower())

    deduped: list[str] = []
    for token in tokens:
        if token and token not in deduped:
            deduped.append(token)
    return deduped


@lru_cache(maxsize=4)
def _load_dataset(sample_dir: str) -> dict[str, Any]:
    root = Path(sample_dir)
    traces_path = root / "evidence" / "traces.json"
    logs_path = root / "evidence" / "logs.json"
    metrics_path = root / "evidence" / "metrics.json"
    scenarios_path = root / "scenarios" / "index.json"

    missing = [
        str(p)
        for p in (traces_path, logs_path, metrics_path, scenarios_path)
        if not p.is_file()
    ]
    if missing:
        raise FileNotFoundError(
            f"UnifiedModel sample files missing under {sample_dir}: {', '.join(missing)}"
        )

    scenarios = _read_json(scenarios_path)
    scenario_map = {
        str(item.get("scenario_id")): item
        for item in scenarios
        if isinstance(item, dict) and item.get("scenario_id")
    }
    return {
        "traces": _read_json(traces_path),
        "logs": _read_json(logs_path),
        "metrics": _read_json(metrics_path),
        "scenarios": scenario_map,
    }


def _select_scenario_id(dataset: dict[str, Any], case_id: str | None) -> str | None:
    if case_id and case_id in dataset["scenarios"]:
        return case_id
    if case_id:
        logger.warning(
            "[UnifiedModelAdapter] scenario_id=%s not found, fallback to first scenario",
            case_id,
        )
    return next(iter(dataset["scenarios"].keys()), None)


def _filter_traces_by_scenario(traces: list[dict], scenario: dict[str, Any] | None) -> list[dict]:
    if not scenario:
        return traces

    synthetic_trace_id = str(scenario.get("synthetic_trace_id") or "")
    source_trace_id = str(scenario.get("source_trace_id") or "")
    fault_type = str(scenario.get("fault_type") or "")

    filtered = [
        item
        for item in traces
        if (
            (synthetic_trace_id and str(item.get("traceId") or "") == synthetic_trace_id)
            or (source_trace_id and str(item.get("source.traceId") or "") == source_trace_id)
            or (fault_type and str(item.get("sample.scenario_fault_type") or "") == fault_type)
        )
    ]
    return filtered or traces


def _filter_by_scenario_id(items: list[dict], scenario_id: str | None) -> list[dict]:
    if not scenario_id:
        return items
    filtered = [item for item in items if str(item.get("sample.scenario_id") or "") == scenario_id]
    return filtered or items


class MModelApiAdapter:
    """Fetch runtime entities and evidence via MModel REST API (Query Service).

    Replaces file-based UnifiedModelAdapter when DATA_SOURCE=mmodel_api.

    Entity resolution strategy (in priority order):
      1. If the context contains a 32-char hex entity_id, use it directly.
      2. If the context has a service name, search .entity by query=service_name
         and use the first matching entity's __entity_id__.
      3. If neither, query all entities in the workspace and aggregate evidence
         across them (wide scan).
    """

    _ENTITY_ID_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")

    def __init__(self) -> None:
        self._client = get_mmodel_client()

    @staticmethod
    def _is_entity_id(value: str) -> bool:
        return bool(MModelApiAdapter._ENTITY_ID_PATTERN.match(value))

    def _resolve_entity_ids(
        self,
        query_context: QueryContext | None,
        limit: int = 50,
    ) -> list[str]:
        """Resolve one or more entity IDs from the query context.

        Returns a list of __entity_id__ values for otel.service entities
        (which have DataLinks for trace/log/metric evidence). Infra entities
        are excluded because they lack telemetry DataLinks.
        """
        # Always query service entities — infra entities have no DataLinks
        def _service_entities() -> list[dict[str, Any]]:
            entities = self._client.query_entities(entity_type="otel.service", limit=limit)
            services = [
                e for e in entities
                if str(e.get("__entity_type__") or "").lower() == "otel.service"
            ]
            return services or entities

        def _entity_name(entity: dict[str, Any]) -> str:
            return str(entity.get("display_name") or entity.get("entity_name") or entity.get("name") or "").lower()

        if query_context is None:
            entities = _service_entities()
            return [e.get("__entity_id__", "") for e in entities if e.get("__entity_id__")]

        candidate = query_context.service or query_context.instance or ""
        if candidate:
            if self._is_entity_id(candidate):
                return [candidate]
            # Service name → search by name (prefer otel.service)
            entities = _service_entities()
            matching = [
                e for e in entities
                if candidate.lower() in _entity_name(e)
            ]
            if matching:
                return [e.get("__entity_id__", "") for e in matching if e.get("__entity_id__")]

        # Fallback: wide scan — otel.service entities only
        entities = _service_entities()
        api_tokens = _service_tokens_from_api(query_context.api)
        if api_tokens:
            matching = [
                e for e in entities
                if any(token in _entity_name(e) for token in api_tokens)
            ]
            if matching:
                return [e.get("__entity_id__", "") for e in matching if e.get("__entity_id__")]

        return [e.get("__entity_id__", "") for e in entities if e.get("__entity_id__")]

    def _time_range_from_context(self, query_context: QueryContext | None) -> tuple[str | None, str | None]:
        if query_context is None:
            return None, None
        return query_context.time_start, query_context.time_end

    def _query_evidence_for_entities(
        self,
        entity_ids: list[str],
        kind: str,
        from_ts: str | None,
        to_ts: str | None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query evidence across one or more entities, deduplicating results."""
        all_items: list[dict[str, Any]] = []
        seen: set[str] = set()
        max_entities = _env_int("MMODEL_EVIDENCE_MAX_ENTITIES", 1)
        attempted_entity_ids = entity_ids[:max_entities]
        per_entity_limit = max(limit // max(len(attempted_entity_ids), 1), 10)
        successful_queries = 0
        failures: list[str] = []
        for eid in attempted_entity_ids:
            try:
                items = self._client.query_evidence(
                    entity_id=eid,
                    kind=kind,
                    from_ts=from_ts,
                    to_ts=to_ts,
                    limit=per_entity_limit,
                )
                successful_queries += 1
                for item in items:
                    key = str(item.get("traceId") or item.get("spanId") or item.get("_id") or hash(str(item)))
                    if key not in seen:
                        seen.add(key)
                        all_items.append(item)
            except Exception as exc:
                failures.append(f"{eid}: {exc}")
                logger.warning(
                    "[MModelApiAdapter] evidence query failed for entity=%s kind=%s: %s",
                    eid, kind, exc,
                )
        if attempted_entity_ids and successful_queries == 0 and failures:
            raise RuntimeError(
                f"MModel API evidence query failed for all {len(attempted_entity_ids)} "
                f"attempted entities (kind={kind}): {failures[-1]}"
            )
        return all_items

    def _expand_trace_items_with_related_services(
        self,
        items: list[dict[str, Any]],
        from_ts: str | None,
        to_ts: str | None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        trace_ids = {str(item.get("traceId") or "") for item in items if item.get("traceId")}
        if not trace_ids:
            return items

        current_services = {
            str(item.get("serviceName") or item.get("resource.attributes.service@name") or "").lower()
            for item in items
            if item.get("serviceName") or item.get("resource.attributes.service@name")
        }
        tokens = [
            token for token in _service_tokens_from_trace_items(items)
            if token not in current_services
        ]
        if not tokens:
            return items

        try:
            entities = self._client.query_entities(entity_type="otel.service", limit=50)
        except Exception as exc:
            logger.warning("[MModelApiAdapter] related service entity query failed: %s", exc)
            return items

        related_entity_ids: list[str] = []
        for entity in entities:
            if str(entity.get("__entity_type__") or "").lower() != "otel.service":
                continue
            name = str(entity.get("display_name") or entity.get("entity_name") or entity.get("name") or "").lower()
            if name in current_services:
                continue
            if any(token in name for token in tokens):
                entity_id = str(entity.get("__entity_id__") or "")
                if entity_id and entity_id not in related_entity_ids:
                    related_entity_ids.append(entity_id)

        if not related_entity_ids:
            return items

        try:
            related_items = self._query_evidence_for_entities(
                related_entity_ids,
                kind="trace_set",
                from_ts=from_ts,
                to_ts=to_ts,
                limit=limit,
            )
        except Exception as exc:
            logger.warning("[MModelApiAdapter] related trace expansion failed: %s", exc)
            return items

        merged = list(items)
        seen = {str(item.get("spanId") or item.get("_id") or hash(str(item))) for item in merged}
        for item in related_items:
            if str(item.get("traceId") or "") not in trace_ids:
                continue
            key = str(item.get("spanId") or item.get("_id") or hash(str(item)))
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
        return merged

    def query_trace(
        self,
        query_context: QueryContext | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        entity_ids = self._resolve_entity_ids(query_context)
        from_ts, to_ts = self._time_range_from_context(query_context)

        if not entity_ids:
            logger.warning("[MModelApiAdapter] No entities found in workspace, returning empty traces")
            return {"source": "mmodel_api", "total_hits": 0, "items": [], "aggregations": {}}

        items = self._query_evidence_for_entities(
            entity_ids, kind="trace_set", from_ts=from_ts, to_ts=to_ts,
        )

        # Filter by trace_id if specified, then still expand to related service
        # entities so a trace-scoped query returns the complete cross-service
        # evidence set instead of only the entry entity's spans.
        if query_context and query_context.trace_id:
            items = [t for t in items if str(t.get("traceId") or "") == query_context.trace_id]
            items = self._expand_trace_items_with_related_services(items, from_ts=from_ts, to_ts=to_ts)
        else:
            items = self._expand_trace_items_with_related_services(items, from_ts=from_ts, to_ts=to_ts)

        return {
            "source": "mmodel_api",
            "entity_ids": entity_ids,
            "total_hits": len(items),
            "items": items,
            "aggregations": {},
        }

    def query_log(
        self,
        query_context: QueryContext | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        entity_ids = self._resolve_entity_ids(query_context)
        from_ts, to_ts = self._time_range_from_context(query_context)

        if not entity_ids:
            logger.warning("[MModelApiAdapter] No entities found in workspace, returning empty logs")
            return {"source": "mmodel_api", "total_hits": 0, "items": [], "aggregations": {}}

        items = self._query_evidence_for_entities(
            entity_ids, kind="log_set", from_ts=from_ts, to_ts=to_ts,
        )
        return {
            "source": "mmodel_api",
            "entity_ids": entity_ids,
            "total_hits": len(items),
            "items": items,
            "aggregations": {},
        }

    def query_metric(
        self,
        query_context: QueryContext | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        entity_ids = self._resolve_entity_ids(query_context)
        from_ts, to_ts = self._time_range_from_context(query_context)

        if not entity_ids:
            logger.warning("[MModelApiAdapter] No entities found in workspace, returning empty metrics")
            return {"source": "mmodel_api", "total_hits": 0, "items": [], "aggregations": {}}

        items = self._query_evidence_for_entities(
            entity_ids, kind="metric_set", from_ts=from_ts, to_ts=to_ts,
        )
        return {
            "source": "mmodel_api",
            "entity_ids": entity_ids,
            "total_hits": len(items),
            "items": items,
            "aggregations": {},
        }

    def query_entities(self, domain: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        return self._client.query_entities(domain=domain, limit=limit)

    def query_topo(self, entity_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        return self._client.query_topo(entity_id=entity_id, limit=limit)

    def check_connectivity(self) -> dict[str, Any]:
        return self._client.check_connectivity()


_mmodel_api_adapter = MModelApiAdapter()


class UnifiedModelAdapter:
    def query_trace(
        self,
        query_context: QueryContext | None = None,
        *,
        data_dir: str | None = None,
        case_id: str | None = None,
    ) -> dict[str, Any]:
        sample_dir = _resolve_sample_dir(data_dir)
        dataset = _load_dataset(sample_dir)
        scenario_id = _select_scenario_id(dataset, case_id)
        scenario = dataset["scenarios"].get(scenario_id) if scenario_id else None

        traces = _filter_traces_by_scenario(dataset["traces"], scenario)
        if query_context and query_context.trace_id:
            selected = [t for t in traces if str(t.get("traceId") or "") == query_context.trace_id]
            if selected:
                traces = selected

        return {
            "source": "unifiedmodel",
            "scenario_id": scenario_id,
            "total_hits": len(traces),
            "items": traces,
            "aggregations": {},
        }

    def query_log(
        self,
        query_context: QueryContext | None = None,
        *,
        data_dir: str | None = None,
        case_id: str | None = None,
    ) -> dict[str, Any]:
        sample_dir = _resolve_sample_dir(data_dir)
        dataset = _load_dataset(sample_dir)
        scenario_id = _select_scenario_id(dataset, case_id)
        logs = _filter_by_scenario_id(dataset["logs"], scenario_id)
        return {
            "source": "unifiedmodel",
            "scenario_id": scenario_id,
            "total_hits": len(logs),
            "items": logs,
            "aggregations": {},
        }

    def query_metric(
        self,
        query_context: QueryContext | None = None,
        *,
        data_dir: str | None = None,
        case_id: str | None = None,
    ) -> dict[str, Any]:
        sample_dir = _resolve_sample_dir(data_dir)
        dataset = _load_dataset(sample_dir)
        scenario_id = _select_scenario_id(dataset, case_id)
        metrics = _filter_by_scenario_id(dataset["metrics"], scenario_id)
        return {
            "source": "unifiedmodel",
            "scenario_id": scenario_id,
            "total_hits": len(metrics),
            "items": metrics,
            "aggregations": {},
        }


_unifiedmodel_adapter = UnifiedModelAdapter()


def get_traces(
    query_context: QueryContext | None = None,
    data_dir: str | None = None,
    case_id: str | None = None,
) -> list[dict]:
    return _unifiedmodel_adapter.query_trace(
        query_context,
        data_dir=data_dir,
        case_id=case_id,
    ).get("items", [])


def get_logs(
    query_context: QueryContext | None = None,
    data_dir: str | None = None,
    case_id: str | None = None,
) -> list[dict]:
    return _unifiedmodel_adapter.query_log(
        query_context,
        data_dir=data_dir,
        case_id=case_id,
    ).get("items", [])


def get_metrics(
    query_context: QueryContext | None = None,
    data_dir: str | None = None,
    case_id: str | None = None,
) -> list[dict]:
    return _unifiedmodel_adapter.query_metric(
        query_context,
        data_dir=data_dir,
        case_id=case_id,
    ).get("items", [])


def get_scenario_metadata(
    case_id: str | None = None,
    data_dir: str | None = None,
) -> dict[str, Any]:
    """Return the full scenario dict for case_id, or {} if not found."""
    sample_dir = _resolve_sample_dir(data_dir)
    try:
        dataset = _load_dataset(sample_dir)
    except FileNotFoundError:
        logger.warning("[UnifiedModelAdapter] sample dir not found: %s", sample_dir)
        return {}
    scenario_id = _select_scenario_id(dataset, case_id)
    if not scenario_id:
        return {}
    return dict(dataset["scenarios"].get(scenario_id) or {})
