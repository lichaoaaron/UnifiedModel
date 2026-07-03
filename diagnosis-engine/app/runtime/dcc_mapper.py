"""Mapper helpers for DCC payloads and DiagnosisContext seed data."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _extract_rows(section: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not section:
        return []
    rows = section.get("rows")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    return []


def _infer_availability(items: list[dict[str, Any]], supplied: bool) -> str:
    if not supplied:
        return "unavailable"
    if not items:
        return "empty"
    return "available"


def map_unifiedmodel_outputs_to_dcc(
    *,
    workspace_id: str,
    alert_api: str,
    alert_time: str,
    alert_symptom: str,
    entity_query_result: dict[str, Any] | None = None,
    topo_query_result: dict[str, Any] | None = None,
    trace_query_result: dict[str, Any] | None = None,
    log_query_result: dict[str, Any] | None = None,
    metric_query_result: dict[str, Any] | None = None,
    producer: str = "unifiedmodel.mapper",
) -> dict[str, Any]:
    """Build a DCC v0.1 payload from minimal UnifiedModel query outputs."""
    entity_rows = _extract_rows(entity_query_result)
    topo_rows = _extract_rows(topo_query_result)
    trace_rows = _extract_rows(trace_query_result)
    log_rows = _extract_rows(log_query_result)
    metric_rows = _extract_rows(metric_query_result)

    entities: list[dict[str, Any]] = []
    for row in entity_rows:
        entity_id = row.get("id") or row.get("__entity_id__") or row.get("entity_id")
        if not entity_id:
            continue
        entities.append(
            {
                "entity_id": str(entity_id),
                "entity_type": str(row.get("entity_type") or row.get("__entity_type__") or "unknown"),
                "entity_name": str(row.get("entity_name") or row.get("display_name") or entity_id),
                "domain": str(row.get("domain") or row.get("__domain__") or "default"),
                "attrs": {k: v for k, v in row.items() if isinstance(k, str) and not k.startswith("__")},
            }
        )

    topo_nodes: list[dict[str, Any]] = []
    topo_edges: list[dict[str, Any]] = []
    node_ids: set[str] = set()
    for row in topo_rows:
        source = row.get("source") or row.get("src") or row.get("from")
        target = row.get("target") or row.get("dst") or row.get("to")
        relation = row.get("relation") or row.get("type") or "calls"
        if source:
            sid = str(source)
            if sid not in node_ids:
                node_ids.add(sid)
                topo_nodes.append({"id": sid, "node_type": "service", "label": sid})
        if target:
            tid = str(target)
            if tid not in node_ids:
                node_ids.add(tid)
                topo_nodes.append({"id": tid, "node_type": "service", "label": tid})
        if source and target:
            topo_edges.append({"source": str(source), "target": str(target), "relation": str(relation)})

    trace_supplied = trace_query_result is not None
    log_supplied = log_query_result is not None
    metric_supplied = metric_query_result is not None

    return {
        "protocol_version": "dcc.v0.1",
        "context_id": f"dcc-{uuid4().hex}",
        "generated_at": _utc_now_iso(),
        "workspace": {"workspace_id": workspace_id},
        "alert": {
            "api": alert_api,
            "time": alert_time,
            "symptom": alert_symptom,
        },
        "objects": {
            "entities": entities,
            "relations": [],
            "topology": {
                "nodes": topo_nodes,
                "edges": topo_edges,
            },
        },
        "evidence": {
            "trace": {
                "availability": _infer_availability(trace_rows, trace_supplied),
                "items": trace_rows,
                "query_context": trace_query_result.get("query", {}) if trace_query_result else {},
            },
            "log": {
                "availability": _infer_availability(log_rows, log_supplied),
                "items": log_rows,
                "query_context": log_query_result.get("query", {}) if log_query_result else {},
            },
            "metric": {
                "availability": _infer_availability(metric_rows, metric_supplied),
                "items": metric_rows,
                "query_context": metric_query_result.get("query", {}) if metric_query_result else {},
            },
        },
        "candidates": {
            "root_cause": [],
            "impact_scope": [],
        },
        "provenance": {
            "producer": producer,
            "source": "unifiedmodel",
        },
        "meta": {
            "availability": "available",
            "warnings": [],
        },
    }


def map_dcc_to_context_seed(dcc: dict[str, Any]) -> dict[str, Any]:
    """Convert DCC payload into a minimal seed understood by current orchestrator."""
    alert = dcc.get("alert") or {}
    objects = dcc.get("objects") or {}
    topology = objects.get("topology") or {}
    evidence = dcc.get("evidence") or {}
    candidates = dcc.get("candidates") or {}

    entities = objects.get("entities") if isinstance(objects.get("entities"), list) else []
    nodes = topology.get("nodes") if isinstance(topology.get("nodes"), list) else []
    edges = topology.get("edges") if isinstance(topology.get("edges"), list) else []

    trace_bucket = evidence.get("trace") if isinstance(evidence.get("trace"), dict) else {}
    log_bucket = evidence.get("log") if isinstance(evidence.get("log"), dict) else {}
    metric_bucket = evidence.get("metric") if isinstance(evidence.get("metric"), dict) else {}

    return {
        "api": str(alert.get("api") or ""),
        "time": str(alert.get("time") or ""),
        "symptom": str(alert.get("symptom") or ""),
        "query_context": {
            "time_window": (
                dcc.get("diagnosis_input", {}).get("time_window")
                if isinstance(dcc.get("diagnosis_input"), dict)
                else {}
            ),
            "dcc_context_id": dcc.get("context_id"),
            "dcc_protocol_version": dcc.get("protocol_version"),
        },
        "entity_result": {
            "services": [
                item.get("entity_name")
                for item in entities
                if isinstance(item, dict)
                and isinstance(item.get("entity_type"), str)
                and "service" in item.get("entity_type", "").lower()
                and item.get("entity_name")
            ],
            "binding_count": len(entities),
        },
        "graph_result": {
            "nodes": [
                {
                    "id": str(n.get("id") or ""),
                    "label": str(n.get("label") or n.get("id") or ""),
                    "node_type": n.get("node_type") or n.get("type") or "Service",
                }
                for n in nodes
                if isinstance(n, dict) and n.get("id")
            ],
            "edges": [
                {
                    "source": str(e.get("source") or ""),
                    "target": str(e.get("target") or ""),
                    "label": str(e.get("label") or e.get("relation") or "calls"),
                }
                for e in edges
                if isinstance(e, dict) and e.get("source") and e.get("target")
            ],
            "interface_edges": [],
        },
        "trace_result": {
            "trace_evidence": trace_bucket.get("items", []),
            "root_candidates": candidates.get("root_cause", []),
            "service_call": "",
            "call_path": [],
        },
        "log_result": {
            "log_evidence": log_bucket.get("items", []),
            "root_candidates": candidates.get("root_cause", []),
        },
        "metric_result": {
            "metric_evidence": metric_bucket.get("items", []),
            "metric_root_candidates": candidates.get("root_cause", []),
        },
    }
