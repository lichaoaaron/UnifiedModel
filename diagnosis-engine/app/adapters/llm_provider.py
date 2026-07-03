"""
LLMProvider: interface + implementations for language model explanation generation.

Implementations:
  MockLLMProvider           — rule-based template report (no API call)
  OpenAICompatibleProvider  — calls any OpenAI-compatible API (Qwen / GPT / etc.)

Fallback order (production):
  1. Real LLM streaming       (OpenAI-compatible, stream=True)
  2. Real LLM non-streaming   (OpenAI-compatible, stream=False)
  3. Rule-based template      (MockLLMProvider — always produces a usable report)
  4. Mock simulation          (only if LLM_ALLOW_MOCK_FALLBACK=true in .env)

Configuration (backend/.env):
  LLM_PROVIDER=openai                   # openai | mock
  LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
  LLM_API_KEY=sk-xxx
  LLM_MODEL=qwen-plus
  LLM_ENABLE_STREAM=true                # default: true
  LLM_STREAM_TIMEOUT_SECONDS=60         # default: 60
  LLM_NON_STREAM_TIMEOUT_SECONDS=30     # default: 30
  LLM_MAX_RETRIES=1                     # default: 1
  LLM_ALLOW_MOCK_FALLBACK=false         # default: false (production-safe)

Factory:
  from app.adapters.llm_provider import get_llm_provider
  provider = get_llm_provider()   # auto-selects based on .env
"""
from __future__ import annotations
import logging
import os
from collections.abc import Iterator
from typing import Any

logger = logging.getLogger(__name__)

# Lazy import to avoid circular dep; called only when needed
def _get_llm_config():
    from app.adapters.llm_config import load_llm_config
    return load_llm_config()

# ---------------------------------------------------------------------------
# Base interface
# ---------------------------------------------------------------------------

class LLMProvider:
    """Base interface. Replace with OpenAICompatibleProvider, etc."""

    def generate_explanation(self, context: dict[str, Any]) -> str:
        raise NotImplementedError

    def generate_text(self, prompt: str, system: str = "你是一名可观测性智能诊断专家，请用中文回答。") -> str:
        """Return full text at once (non-streaming). Used for plan generation."""
        raise NotImplementedError

    def stream_text(self, prompt: str, system: str = "你是一名可观测性智能诊断专家，请用中文回答。") -> Iterator[str]:
        """Yield text chunks. Default: yield whole text at once."""
        raise NotImplementedError

    def stream_report(self, context: dict[str, Any]) -> Iterator[str]:
        """Stream the final diagnosis report char by char. context includes root_cause/impact/trace/log/metric/api/time/symptom."""
        raise NotImplementedError

    def generate_undetermined_report(self, context: dict[str, Any]) -> str:
        """Generate a special report for when root cause is undetermined (is_confirmed=False).
        Default: falls back to generate_explanation."""
        return self.generate_explanation(context)


# ---------------------------------------------------------------------------
# MockLLMProvider — template-based, no external API
# ---------------------------------------------------------------------------

