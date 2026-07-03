"""
GraphAnalysisSkill: builds the current diagnosis runtime subgraph from repository evidence.
"""
import logging
import time as _time
from datetime import datetime, timezone
from urllib.parse import urlparse
from app.skills.base_skill import BaseSkill
from app.models.context import DiagnosisContext
from app.models.diagnosis import SkillResult
from app.adapters.ontology_config_adapter import OntologyConfigAdapter
from app.repositories import MetricRepository, ServiceMapRepository, get_metric_repository, get_service_map_repository
from app.skills.evidence_classifier import normalize_api

logger = logging.getLogger(__name__)


def _interface_path(span: dict) -> str:
    for key in ("span.attributes.url", "resource.attributes.http@url"):
        raw_url = span.get(key, "")
        if raw_url:
            path = urlparse(raw_url).path
            if path and path != "/":
                return path
    normalized = normalize_api(span.get("name", ""))
    if not normalized:
        return ""
    # Keep only meaningful interface identifiers:
    # 1) HTTP path style (/api/xxx)
    # 2) RPC service/method style (Service/Method)
    if normalized.startswith("/"):
        return normalized
    if "/" in normalized and " " not in normalized:
        return normalized
    return ""


def _dependency_type(service_name: str) -> str:
    lowered = (service_name or "").lower()
    if lowered.startswith(("redis-", "mysql-")) or lowered in {"node-network", "network"}:
        return "Dependency"
    return "Service"


