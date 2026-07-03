"""
Observability adapter selector.

DATA_SOURCE values:
  - local_json (default)
  - opensearch
  - unifiedmodel
  - mmodel_api

When OpenSearch adapter is selected but query fails, this module falls back
to local_json and records warnings so the orchestrator can surface them
to the API response and frontend.

mmodel_api mode calls MModel's Query Service (evidence() operator) via REST API
instead of reading local files. Requires MModel server running at MMODEL_API_URL.
"""
import logging
import os
from typing import Any

from app.adapters import local_json_adapter
from app.adapters.opensearch_adapter import OpenSearchAdapter
from app.adapters.unifiedmodel_adapter import UnifiedModelAdapter, _mmodel_api_adapter
from app.models.query_context import QueryContext

logger = logging.getLogger(__name__)

_DEFAULT_DATA_SOURCE = "local_json"
_SUPPORTED_DATA_SOURCES = {_DEFAULT_DATA_SOURCE, "opensearch", "unifiedmodel", "mmodel_api"}
_opensearch_adapter = OpenSearchAdapter()
_unifiedmodel_adapter = UnifiedModelAdapter()

# Module-level state tracking fallback per data kind.
# Cleared by clear_data_source_warnings() at start of each diagnosis run.
_data_source_warnings: list[str] = []
_fallback_occurred: dict[str, bool] = {"trace": False, "log": False, "metric": False}


def _resolve_data_source() -> str:
    configured = os.environ.get("DATA_SOURCE", _DEFAULT_DATA_SOURCE).strip().lower()
    if configured not in _SUPPORTED_DATA_SOURCES:
        logger.warning(
            "[ObservabilityAdapter] Unsupported DATA_SOURCE=%s, fallback to %s",
            configured,
            _DEFAULT_DATA_SOURCE,
        )
        return _DEFAULT_DATA_SOURCE
    return configured


def get_data_source() -> str:
    return _resolve_data_source()


def clear_data_source_warnings() -> None:
    """Reset fallback tracking. Call at the start of each diagnosis run."""
    _data_source_warnings.clear()
    _fallback_occurred["trace"] = False
    _fallback_occurred["log"] = False
    _fallback_occurred["metric"] = False


def get_data_source_status() -> dict[str, Any]:
    """Return structured data source status for API responses."""
    active = _resolve_data_source()
    if active == "mmodel_api":
        connectivity = _mmodel_api_adapter.check_connectivity()
    elif active == "opensearch":
        connectivity = _opensearch_adapter.check_connectivity()
    else:
        connectivity = None
    per_kind: dict[str, str] = {}
    for kind in ("trace", "log", "metric"):
        if active == "local_json":
            per_kind[kind] = "local_json"
        elif _fallback_occurred.get(kind):
            per_kind[kind] = "local_fallback"
        else:
            per_kind[kind] = active
    return {
        "active_source": active,
        "opensearch_connectivity": connectivity,
        "per_kind_source": per_kind,
        "fallback_occurred": any(_fallback_occurred.values()),
        "warnings": list(_data_source_warnings),
    }


def _to_query_context(query_context: QueryContext | dict | None) -> QueryContext | None:
    if query_context is None or isinstance(query_context, QueryContext):
        return query_context
    time_window = query_context.get("time_window") or {}
    return QueryContext(
        time_start=time_window.get("start") or query_context.get("time_start"),
        time_end=time_window.get("end") or query_context.get("time_end"),
        api=query_context.get("alert_api") or query_context.get("api"),
        service=query_context.get("service"),
        instance=query_context.get("instance"),
        trace_id=query_context.get("trace_id"),
        level=query_context.get("level"),
        keyword=query_context.get("keyword"),
        limit=query_context.get("limit"),
    )


def _fallback_to_local_json(kind: str, warning_msg: str, data_dir: str | None = None, case_id: str | None = None) -> list[dict]:
    logger.warning(
        "[ObservabilityAdapter] %s %s, falling back to local_json",
        kind,
        warning_msg,
    )
    _fallback_occurred[kind] = True
    _data_source_warnings.append(f"[{kind}] {warning_msg}，已降级到本地 Case 数据")
    try:
        if kind == "trace":
            return local_json_adapter.get_traces(data_dir=data_dir, case_id=case_id)
        if kind == "log":
            return local_json_adapter.get_logs(data_dir=data_dir, case_id=case_id)
        return local_json_adapter.get_metrics(data_dir=data_dir, case_id=case_id)
    except (ValueError, OSError) as exc:
        logger.warning(
            "[ObservabilityAdapter] %s local_json fallback also failed: %s, returning empty result",
            kind,
            exc,
        )
        _fallback_occurred[kind] = True
        _data_source_warnings.append(
            f"[{kind}] OpenSearch 查询失败（{warning_msg}），且本地 Case 数据不可用（{exc}），"
            "请检查 OPENSEARCH_URL 是否可达，或设置 MMODEL_DATA_DIR 指向本地评测数据目录"
        )
        return []