class MockLLMProvider(LLMProvider):
    """
    Template-based report generator.
    Used when LLM_PROVIDER != 'openai' or when API call fails.
    """

    def generate_undetermined_report(self, context: dict[str, Any]) -> str:
        """Generate a special report for when root cause is undetermined (is_confirmed=False)."""
        rc = context.get("root_cause", {})
        trace = context.get("trace", {})
        log = context.get("log", {})
        metric = context.get("metric", {})
        api = context.get("api", "/unknown")
        ctx_time = context.get("time", "（未知时间）")
        symptom = context.get("symptom", "故障")
        consistency = context.get("evidence_consistency", {}) or {}

        candidate_service = rc.get("root_cause_service") or "（未知服务）"
        candidate_type = rc.get("root_cause_type") or "未知异常类型"
        candidate_api = rc.get("root_cause_api") or "（未知接口）"
        confidence = rc.get("confidence", "（未知）")
        trace_id = trace.get("trace_id", "N/A")

        conflict_lines_text = ""
        if consistency.get("has_conflict"):
            conflict_parts = []
            for c in consistency.get("conflicts", []):
                conflict_parts.append(
                    f"  · 字段 [{c['field']}]: {c['source_a']} 记录值={c['source_a_value']}，"
                    f"{c['source_b']} 记录值={c['source_b_value']}"
                )
            if conflict_parts:
                conflict_lines_text = "\n".join(conflict_parts)

        evidence_conflicts = rc.get("evidence_conflicts", [])
        rc_conflict_text = ""
        if evidence_conflicts:
            rc_conflict_parts = [f"  · {c}" for c in evidence_conflicts]
            rc_conflict_text = "\n".join(rc_conflict_parts)

        metric_conclusion = metric.get("conclusion", "未发现资源异常")

        return f"""【故障结论】
时间范围：{ctx_time}
核心问题：{api} 接口出现 {symptom}
根因状态：待确认（多源证据冲突，无法高置信确认）

【异常现象】
接口 {api} 返回异常（{symptom}）
traceId：{trace_id}
Metric 证据：{metric_conclusion}

【根因定位】
当前候选根因为：
- 候选根因服务：{candidate_service}
- 候选根因接口：{candidate_api}
- 候选根因类型：{candidate_type}
- 当前置信度：{confidence}

关键说明：以上为候选结论，因证据冲突，异常参数等细节暂不可信，不作为最终根因结论。

【证据链分析】
Trace/Log 证据冲突详情：
{conflict_lines_text or rc_conflict_text or "证据不一致（详情不可用）"}

【实例与资源状态】
调用链中已识别异常传播现象，但根因实例细节尚无法确认
上下游异常传播关系存在，但关键字段仍需人工复核

【影响面分析】
当前因根因未确认，影响面结论暂不输出
建议先完成证据核查后再进行业务影响评估

【处置建议】
紧急措施：
- 手动核查 traceId {trace_id} 对应的完整调用链与日志窗口是否对齐

根本修复建议：
- 对比 trace 与 log 的关键字段记录，确认参数与异常类型是否一致
- 排查采集链路是否存在日志丢失、延迟或字段映射偏差

【长期优化建议】
- 建立多源证据一致性巡检，定期校验 trace/log 字段对齐情况
- 对关键故障字段增加采集质量告警，降低证据冲突导致的误判风险

【诊断依据与可信度】
本次诊断已收敛到候选根因，但因多源证据冲突未能最终确认。应优先提升观测数据一致性，再执行自动诊断闭环。"""

    # ------------------------------------------------------------------
    # Root-cause-type → (diagnosis_detail, fix_urgent, fix_root, prevention, lesson)
    # All templates use only variables passed in; no hardcoded service/param names.
    # ------------------------------------------------------------------
    _RC_TEMPLATES: dict[str, dict[str, str]] = {
        "业务异常": {
            "diagnosis_detail":
                "{root_service} 处理请求时抛出 {exc_type}，接口直接返回 500。",
            "fix_urgent":
                "在 {root_service} 接口入口处增加参数合法性校验，对非法输入返回 400 Bad Request。",
            "fix_root":
                "在 {root_service} 添加全局异常处理器，捕获 {exc_type} 并返回标准化错误结构；"
                "在 {upstream_svc} 调用侧增加 fallback/降级逻辑，避免单点异常扩散；"
                "完善接口契约测试，覆盖非法参数边界场景。",
            "prevention":
                "在 CI 流程中加入接口参数边界测试；在 API 网关层统一做入参格式校验；"
                "配置告警规则：单接口 5xx 率超阈值时自动触发排查流程。",
            "lesson":
                "本次故障暴露了参数校验缺失和异常隔离不足两个问题。"
                "建议将参数校验作为服务接入标准，并在调用链中落实熔断降级策略。",
        },
        "超时异常": {
            "diagnosis_detail":
                "{root_service} 处理请求时发生超时（{exc_type}），导致上游调用失败。",
            "fix_urgent":
                "临时增大 {root_service} 调用超时阈值或对外暴露降级接口，恢复业务可用性。",
            "fix_root":
                "排查 {root_service} 内部慢查询、锁竞争或外部依赖延迟；"
                "在 {upstream_svc} 侧配置合理超时时间和重试策略（带指数退避）；"
                "为 {root_service} 配置熔断器，避免超时级联。",
            "prevention":
                "建立服务 P99 延迟基线告警；对关键调用链路进行超时链路压测；"
                "确保所有 RPC 调用均配置超时时间，禁止无超时调用。",
            "lesson":
                "超时问题往往源于下游依赖抖动或资源竞争。"
                "需要在每个调用层面设置合理超时，并配套熔断和降级兜底。",
        },
        "数据库异常": {
            "diagnosis_detail":
                "{root_service} 执行数据库操作时出现 {exc_type}，导致请求失败。",
            "fix_urgent":
                "检查 {root_service} 连接的数据库实例是否正常，必要时切换到备库或启用只读降级。",
            "fix_root":
                "排查 SQL 慢查询、锁等待、连接池耗尽等问题；"
                "优化高频查询，添加合适索引；"
                "配置数据库连接池监控和自动重连策略。",
            "prevention":
                "配置数据库连接池水位告警；定期审查慢查询日志；"
                "在测试环境覆盖数据库异常场景（模拟连接超时、主从切换）。",
            "lesson":
                "数据库异常影响范围广，需要在应用层做好连接池管理和异常隔离，"
                "避免数据库问题导致整个服务不可用。",
        },
        "资源耗尽": {
            "diagnosis_detail":
                "{root_service} 发生资源耗尽（{exc_type}），新请求被拒绝或崩溃。",
            "fix_urgent":
                "立即重启受影响的 {root_service} 实例，释放资源；检查是否有内存泄漏或线程泄漏。",
            "fix_root":
                "分析 {root_service} 堆转储或线程转储，定位泄漏根因；"
                "设置合理的线程池大小和队列容量；"
                "在 {upstream_svc} 侧增加熔断器，避免级联雪崩。",
            "prevention":
                "配置 JVM/容器内存和线程数水位告警；"
                "在 CI 中加入内存泄漏检测工具（如 LeakCanary / Valgrind）；"
                "配置自动重启策略（如 Kubernetes liveness probe）。",
            "lesson":
                "资源耗尽往往是内存/线程泄漏累积导致的。"
                "需要结合监控和自动化恢复机制，防止单实例故障扩散。",
        },
        "网络连接异常": {
            "diagnosis_detail":
                "{root_service} 无法连接依赖的下游服务或外部资源，出现 {exc_type}。",
            "fix_urgent":
                "建议排查 {root_service} 与依赖服务之间的网络连通性和 DNS 解析状态。",
            "fix_root":
                "确认服务发现/注册中心配置正确；"
                "建议排查网络策略变更（如安全组、ACL、Service Mesh 配置）；"
                "在 {upstream_svc} 侧配置 fallback，网络不通时返回缓存或降级数据。",
            "prevention":
                "配置网络连通性探针和告警；"
                "在变更管理中加入网络配置变更审核流程；"
                "定期演练网络故障（混沌工程）。",
            "lesson":
                "网络问题排查链路长，需要关注变更窗口（网络/安全策略变更）。"
                "配套服务网格和连通性监控能显著缩短 MTTR。",
        },
    }
    # Default template used when root_cause_type doesn't match any key
    _RC_TEMPLATE_DEFAULT: dict[str, str] = {
        "diagnosis_detail":
            "{root_service} 处理请求时出现 {exc_type}，导致接口返回异常。",
        "fix_urgent":
            "检查 {root_service} 的运行状态和错误日志，确认是否需要紧急重启或回滚。",
        "fix_root":
            "根据 {exc_type} 具体类型排查根因；"
            "在 {upstream_svc} 调用侧增加异常处理和降级逻辑。",
        "prevention":
            "完善该类型异常的监控告警和自动化恢复策略。",
        "lesson":
            "建议补充该类型异常场景的测试覆盖，防止类似问题再次发生。",
    }

    def _get_rc_template(self, root_type: str) -> dict[str, str]:
        """Return the template dict for the given root_cause_type (fuzzy match)."""
        # Exact match first
        if root_type in self._RC_TEMPLATES:
            return self._RC_TEMPLATES[root_type]
        # Fuzzy: check if any key is a substring of root_type or vice versa
        for key, tmpl in self._RC_TEMPLATES.items():
            if key in root_type or root_type in key:
                return tmpl
        return self._RC_TEMPLATE_DEFAULT

    def _red_metric_items(self, root_service: str, rc: dict[str, Any], metric: dict[str, Any]) -> list[dict[str, Any]]:
        evidence = (rc.get("evidence_by_source") or {}).get("red_metrics") or metric.get("red_metrics") or []
        items = [item for item in evidence if isinstance(item, dict)]
        root_items = [item for item in items if item.get("service_name") == root_service]
        return root_items or items[:3]

    def _format_red_metric_line(self, root_service: str, rc: dict[str, Any], metric: dict[str, Any], fallback: str) -> str:
        items = self._red_metric_items(root_service, rc, metric)
        if not items:
            return fallback
        parts = []
        for item in items[:3]:
            service = item.get("service_name") or "unknown"
            rate = item.get("rate", {}) or {}
            error = item.get("error", {}) or {}
            duration = item.get("duration", {}) or {}
            p95 = duration.get("metric_p95_duration_ms") or duration.get("p95_duration_ms")
            parts.append(
                f"{service} RED 异常评分={item.get('overall_anomaly_score', 'unknown')} "
                f"(rate={item.get('rate_signal', 'unknown')}, "
                f"error={item.get('error_signal', 'unknown')}, "
                f"duration={item.get('duration_signal', 'unknown')}; "
                f"requests={rate.get('request_count', 0)}, "
                f"error_rate={error.get('error_rate', 'unknown')}, "
                f"p95_ms={p95})"
            )
        return "RED Metrics 证据：" + "；".join(parts)

    def _service_map_edges(self, rc: dict[str, Any], graph: dict[str, Any]) -> list[dict[str, Any]]:
        service_map = (rc.get("evidence_by_source") or {}).get("service_map") or graph.get("service_map_evidence") or {}
        edges = service_map.get("call_edges") or graph.get("call_edges") or []
        return [edge for edge in edges if isinstance(edge, dict)]

    def _edge_services(self, edges: list[dict[str, Any]]) -> list[str]:
        services: list[str] = []
        for edge in edges:
            for key_pair in (("source_service", "source"), ("target_service", "target")):
                service = edge.get(key_pair[0]) or edge.get(key_pair[1])
                if service and service not in services:
                    services.append(str(service))
        return services

    def _format_call_edge_observation(self, edge: dict[str, Any], *, include_p95: bool = False) -> str:
        source = edge.get("source_service") or edge.get("source") or "unknown"
        target = edge.get("target_service") or edge.get("target") or "unknown"
        try:
            call_count = int(edge.get("call_count") or 0)
        except (TypeError, ValueError):
            call_count = 0
        try:
            error_count = int(edge.get("error_count") or 0)
        except (TypeError, ValueError):
            error_count = 0

        details = [f"calls={call_count}", f"errors={error_count}"]
        if call_count <= 1:
            details.append("单样本观测，不外推全局错误率")
        else:
            details.append(f"observed_error_rate={edge.get('error_rate', 0)}")
        if include_p95:
            details.append(f"p95_ms={edge.get('p95_duration_ms')}")
        return f"{source}→{target}(" + ", ".join(details) + ")"

    def _format_service_map_path_line(self, rc: dict[str, Any], graph: dict[str, Any]) -> str:
        edges = self._service_map_edges(rc, graph)
        if not edges:
            return "（当前结构化字段不足以还原完整路径）"
        return "；".join(self._format_call_edge_observation(edge) for edge in edges[:8])

    def _format_impact_scope_line(self, impact: dict[str, Any], rc: dict[str, Any], graph: dict[str, Any]) -> str:
        affected_service_list = [str(service) for service in (impact.get("affected_services", []) or []) if service]
        affected_api_list = [str(api) for api in (impact.get("affected_apis", []) or []) if api]
        propagation_services = self._edge_services(self._service_map_edges(rc, graph))

        affected_services = ", ".join(affected_service_list) or "（未知）"
        affected_apis = ", ".join(affected_api_list) or "（未知）"
        if affected_services == "（未知）" and affected_apis == "（未知）":
            return "影响范围：当前结构化证据不足，暂无法确认具体影响范围。"

        propagation_only = [service for service in propagation_services if service not in affected_service_list]
        if propagation_only:
            return (
                f"影响范围：核心受影响服务为 {affected_services}，上游传播链路涉及 {', '.join(propagation_services)}；"
                f"受影响接口为 {affected_apis}。"
            )
        if affected_services != "（未知）" and affected_apis != "（未知）":
            return f"影响范围：当前可确认受影响服务为 {affected_services}，受影响接口为 {affected_apis}。"
        if affected_services != "（未知）":
            return f"影响范围：当前可确认受影响服务为 {affected_services}，接口范围暂无法确认。"
        return f"影响范围：当前可确认受影响接口为 {affected_apis}，服务范围暂无法确认。"

    def _format_confidence_assessment(self, confidence: Any, *, metric_no_threshold: bool, no_log_root_evidence: bool) -> str:
        confidence_value = str(confidence or "（未知）").lower()
        limitations = []
        if no_log_root_evidence:
            limitations.append("日志证据缺失")
        if metric_no_threshold:
            limitations.append("资源阈值未配置")
        limitation_text = "；".join(limitations)
        if confidence_value == "high":
            suffix = f"；{limitation_text}仅表示部分证据维度仍需补充，不改变当前根因结论置信度。" if limitation_text else "。"
            return f"当前根因结论置信度为 high{suffix}"
        if confidence_value == "medium":
            return "当前结论为中等置信度，仍需补充日志或指标验证。"
        if confidence_value:
            suffix = f"；证据限制：{limitation_text}。" if limitation_text else "。"
            return f"当前根因结论置信度为 {confidence}{suffix}"
        return "当前结论需结合后续证据持续校验。"

    def _format_business_impact_line(self, impact: dict[str, Any], root_service: str) -> str:
        business_impact = impact.get("business_impact") or {}
        if not isinstance(business_impact, dict) or not business_impact:
            return "业务影响数据：当前未从 trace/log/metric 中识别到可证明业务受损的结构化字段。"
        affected_orders = business_impact.get("affected_order_count", "unknown")
        failed_transactions = business_impact.get("failed_transaction_count", "unknown")
        affected_users = business_impact.get("affected_user_count", "unknown")
        revenue = business_impact.get("estimated_revenue_impact", business_impact.get("estimated_gmv_loss", "unknown"))
        currency = business_impact.get("currency") or ""
        confidence = business_impact.get("confidence", "none")
        failed_estimated = bool(business_impact.get("failed_transaction_count_estimated"))
        failed_is_confirmed = str(confidence).lower() == "high" and not failed_estimated
        failed_label = "失败交易数" if failed_is_confirmed else "失败交易信号"
        failed_suffix = "（可观测证据推导值，非最终业务交易事实）" if failed_transactions != "unknown" and not failed_is_confirmed else ""
        trace_ids = business_impact.get("related_trace_ids") or (business_impact.get("evidence_links") or {}).get("trace_ids") or []
        services = business_impact.get("related_services") or (business_impact.get("evidence_links") or {}).get("related_services") or []
        evidence_parts = []
        if trace_ids:
            evidence_parts.append(f"trace_ids={', '.join(str(trace_id) for trace_id in trace_ids[:3])}")
        if services:
            evidence_parts.append(f"services={', '.join(str(service) for service in services[:5])}")
        evidence_text = "；关联证据：" + "，".join(evidence_parts) if evidence_parts else ""
        causal_service = root_service if root_service and root_service != "（未知服务）" else business_impact.get("root_cause_service") or "根因服务"
        return (
            f"业务影响数据：{causal_service} 技术异常关联到可观测业务受损信号，"
            f"受影响订单数={affected_orders}，{failed_label}={failed_transactions}{failed_suffix}，"
            f"受影响用户数={affected_users}，估算金额影响={revenue}{currency}，confidence={confidence}{evidence_text}。"
        )

    def _format_service_map_line(self, root_service: str, rc: dict[str, Any], graph: dict[str, Any]) -> str:
        edges = self._service_map_edges(rc, graph)
        if not edges:
            return "Service Map 证据：当前结构化调用边不足，暂无法还原完整传播路径。"
        root_related = [
            edge for edge in edges
            if root_service in {edge.get("source_service") or edge.get("source"), edge.get("target_service") or edge.get("target")}
        ]
        selected_edges = root_related or edges[:5]
        edge_text = []
        for edge in selected_edges[:5]:
            edge_text.append(self._format_call_edge_observation(edge, include_p95=True))
        return "Service Map 证据：" + "；".join(edge_text)

    def generate_explanation(self, context: dict[str, Any]) -> str:
        rc = context.get("root_cause", {})
        impact = context.get("impact", {})
        trace = context.get("trace", {})
        graph = context.get("graph", {})
        log = context.get("log", {})
        metric = context.get("metric", {})
        api = context.get("api", "/unknown")
        ctx_time = context.get("time", "（未知时间）")
        symptom = context.get("symptom", "故障")

        root_service = rc.get("root_cause_service") or "（未知服务）"
        root_api = rc.get("root_cause_api") or "（未知接口）"
        root_type = rc.get("root_cause_type") or "服务异常"
        exc_type = rc.get("exception_type") or "未知异常"
        trace_id = trace.get("trace_id", "N/A")
        upstream_svc = log.get("upstream_service") or "（未知上游服务）"
        downstream_url = log.get("downstream_url") or f"http://{root_service}{root_api}"
        metric_conclusion = metric.get("conclusion", "指标状态未知")
        affected_services = ", ".join(impact.get("affected_services", [])) or "（未知）"
        affected_apis = ", ".join(impact.get("affected_apis", [])) or "（未知）"
        raw_affected_business = [str(item) for item in (impact.get("affected_business", []) or []) if item]
        has_demo_marked_business = any(("演示" in item) or ("本体推断" in item) for item in raw_affected_business)
        cleaned_business = [
            item.replace("（演示业务本体推断）", "").replace("(演示业务本体推断)", "").strip()
            for item in raw_affected_business
        ]
        cleaned_business = [item for item in cleaned_business if item]
        affected_business = ", ".join(cleaned_business) or "（无）"
        impact_scale = impact.get("impact_scale", "unavailable")
        affected_user_groups = impact.get("affected_user_groups", []) or []

        log_evidence = log.get("log_evidence", []) or []
        log_root_candidates = log.get("root_candidates", []) or []
        no_log_root_evidence = (len(log_evidence) == 0) or (len(log_root_candidates) == 0)

        metric_status = metric.get("resource_status")
        metric_no_threshold = metric_status == "no_threshold"

        trace_call_services = list(dict.fromkeys(
            p.split(":", 1)[0].strip() for p in (trace.get("call_path", []) or []) if p
        ))
        root_in_trace_chain = bool(root_service and root_service in trace_call_services)

        derived_impact_path = ""
        if impact.get("affected_path"):
            derived_impact_path = str(impact.get("affected_path"))
        elif impact.get("impact_path"):
            path_nodes = []
            for seg in impact.get("impact_path", []):
                if not isinstance(seg, dict):
                    continue
                src = seg.get("source")
                tgt = seg.get("target")
                if src and src not in path_nodes:
                    path_nodes.append(src)
                if tgt and tgt not in path_nodes:
                    path_nodes.append(tgt)
            if path_nodes:
                derived_impact_path = " → ".join(path_nodes)
        elif trace_call_services:
            derived_impact_path = " → ".join(trace_call_services)
        else:
            graph_calls = [e for e in (graph.get("edges", []) or []) if isinstance(e, dict) and e.get("label") == "calls"]
            graph_path_nodes = []
            for edge in graph_calls:
                for key in ("source", "target"):
                    value = edge.get(key)
                    if value and value not in graph_path_nodes:
                        graph_path_nodes.append(value)
            if graph_path_nodes:
                derived_impact_path = " → ".join(graph_path_nodes)

        # Select template based on root_cause_type
        tmpl = self._get_rc_template(root_type)
        _vars = dict(
            root_service=root_service, root_api=root_api, root_type=root_type,
            exc_type=exc_type,
            upstream_svc=upstream_svc, downstream_url=downstream_url,
        )
        diagnosis_detail = tmpl["diagnosis_detail"].format(**_vars)
        fix_urgent = tmpl["fix_urgent"].format(**_vars)
        fix_root = tmpl["fix_root"].format(**_vars)
        prevention = tmpl["prevention"].format(**_vars)
        lesson = tmpl["lesson"].format(**_vars)

        impact_scale_line = (
            f"影响规模：{impact_scale}"
            if impact_scale and impact_scale != "unavailable"
            else "影响规模：unavailable（当前未接入可量化业务规模指标）"
        )

        # Evidence conflict section
        consistency = context.get("evidence_consistency", {}) or {}
        is_confirmed = rc.get("is_confirmed", True)
        evidence_conflict_section = ""
        if consistency.get("has_conflict"):
            conflict_lines = []
            for c in consistency.get("conflicts", []):
                conflict_lines.append(
                    f"  · 字段 [{c['field']}]: {c['source_a']} 记录值={c['source_a_value']}，"
                    f"{c['source_b']} 记录值={c['source_b_value']}"
                )
            evidence_conflict_section = (
                f"\n\n证据一致性警告：\n"
                f"当前 trace 与 log 证据存在不一致，无法高置信确认所有根因细节：\n"
                f"{chr(10).join(conflict_lines)}\n"
                f"置信度已自动降低，当前根因结论为候选根因，尚未完全确认。\n"
                f"建议核查：\n"
                f"  1. traceId {trace_id} 对应的完整调用链是否完整采集\n"
                f"  2. 日志时间窗口与 trace 时间窗口是否对齐\n"
                f"  3. 日志采集是否存在丢失或延迟\n"
                f"  4. 请求参数在服务调用链路中的传递是否存在变换"
            )
        elif not is_confirmed:
            evidence_conflict_section = "\n\n【注意】当前根因为候选结论，证据支持度不足，建议进一步核查。"

        root_cause_status = "已确认" if is_confirmed else "候选根因（待确认）"
        current_confidence = rc.get("confidence", "（未知）")

        if no_log_root_evidence:
            log_line = "Log 证据：未查到可用于确认根因的日志证据。"
        else:
            log_line = f"Log 证据：{upstream_svc} 侧记录错误，下游 URL：{downstream_url}"

        metric_fallback_line = "Metric 证据：指标仅作为辅助，未配置阈值，不能单独判断资源异常。" if metric_no_threshold else f"Metric 证据：{metric_conclusion}"
        metric_line = self._format_red_metric_line(root_service, rc, metric, metric_fallback_line)
        service_map_line = self._format_service_map_line(root_service, rc, graph)
        service_map_path_line = self._format_service_map_path_line(rc, graph)
        confidence_assessment_line = self._format_confidence_assessment(
            current_confidence,
            metric_no_threshold=metric_no_threshold,
            no_log_root_evidence=no_log_root_evidence,
        )

        if metric_no_threshold:
            resource_section = (
                "- 当前未接入实例健康探测，无法判断实例心跳状态。\n"
                "- 当前未接入端口探测，无法判断端口监听状态。"
            )
        else:
            resource_section = (
                f"- {root_service} 实例：接收到请求后出现 {exc_type}，HTTP 状态码异常\n"
                f"- {upstream_svc} 实例：调用 {root_service}，收到错误响应，向上透传"
            )

        confidence_line = confidence_assessment_line

        if root_in_trace_chain:
            relation_line = f"调用链中可见服务链路包含根因服务 {root_service}。"
        else:
            relation_line = "根因接口由 trace/RPC 异常候选推断，与入口请求存在诊断关联。"

        call_chain_services = "、".join(trace_call_services) if trace_call_services else "（当前未从 trace 明确提取）"
        confirmed_affected_services = affected_services if affected_services != "（未知）" else "（当前结构化证据不足，暂无法确认）"

        impact_scope_line = self._format_impact_scope_line(impact, rc, graph)

        business_impact_line = ""
        if affected_business and affected_business != "（无）" and not has_demo_marked_business:
            business_impact_line = f"业务功能影响：{affected_business}"
        else:
            business_impact_line = "业务功能影响：当前结构化证据不足，暂无法确认。"
        observability_business_impact_line = self._format_business_impact_line(impact, root_service)

        demo_user_group_names = []
        for ug in affected_user_groups:
            if isinstance(ug, dict):
                name = ug.get("name") or ug.get("id")
                if name:
                    demo_user_group_names.append(str(name))
            elif ug:
                demo_user_group_names.append(str(ug))

        user_impact_line = "当前未接入真实用户群/订单/会话数据，无法确认具体用户群影响。"
        if demo_user_group_names:
            user_impact_line += f" 当前结构化候选用户群：{', '.join(demo_user_group_names)}（需后续验证）。"

        if impact_scale and impact_scale != "unavailable":
            impact_scale_line = f"影响规模：{impact_scale}（需结合真实业务指标复核）"
        else:
            impact_scale_line = "影响规模：暂不估算具体影响规模（当前未接入真实 UV/PV/QPS/订单量/失败交易数/工单量）。"

        return f"""【故障结论】
时间范围：{ctx_time}
核心问题：{api} 接口出现 {symptom}
根因状态：{root_cause_status}（置信度：{current_confidence}）
根因类型：{root_type}
{impact_scope_line}
可信度补充：{confidence_line}
{evidence_conflict_section}
【异常现象】
› 接口 {api} 出现 {symptom}
› {relation_line}
› traceId：{trace_id}

【根因定位】
根因服务：{root_service}
根因接口：{root_api}
根因类型：{root_type}
异常类型：{exc_type}
根因状态：{root_cause_status}
分析：{diagnosis_detail}

【证据链分析】
Trace 证据：{root_service} span 中出现 {exc_type}（traceId: {trace_id}）
{log_line}
{metric_line}
{service_map_line}
MModel 本体证据：通过轻量本体配置和绑定规则，将 trace/log/metric 映射到 Service、Instance、Interface 和 BusinessFlow

【实例与资源状态】
{resource_section}

【影响面分析】
- 调用链涉及服务：{call_chain_services}
- 确认受影响服务：{confirmed_affected_services}
- Service Map 观测路径：{service_map_path_line}
- 影响路径：{derived_impact_path or '（当前结构化字段不足以还原完整路径）'}
- 受影响服务：{affected_services}
- 受影响接口：{affected_apis}
- {business_impact_line}
- {observability_business_impact_line}
- 用户群影响：{user_impact_line}
- {impact_scale_line}

【处置建议】
紧急措施（建议排查）：
- {fix_urgent}
根本修复建议：
- 建议排查：{fix_root}

【长期优化建议】
- 建议排查：{prevention}

【诊断依据与可信度】
{lesson}
{confidence_assessment_line}"""

    def stream_report(self, context: dict[str, Any]) -> Iterator[str]:
        """Mock: build report text and yield char by char. Uses undetermined template when is_confirmed=False."""
        import time as _t
        rc = context.get("root_cause", {}) or {}
        if not rc.get("is_confirmed", True):
            text = self.generate_undetermined_report(context)
        else:
            text = self.generate_explanation(context)
        for char in text:
            yield char
            _t.sleep(0.06)  # 60ms per char — slower, matches visual pacing

    def stream_text(self, prompt: str, system: str = "你是一名可观测性智能诊断专家，请用中文回答。") -> Iterator[str]:
        """Mock: yield a context-aware short sentence based on prompt keywords."""
        # Map skill keywords to meaningful output sentences
        _SKILL_TEXT: list[tuple[str, str]] = [
            ("set_time_range",      "已确认故障时间窗口，开始圈定排查范围。"),
            ("时间范围",              "已确认故障时间窗口，开始圈定排查范围。"),
            ("analyze_trace",       "正在解析调用链 Span，追踪异常传播路径。"),
            ("调用链",               "正在解析调用链 Span，追踪异常传播路径。"),
            ("bind_entities",       "正在将 Trace/Log/Metric 绑定到本体实体。"),
            ("实体绑定",              "正在将 Trace/Log/Metric 绑定到本体实体。"),
            ("analyze_log",         "正在扫描错误日志，定位异常堆栈与下游 URL。"),
            ("日志分析",              "正在扫描错误日志，定位异常堆栈与下游 URL。"),
            ("check_metrics",       "正在核查资源指标，排除 CPU/内存/延迟异常。"),
            ("指标检查",              "正在核查资源指标，排除 CPU/内存/延迟异常。"),
            ("query_graph",         "正在查询服务依赖图，构建调用拓扑。"),
            ("关系图",               "正在查询服务依赖图，构建调用拓扑。"),
            ("infer_root_cause",    "正在综合证据推断根因服务与异常类型。"),
            ("根因",                 "正在综合证据推断根因服务与异常类型。"),
            ("analyze_impact",      "正在评估故障影响范围与业务影响链路。"),
            ("影响面",               "正在评估故障影响范围与业务影响链路。"),
            # Post-skill transitions keyed on result summary keywords
            ("时间范围已确定",        "时间窗口锁定完成，接下来拉取调用链数据。"),
            ("span",                "调用链分析完成，已提取异常 Span，继续排查日志。"),
            ("FeignException",      "日志分析完成，发现传播性异常，准备核查指标。"),
            ("Exception",           "日志分析完成，发现异常，准备核查指标。"),
            ("根因定位",             "根因定位完成，异常已确认，分析影响面。"),
            ("影响接口",             "影响面分析完成，受影响服务和接口已识别。"),
        ]
        text = "好的，我正在分析故障现象，逐步排查根因。"
        for keyword, sentence in _SKILL_TEXT:
            if keyword in prompt:
                text = sentence
                break
        for char in text:
            yield char

    def generate_text(self, prompt: str, system: str = "你是一名可观测性智能诊断专家，请用中文回答。") -> str:
        """Mock: return a default plan JSON instantly (no sleep)."""
        return '{"plan": []}'


