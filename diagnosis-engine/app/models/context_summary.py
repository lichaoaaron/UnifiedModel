"""
MModel Context Summary: builds a structured snapshot of the current case context
for use in LLM prompts.

Data sources (read-only, no side effects):
  - backend/data/mmodel/runtime_domain_model.yaml  via OntologyConfigAdapter
    - observability data via internal repositories
  - backend/app/skills/registry.py        for Skill metadata

Public API:
    get_mmodel_context_summary(user_query=None, case_id=None, data_dir=None) -> dict
  format_mmodel_context_for_llm(summary: dict) -> str
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe(fn, default=None):
    """Call fn(); return default on any exception."""
    try:
        return fn()
    except Exception as e:
        logger.debug("[ContextSummary] _safe fallback: %s", e)
        return default


def _extract_trace_summary(spans: list[dict]) -> dict[str, Any]:
    """Extract minimal trace info without hardcoding conclusions."""
    services: set[str] = set()
    error_services: set[str] = set()
    error_exceptions: list[str] = []
    trace_id = "unknown"
    call_pairs: list[str] = []

    # Build service → parent mapping for call pairs
    span_map: dict[str, dict] = {}
    for span in spans:
        sid = span.get("spanId") or span.get("span_id", "")
        if sid:
            span_map[sid] = span

    for span in spans:
        tid = span.get("traceId") or span.get("trace_id", "")
        if tid:
            trace_id = tid

        svc = (span.get("resource.attributes.service@name")
               or span.get("serviceName", ""))
        if svc:
            services.add(svc)

        # Detect errors
        status = span.get("status.code", 0)
        http_code = str(span.get("span.attributes.http@status_code", ""))
        if status == 2 or http_code == "500":
            if svc:
                error_services.add(svc)
            for event in span.get("events", []):
                exc = event.get("attributes", {}).get("error@kind", "")
                if exc and exc not in error_exceptions:
                    error_exceptions.append(exc)

        # Call pairs: child → parent service
        parent_id = span.get("parentSpanId") or span.get("parent_span_id", "")
        parent_span = span_map.get(parent_id)
        if parent_span:
            parent_svc = (parent_span.get("resource.attributes.service@name")
                          or parent_span.get("serviceName", ""))
            if parent_svc and svc and parent_svc != svc:
                pair = f"{parent_svc} → {svc}"
                if pair not in call_pairs:
                    call_pairs.append(pair)

    return {
        "trace_id": trace_id,
        "services_observed": sorted(services),
        "error_services": sorted(error_services),
        "error_exceptions": error_exceptions,
        "call_pairs": call_pairs,
        "span_count": len(spans),
    }


def _extract_log_summary(logs: list[dict]) -> dict[str, Any]:
    """Extract minimal log info."""
    import re
    error_services: set[str] = set()
    error_keywords: list[str] = []
    downstream_urls: list[str] = []

    for log in logs:
        svc = log.get("resource.attributes.service@name", "")
        msg = log.get("log.attributes.message", "") or log.get("body", "")
        stack = log.get("log.attributes.stack_trace", "")
        combined = (msg or "") + "\n" + (stack or "")

        if "ERROR" in log.get("severityText", "") or "FeignException" in combined or "Exception" in combined:
            if svc:
                error_services.add(svc)
            for kw in ("FeignException", "NumberFormatException", "NullPointerException", "RuntimeException"):
                if kw in combined and kw not in error_keywords:
                    error_keywords.append(kw)
            m = re.search(r'during \[GET\] to \[([^\]]+)\]', combined)
            if m and m.group(1) not in downstream_urls:
                downstream_urls.append(m.group(1))

    return {
        "error_services": sorted(error_services),
        "error_keywords": error_keywords,
        "downstream_urls": downstream_urls,
        "log_count": len(logs),
    }


def _extract_metric_summary(metrics: list[dict]) -> dict[str, Any]:
    """Extract minimal metric info."""
    services: set[str] = set()
    metric_names: list[str] = []

    for m in metrics:
        svc = m.get("resource.attributes.compose_service", "")
        name = m.get("name", "")
        if svc:
            services.add(svc)
        if name and name not in metric_names:
            metric_names.append(name)

    return {
        "services_with_metrics": sorted(services),
        "metric_names": metric_names[:8],  # cap for brevity
        "metric_count": len(metrics),
    }


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def get_mmodel_context_summary(
    user_query: str | None = None,
    case_id: str | None = None,
    data_dir: str | None = None,
) -> dict[str, Any]:
    """
    Build and return a structured MModel context snapshot.
    All data sources are read-only. Returns stable dict even on partial failures.
    Never executes any Skill. Never modifies data files.
    """
    from app.adapters.ontology_config_adapter import OntologyConfigAdapter
    from app.repositories import get_log_repository, get_metric_repository, get_trace_repository
    from app.skills.registry import get_skill_registry, list_skill_names

    # ── Ontology ────────────────────────────────────────────────────────────
    onto = _safe(OntologyConfigAdapter, OntologyConfigAdapter())
    entity_types = _safe(onto.load_entity_types, [])
    relation_types = _safe(onto.load_relation_types, [])
    entities = _safe(onto.load_entities, [])
    relations = _safe(onto.load_relations, [])
    umodel_categories = _safe(onto.list_umodel_yaml_categories, [])

    ontology_summary = {
        "entity_types": [e["name"] for e in entity_types],
        "relation_types": [r["name"] for r in relation_types],
        "entity_count": len(entities),
        "relation_count": len(relations),
        "umodel_categories": umodel_categories,
    }

    # Condense entities to lightweight list
    entity_list = [
        {"id": e.get("id"), "type": e.get("type"), "name": e.get("name")}
        for e in entities
    ]

    # Condense relations to lightweight list
    relation_list = [
        {"type": r.get("type"), "source": r.get("source"), "target": r.get("target")}
        for r in relations
    ]

    # ── Observability data ──────────────────────────────────────────────────
    trace_repository = get_trace_repository()
    log_repository = get_log_repository()
    metric_repository = get_metric_repository()
    spans = _safe(lambda: trace_repository.get_traces(data_dir=data_dir, case_id=case_id).items, [])
    logs = _safe(lambda: log_repository.get_logs(data_dir=data_dir, case_id=case_id).items, [])
    metrics = _safe(lambda: metric_repository.get_red_metrics(data_dir=data_dir, case_id=case_id).items, [])

    trace_summary = _safe(lambda: _extract_trace_summary(spans), {})
    log_summary = _safe(lambda: _extract_log_summary(logs), {})
    metric_summary = _safe(lambda: _extract_metric_summary(metrics), {})

    # ── Topology (derive from relations already loaded) ─────────────────────
    call_rels = [r for r in relations if r.get("type") == "calls"]
    topology_summary = {
        "call_relations": [
            f"{r['source']} → {r['target']}" for r in call_rels
        ],
    }

    # ── Evidence hints (lightweight, not final conclusions) ─────────────────
    evidence_hints: list[str] = []
    trace_errors = trace_summary.get("error_services", [])
    trace_exceptions = trace_summary.get("error_exceptions", [])
    log_errors = log_summary.get("error_keywords", [])
    log_urls = log_summary.get("downstream_urls", [])

    if trace_errors:
        evidence_hints.append(f"Trace 中发现异常服务：{', '.join(trace_errors)}")
    if trace_exceptions:
        evidence_hints.append(f"Trace 中发现异常类型：{', '.join(trace_exceptions)}")
    if log_errors:
        evidence_hints.append(f"Log 中发现异常关键字：{', '.join(log_errors)}")
    if log_urls:
        evidence_hints.append(f"Log 中发现 Feign 下游 URL：{', '.join(log_urls)}")
    if metric_summary.get("services_with_metrics"):
        evidence_hints.append(
            f"Metric 数据涵盖服务：{', '.join(metric_summary['services_with_metrics'])}"
        )

    # ── Recommended analysis path (from registry) ───────────────────────────
    recommended_path = list_skill_names()  # canonical pipeline order

    # ── Skill registry summary ──────────────────────────────────────────────
    registry = get_skill_registry()
    skill_registry_summary = {
        name: {
            "display_name": info["display_name"],
            "tool_key": info["tool_key"],
            "description": info["description"],
            "dependencies": info["dependencies"],
        }
        for name, info in registry.items()
    }

    return {
        "alert_context": {
            "user_query": user_query or "（未指定）",
        },
        "ontology_summary": ontology_summary,
        "entities": entity_list,
        "relations": relation_list,
        "observability_data": {
            "trace_summary": trace_summary,
            "log_summary": log_summary,
            "metric_summary": metric_summary,
        },
        "topology_summary": topology_summary,
        "evidence_summary": evidence_hints,
        "recommended_analysis_path": recommended_path,
        "skill_registry_summary": skill_registry_summary,
    }


def format_mmodel_context_for_llm(summary: dict[str, Any]) -> str:
    """
    Convert a context summary dict into a compact LLM-readable text (≤1000 tokens).
    Designed for inclusion in planning prompts.
    Does not hardcode final root cause conclusions.
    """
    lines: list[str] = ["## MModel 当前案例上下文\n"]

    # Alert context
    query = summary.get("alert_context", {}).get("user_query", "（未指定）")
    lines.append(f"**用户问题**：{query}\n")

    # Ontology
    onto = summary.get("ontology_summary", {})
    lines.append(
        f"**本体定义**：实体类型 {onto.get('entity_types', [])}，"
        f"关系类型 {onto.get('relation_types', [])}，"
        f"实体实例 {onto.get('entity_count', 0)} 个，"
        f"UModel 数据目录 {onto.get('umodel_categories', [])}。\n"
    )

    # Entities (compact)
    entities = summary.get("entities", [])
    if entities:
        ent_str = "；".join(
            f"{e['type']}:{e['name']}" for e in entities if e.get("type") and e.get("name")
        )
        lines.append(f"**已知实体**：{ent_str}\n")

    # Relations (compact)
    relations = summary.get("relations", [])
    if relations:
        rel_str = "；".join(
            f"{r['source']} -{r['type']}→ {r['target']}"
            for r in relations
            if r.get("source") and r.get("target")
        )
        lines.append(f"**已知关系**：{rel_str}\n")

    # Observability
    obs = summary.get("observability_data", {})
    tr = obs.get("trace_summary", {})
    lg = obs.get("log_summary", {})
    mt = obs.get("metric_summary", {})

    trace_parts = []
    if tr.get("trace_id") and tr["trace_id"] != "unknown":
        trace_parts.append(f"traceId={tr['trace_id']}")
    if tr.get("services_observed"):
        trace_parts.append(f"涉及服务={tr['services_observed']}")
    if tr.get("call_pairs"):
        trace_parts.append(f"调用链={tr['call_pairs']}")
    if tr.get("error_services"):
        trace_parts.append(f"异常服务={tr['error_services']}")
    if tr.get("error_exceptions"):
        trace_parts.append(f"异常类型={tr['error_exceptions']}")
    if trace_parts:
        lines.append(f"**Trace**：{' | '.join(trace_parts)}\n")

    log_parts = []
    if lg.get("error_services"):
        log_parts.append(f"异常服务={lg['error_services']}")
    if lg.get("error_keywords"):
        log_parts.append(f"关键字={lg['error_keywords']}")
    if lg.get("downstream_urls"):
        log_parts.append(f"下游URL={lg['downstream_urls']}")
    if log_parts:
        lines.append(f"**Log**：{' | '.join(log_parts)}\n")

    if mt.get("services_with_metrics"):
        lines.append(
            f"**Metric**：已采集服务 {mt['services_with_metrics']}，"
            f"指标项 {mt.get('metric_names', [][:4])}\n"
        )

    # Evidence hints
    evidence = summary.get("evidence_summary", [])
    if evidence:
        lines.append("**初步证据线索**：")
        for h in evidence:
            lines.append(f"  - {h}")
        lines.append("")

    # Topology
    topo = summary.get("topology_summary", {})
    calls = topo.get("call_relations", [])
    if calls:
        lines.append(f"**调用拓扑**：{' | '.join(calls)}\n")

    # Recommended path
    path = summary.get("recommended_analysis_path", [])
    if path:
        lines.append(f"**建议分析路径**（Skill 执行顺序）：{' → '.join(path)}\n")

    # Skill registry (compact: name + one-line description)
    reg = summary.get("skill_registry_summary", {})
    if reg:
        lines.append("**可用 Skill**：")
        for name, info in reg.items():
            lines.append(
                f"  - {info['tool_key']}（{info['display_name']}）：{info['description'][:40]}…"
            )
        lines.append("")

    return "\n".join(lines)
