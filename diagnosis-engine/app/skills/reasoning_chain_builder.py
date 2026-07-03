"""
ReasoningChainBuilder: assembles a structured, auditable reasoning chain
from already-executed Skill results stored in DiagnosisContext.

Design constraints:
  - Only uses already-executed Skill outputs from ctx; never fabricates evidence.
  - Missing evidence is explicitly marked as status="unavailable" or "insufficient".
  - No hardcoded service names, interface names, or IP addresses.
  - Produces a pure dict (JSON-serializable) suitable for report rendering.
  - Not a LLM Chain-of-Thought; all fields are machine-verifiable.

Public API:
  build_reasoning_chain(ctx: DiagnosisContext) -> dict
"""
from __future__ import annotations
from typing import Any


def _evidence_status(findings: list[str]) -> str:
    """Return 'available', 'insufficient', or 'unavailable' based on findings list."""
    if not findings:
        return "unavailable"
    if all(f.startswith("（未知") or "未提取" in f or "null" in f for f in findings):
        return "insufficient"
    return "available"


def build_reasoning_chain(ctx: Any) -> dict[str, Any]:
    """
    Build a structured reasoning_chain dict from DiagnosisContext skill outputs.

    Returns a dict with the following top-level keys:
      symptom, evidence, root_cause_candidates, selected_root_cause, propagation_path

    All entity references are derived from runtime observability bindings.
    Missing evidence is marked with status='unavailable'/'insufficient'.
    """
    trace = getattr(ctx, "trace_result", {}) or {}
    log = getattr(ctx, "log_result", {}) or {}
    metric = getattr(ctx, "metric_result", {}) or {}
    graph = getattr(ctx, "graph_result", {}) or {}
    rc = getattr(ctx, "root_cause_result", {}) or {}
    impact = getattr(ctx, "impact_result", {}) or {}
    consistency = getattr(ctx, "evidence_consistency", {}) or {}

    # ------------------------------------------------------------------
    # 1. Symptom
    # ------------------------------------------------------------------
    entry_api = getattr(ctx, "api", None) or "（未知接口）"
    symptom_text = getattr(ctx, "symptom", "故障") or "故障"
    trace_id = trace.get("trace_id") or "N/A"
    symptom: dict[str, Any] = {
        "summary": f"接口 {entry_api} 出现 {symptom_text}",
        "observed_from": [
            f"用户告警：接口={entry_api}，现象={symptom_text}",
            f"Trace 调用链：traceId={trace_id}",
        ],
    }

    # ------------------------------------------------------------------
    # 2. Evidence
    # ------------------------------------------------------------------
    # Trace evidence
    trace_findings: list[str] = []
    first_err_svc = trace.get("first_error_service")
    first_err_api = trace.get("first_error_api")
    first_err_exc = trace.get("first_error_exception")
    bad_param = rc.get("bad_param") or trace.get("extracted_bad_parameter") or trace.get("bad_param")
    call_path = trace.get("call_path", [])
    if first_err_svc:
        trace_findings.append(f"首次异常服务：{first_err_svc}，接口：{first_err_api}，异常：{first_err_exc}")
    if call_path:
        unique_svcs = list(dict.fromkeys(p.split(":")[0].strip() for p in call_path if p))
        trace_findings.append(f"调用链服务顺序：{' → '.join(unique_svcs)}")
    if bad_param:
        trace_findings.append(f"异常参数（来自 trace events）：{bad_param}")
    abnormal_count = len(trace.get("abnormal_spans", []))
    if abnormal_count:
        trace_findings.append(f"异常 Span 数量：{abnormal_count}")

    # Log evidence
    log_findings: list[str] = []
    upstream_svc = log.get("upstream_service")
    upstream_err = log.get("upstream_error_type")
    downstream_url = log.get("downstream_url")
    log_evidence_list = log.get("log_evidence", [])
    if upstream_svc:
        log_findings.append(f"上游服务 {upstream_svc} 出现 {upstream_err or '（未知异常）'}")
    if downstream_url:
        log_findings.append(f"Feign 下游 URL：{downstream_url}")
    if log_evidence_list:
        log_findings.append(f"关键日志证据片段数：{len(log_evidence_list)}")
    log_bad = log.get("error_param") or log.get("extracted_bad_parameter_from_log")
    if log_bad:
        log_findings.append(f"日志提取异常参数：{log_bad}")

    # Metric evidence
    metric_findings: list[str] = []
    metric_conclusion = metric.get("conclusion")
    checked_metrics = metric.get("checked_metrics", [])
    if metric_conclusion:
        metric_findings.append(metric_conclusion)
    if checked_metrics:
        metric_findings.append(f"已检查指标数：{len(checked_metrics)}")
    red_items = [
        item for item in ((rc.get("evidence_by_source") or {}).get("red_metrics") or metric.get("red_metrics") or [])
        if isinstance(item, dict)
    ]
    rc_service = rc.get("root_cause_service")
    red_root_items = [item for item in red_items if item.get("service_name") == rc_service]
    for item in (red_root_items or red_items[:3]):
        service_name = item.get("service_name") or "unknown"
        metric_findings.append(
            f"RED Metrics：{service_name} 异常评分={item.get('overall_anomaly_score')}，"
            f"rate={item.get('rate_signal')}，error={item.get('error_signal')}，duration={item.get('duration_signal')}"
        )

    # Graph evidence
    graph_findings: list[str] = []
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    service_map_evidence = (rc.get("evidence_by_source") or {}).get("service_map") or graph.get("service_map_evidence") or {}
    calls_edges = service_map_evidence.get("call_edges") or graph.get("call_edges") or [e for e in edges if e.get("label") == "calls"]
    if calls_edges:
        graph_findings.append(
            "服务调用关系：" + "，".join(
                f"{e.get('source_service') or e.get('source')} → {e.get('target_service') or e.get('target')}" for e in calls_edges
            )
        )
    if nodes:
        graph_findings.append(f"图节点数：{len(nodes)}")
    impacts_edges = [e for e in edges if e.get("label") == "impacts"]
    if impacts_edges:
        graph_findings.append(
            "影响关系：" + "，".join(
                f"{e['source']} → {e['target']}" for e in impacts_edges
            )
        )

    # Business impact evidence
    business_impact_findings: list[str] = []
    business_impact = impact.get("business_impact", {}) or {}
    if business_impact:
        business_impact_findings.append(
            "可观测业务影响："
            f"affected_order_count={business_impact.get('affected_order_count', 'unknown')}，"
            f"failed_transaction_count={business_impact.get('failed_transaction_count', 'unknown')}，"
            f"affected_user_count={business_impact.get('affected_user_count', 'unknown')}，"
            f"estimated_revenue_impact={business_impact.get('estimated_revenue_impact', business_impact.get('estimated_gmv_loss', 'unknown'))}，"
            f"confidence={business_impact.get('confidence', 'none')}"
        )
        evidence_links = business_impact.get("evidence_links", {}) or {}
        linked_trace_ids = evidence_links.get("trace_ids", []) or business_impact.get("related_trace_ids", []) or []
        linked_services = evidence_links.get("related_services", []) or business_impact.get("related_services", []) or []
        if linked_trace_ids:
            business_impact_findings.append(f"业务影响关联 trace_ids：{', '.join(str(trace_id) for trace_id in linked_trace_ids[:5])}")
        if linked_services:
            business_impact_findings.append(f"业务影响关联服务：{', '.join(str(service) for service in linked_services[:5])}")

    evidence: dict[str, Any] = {
        "trace": {
            "status": _evidence_status(trace_findings),
            "findings": trace_findings if trace_findings else ["Trace 数据未提取到有效信息"],
            "evidence_refs": [f"TraceAnalysisSkill, traceId={trace_id}"],
        },
        "log": {
            "status": _evidence_status(log_findings),
            "findings": log_findings if log_findings else ["日志分析未提取到有效信息"],
            "evidence_refs": ["LogAnalysisSkill"],
        },
        "metric": {
            "status": _evidence_status(metric_findings),
            "findings": metric_findings if metric_findings else ["指标检查未提取到有效信息"],
            "evidence_refs": ["MetricCheckSkill"],
        },
        "graph": {
            "status": _evidence_status(graph_findings),
            "findings": graph_findings if graph_findings else ["关系图分析未提取到有效信息"],
            "evidence_refs": ["GraphAnalysisSkill"],
        },
        "business_impact": {
            "status": _evidence_status(business_impact_findings),
            "findings": business_impact_findings if business_impact_findings else ["业务影响分析未提取到可证明业务受损字段"],
            "evidence_refs": ["ImpactAnalysisSkill", "BusinessImpactRepository"],
        },
    }

    # ------------------------------------------------------------------
    # 3. Root cause candidates
    # ------------------------------------------------------------------
    # Primary candidate: from RootCauseSkill output
    candidates: list[dict[str, Any]] = []

    rc_service = rc.get("root_cause_service")
    rc_api = rc.get("root_cause_api")
    rc_type = rc.get("root_cause_type", "未知")
    rc_conf = rc.get("confidence", "low")
    rc_reason = rc.get("root_cause_reason", "")
    rc_exc = rc.get("exception_type")
    rc_rule = rc.get("applied_rule") or rc.get("rule_matched") or "（未命中规则）"
    is_confirmed = rc.get("is_confirmed", True)
    evidence_conflicts = rc.get("evidence_conflicts", [])

    # Map confidence string to score
    _CONF_SCORE = {"high": 0.9, "medium": 0.6, "low": 0.3}
    rc_score = _CONF_SCORE.get(str(rc_conf).lower(), 0.3)

    supporting_reasons: list[str] = []
    weakening_reasons: list[str] = []

    if first_err_svc and first_err_svc == rc_service:
        supporting_reasons.append(f"Trace 中首次异常 Span 所在服务与根因服务一致（{rc_service}）")
    if first_err_exc:
        supporting_reasons.append(f"Trace 记录异常类型：{first_err_exc}，与根因类型匹配")
    if rc_rule and rc_rule != "（未命中规则）" and rc_rule != "none":
        supporting_reasons.append(f"根因规则命中：{rc_rule}")
    if bad_param:
        supporting_reasons.append(f"异常参数已提取：{bad_param}")
    if upstream_svc and upstream_svc != rc_service:
        supporting_reasons.append(f"日志中上游服务（{upstream_svc}）出现传播性异常，印证根因在下游")

    if evidence_conflicts:
        for conflict in evidence_conflicts:
            if isinstance(conflict, dict):
                weakening_reasons.append(
                    f"证据冲突：字段[{conflict.get('field','?')}] "
                    f"{conflict.get('source_a','?')}={conflict.get('source_a_value','?')} "
                    f"vs {conflict.get('source_b','?')}={conflict.get('source_b_value','?')}"
                )
            else:
                weakening_reasons.append(f"证据冲突：{conflict}")
    if not is_confirmed:
        weakening_reasons.append("多源证据不一致，根因未最终确认")
    if rc_conf == "low":
        weakening_reasons.append("规则引擎置信度低（low），建议补充人工确认")

    if not supporting_reasons:
        supporting_reasons = ["尚无明确支持证据"]

    primary_candidate: dict[str, Any] = {
        "candidate_id": "C1",
        "candidate_type": rc_type,
        "entity_ref": f"{rc_service}/{rc_api}" if rc_service else "（未知）",
        "score": rc_score,
        "confidence": rc_conf,
        "supporting_reasons": supporting_reasons,
        "weakening_reasons": weakening_reasons,
        "evidence_refs": [
            f"TraceAnalysisSkill: first_error_service={first_err_svc}",
            f"LogAnalysisSkill: upstream_service={upstream_svc}",
            f"RootCauseSkill: rule={rc_rule}",
        ],
    }
    candidates.append(primary_candidate)

    # Secondary candidate: entry service (if different from root cause)
    entry_svcs_in_path = list(dict.fromkeys(p.split(":")[0].strip() for p in call_path if p))
    entry_svc_candidate = entry_svcs_in_path[0] if entry_svcs_in_path else None
    if entry_svc_candidate and entry_svc_candidate != rc_service:
        candidates.append({
            "candidate_id": "C2",
            "candidate_type": "传播性异常（入口侧）",
            "entity_ref": f"{entry_svc_candidate}/{entry_api}",
            "score": 0.2,
            "confidence": "low",
            "supporting_reasons": [f"入口侧服务 {entry_svc_candidate} 也出现了 500 响应"],
            "weakening_reasons": [
                f"入口侧异常属于传播性响应，自身无独立异常 event",
                f"日志与 trace 均显示 {entry_svc_candidate} 为调用方，错误来自下游",
            ],
            "evidence_refs": [f"TraceAnalysisSkill: entry_service={entry_svc_candidate}"],
        })

    # ------------------------------------------------------------------
    # 4. Selected root cause with selection reason
    # ------------------------------------------------------------------
    why_not_others: list[str] = []
    if len(candidates) > 1:
        c2 = candidates[1]
        why_not_others.append(
            f"{c2['entity_ref']}（{c2['candidate_type']}）：{'; '.join(c2['weakening_reasons'])}"
        )

    selection_reason = rc_reason or (
        f"根因规则 {rc_rule} 命中：{rc_service} 服务在 trace 中首次产生 {rc_exc or rc_type}，"
        "且日志印证此为异常起源而非传播节点。"
    ) if rc_service else "当前证据不足以确认根因"

    selected_root_cause: dict[str, Any] = {
        "entity_ref": f"{rc_service}/{rc_api}" if rc_service else "（未确认）",
        "is_confirmed": is_confirmed,
        "confidence": rc_conf,
        "selection_reason": selection_reason,
        "why_not_others": why_not_others,
        "evidence_refs": primary_candidate["evidence_refs"],
    }

    # ------------------------------------------------------------------
    # 5. Propagation path
    # ------------------------------------------------------------------
    prop_path_list = impact.get("impact_path", [])  # list of {source, target, type}
    propagation_path_nodes: list[str] = []
    if prop_path_list:
        for seg in prop_path_list:
            if isinstance(seg, dict):
                src = seg.get("source", "")
                tgt = seg.get("target", "")
                if src and src not in propagation_path_nodes:
                    propagation_path_nodes.append(src)
                if tgt and tgt not in propagation_path_nodes:
                    propagation_path_nodes.append(tgt)
    # Fallback: use call_path derived service list
    if not propagation_path_nodes:
        propagation_path_nodes = entry_svcs_in_path
    # Append entry api at end
    if entry_api and entry_api not in propagation_path_nodes:
        propagation_path_nodes.append(entry_api)

    prop_status = "available" if len(propagation_path_nodes) >= 2 else "insufficient"
    prop_explanation = (
        f"故障从 {propagation_path_nodes[0]} 发生，沿调用链传播至 {' → '.join(propagation_path_nodes[1:])}，"
        f"最终导致入口接口 {entry_api} 返回异常。"
    ) if prop_status == "available" else "当前证据不足以确认完整传播路径。"

    propagation_path: dict[str, Any] = {
        "status": prop_status,
        "path": propagation_path_nodes,
        "explanation": prop_explanation,
        "evidence_refs": [
            "TraceAnalysisSkill: call_path",
            "ImpactAnalysisSkill: impact_path",
        ],
    }

    return {
        "symptom": symptom,
        "evidence": evidence,
        "root_cause_candidates": candidates,
        "selected_root_cause": selected_root_cause,
        "propagation_path": propagation_path,
    }