# ---------------------------------------------------------------------------
# OpenAICompatibleProvider — real API (Qwen / GPT / any OpenAI-compatible)
# ---------------------------------------------------------------------------

class OpenAICompatibleProvider(LLMProvider):
    """
    Calls any OpenAI-compatible chat completion API.
    Tested with:
      - 通义千问 via https://dashscope.aliyuncs.com/compatible-mode/v1
      - OpenAI GPT via https://api.openai.com/v1
    Falls back to MockLLMProvider on any error.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = "qwen-plus",
        enable_stream: bool = True,
        stream_timeout: int = 60,
        non_stream_timeout: int = 30,
        max_retries: int = 1,
        allow_mock_fallback: bool = False,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._enable_stream = enable_stream
        self._stream_timeout = stream_timeout
        self._non_stream_timeout = non_stream_timeout
        self._max_retries = max_retries
        self._allow_mock_fallback = allow_mock_fallback
        self._rule_based_fallback = MockLLMProvider()
        # Keep old name as alias for compatibility
        self._mock_fallback = self._rule_based_fallback

    def _log_fallback(self, method: str, stage: str, error: Exception, fallback_to: str) -> None:
        logger.error(
            "[LLM][fallback] method=%s stage=%s fallback_to=%s "
            "error_type=%s error=%s",
            method, stage, fallback_to, type(error).__name__, error,
            exc_info=False,
        )

    def _build_report_prompt(self, context: dict[str, Any]) -> str:
        rc = context.get("root_cause", {})
        impact = context.get("impact", {})
        trace = context.get("trace", {})
        log = context.get("log", {})
        metric = context.get("metric", {})
        graph = context.get("graph", {})
        api = context.get("api", "/unknown")
        ctx_time = context.get("time", "（未知时间）")
        symptom = context.get("symptom", "故障")
        root_service = rc.get("root_cause_service")

        red_items = [
            item for item in ((rc.get("evidence_by_source") or {}).get("red_metrics") or metric.get("red_metrics") or [])
            if isinstance(item, dict)
        ]
        red_root_items = [item for item in red_items if item.get("service_name") == root_service]
        red_prompt_line = "; ".join(
            f"{item.get('service_name')}: score={item.get('overall_anomaly_score')}, "
            f"rate={item.get('rate_signal')}, error={item.get('error_signal')}, duration={item.get('duration_signal')}"
            for item in (red_root_items or red_items[:3])
        ) or "无"

        service_map_evidence = (rc.get("evidence_by_source") or {}).get("service_map") or graph.get("service_map_evidence") or {}
        service_map_edges = service_map_evidence.get("call_edges") or graph.get("call_edges") or []
        service_map_prompt_line = "; ".join(
            self._rule_based_fallback._format_call_edge_observation(edge)
            for edge in service_map_edges[:6]
            if isinstance(edge, dict)
        ) or "无"
        propagation_services = ", ".join(self._rule_based_fallback._edge_services([
            edge for edge in service_map_edges if isinstance(edge, dict)
        ])) or "无"
        confidence_value = rc.get("confidence", "（未知）")
        business_impact = impact.get("business_impact") or {}
        business_impact_prompt_line = "无"
        business_impact_report_line = self._rule_based_fallback._format_business_impact_line(impact, root_service or "")
        if isinstance(business_impact, dict) and business_impact:
            business_impact_prompt_line = (
                f"affected_order_count={business_impact.get('affected_order_count', 'unknown')}, "
                f"failed_transaction_count={business_impact.get('failed_transaction_count', 'unknown')}, "
            f"failed_transaction_count_estimated={business_impact.get('failed_transaction_count_estimated', False)}, "
                f"affected_user_count={business_impact.get('affected_user_count', 'unknown')}, "
                f"estimated_revenue_impact={business_impact.get('estimated_revenue_impact', business_impact.get('estimated_gmv_loss', 'unknown'))}, "
                f"confidence={business_impact.get('confidence', 'none')}, "
                f"evidence_links={business_impact.get('evidence_links', {})}"
            )

        report_guardrails = context.get("report_guardrails", {}) or {}
        guardrails_text = (
            "- 日志约束：当 log_evidence 为空或 root_candidates=0 时，必须明确写“未查到可用于确认根因的日志证据”，不得编造日志细节。\n"
            "- 指标约束：当存在 RED Metrics 证据时，必须引用服务级 RED 异常评分；resource_status=no_threshold 仅表示资源阈值不足，不得否定 RED 证据。无 RED 证据且 resource_status=no_threshold 时，才写“指标仅作为辅助，未配置阈值，不能单独判断资源异常”。\n"
            "- 置信度约束：root_cause.confidence 是根因结论置信度的唯一来源；confidence=high 时必须写 high/高置信，不得因日志缺失或资源阈值缺失改写成中等置信度。日志缺失和阈值缺失只能写成证据限制。confidence=medium 时才写“中等置信度，仍需补充日志或指标验证”。\n"
            "- 影响范围约束：区分核心受影响服务 impact.affected_services 与 Service Map 上游传播链路；若 Service Map 包含更多服务，不得只写两个服务受影响，应写“核心受影响服务...”和“传播链路涉及...”。\n"
            "- 调用边错误率约束：Service Map 中 call_count<=1 的边只能写“当前观测窗口内 calls/errors，单样本观测，不外推全局错误率”；不得写“错误率高达100%”“无成功响应”“所有请求失败”。\n"
            "- 影响路径约束：影响路径只能来自 impact.affected_path、impact.impact_path、trace.call_path 或 graph.call_edges / graph.edges(label=calls) 的真实字段。\n"
            "- 关联约束：当 root_cause_service/root_cause_api 不在 trace.call_path 中，不得写“调用链断裂于某服务”，应写“根因接口由 trace/RPC 异常候选推断，与入口请求存在诊断关联”。\n"
            "- 业务影响约束：业务功能影响仅可引用结构化结果；若证据不足，必须写“暂无法确认”。\n"
            f"- 可观测业务影响约束：必须在【影响面分析】中单独输出“可观测业务影响：{business_impact_report_line}”的等价内容；只能引用 business_impact 中的 affected_order_count、failed_transaction_count、affected_user_count、estimated_revenue_impact 和 evidence_links；字段为 unknown 时必须保留 unknown，不得用请求数、错误数或平均客单价替代。必须说明业务影响来自 trace/log/metric 与 root cause/service map 的关联证据。\n"
            "- 失败交易表述约束：当 business_impact.confidence 不是 high，或 failed_transaction_count_estimated=true 时，failed_transaction_count 只能写成“失败交易信号/可观测证据推导值”，不得写成“单笔交易失败”“导致 N 笔交易失败”“确认 N 笔交易失败”。\n"
            "- 用户影响约束：无真实用户/订单/会话数据时，必须写“当前未接入真实用户群/订单/会话数据，无法确认具体用户群影响”。\n"
            "- 规模约束：无真实 UV/PV/QPS/订单量/失败交易数/工单量时，必须写“暂不估算具体影响规模”。\n"
            "- 探测约束：当缺少实例健康/端口探测字段时，必须明确写“当前未接入实例健康探测，无法判断实例心跳状态”和“当前未接入端口探测，无法判断端口监听状态”。\n"
            "- 禁写项：无证据时不得写完全阻塞、所有用户、错误率飙升、错误率 100%、实例无心跳、端口监听异常、防火墙异常、未配置熔断、服务崩溃、无有效错误处理机制、资源耗尽迹象。\n"
            "- 影响面约束：只能引用 impact 中的 affected_services、affected_apis、affected_business、impact_scale，不得扩展未给出的链路。\n"
            "- 措施约束：处置内容只能写“建议排查”，不得写成已确认事实。"
        )

        return f"""你是一名可观测性智能诊断专家。根据以下结构化诊断结果，生成一份专业的故障诊断报告。