def _try_mmodel_api(kind: str, fetcher, query_context, data_dir=None, case_id=None):
    """Call an MModel API fetcher with fallback on failure.

    Fallback chain: mmodel_api → opensearch (if configured) → local_json
    """
    try:
        result = fetcher()
        items = result.get("items", [])
        if items:
            return items
        # Empty result from mmodel_api — still counts as success (workspace may be empty)
        return items
    except Exception as exc:
        msg = f"MModel API unreachable: {exc}"
        logger.warning("[ObservabilityAdapter] %s %s", kind, msg)
        _fallback_occurred[kind] = True
        _data_source_warnings.append(f"[{kind}] {msg}，尝试降级")

    # Fallback to OpenSearch if configured
    opensearch_url = os.environ.get("OPENSEARCH_URL", "").strip()
    if opensearch_url:
        try:
            logger.info("[ObservabilityAdapter] %s falling back to OpenSearch", kind)
            if kind == "trace":
                return _opensearch_adapter.query_trace(_to_query_context(query_context)).get("items", [])
            elif kind == "log":
                return _opensearch_adapter.query_log(_to_query_context(query_context)).get("items", [])
            elif kind == "metric":
                return _opensearch_adapter.query_metric(_to_query_context(query_context)).get("items", [])
        except Exception as os_exc:
            logger.warning("[ObservabilityAdapter] %s OpenSearch fallback also failed: %s", kind, os_exc)

    # Final fallback: local JSON
    return _fallback_to_local_json(kind, "MModel API + OpenSearch 均不可用", data_dir=data_dir, case_id=case_id)


def get_traces(query_context: QueryContext | dict | None = None, data_dir: str | None = None, case_id: str | None = None) -> list[dict]:
    data_source = _resolve_data_source()
    if data_source == "mmodel_api":
        return _try_mmodel_api(
            "trace",
            lambda: _mmodel_api_adapter.query_trace(_to_query_context(query_context)),
            query_context, data_dir, case_id,
        )
    if data_source == "opensearch":
        result = _opensearch_adapter.query_trace(_to_query_context(query_context))
        if result.get("warning"):
            return _fallback_to_local_json("trace", result["warning"], data_dir=data_dir, case_id=case_id)
        return result.get("items", [])
    if data_source == "unifiedmodel":
        return _unifiedmodel_adapter.query_trace(
            _to_query_context(query_context),
            data_dir=data_dir,
            case_id=case_id,
        ).get("items", [])
    return local_json_adapter.get_traces(data_dir=data_dir, case_id=case_id)


def get_logs(query_context: QueryContext | dict | None = None, data_dir: str | None = None, case_id: str | None = None) -> list[dict]:
    data_source = _resolve_data_source()
    if data_source == "mmodel_api":
        return _try_mmodel_api(
            "log",
            lambda: _mmodel_api_adapter.query_log(_to_query_context(query_context)),
            query_context, data_dir, case_id,
        )
    if data_source == "opensearch":
        result = _opensearch_adapter.query_log(_to_query_context(query_context))
        if result.get("warning"):
            return _fallback_to_local_json("log", result["warning"], data_dir=data_dir, case_id=case_id)
        return result.get("items", [])
    if data_source == "unifiedmodel":
        return _unifiedmodel_adapter.query_log(
            _to_query_context(query_context),
            data_dir=data_dir,
            case_id=case_id,
        ).get("items", [])
    return local_json_adapter.get_logs(data_dir=data_dir, case_id=case_id)


def get_metrics(query_context: QueryContext | dict | None = None, data_dir: str | None = None, case_id: str | None = None) -> list[dict]:
    data_source = _resolve_data_source()
    if data_source == "mmodel_api":
        return _try_mmodel_api(
            "metric",
            lambda: _mmodel_api_adapter.query_metric(_to_query_context(query_context)),
            query_context, data_dir, case_id,
        )
    if data_source == "opensearch":
        result = _opensearch_adapter.query_metric(_to_query_context(query_context))
        if result.get("warning"):
            return _fallback_to_local_json("metric", result["warning"], data_dir=data_dir, case_id=case_id)
        return result.get("items", [])
    if data_source == "unifiedmodel":
        return _unifiedmodel_adapter.query_metric(
            _to_query_context(query_context),
            data_dir=data_dir,
            case_id=case_id,
        ).get("items", [])
    return local_json_adapter.get_metrics(data_dir=data_dir, case_id=case_id)
