"""
ImpactAnalysisSkill: derives impact scope from root cause.

Evidence layers:
  1. Interface-level impact  — from trace / call graph (confidence=high)
  2. Business semantic impact — from demo_business_ontology.yaml (confidence=medium)
  3. Impact scale            — requires real business metrics (UV/PV/QPS/etc.);
                               outputs impact_scale=unavailable when metrics absent
"""
import time as _time
from datetime import datetime, timezone
from app.skills.base_skill import BaseSkill
from app.models.context import DiagnosisContext
from app.models.diagnosis import SkillResult
from app.adapters.ontology_config_adapter import OntologyConfigAdapter
from app.repositories import BusinessImpactRepository, get_business_impact_repository
from app.runtime.impact_input_resolver import resolve_impact_input as _resolve_impact_input


class ImpactAnalysisSkill(BaseSkill):
    skill_name = "ImpactAnalysisSkill"
    tool_name = "MModelSkill/analyze_impact"
    title = "影响面分析"

    def __init__(self, business_impact_repository: BusinessImpactRepository | None = None):
        self.business_impact_repository = business_impact_repository or get_business_impact_repository()

    def run(self, ctx: DiagnosisContext) -> SkillResult:
        t0 = _time.monotonic()
        started_at = datetime.now(timezone.utc).isoformat()
        execution_log = []

        rc = ctx.root_cause_result
        graph = ctx.graph_result
        root_cause_service = rc.get("root_cause_service") or ""
        edges = graph.get("edges", [])

        # ── DCC-first: resolve object-level impact candidate context ──────────────
        resolution = _resolve_impact_input(ctx)
        for w in resolution.warnings:
            execution_log.append(w)
        if resolution.dcc_used:
            execution_log.append(
                f"[DCC-object-centered] impact candidate_source={resolution.candidate_source}, "
                f"topology_nodes={len(resolution.topology_context.get('nodes', []))}, "
                f"entities={len(resolution.entity_context)}"
            )

        # ------------------------------------------------------------------
        # Layer 1: Interface-level impact (from trace / call graph)
        # ------------------------------------------------------------------
        execution_log.append(f"[接口级] 从根因服务 {root_cause_service} 沿 trace 调用链反向推导上游影响")

        runtime_call_edges = graph.get("call_edges") or [edge for edge in edges if edge.get("label") == "calls"]
        call_services = []
        for edge in runtime_call_edges:
            for svc in (
                edge.get("source_service") or edge.get("source", ""),
                edge.get("target_service") or edge.get("target", ""),
            ):
                if svc and svc not in call_services:
                    call_services.append(svc)
        if not call_services:
            call_path = ctx.trace_result.get("call_path", []) if ctx.trace_result else []
            call_services = list(dict.fromkeys(p.split(":")[0].strip() for p in call_path if p))
        _dcc_authoritative = resolution.candidate_source in {
            "dcc_impact_candidates", "topology_propagation"
        }
        if _dcc_authoritative and resolution.impact_candidates:
            # DCC/topology provides object-level authoritative candidate set.
            # Exclude merely_observed_node — they have no confirmed impact path.
            affected_services = list(dict.fromkeys(
                c["service"]
                for c in resolution.impact_candidates
                if c.get("node_type") != "merely_observed_node" and c.get("service")
            ))
            execution_log.append(
                f"[DCC-object-centered] 使用 DCC 影响面候选 {len(resolution.impact_candidates)} 个 "
                f"(source={resolution.candidate_source}), "
                f"过滤 merely_observed 后受影响服务: {affected_services}"
            )
        else:
            # Evidence-based path: derive affected_services from call graph / trace
            affected_services = []
            if root_cause_service and root_cause_service in call_services:
                root_index = call_services.index(root_cause_service)
                # For platform-level failures (middleware/infrastructure), the entire
                # call chain is affected (both upstream callers and downstream callees).
                # For service-level failures, only upstream callers are impacted.
                _rc_type = (rc.get("root_cause_type") or "")
                if _rc_type in ("platform.redis", "platform.database"):
                    affected_services = list(call_services)
                else:
                    affected_services = call_services[:root_index + 1]
            elif call_services:
                affected_services = call_services
            elif root_cause_service:
                affected_services = [root_cause_service]
            _src_label = (
                "evidence_based+dcc_context"
                if resolution.dcc_used
                else "legacy_call_chain"
            )
            execution_log.append(
                f"[{_src_label}] 从调用链构造受影响服务 {len(affected_services)} 个"
            )

        affected_interface = ctx.api or ""
        affected_apis = list(dict.fromkeys([api for api in [affected_interface, rc.get("root_cause_api") or ""] if api]))
        affected_path = " → ".join(reversed(affected_services)) if affected_services else root_cause_service
        execution_log.append(f"[接口级] 受影响服务：{', '.join(affected_services)}；受影响接口：{affected_interface}（来自 trace，confidence=high）")

        # ── Build node classifications from impact resolution ────────────────────
        _NODE_TYPE_TO_KEY = {
            "root_cause_node": "root_cause_nodes",
            "propagation_node": "propagation_nodes",
            "directly_affected_node": "directly_affected_nodes",
            "indirectly_affected_node": "indirectly_affected_nodes",
            "merely_observed_node": "merely_observed_nodes",
        }
        node_classifications: dict[str, list] = {v: [] for v in _NODE_TYPE_TO_KEY.values()}
        for _c in resolution.impact_candidates:
            _ntype = _c.get("node_type", "directly_affected_node")
            _key = _NODE_TYPE_TO_KEY.get(_ntype, "directly_affected_nodes")
            node_classifications[_key].append({
                "service": _c.get("service"),
                "confidence": _c.get("confidence"),
                "source": _c.get("source"),
                "reason": _c.get("reason"),
            })
        if resolution.impact_candidates:
            execution_log.append(
                f"[对象化分类] root_cause={len(node_classifications['root_cause_nodes'])}, "
                f"directly_affected={len(node_classifications['directly_affected_nodes'])}, "
                f"indirectly_affected={len(node_classifications['indirectly_affected_nodes'])}, "
                f"merely_observed={len(node_classifications['merely_observed_nodes'])}"
            )

        business_impact_fetch = self.business_impact_repository.get_business_impact_for_services(
            affected_services or ([root_cause_service] if root_cause_service else []),
            (ctx.query_context or {}).get("time_window"),
            query=ctx.query_context,
            data_dir=ctx.data_dir,
            case_id=ctx.case_id,
        )
        business_impact_summary = dict(business_impact_fetch.items[0]) if business_impact_fetch.items else {}
        service_map_edge_links = [
            {
                "source": edge.get("source_service") or edge.get("source"),
                "target": edge.get("target_service") or edge.get("target"),
                "call_count": edge.get("call_count"),
                "error_count": edge.get("error_count"),
                "error_rate": edge.get("error_rate"),
            }
            for edge in runtime_call_edges
            if isinstance(edge, dict)
        ]
        evidence_links = dict(business_impact_summary.get("evidence_links") or {})
        evidence_links["service_map_edges"] = service_map_edge_links
        evidence_links["root_cause_service"] = root_cause_service
        business_impact_summary["evidence_links"] = evidence_links
        business_impact_summary["related_service_map_edges"] = service_map_edge_links
        business_impact_summary["root_cause_service"] = root_cause_service

        # ------------------------------------------------------------------
        # Layer 2: Business semantic impact (from demo_business_ontology.yaml)
        # ------------------------------------------------------------------
        execution_log.append("[业务语义] 加载演示业务本体 demo_business_ontology.yaml")
        onto = OntologyConfigAdapter()
        biz_onto = onto.load_demo_business_ontology()
        biz_relations = biz_onto.get("business_relations", [])

        # Build lookup index: source_interface → related targets
        cap_index: dict[str, list[dict]] = {}    # interface → [capability_id, ...]
        proc_index: dict[str, list[dict]] = {}   # capability_id → [process_id, ...]
        page_index: dict[str, list[dict]] = {}   # interface → [page_id, ...]
        ug_index: dict[str, list[dict]] = {}     # capability_id → [user_group_id, ...]

        for rel in biz_relations:
            rtype = rel.get("type", "")
            src = rel.get("source", "")
            tgt = rel.get("target", "")
            conf = rel.get("confidence", "medium")
            evid = rel.get("evidence_source", "demo_business_ontology")
            entry = {"id": tgt, "confidence": conf, "evidence_source": evid}
            if rtype == "supports_capability":
                cap_index.setdefault(src, []).append(entry)
            elif rtype == "belongs_to_process":
                proc_index.setdefault(src, []).append(entry)
            elif rtype == "depends_on_interface":
                page_index.setdefault(src, []).append(entry)
            elif rtype == "affects_user_group":
                ug_index.setdefault(src, []).append(entry)

        # Build page_by_interface: interface → [page_id] (reverse of FrontendPage→Interface)
        page_by_interface: dict[str, list[dict]] = {}
        for rel in biz_relations:
            if rel.get("type") == "depends_on_interface":
                iface = rel.get("target", "")
                page_id = rel.get("source", "")
                conf = rel.get("confidence", "medium")
                evid = rel.get("evidence_source", "demo_business_ontology")
                page_by_interface.setdefault(iface, []).append({"id": page_id, "confidence": conf, "evidence_source": evid})

        # Collect all affected interfaces (entry + root cause api)
        affected_interfaces_set = set()
        if affected_interface:
            affected_interfaces_set.add(affected_interface)
        root_api = rc.get("root_cause_api") or ""
        if root_api:
            affected_interfaces_set.add(root_api)

        # Resolve capabilities from affected interfaces
        affected_capabilities: list[dict] = []
        seen_caps: set[str] = set()
        for iface in affected_interfaces_set:
            for cap_entry in cap_index.get(iface, []):
                if cap_entry["id"] not in seen_caps:
                    seen_caps.add(cap_entry["id"])
                    # Resolve human-readable name from biz_onto
                    cap_name = cap_entry["id"]
                    for bc in biz_onto.get("business_capabilities", []):
                        if bc["id"] == cap_entry["id"]:
                            cap_name = bc.get("name", cap_entry["id"])
                            break
                    affected_capabilities.append({
                        "id": cap_entry["id"],
                        "name": cap_name,
                        "confidence": cap_entry["confidence"],
                        "evidence_source": cap_entry["evidence_source"],
                    })

        if affected_capabilities:
            execution_log.append(f"[业务语义] 匹配到业务能力：{[c['name'] for c in affected_capabilities]}（来自演示业务本体，confidence=medium）")
        else:
            execution_log.append("[业务语义] 当前业务本体未覆盖该接口的业务语义关系，仅输出接口级影响")

        # Resolve processes from capabilities
        affected_processes: list[dict] = []
        seen_procs: set[str] = set()
        for cap in affected_capabilities:
            for proc_entry in proc_index.get(cap["id"], []):
                if proc_entry["id"] not in seen_procs:
                    seen_procs.add(proc_entry["id"])
                    proc_name = proc_entry["id"]
                    for bp in biz_onto.get("business_processes", []):
                        if bp["id"] == proc_entry["id"]:
                            proc_name = bp.get("name", proc_entry["id"])
                            break
                    affected_processes.append({
                        "id": proc_entry["id"],
                        "name": proc_name,
                        "confidence": proc_entry["confidence"],
                        "evidence_source": proc_entry["evidence_source"],
                    })

        # Resolve pages from affected interfaces
        affected_pages: list[dict] = []
        seen_pages: set[str] = set()
        for iface in affected_interfaces_set:
            for page_entry in page_by_interface.get(iface, []):
                if page_entry["id"] not in seen_pages:
                    seen_pages.add(page_entry["id"])
                    page_name = page_entry["id"]
                    for fp in biz_onto.get("frontend_pages", []):
                        if fp["id"] == page_entry["id"]:
                            page_name = fp.get("name", page_entry["id"])
                            break
                    affected_pages.append({
                        "id": page_entry["id"],
                        "name": page_name,
                        "confidence": page_entry["confidence"],
                        "evidence_source": page_entry["evidence_source"],
                    })

        # Resolve user groups from capabilities
        affected_user_groups: list[dict] = []
        seen_ugs: set[str] = set()
        for cap in affected_capabilities:
            for ug_entry in ug_index.get(cap["id"], []):
                if ug_entry["id"] not in seen_ugs:
                    seen_ugs.add(ug_entry["id"])
                    ug_name = ug_entry["id"]
                    for ug in biz_onto.get("user_groups", []):
                        if ug["id"] == ug_entry["id"]:
                            ug_name = ug.get("name", ug_entry["id"])
                            break
                    affected_user_groups.append({
                        "id": ug_entry["id"],
                        "name": ug_name,
                        "confidence": ug_entry["confidence"],
                        "evidence_source": ug_entry["evidence_source"],
                    })

        # ------------------------------------------------------------------
        # Layer 3: Impact scale — requires real business metrics
        # ------------------------------------------------------------------
        # impact_scale is unavailable until real UV/PV/QPS/etc. are connected
        impact_scale = "unavailable"
        execution_log.append("[影响规模] 当前测试数据未接入真实业务指标（UV/PV/QPS），impact_scale=unavailable")
        execution_log.append(
            "[业务影响Repository] 从可观测数据推导业务影响："
            f"orders={business_impact_summary.get('affected_order_count', 'unknown')}, "
            f"failed_transactions={business_impact_summary.get('failed_transaction_count', 'unknown')}, "
            f"estimated_revenue_impact={business_impact_summary.get('estimated_revenue_impact', 'unknown')}, "
            f"confidence={business_impact_summary.get('confidence', 'none')}"
        )

        # ------------------------------------------------------------------
        # Build backward-compat affected_business list for report_skill
        # ------------------------------------------------------------------
        affected_business_compat = (
            [f"{c['name']}受影响（演示业务本体推断）" for c in affected_capabilities]
            + [f"{p['name']}受影响（演示业务本体推断）" for p in affected_processes]
        )
        if not affected_business_compat:
            affected_business_compat = []

        ctx.impact_result = {
            # Layer 1
            "root_cause_service": root_cause_service,
            "affected_services": affected_services,
            "affected_apis": affected_apis,
            "affected_interface": affected_interface,
            "affected_path": affected_path,
            "impact_path": [{"source": root_cause_service, "target": s, "type": "impacts"} for s in affected_services if s != root_cause_service],
            # Layer 2
            "affected_capabilities": affected_capabilities,
            "affected_processes": affected_processes,
            "affected_pages": affected_pages,
            "affected_user_groups": affected_user_groups,
            "business_impact": business_impact_summary,
            # Layer 3
            "impact_scale": impact_scale,
            # Summary fields
            "impact_level": "high",
            "confidence": {
                "interface": "high",
                "business_semantic": "medium" if affected_capabilities else "none",
                "impact_scale": "unavailable",
            },
            # Backward compat
            "affected_businesses": [c["id"] for c in affected_capabilities],
            "affected_flows": [p["id"] for p in affected_processes],
            "affected_business": affected_business_compat,
            # Object-centered impact fields
            "node_classifications": node_classifications,
            "impact_nodes_by_type": {
                k: [e["service"] for e in v if e.get("service")]
                for k, v in node_classifications.items()
            },
            "candidate_source": resolution.candidate_source,
            "dcc_candidates_used": resolution.dcc_used,
            "object_centered_mode": _dcc_authoritative and bool(resolution.impact_candidates),
        }

        duration_ms = max(1, int((_time.monotonic() - t0) * 1000))
        finished_at = datetime.now(timezone.utc).isoformat()

        evidence = [
            f"影响面候选来源：{resolution.candidate_source}",
            f"DCC 对象化候选数：{len(resolution.impact_candidates)} 个" if resolution.dcc_used else "无 DCC 影响候选 (证据扩散模式)",
            f"[接口级, confidence=high] 影响路径：{affected_path}（来自 trace 调用链分析）",
            f"[接口级, confidence=high] 受影响接口：{affected_interface}（来自告警输入或 trace）",
        ]
        if affected_capabilities:
            evidence.append(
                f"[业务语义, confidence=medium] 业务能力影响：{[c['name'] for c in affected_capabilities]}（来自演示业务本体 demo_business_ontology.yaml）"
            )
        if affected_processes:
            evidence.append(
                f"[业务语义, confidence=medium] 业务流程影响：{[p['name'] for p in affected_processes]}（来自演示业务本体）"
            )
        if affected_pages:
            evidence.append(
                f"[业务语义, confidence=medium] 前端页面影响：{[p['name'] for p in affected_pages]}（来自演示业务本体）"
            )
        if affected_user_groups:
            evidence.append(
                f"[业务语义, confidence=medium] 用户群影响：{[u['name'] for u in affected_user_groups]}（来自演示业务本体）"
            )
        if not affected_capabilities:
            evidence.append("[业务语义] 当前业务本体未覆盖该接口的业务语义关系，仅输出接口级影响")
        evidence.append(
            "[影响规模, unavailable] 当前测试数据未接入真实 UV、PV、QPS、访问量、失败率或工单量等业务指标，暂不估算具体影响用户数和高峰占比"
        )
        if business_impact_summary:
            evidence.append(
                "[业务影响Repository] 可观测数据推导："
                f"affected_order_count={business_impact_summary.get('affected_order_count', 'unknown')}, "
                f"failed_transaction_count={business_impact_summary.get('failed_transaction_count', 'unknown')}, "
                f"affected_user_count={business_impact_summary.get('affected_user_count', 'unknown')}, "
                f"estimated_revenue_impact={business_impact_summary.get('estimated_revenue_impact', 'unknown')}, "
                f"confidence={business_impact_summary.get('confidence', 'none')}"
            )

        biz_summary = (
            "；".join(f"{c['name']}" for c in affected_capabilities)
            or "暂无业务影响数据"
        )
        return SkillResult(
            skill_name=self.skill_name,
            tool_name=self.tool_name,
            title=self.title,
            status="success",
            summary=(
                f"受影响服务：{', '.join(affected_services) or '（无）'}；"
                f"受影响接口：{affected_interface}；"
                f"业务影响：{biz_summary}。"
            ),
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            input={
                "root_cause_service": root_cause_service,
                "call_graph_edges": len(edges),
                "candidate_source": resolution.candidate_source,
                "dcc_candidates_count": len(resolution.impact_candidates) if resolution.dcc_used else 0,
            },
            output=ctx.impact_result,
            evidence=evidence,
            execution_log=execution_log,
            explanation=(
                "基于 DCC 对象化候选先收敛影响面，再结合业务语义与规模分析确认受影响范围 (object-centered)。"
                if resolution.dcc_used and _dcc_authoritative
                else (
                    "影响面分析分三层：① 接口级影响来自 trace / 调用链（confidence=high）；"
                    "② 业务语义影响来自演示业务本体 demo_business_ontology.yaml（confidence=medium，仅供演示）；"
                    "③ 影响规模需真实业务指标（UV/PV/QPS 等），当前测试数据未接入，impact_scale=unavailable。"
                )
            ),
        )