## 诊断数据

时间：{ctx_time}
接口：{api}
现象：{symptom}
根因服务：{rc.get("root_cause_service")}
根因接口：{rc.get("root_cause_api")}
根因类型：{rc.get("root_cause_type")}
异常类型：{rc.get("exception_type")}
根因置信度：{confidence_value}
Trace 证据：{trace.get("summary", "")}
Log 证据：{log.get("summary", "")}
Metric 证据：{metric.get("conclusion", "未发现资源异常")}
RED Metrics 证据：{red_prompt_line}
Service Map 调用边：{service_map_prompt_line}
Service Map 传播链路服务：{propagation_services}
可观测业务影响：{business_impact_prompt_line}
可观测业务影响报告行：{business_impact_report_line}
影响服务：{", ".join(impact.get("affected_services", []))}
影响接口：{", ".join(impact.get("affected_apis", []))}
业务能力影响：{", ".join(c["name"] for c in impact.get("affected_capabilities", [])) or "未覆盖"}
业务流程影响：{", ".join(p["name"] for p in impact.get("affected_processes", [])) or "未覆盖"}
前端页面影响：{", ".join(p["name"] for p in impact.get("affected_pages", [])) or "未覆盖"}
用户群影响：{", ".join(u["name"] for u in impact.get("affected_user_groups", [])) or "未覆盖"}
影响规模：{impact.get("impact_scale", "unavailable")}（当前测试数据未接入真实业务指标，不得输出具体用户数、高峰占比等量化结论）
报告约束：{report_guardrails}