class GraphAnalysisSkill(BaseSkill):
    skill_name = "GraphAnalysisSkill"
    tool_name = "MModelSkill/query_graph"
    title = "关系图查询"

    def __init__(
        self,
        service_map_repository: ServiceMapRepository | None = None,
        metric_repository: MetricRepository | None = None,
    ):
        self.service_map_repository = service_map_repository or get_service_map_repository()
        self.metric_repository = metric_repository or get_metric_repository()

    def run(self, ctx: DiagnosisContext) -> SkillResult:
        t0 = _time.monotonic()
        started_at = datetime.now(timezone.utc).isoformat()
        execution_log = []

        # --- Step 1: Load MModel ontology types only ---
        execution_log.append("初始化 OntologyConfigAdapter，读取 backend/data/mmodel/runtime_domain_model.yaml")
        onto = OntologyConfigAdapter()
        entity_types = onto.load_entity_types()
        relation_types = onto.load_relation_types()
        entities = onto.load_entities()
        relations = onto.load_relations()

        mmodel_entity_type_count = len(entity_types)
        mmodel_relation_type_count = len(relation_types)
        mmodel_entity_count = len(entities)
        mmodel_relation_count = len(relations)

        logger.info(
            "[Graph] source=domain_model use_umodel_reference=false "
            "mmodel_entity_types_count=%d mmodel_relation_types_count=%d "
            "umodel_entity_sets_skipped=true",
            mmodel_entity_type_count, mmodel_relation_type_count,
        )
        execution_log.append(
            f"MModel 本体：{mmodel_entity_type_count} 个实体类型，"
            f"{mmodel_relation_type_count} 个关系类型，"
            f"{mmodel_entity_count} 个实体实例，{mmodel_relation_count} 条关系实例"
        )

        # --- Step 2: Build runtime subgraph from current trace/log/metric evidence ---
        execution_log.append("基于本次 trace/log/metric 构建运行态子图")
        trace = ctx.trace_result
        service_map_query = dict(ctx.query_context or {})
        service_map_trace_id = trace.get("service_map_trace_id") or trace.get("entry_trace_id") or service_map_query.get("trace_id")
        if service_map_trace_id:
            service_map_query["trace_id"] = service_map_trace_id
            service_map_query["alert_api"] = None
            service_map_query["api"] = None
        service_map_fetch = self.service_map_repository.get_service_map(query=service_map_query, data_dir=ctx.data_dir, case_id=ctx.case_id)
        service_map_item = service_map_fetch.items[0] if service_map_fetch.items else {}
        spans = [span.get("_source", span) for span in service_map_item.get("spans", [])]
        call_edges = service_map_item.get("call_edges", service_map_item.get("edges", []))
        if service_map_trace_id:
            execution_log.append(f"Service Map 使用 traceId: {service_map_trace_id}")

        span_by_id = {span.get("spanId", ""): span for span in spans if span.get("spanId")}
        children_by_parent: dict[str, list[str]] = {}
        for span_id, span in span_by_id.items():
            parent_id = span.get("parentSpanId", "")
            if parent_id:
                children_by_parent.setdefault(parent_id, []).append(span_id)

        entry_span = next(
            (
                span for span in spans
                if span.get("kind") == "SPAN_KIND_SERVER" and normalize_api(span.get("name", "")) == ctx.api
            ),
            None,
        )
        if entry_span is None:
            entry_span = next((span for span in spans if normalize_api(span.get("name", "")) == ctx.api), None)
        if entry_span is None and spans:
            entry_span = spans[0]

        active_span_ids: set[str] = set()
        active_span_order: list[str] = []
        if entry_span and entry_span.get("spanId"):
            queue = [entry_span["spanId"]]
            while queue:
                span_id = queue.pop(0)
                if span_id in active_span_ids:
                    continue
                active_span_ids.add(span_id)
                active_span_order.append(span_id)
                queue.extend(children_by_parent.get(span_id, []))
        active_spans = [span_by_id[span_id] for span_id in active_span_order] if active_span_order else spans

        services = list(dict.fromkeys(
            (span.get("serviceName") or span.get("resource.attributes.service@name", ""))
            for span in active_spans
            if span.get("serviceName") or span.get("resource.attributes.service@name")
        ))
        first_error_svc = trace.get("first_error_service", "") or ""
        entry_svc = (entry_span or {}).get("serviceName") or (entry_span or {}).get("resource.attributes.service@name", "")

        nodes_by_id: dict[str, dict] = {}
        edges_by_key: dict[tuple[str, str, str], dict] = {}

        def add_node(node_id: str, label: str | None = None, node_type: str = "Service") -> None:
            if not node_id:
                return
            nodes_by_id.setdefault(node_id, {
                "id": node_id,
                "label": label or node_id,
                "node_type": node_type,
                "is_root_cause": node_id == first_error_svc,
                "is_entry": node_id == entry_svc,
            })

        def add_edge(source: str, target: str, label: str) -> None:
            if source and target and source != target:
                edges_by_key.setdefault((source, target, label), {"source": source, "target": target, "label": label})

        for svc in services:
            add_node(svc, node_type=_dependency_type(svc))
        service_by_span = {
            span.get("spanId", ""): span.get("serviceName") or span.get("resource.attributes.service@name", "")
            for span in active_spans
            if span.get("spanId")
        }
        for span in active_spans:
            span_service = span.get("serviceName") or span.get("resource.attributes.service@name", "")
            parent_service = service_by_span.get(span.get("parentSpanId", ""), "")
            if parent_service and span_service:
                add_edge(parent_service, span_service, "calls")
                if _dependency_type(span_service) == "Dependency":
                    add_edge(parent_service, span_service, "depends_on")

            api = _interface_path(span)
            if span_service and api:
                add_node(api, node_type="Interface")
                add_edge(span_service, api, "exposes")

            inst_raw = span.get("resource.attributes.service@instance@id", "")
            if span_service and inst_raw:
                instance_id = inst_raw.split("@", 1)[1] if "@" in inst_raw else inst_raw
                add_node(instance_id, node_type="Instance")
                add_edge(span_service, instance_id, "runs_on")

        for edge in call_edges:
            source = edge.get("source_service") or edge.get("source", "")
            target = edge.get("target_service") or edge.get("target", "")
            if source:
                add_node(source, node_type=_dependency_type(source))
            if target:
                add_node(target, node_type=_dependency_type(target))
            add_edge(source, target, "calls")

        red_metric_items = self.metric_repository.get_red_metrics(time_range=(ctx.query_context or {}).get("time_window"), data_dir=ctx.data_dir, case_id=ctx.case_id).items
        for metric in [series for item in red_metric_items for series in item.get("metric_series", [])]:
            metric_service = metric.get("resource.attributes.compose_service") or metric.get("serviceName") or metric.get("resource.attributes.container@name", "")
            if metric_service and metric_service not in services:
                continue
            container = metric.get("resource.attributes.container@id") or metric.get("resource.attributes.container@name", "")
            if metric_service and container:
                add_node(container, node_type="Instance")
                add_edge(metric_service, container, "runs_on")

        for candidate in (ctx.root_cause_result or {}).get("candidates", []):
            svc = candidate.get("service", "")
            api = candidate.get("api", "")
            if svc:
                add_node(svc, node_type=_dependency_type(svc))
            if svc and api:
                add_node(api, node_type="Interface")
                add_edge(svc, api, "exposes")

        rc = ctx.root_cause_result or {}
        rc_service = rc.get("root_cause_service", "")
        rc_api = rc.get("root_cause_api", "")
        if rc_service:
            add_node(rc_service, node_type=_dependency_type(rc_service))
        if rc_api:
            add_node(rc_api, node_type="Interface")
        if rc_service and rc_api:
            add_edge(rc_service, rc_api, "exposes")

        interface_nodes = [n["id"] for n in nodes_by_id.values() if n.get("node_type") == "Interface"]
        interface_edges = []
        for i in range(len(interface_nodes) - 1):
            interface_edges.append({
                "source": interface_nodes[i],
                "target": interface_nodes[i + 1],
                "label": "downstream call",
            })
        trace_entry_api = ctx.api
        trace_first_api = trace.get("first_error_api")
        if trace_first_api and trace_entry_api and trace_first_api != trace_entry_api:
            candidate = {"source": trace_entry_api, "target": trace_first_api, "label": "downstream call"}
            if candidate not in interface_edges:
                interface_edges.append(candidate)

        # impact_propagation_path: from root cause service outward to callers/entry
        # Direction: root_cause_service → ... → entry_service → entry_api
        # This represents "who is impacted by the root cause", NOT a reverse inference.
        impact_path = []

        upstream_by_service: dict[str, list[str]] = {}
        downstream_by_service: dict[str, list[str]] = {}
        for edge in call_edges:
            source = edge.get("source_service") or edge.get("source", "")
            target = edge.get("target_service") or edge.get("target", "")
            if source and target:
                downstream_by_service.setdefault(source, [])
                if target not in downstream_by_service[source]:
                    downstream_by_service[source].append(target)
                upstream_by_service.setdefault(target, [])
                if source not in upstream_by_service[target]:
                    upstream_by_service[target].append(source)

        impacted_services = []
        if first_error_svc:
            queue = [first_error_svc]
            seen = {first_error_svc}
            while queue:
                current = queue.pop(0)
                for upstream in upstream_by_service.get(current, []):
                    if upstream not in seen:
                        seen.add(upstream)
                        impacted_services.append(upstream)
                        queue.append(upstream)
            impact_path = [first_error_svc] + impacted_services
            if ctx.api:
                impact_path.append(ctx.api)
        execution_log.append(f"影响传播路径（从根因出发）：{' → '.join(impact_path)}")
        service_map_evidence = {
            "call_edges": call_edges,
            "upstream_services": upstream_by_service,
            "downstream_services": downstream_by_service,
            "impacted_services": impacted_services,
            "root_to_entry_path": impact_path,
        }

        nodes = list(nodes_by_id.values())

        # ── Fix entry service: ensure the is_entry node actually exposes ctx.api ──
        _entry_api = ctx.api
        _entry_exposing_services = {
            e.get("source") for e in edges_by_key.values()
            if e.get("label") == "exposes" and e.get("target") == _entry_api
        }
        if _entry_exposing_services:
            _current_entry = next((n["id"] for n in nodes if n.get("is_entry")), None)
            if _current_entry not in _entry_exposing_services:
                # The current entry service doesn't expose the entry API.
                # Pick the first service in the call chain that does.
                _new_entry = next(
                    (svc for svc in services if svc in _entry_exposing_services),
                    next(iter(_entry_exposing_services)),
                )
                for n in nodes:
                    n["is_entry"] = (n.get("id") == _new_entry)
                entry_svc = _new_entry
        edges = list(edges_by_key.values())
        svc_summary = " → ".join(f"{e['source']} calls {e['target']}" for e in edges if e.get('label') == 'calls') or "（无服务调用边）"
        ctx.graph_result = {
            "nodes": nodes,
            "edges": edges,
            "call_edges": call_edges,
            "interface_edges": interface_edges,
            "impact_propagation_path": impact_path,
            "service_map_evidence": service_map_evidence,
            "upstream_services": upstream_by_service,
            "downstream_services": downstream_by_service,
            "impacted_services": impacted_services,
            "mmodel_entity_types": mmodel_entity_type_count,
            "mmodel_relation_types": mmodel_relation_type_count,
            "graph_source": "runtime_observability",
            "graph_engine": "runtime_subgraph",
            "summary": f"{svc_summary}；影响传播路径（根因→入口）：{' → '.join(impact_path)}",
        }

        duration_ms = max(1, int((_time.monotonic() - t0) * 1000))
        finished_at = datetime.now(timezone.utc).isoformat()

        evidence = [
            f"MModel 本体来源：backend/data/mmodel/runtime_domain_model.yaml",
            f"MModel 实体类型：{mmodel_entity_type_count} 个，关系类型：{mmodel_relation_type_count} 个",
            f"运行态子图节点：{len(nodes)} 个，边：{len(edges)} 条（来自本次 trace/log/metric 结构化结果）",
            f"服务调用关系：{svc_summary}（来自本次 trace）",
            f"入口接口：{ctx.api}，首次出错接口：{trace_first_api or '（未知）'}",
            f"影响传播路径（根因服务 → 入口接口）：{' → '.join(impact_path)}",
        ]
        if call_edges:
            evidence.append(
                "Service Map 边统计："
                + "; ".join(
                    f"{edge.get('source_service') or edge.get('source')}→{edge.get('target_service') or edge.get('target')} "
                    f"calls={edge.get('call_count')}, errors={edge.get('error_count')}, p95={edge.get('p95_duration_ms')}ms"
                    for edge in call_edges[:6]
                )
            )

        return SkillResult(
            skill_name=self.skill_name,
            tool_name=self.tool_name,
            title=self.title,
            status="success",
            summary=(
                "已加载 MModel 本体，基于本次观测数据构建运行态子图。"
            ),
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            input={
                "graph_source": "backend/data/mmodel/runtime_domain_model.yaml",
                "use_umodel_reference": False,
                "runtime_sources": ["trace", "log", "metric", "entity_binding", "root_cause"],
            },
            output=ctx.graph_result,
            evidence=evidence,
            execution_log=execution_log,
            explanation=(
                "基于本次请求读取到的 trace/log/metric 和实体绑定结果构建运行态子图，"
                "不默认展示非本次链路的全局本体节点。"
            ),
        )