## 要求

先遵守以下硬约束：
{guardrails_text}

请严格按照以下9节格式输出，不要添加多余内容：

【故障结论】
时间范围：...
核心问题：...
根本原因：...
影响范围：...

【异常现象】
...

【根因定位】
根因服务：...
根因接口：...
根因类型：...
异常类型：...
分析：...

【证据链分析】
Trace 证据：...
Log 证据：...
Metric 证据：...
MModel 本体证据：...

【实例与资源状态】
...

【影响面分析】
影响路径：...（只能来自 impact.affected_path / impact.impact_path / trace.call_path / graph.calls）
影响接口：...（只能来自 impact.affected_apis 或 root_cause_api）
业务功能影响：仅可引用结构化结果；若证据不足，必须写“暂无法确认”
可观测业务影响：必须显式输出可观测业务影响报告行；unknown 保持 unknown；中低置信失败交易只写“失败交易信号/推导值”
用户群影响：若无真实用户数据，必须写“当前未接入真实用户群/订单/会话数据，无法确认具体用户群影响”
影响规模：若无真实 UV/PV/QPS/订单量/失败交易数/工单量，必须写“暂不估算具体影响规模”
可信度说明：仅引用结构化证据可支持的范围，不扩展未给出的结论。

【处置建议】
紧急措施：
- ...
根本修复建议：
- ...

【长期优化建议】
- ...

【诊断依据与可信度】
（一段话总结本次故障根因、传播路径和改进方向）"""

    def _build_undetermined_report_prompt(self, context: dict[str, Any]) -> str:
        rc = context.get("root_cause", {})
        trace = context.get("trace", {})
        log = context.get("log", {})
        metric = context.get("metric", {})
        api = context.get("api", "/unknown")
        ctx_time = context.get("time", "（未知时间）")
        symptom = context.get("symptom", "故障")
        consistency = context.get("evidence_consistency", {}) or {}

        conflict_lines = []
        for c in consistency.get("conflicts", []):
            conflict_lines.append(
                f"- 字段[{c.get('field', '')}]：{c.get('source_a', '')}={c.get('source_a_value', '')}；"
                f"{c.get('source_b', '')}={c.get('source_b_value', '')}"
            )
        conflict_text = "\n".join(conflict_lines) if conflict_lines else "- 存在证据冲突（详细字段待核查）"

        return f"""你是一名可观测性智能诊断专家。当前案例已判定为“根因待确认”（is_confirmed=false）。

请基于以下结构化数据，输出“根因待确认”报告：

时间：{ctx_time}
接口：{api}
现象：{symptom}
候选根因服务：{rc.get("root_cause_service", "")}
候选根因接口：{rc.get("root_cause_api", "")}
候选根因类型：{rc.get("root_cause_type", "")}
候选异常类型：{rc.get("exception_type", "")}
候选置信度：{rc.get("confidence", "")}
traceId：{trace.get("trace_id", "")}
Trace 摘要：{trace.get("summary", "")}
Log 摘要：{log.get("summary", "")}
Metric 结论：{metric.get("conclusion", "")}
证据冲突：
{conflict_text}

要求：
1. 格式需参考已确认根因报告风格，使用清晰分节标题输出。
2. 必须包含以下分节，且标题必须与已确认根因报告完全一致：
    【故障结论】、【异常现象】、【根因定位】、【证据链分析】、【实例与资源状态】、【影响面分析】、【处置建议】、【长期优化建议】、【诊断依据与可信度】。
3. 明确写出“根因未确认/待确认”，不要写成已确认。
4. 输出候选根因与冲突点，并给出下一步人工核查建议。
5. 不输出未经证据支持的具体参数结论，不编造影响范围。
6. 【重要】严格遵循纯文本格式，不要使用任何 Markdown 格式符号（如 **, ##, >, ·, ›, 反引号等）。
   - 用"- "代替列表符号
   - 用"："进行字段标识（不使用加粗）
   - 用换行和缩进处理嵌套内容（不使用引用块 >）
   - 用标准分节标题【】，不使用 ## 或其他符号"""

    def _build_prompt_by_context(self, context: dict[str, Any]) -> str:
        rc = context.get("root_cause", {}) or {}
        if not rc.get("is_confirmed", True):
            return self._build_undetermined_report_prompt(context)
        return self._build_report_prompt(context)

    # Keep _build_prompt as alias for backward compat (generate_explanation uses it)
    def _build_prompt(self, context: dict[str, Any]) -> str:
        return self._build_prompt_by_context(context)

    def generate_explanation(self, context: dict[str, Any]) -> str:
        try:
            import urllib.request
            import json as _json

            prompt = self._build_prompt(context)
            payload = _json.dumps({
                "model": self._model,
                "messages": [
                    {"role": "system", "content": "你是一名可观测性智能诊断专家，请用中文输出专业诊断报告。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 1024,
            }).encode("utf-8")

            last_error: Exception | None = None
            for attempt in range(max(1, self._max_retries)):
                try:
                    logger.info(
                        "[LLM][generate_explanation] attempt=%d url=%s/chat/completions model=%s",
                        attempt, self._base_url, self._model,
                    )
                    req = urllib.request.Request(
                        f"{self._base_url}/chat/completions",
                        data=payload,
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {self._api_key}",
                        },
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=self._non_stream_timeout) as resp:
                        result = _json.loads(resp.read().decode("utf-8"))
                    content = result["choices"][0]["message"]["content"].strip()
                    logger.info("[LLM][generate_explanation] success len=%d", len(content))
                    return content
                except Exception as e:
                    last_error = e
                    logger.warning(
                        "[LLM][generate_explanation] attempt=%d failed: %s: %s",
                        attempt, type(e).__name__, e,
                    )

            # All retries exhausted → rule-based fallback
            self._log_fallback("generate_explanation", "all_retries_exhausted",
                               last_error or Exception("unknown"), "rule_based")
            fallback = self._rule_based_fallback.generate_explanation(context)
            return (
                f"{fallback}\n\n"
                f"（⚠ LLM 调用失败（已重试 {self._max_retries} 次），已降级为规则模板报告。"
                f"错误：{last_error}）"
            )

        except Exception as e:
            self._log_fallback("generate_explanation", "unexpected", e, "rule_based")
            fallback = self._rule_based_fallback.generate_explanation(context)
            return f"{fallback}\n\n（⚠ LLM 调用异常，已降级为规则模板报告。错误：{e}）"

    def stream_report(self, context: dict[str, Any]) -> Iterator[str]:
        """Stream the diagnosis report via SSE.
        Fallback order: LLM stream → LLM non-stream → rule-based report.
        Mock fallback only if self._allow_mock_fallback is True.
        """
        import urllib.request
        import json as _json
        import time as _t

        if not self._enable_stream:
            logger.info("[LLM][stream_report] streaming disabled by config, using non-stream")
            yield from self._stream_via_nonstream(context)
            return

        prompt = self._build_prompt_by_context(context)
        payload = _json.dumps({
            "model": self._model,
            "messages": [
                {"role": "system", "content": "你是一名可观测性智能诊断专家，请用中文输出专业诊断报告。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 2048,
            "stream": True,
        }).encode("utf-8")

        logger.info("[LLM][stream_report] start streaming: url=%s model=%s timeout=%ds",
                    self._base_url, self._model, self._stream_timeout)
        stream_ok = False
        try:
            req = urllib.request.Request(
                f"{self._base_url}/chat/completions",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._api_key}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self._stream_timeout) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8").strip()
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        stream_ok = True
                        break
                    try:
                        chunk = _json.loads(data_str)
                        delta = chunk["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except Exception:
                        continue
            if stream_ok:
                logger.info("[LLM][stream_report] streaming completed successfully")
                return
            # Received all data but no [DONE] — treat as partial success (stream_ok still used below)
            logger.warning("[LLM][stream_report] stream ended without [DONE] token")
            return
        except Exception as e:
            self._log_fallback("stream_report", "stream_failed", e, "non_stream")
            logger.info("[LLM][stream_report] falling back to non-stream LLM")

        # Fallback: non-stream LLM
        yield from self._stream_via_nonstream(context)

    def _stream_via_nonstream(self, context: dict[str, Any]) -> Iterator[str]:
        """Fallback: call LLM non-streaming, yield text. Falls back to rule-based on failure."""
        import urllib.request
        import json as _json

        prompt = self._build_prompt_by_context(context)
        last_error: Exception | None = None
        for attempt in range(max(1, self._max_retries)):
            try:
                payload = _json.dumps({
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": "你是一名可观测性智能诊断专家，请用中文输出专业诊断报告。"},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 2048,
                }).encode("utf-8")
                req = urllib.request.Request(
                    f"{self._base_url}/chat/completions",
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self._api_key}",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=self._non_stream_timeout) as resp:
                    result = _json.loads(resp.read().decode("utf-8"))
                text = result["choices"][0]["message"]["content"].strip()
                logger.info("[LLM][_stream_via_nonstream] non-stream success len=%d attempt=%d", len(text), attempt)
                yield text
                return
            except Exception as e:
                last_error = e
                logger.warning("[LLM][_stream_via_nonstream] attempt=%d failed: %s", attempt, e)

        # Both stream and non-stream failed → rule-based report
        self._log_fallback("_stream_via_nonstream", "all_retries_exhausted",
                           last_error or Exception("unknown"), "rule_based")
        rc = context.get("root_cause", {}) or {}
        fallback_report = (
            self._rule_based_fallback.generate_undetermined_report(context)
            if not rc.get("is_confirmed", True)
            else self._rule_based_fallback.generate_explanation(context)
        )
        warn_note = (
            f"\n\n（⚠ 真实 LLM 调用全部失败（stream + non-stream，各重试 {self._max_retries} 次）"
            f"，已降级为规则模板报告。最后错误：{last_error}）"
        )
        yield fallback_report + warn_note

    def generate_text(self, prompt: str, system: str = "你是一名可观测性智能诊断专家，请用中文回答。") -> str:
        """Non-streaming single-turn completion. Used for plan/decision generation."""
        import urllib.request
        import json as _json
        last_error: Exception | None = None
        for attempt in range(max(1, self._max_retries)):
            try:
                payload = _json.dumps({
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 512,
                }).encode("utf-8")
                req = urllib.request.Request(
                    f"{self._base_url}/chat/completions",
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self._api_key}",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=self._non_stream_timeout) as resp:
                    result = _json.loads(resp.read().decode("utf-8"))
                content = result["choices"][0]["message"]["content"].strip()
                logger.info("[LLM][generate_text] success len=%d attempt=%d", len(content), attempt)
                return content
            except Exception as e:
                last_error = e
                logger.warning("[LLM][generate_text] attempt=%d failed: %s: %s",
                               attempt, type(e).__name__, e)
        self._log_fallback("generate_text", "all_retries_exhausted",
                           last_error or Exception("unknown"), "empty_string")
        return ""

    def stream_text(self, prompt: str, system: str = "你是一名可观测性智能诊断专家，请用中文回答。") -> Iterator[str]:
        """
        Stream text via LLM. Fallback order:
          1. LLM stream
          2. LLM non-stream (simulated char-by-char)
          3. Rule-based mock (only if allow_mock_fallback=True, else empty)
        """
        import urllib.request
        import json as _json

        if not self._enable_stream:
            # Config says no stream: use non-stream and yield whole text
            text = self.generate_text(prompt, system)
            if text:
                yield text
            return

        payload = _json.dumps({
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 512,
            "stream": True,
        }).encode("utf-8")

        logger.info("[LLM][stream_text] start: url=%s model=%s timeout=%ds",
                    self._base_url, self._model, self._stream_timeout)
        stream_error: Exception | None = None
        try:
            req = urllib.request.Request(
                f"{self._base_url}/chat/completions",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._api_key}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self._stream_timeout) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8").strip()
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = _json.loads(data_str)
                        delta = chunk["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except Exception:
                        continue
            logger.info("[LLM][stream_text] stream completed successfully")
            return
        except Exception as e:
            stream_error = e
            self._log_fallback("stream_text", "stream_failed", e, "non_stream")

        # Fallback: non-stream
        logger.info("[LLM][stream_text] falling back to non-stream")
        last_error: Exception | None = stream_error
        for attempt in range(max(1, self._max_retries)):
            try:
                fallback_payload = _json.dumps({
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 512,
                }).encode("utf-8")
                req2 = urllib.request.Request(
                    f"{self._base_url}/chat/completions",
                    data=fallback_payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self._api_key}",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req2, timeout=self._non_stream_timeout) as resp2:
                    result = _json.loads(resp2.read().decode("utf-8"))
                text = result["choices"][0]["message"]["content"].strip()
                logger.info("[LLM][stream_text] non-stream fallback success len=%d attempt=%d", len(text), attempt)
                yield text
                return
            except Exception as e2:
                last_error = e2
                logger.warning("[LLM][stream_text] non-stream attempt=%d failed: %s", attempt, e2)

        # Both failed
        self._log_fallback("stream_text", "all_fallbacks_exhausted",
                           last_error or Exception("unknown"), "rule_based" if self._allow_mock_fallback else "empty")
        if self._allow_mock_fallback:
            logger.warning("[LLM][stream_text] using Mock (allow_mock_fallback=True)")
            yield from self._rule_based_fallback.stream_text(prompt, system)
        else:
            logger.warning("[LLM][stream_text] all fallbacks exhausted, allow_mock_fallback=False — yielding empty")
            # yield nothing; orchestrator has its own text fallback


# ---------------------------------------------------------------------------
# Factory — auto-select provider from environment / .env file via LlmConfig
# ---------------------------------------------------------------------------

def _load_dotenv(dotenv_path: str) -> dict[str, str]:
    """Minimal .env loader (no external dependency). Kept for backward compatibility."""
    env: dict[str, str] = {}
    if not os.path.isfile(dotenv_path):
        return env
    with open(dotenv_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def get_llm_provider() -> LLMProvider:
    """
    Factory function. Reads backend/.env via LlmConfig and returns the appropriate provider.

    Priority:
      1. Environment variables (already set in process)
      2. backend/.env file
      3. Fallback: MockLLMProvider (rule-based, always safe)

    Fallback order for OpenAICompatibleProvider:
      stream → non-stream → rule-based report → Mock (only if LLM_ALLOW_MOCK_FALLBACK=true)
    """
    try:
        cfg = _get_llm_config()
    except Exception as e:
        logger.warning("[LLM][get_llm_provider] failed to load LlmConfig: %s — using MockLLMProvider", e)
        return MockLLMProvider()

    if cfg.provider == "openai":
        if cfg.api_key:
            logger.info(
                "[LLM] using OpenAICompatibleProvider: base_url=%s model=%s "
                "enable_stream=%s stream_timeout=%ds non_stream_timeout=%ds "
                "max_retries=%d allow_mock_fallback=%s",
                cfg.base_url, cfg.model,
                cfg.enable_stream, cfg.stream_timeout, cfg.non_stream_timeout,
                cfg.max_retries, cfg.allow_mock_fallback,
            )
            return OpenAICompatibleProvider(
                base_url=cfg.base_url,
                api_key=cfg.api_key,
                model=cfg.model,
                enable_stream=cfg.enable_stream,
                stream_timeout=cfg.stream_timeout,
                non_stream_timeout=cfg.non_stream_timeout,
                max_retries=cfg.max_retries,
                allow_mock_fallback=cfg.allow_mock_fallback,
            )
        else:
            logger.warning(
                "[LLM] LLM_PROVIDER=openai but LLM_API_KEY not set — "
                "falling back to rule-based MockLLMProvider"
            )

    logger.info("[LLM] using MockLLMProvider (rule-based; LLM_PROVIDER=%s)", cfg.provider)
    return MockLLMProvider()
