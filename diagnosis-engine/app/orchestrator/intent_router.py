"""Intent routing and focused evidence execution for multi-turn diagnosis."""
from __future__ import annotations

import re
import time as _time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.models.diagnosis import CallGraph, DiagnosisMessage, DiagnosisResponse, DiagnosisSummary, SkillResult
from app.repositories import (
    get_business_impact_repository,
    get_log_repository,
    get_metric_repository,
    get_service_map_repository,
    get_trace_repository,
)
from app.session import (
    DiagnosisSession,
    DiagnosisSessionStore,
    SessionFocus,
    memory_summary,
    update_session_from_observability_query,
)

INTENTS = {
    "initial_diagnosis",
    "followup_inspect_logs",
    "followup_inspect_metrics",
    "followup_inspect_traces",
    "followup_inspect_service_map",
    "followup_inspect_business_impact",
    "followup_explain_root_cause",
    "switch_focus",
    "summarize_current_case",
    "observability_query",
    "entity_list",
    "clarify",
}

_TOOL_KEY_BY_SKILL = {
    "AlertContextSkill": "set_time_range",
    "TraceAnalysisSkill": "analyze_trace",
    "EntityBindingSkill": "bind_entities",
    "LogAnalysisSkill": "analyze_log",
    "MetricCheckSkill": "check_metrics",
    "GraphAnalysisSkill": "analyze_graph",
    "RootCauseSkill": "infer_root_cause",
    "ImpactAnalysisSkill": "analyze_impact",
    "ReportSkill": "generate_report",
    "RootCauseExplanation": "explain_root_cause",
    "ContextSwitch": "switch_focus",
    "CaseSummary": "summarize_current_case",
    "ObservabilityQuery": "observability_query",
    "EntityList": "entity_list",
}


def skill_result_to_tool_key(result: SkillResult) -> str:
    return _TOOL_KEY_BY_SKILL.get(result.skill_name, result.skill_name)


@dataclass
class IntentDecision:
    intent: str
    reason: str
    needs_clarification: bool = False
    clarification_question: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "reason": self.reason,
            "needs_clarification": self.needs_clarification,
            "clarification_question": self.clarification_question,
        }


@dataclass
class IntentTurnResult:
    response: DiagnosisResponse
    intent: str
    skill_results: list[SkillResult] = field(default_factory=list)
    answer: str = ""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_initial_diagnosis_intent(intent: str) -> bool:
    return intent == "initial_diagnosis"


def classify_intent(
    *,
    message: str,
    api: str,
    time: str,
    symptom: str,
    session: DiagnosisSession,
    resolved_context: dict[str, Any],
    mode: str | None = None,
) -> IntentDecision:
    text = (message or "").strip()
    lowered = text.lower()
    request_mode = _normalize_mode(mode)
    has_session_focus = bool(session.current_focus.service_name)
    has_explicit_alert = bool((api and api != "/unknown") and symptom and ("/" in api or "api" in lowered or "接口" in text))
    diagnosis_requested = _explicitly_requests_diagnosis(text)
    effective_has_explicit_alert = has_explicit_alert
    if request_mode == "observability" and not diagnosis_requested:
        effective_has_explicit_alert = False

    if resolved_context.get("needs_clarification"):
        return IntentDecision(
            intent="clarify",
            reason="上下文指代无法解析",
            needs_clarification=True,
            clarification_question=resolved_context.get("clarification_question", "请指定要查看的服务或证据对象。"),
        )

    # Entity listing (e.g. "有哪些服务？") — must be checked BEFORE observability_query
    if _looks_like_entity_list(text):
        return IntentDecision("entity_list", "用户请求列出实体/服务，非异常查询")

    if _looks_like_observability_query(text, has_explicit_alert=effective_has_explicit_alert):
        return IntentDecision("observability_query", "自然语言观测查询，不进入完整根因流程")

    if _contains_any(text, ("日志", "log", "错误日志")):
        if has_session_focus or _has_service_reference(text, session) or _mentions_rank_reference(text):
            return IntentDecision("followup_inspect_logs", "用户请求查看当前对象日志")
        return IntentDecision("clarify", "日志追问缺少服务焦点", True, "要查看哪个服务的日志？")

    if _contains_any(lowered, ("metric", "metrics", "red", "p95", "p99", "延迟", "错误率", "指标")):
        if has_session_focus or _has_service_reference(text, session) or _mentions_rank_reference(text):
            return IntentDecision("followup_inspect_metrics", "用户请求查看当前对象指标")
        if not effective_has_explicit_alert:
            return IntentDecision("observability_query", "指标排行/查询类问题")

    if _contains_any(lowered, ("trace", "调用链")):
        if has_session_focus or _has_service_reference(text, session) or _mentions_rank_reference(text):
            return IntentDecision("followup_inspect_traces", "用户请求查看 trace 证据")
        return IntentDecision("observability_query", "trace 查询类问题")

    if _contains_any(text, ("下游", "上游", "拓扑", "传播", "调用拓扑", "受害者")):
        if has_session_focus or _has_service_reference(text, session):
            return IntentDecision("followup_inspect_service_map", "用户请求查看上下游和传播关系")
        return IntentDecision("clarify", "服务拓扑追问缺少服务焦点", True, "要查看哪个服务的上下游？")

    if _contains_any(text, ("多少订单", "影响多少用户", "多少用户", "失败了多少交易", "失败交易", "金额影响", "损失多少金额", "影响了多少订单")):
        if has_session_focus:
            return IntentDecision("followup_inspect_business_impact", "用户请求查看业务影响")
        return IntentDecision("clarify", "业务影响追问缺少当前服务焦点", True, "要查看哪个服务或根因候选的业务影响？")

    if _contains_any(text, ("为什么", "为何", "根因", "证据", "为什么不是")) and (session.root_cause_candidates or session.latest_skill_outputs.get("root_cause")):
        return IntentDecision("followup_explain_root_cause", "用户请求解释根因依据")

    if _contains_any(text, ("总结", "当前证据链", "现在结论", "排障摘要", "结论是什么")):
        return IntentDecision("summarize_current_case", "用户请求总结当前会话")

    if _looks_like_switch_focus(text, session, resolved_context):
        return IntentDecision("switch_focus", "用户明确切换当前关注对象")

    if request_mode == "observability" and not diagnosis_requested:
        return IntentDecision("observability_query", "观测问答模式：按轻量可观测查询处理")

    # Fault-like input with error indicators — always triggers diagnosis in diagnosis mode
    _looks_like_fault = bool(
        _contains_any(lowered, ("http 500", "http 502", "http 503", "error", "fail", "timeout", "500", "502", "503", "504", "异常", "错误", "超时", "失败", "故障"))
    )

    if request_mode == "diagnosis" and (has_explicit_alert or diagnosis_requested or _looks_like_fault):
        return IntentDecision("initial_diagnosis", "故障诊断模式：执行完整根因流程")

    if effective_has_explicit_alert:
        return IntentDecision("initial_diagnosis", "输入包含明确告警诊断上下文")

    if _contains_any(text, ("继续看它", "这个呢", "再查一下", "继续看")):
        return IntentDecision("clarify", "追问过短且无法判断要查的证据类型", True, "你想继续看日志、指标、trace、调用关系还是业务影响？")

    if has_session_focus:
        return IntentDecision("summarize_current_case", "有会话焦点但未指定新证据类型，返回当前摘要")

    return IntentDecision("clarify", "无法确定是告警诊断还是观测查询", True, "请补充要诊断的 api/time/symptom，或说明要查询日志、指标还是 trace。")


def _normalize_mode(mode: str | None) -> str | None:
    if not mode:
        return None
    normalized = mode.strip().lower()
    return normalized if normalized in {"observability", "diagnosis", "storm"} else None


def _explicitly_requests_diagnosis(text: str) -> bool:
    return _contains_any(text, ("诊断", "根因", "定位根因", "分析根因", "故障排查", "排障", "完整链路"))


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    """Check if any token is a substring of text.

    For short ASCII tokens (<=4 chars, e.g. "log", "red", "top", "api"),
    requires word-boundary matching to prevent false positives like
    "log" matching inside "catalog" or "top" matching inside "topology".
    Chinese and longer tokens use simple substring matching.
    """
    lowered = text.lower()
    for token in tokens:
        t = token.lower()
        if t not in lowered:
            continue
        # Short ASCII tokens: require word boundaries (not inside another word)
        if t.isascii() and len(t) <= 4:
            if re.search(r'(?<![a-z])' + re.escape(t) + r'(?![a-z])', lowered):
                return True
        else:
            return True
    return False


def _mentions_rank_reference(text: str) -> bool:
    return any(token in text for token in ("第一名", "第1名", "top1", "Top1", "排名第一"))


def _has_service_reference(text: str, session: DiagnosisSession) -> bool:
    lowered = text.lower()
    for item in session.mentioned_services:
        service = str(item.get("service_name") or "").lower()
        if service and (service in lowered or service.replace("-service", "") in lowered):
            return True
    return False


def _looks_like_observability_query(text: str, *, has_explicit_alert: bool) -> bool:
    lowered = text.lower()
    if has_explicit_alert and not _contains_any(text, ("哪些服务", "最高", "最多", "排行", "top", "列出", "有没有异常", "最近")):
        return False
    ranking_tokens = ("哪些服务", "最多", "最高", "排行", "top", "topn", "过去", "最近", "15分钟", "十五分钟", "列出", "有没有异常")
    observability_tokens = ("异常", "错误率", "错误", "p95", "延迟", "慢请求", "日志", "trace", "服务")
    return _contains_any(text, ranking_tokens) and _contains_any(text, observability_tokens)


def _looks_like_entity_list(text: str) -> bool:
    """Detect entity listing queries (NOT anomaly ranking).

    Matches questions like:
      - "otel-demo 里有哪些服务？"
      - "列出所有服务"
      - "有哪些实体？"
      - "服务列表"
      - "xx里有什么？"

    Distinguishes from observability_query by requiring entity-listing
    tokens WITHOUT anomaly/fault context tokens.
    """
    listing_tokens = (
        "有哪些服务", "有哪些实体", "列出所有服务", "列出所有实体",
        "列出服务", "列出实体", "服务列表", "实体列表",
        "所有服务", "所有实体",
    )
    entity_context_tokens = (
        "里有哪些", "里面有哪些", "里有什么", "里面有什么",
        "有哪些服务", "有哪些实体",
    )
    # Anomaly tokens — if present, it's an observability query, not entity list
    anomaly_tokens = (
        "异常", "错误率", "最高", "最多", "排行", "top", "topn",
        "过去", "最近", "15分钟", "十五分钟", "p95", "p99",
        "延迟", "慢请求", "挂了", "宕机", "不可用", "故障",
    )
    lowered = text.lower()
    has_listing = _contains_any(text, listing_tokens) or _contains_any(text, entity_context_tokens)
    has_anomaly = _contains_any(text, anomaly_tokens)
    return has_listing and not has_anomaly


def _looks_like_switch_focus(text: str, session: DiagnosisSession, resolved_context: dict[str, Any]) -> bool:
    if resolved_context.get("resolved_type") != "service":
        return False
    if _contains_any(text, ("日志", "指标", "trace", "调用链", "下游", "上游", "多少订单", "业务影响", "为什么")):
        return False
    return _contains_any(text, ("那", "再看", "换成", "看看", "看下", "看一下"))


def run_intent_turn(
    *,
    session: DiagnosisSession,
    intent_decision: IntentDecision,
    resolved_context: dict[str, Any],
    user_message: str,
    api: str,
    time: str,
    symptom: str,
    case_id: str | None,
    data_dir: str | None,
    mode: str | None = None,
    session_store: DiagnosisSessionStore | None = None,
) -> IntentTurnResult:
    intent = intent_decision.intent
    query_context = dict(session.query_context or {})
    if not query_context:
        query_context = {"alert_api": api, "alert_time": time, "symptom": symptom}
    focus_service = _resolve_focus_service(session, resolved_context)
    if focus_service:
        query_context["focus_service"] = focus_service
        query_context.setdefault("service", focus_service)
    time_range = query_context.get("time_window")

    if intent == "clarify":
        answer = intent_decision.clarification_question or "请指定要查看的服务或证据类型。"
        return _build_turn(session, intent, resolved_context, [], answer, case_id, user_message, mode=mode, session_store=session_store)

    if intent == "switch_focus":
        if focus_service:
            session.current_focus = SessionFocus(type="service", service_name=focus_service, name=focus_service, confidence="high", reason="用户切换当前关注对象")
        answer = _answer_switch_focus(session, focus_service)
        return _build_turn(session, intent, resolved_context, [], answer, case_id, user_message, mode=mode, session_store=session_store)

    if intent == "summarize_current_case":
        answer = _answer_case_summary(session)
        return _build_turn(session, intent, resolved_context, [], answer, case_id, user_message, mode=mode, session_store=session_store)

    if intent == "followup_explain_root_cause":
        answer = _answer_root_cause_explanation(session, focus_service)
        return _build_turn(session, intent, resolved_context, [], answer, case_id, user_message, mode=mode, session_store=session_store)

    skill_results: list[SkillResult] = []
    answer = ""
    evidence_refs: dict[str, Any] = {}

    if intent == "followup_inspect_logs":
        result = _run_log_query(focus_service, time_range, query_context, data_dir, case_id)
        skill_results.append(result)
        answer = _answer_logs(focus_service, result.output)
        evidence_refs = {"logs": result.output.get("logs", [])[:5], "source": result.output.get("source")}
        session.latest_skill_outputs["log"] = result.output

    elif intent == "followup_inspect_metrics":
        result = _run_metric_query(focus_service, time_range, data_dir, case_id)
        skill_results.append(result)
        answer = _answer_metrics(focus_service, result.output)
        evidence_refs = {"red_metrics": result.output.get("red_metrics", [])[:5], "source": result.output.get("source")}
        session.latest_skill_outputs["metric"] = result.output

    elif intent == "followup_inspect_traces":
        result = _run_trace_query(focus_service, time_range, query_context, data_dir, case_id)
        skill_results.append(result)
        answer = _answer_traces(focus_service, result.output)
        evidence_refs = {"traces": result.output.get("traces", [])[:5], "source": result.output.get("source")}
        session.latest_skill_outputs["trace"] = result.output

    elif intent == "followup_inspect_service_map":
        result = _run_service_map_query(focus_service, time_range, data_dir, case_id)
        skill_results.append(result)
        answer = _answer_service_map(focus_service, result.output)
        evidence_refs = {"service_map": result.output, "source": result.output.get("source")}
        session.latest_skill_outputs["service_map"] = result.output

    elif intent == "followup_inspect_business_impact":
        result = _run_business_impact_query(focus_service, time_range, query_context, data_dir, case_id)
        skill_results.append(result)
        answer = _answer_business_impact(focus_service, result.output)
        evidence_refs = {"business_impact": result.output.get("business_impact", {}), "source": result.output.get("source")}
        session.business_impact_summary = result.output.get("business_impact", {}) or session.business_impact_summary
        session.latest_skill_outputs["business_impact"] = result.output

    elif intent == "observability_query":
        result, ranking = _run_observability_query(user_message, time_range, data_dir, case_id)
        skill_results.append(result)
        answer = _answer_observability_query(ranking, user_message, warnings=result.output.get("warnings"))
        evidence_refs = {"ranking": ranking[:5], "source": result.output.get("source")}
        session = update_session_from_observability_query(
            session,
            user_message=user_message,
            answer=answer,
            results=ranking,
            query_context=query_context,
            store=session_store,
        )
        return _build_turn(session, intent, resolved_context, skill_results, answer, case_id, user_message, evidence_refs, mode=mode, session_store=session_store)

    elif intent == "entity_list":
        result, entities = _run_entity_list(time_range, data_dir, case_id)
        skill_results.append(result)
        answer = _answer_entity_list(entities, user_message)
        evidence_refs = {"entities": entities[:20], "source": result.output.get("source")}
        return _build_turn(session, intent, resolved_context, skill_results, answer, case_id, user_message, evidence_refs, mode=mode, session_store=session_store)

    return _build_turn(session, intent, resolved_context, skill_results, answer, case_id, user_message, evidence_refs, mode=mode, session_store=session_store)


def _build_turn(
    session: DiagnosisSession,
    intent: str,
    resolved_context: dict[str, Any],
    skill_results: list[SkillResult],
    answer: str,
    case_id: str | None,
    user_message: str,
    evidence_refs: dict[str, Any] | None = None,
    *,
    mode: str | None = None,
    session_store: DiagnosisSessionStore | None = None,
) -> IntentTurnResult:
    session.last_user_message = user_message
    session.last_assistant_message = answer
    if intent != "observability_query":
        session.history.append({
            "turn_id": f"intent-{int(_time.time() * 1000)}",
            "intent": intent,
            "user_message": user_message,
            "assistant_message": answer,
            "current_focus": session.current_focus.to_dict(),
            "created_at": utc_now(),
        })
        (session_store.update_session(session) if session_store else None)
    executed_skills = [skill_result_to_tool_key(result) for result in skill_results]
    response = DiagnosisResponse(
        case_id=case_id or session.request_context.get("case_id") or "evaluation-case",
        summary=_summary_from_session(session),
        skills=skill_results,
        call_graph=_empty_call_graph(session),
        evidence_chain=_evidence_chain_from_session(session, evidence_refs or {}),
        final_report=answer,
        messages=[
            DiagnosisMessage(role="user", type="text", content=user_message),
            DiagnosisMessage(role="assistant", type="report", content=answer),
        ],
        session_id=session.session_id,
        mode=_normalize_mode(mode),
        intent=intent,
        executed_skills=executed_skills,
        answer=answer,
        evidence_refs=evidence_refs or {},
        current_focus=session.current_focus.to_dict(),
        resolved_context=resolved_context,
        memory_summary=memory_summary(session),
    )
    return IntentTurnResult(response=response, intent=intent, skill_results=skill_results, answer=answer)


def _resolve_focus_service(session: DiagnosisSession, resolved_context: dict[str, Any]) -> str:
    service = resolved_context.get("service_name") or resolved_context.get("resolved_value")
    if isinstance(service, str) and service:
        return service
    return session.current_focus.service_name or ""


def _skill_result(skill_name: str, tool_name: str, title: str, summary: str, output: dict[str, Any], evidence: list[str], execution_log: list[str]) -> SkillResult:
    now = utc_now()
    return SkillResult(
        skill_name=skill_name,
        tool_name=tool_name,
        title=title,
        status="success",
        summary=summary,
        started_at=now,
        finished_at=now,
        duration_ms=1,
        input=output.get("query", {}),
        output=output,
        evidence=evidence,
        execution_log=execution_log,
        explanation="根据本轮 intent 只查询必要证据，不重新执行完整根因链路。",
    )


def _run_log_query(service: str, time_range: dict[str, Any] | None, query: dict[str, Any], data_dir: str | None, case_id: str | None) -> SkillResult:
    repo = get_log_repository()
    fetch = repo.get_error_logs(service or None, time_range, data_dir=data_dir, case_id=case_id)
    logs = fetch.items[:20]
    evidence = [_format_log(log) for log in logs[:8]] or [f"未查询到 {service or '当前范围'} 的错误日志"]
    output = {"query": {"service": service, "time_range": time_range}, "source": fetch.source, "availability": fetch.availability, "logs": logs, "warnings": fetch.warnings}
    return _skill_result("LogAnalysisSkill", "MModelSkill/analyze_log", "日志分析", f"查询到 {len(logs)} 条关键错误日志。", output, evidence, ["按 intent=followup_inspect_logs 查询错误日志"])


def _run_metric_query(service: str, time_range: dict[str, Any] | None, data_dir: str | None, case_id: str | None) -> SkillResult:
    repo = get_metric_repository()
    fetch = repo.get_red_metrics(service or None, time_range, data_dir=data_dir, case_id=case_id)
    red_metrics = fetch.items[:20]
    evidence = [_format_red(item) for item in red_metrics[:8]] or [f"未查询到 {service or '当前范围'} 的 RED Metrics"]
    output = {"query": {"service": service, "time_range": time_range}, "source": fetch.source, "availability": fetch.availability, "red_metrics": red_metrics, "warnings": fetch.warnings}
    return _skill_result("MetricCheckSkill", "MModelSkill/check_metrics", "指标检查", f"查询到 {len(red_metrics)} 个服务的 RED Metrics。", output, evidence, ["按 intent=followup_inspect_metrics 查询 RED Metrics"])


def _run_trace_query(service: str, time_range: dict[str, Any] | None, query: dict[str, Any], data_dir: str | None, case_id: str | None) -> SkillResult:
    repo = get_trace_repository()
    if service:
        fetch = repo.get_error_spans(service, time_range, data_dir=data_dir, case_id=case_id)
    else:
        fetch = repo.get_traces(query, data_dir=data_dir, case_id=case_id)
    traces = fetch.items[:20]
    evidence = [_format_span(span.get("_source", span)) for span in traces[:8]] or [f"未查询到 {service or '当前范围'} 的异常 trace"]
    output = {"query": {"service": service, "time_range": time_range}, "source": fetch.source, "availability": fetch.availability, "traces": traces, "warnings": fetch.warnings}
    return _skill_result("TraceAnalysisSkill", "MModelSkill/analyze_trace", "Trace 分析", f"查询到 {len(traces)} 条异常 span/trace 证据。", output, evidence, ["按 intent=followup_inspect_traces 查询异常 trace"])


def _run_service_map_query(service: str, time_range: dict[str, Any] | None, data_dir: str | None, case_id: str | None) -> SkillResult:
    repo = get_service_map_repository()
    upstream = repo.get_upstream_services(service, time_range, data_dir=data_dir, case_id=case_id) if service else None
    downstream = repo.get_downstream_services(service, time_range, data_dir=data_dir, case_id=case_id) if service else None
    impacted = repo.get_impacted_services(service, time_range, data_dir=data_dir, case_id=case_id) if service else None
    call_edges = repo.get_call_edges(time_range, data_dir=data_dir, case_id=case_id)
    output = {
        "query": {"service": service, "time_range": time_range},
        "source": call_edges.source,
        "availability": call_edges.availability,
        "upstream": upstream.items[0] if upstream and upstream.items else {"service": service, "upstream_services": []},
        "downstream": downstream.items[0] if downstream and downstream.items else {"service": service, "downstream_services": []},
        "impacted": impacted.items[0] if impacted and impacted.items else {"service": service, "impacted_services": []},
        "call_edges": call_edges.items[:20],
    }
    evidence = [
        f"上游服务：{', '.join(output['upstream'].get('upstream_services', [])) or '暂无'}",
        f"下游服务：{', '.join(output['downstream'].get('downstream_services', [])) or '暂无'}",
        f"可能受影响上游：{', '.join(output['impacted'].get('impacted_services', [])) or '暂无'}",
    ]
    return _skill_result("GraphAnalysisSkill", "MModelSkill/query_graph", "关系图查询", f"已查询 {service or '当前范围'} 的上下游关系。", output, evidence, ["按 intent=followup_inspect_service_map 查询 Service Map"])


def _run_business_impact_query(service: str, time_range: dict[str, Any] | None, query: dict[str, Any], data_dir: str | None, case_id: str | None) -> SkillResult:
    repo = get_business_impact_repository()
    fetch = repo.get_business_impact(service or None, time_range, query=query, data_dir=data_dir, case_id=case_id)
    impact = fetch.items[0] if fetch.items else {}
    output = {"query": {"service": service, "time_range": time_range}, "source": fetch.source, "availability": fetch.availability, "business_impact": impact, "warnings": fetch.warnings}
    evidence = [
        f"affected_order_count={impact.get('affected_order_count', 'unknown')}",
        f"failed_transaction_count={impact.get('failed_transaction_count', 'unknown')}",
        f"affected_user_count={impact.get('affected_user_count', 'unknown')}",
        f"confidence={impact.get('confidence', 'none')}",
    ]
    return _skill_result("ImpactAnalysisSkill", "MModelSkill/analyze_impact", "业务影响分析", f"已查询 {service or '当前范围'} 的可观测业务影响。", output, evidence, ["按 intent=followup_inspect_business_impact 查询业务影响"])


def _run_observability_query(message: str, time_range: dict[str, Any] | None, data_dir: str | None, case_id: str | None) -> tuple[SkillResult, list[dict[str, Any]]]:
    metric_repo = get_metric_repository()
    # Use entity-centered aggregation (OpenSearch native aggregations grouped by
    # otel.service entity key field) instead of client-side sampling.
    red_fetch = metric_repo.get_entity_red_metrics(time_range, data_dir=data_dir, case_id=case_id)
    ranking = []
    for item in red_fetch.items:
        error = item.get("error", {}) or {}
        duration = item.get("duration", {}) or {}
        ranking.append({
            "service_name": item.get("service_name"),
            "entity_type": item.get("entity_type", "otel.service"),
            "request_count": item.get("request_count", 0),
            "overall_anomaly_score": item.get("overall_anomaly_score", 0),
            "error_rate": error.get("error_rate", 0),
            "error_count": error.get("error_count", 0),
            "log_error_count": error.get("log_error_count", 0),
            "p50_duration_ms": duration.get("p50_duration_ms"),
            "p95_duration_ms": duration.get("p95_duration_ms"),
            "p99_duration_ms": duration.get("p99_duration_ms"),
            "evidence_summary": item.get("evidence_summary", []),
            "_entity_source": item.get("_entity_source", ""),
        })
    lowered = message.lower()
    if "p95" in lowered or "延迟" in message or "慢请求" in message:
        ranking.sort(key=lambda item: float(item.get("p95_duration_ms") or 0), reverse=True)
    elif "错误率" in message:
        ranking.sort(key=lambda item: float(item.get("error_rate") or 0), reverse=True)
    else:
        # Default: sort by anomaly_score (entity-centered heuristic), then error_count
        ranking.sort(
            key=lambda item: (
                float(item.get("overall_anomaly_score") or 0),
                float(item.get("error_count") or 0) + float(item.get("log_error_count") or 0),
            ),
            reverse=True,
        )
    ranking = [item for item in ranking if item.get("service_name")][:10]
    output = {
        "query": {"message": message, "time_range": time_range},
        "source": red_fetch.source,
        "availability": red_fetch.availability,
        "ranking": ranking,
        "warnings": red_fetch.warnings,
        "entity_source": "opensearch_aggregation",
    }
    evidence = [_format_ranking_item(i, item) for i, item in enumerate(ranking[:8], start=1)] or ["当前范围未查询到可排名的服务异常信号"]
    result = _skill_result("ObservabilityQuery", "MModelQuery/observability_query", "观测查询", f"返回 {len(ranking)} 个服务的观测异常排行（基于实体聚合查询）。", output, evidence, ["按 intent=observability_query 查询 entity-centered RED 聚合"])
    return result, ranking


def _run_entity_list(time_range: dict[str, Any] | None, data_dir: str | None, case_id: str | None) -> tuple[SkillResult, list[dict[str, Any]]]:
    """List all otel.service entities with basic health info (no anomaly ranking)."""
    metric_repo = get_metric_repository()
    red_fetch = metric_repo.get_entity_red_metrics(time_range, data_dir=data_dir, case_id=case_id)

    entities: list[dict[str, Any]] = []
    for item in red_fetch.items:
        error = item.get("error", {}) or {}
        duration = item.get("duration", {}) or {}
        entities.append({
            "service_name": item.get("service_name"),
            "entity_type": item.get("entity_type", "otel.service"),
            "request_count": item.get("request_count", 0),
            "error_count": error.get("error_count", 0),
            "error_rate": error.get("error_rate", 0),
            "p50_latency_ms": duration.get("p50_duration_ms"),
            "p95_latency_ms": duration.get("p95_duration_ms"),
            "p99_latency_ms": duration.get("p99_duration_ms"),
            "log_error_count": error.get("log_error_count", 0),
            "evidence_summary": item.get("evidence_summary", []),
            "_entity_source": item.get("_entity_source", ""),
        })

    # Sort alphabetically for entity listing (not by anomaly)
    entities.sort(key=lambda e: str(e.get("service_name", "")).lower())
    entities = [e for e in entities if e.get("service_name")][:50]

    output = {
        "query": {"message": "entity_list", "time_range": time_range},
        "source": red_fetch.source,
        "availability": red_fetch.availability,
        "entities": entities,
        "warnings": red_fetch.warnings,
        "total": len(entities),
    }
    evidence = [f"发现 {len(entities)} 个 otel.service 实体"] if entities else ["未发现 otel.service 实体"]
    result = _skill_result("EntityList", "MModelQuery/entity_list", "实体列表", f"列出 {len(entities)} 个服务实体。", output, evidence, ["按 intent=entity_list 查询实体列表"])
    return result, entities


def _answer_entity_list(entities: list[dict[str, Any]], message: str) -> str:
    """Generate a friendly entity listing response (NOT anomaly ranking)."""
    if not entities:
        return "当前范围内未发现 otel.service 实体。\n\n请确认数据源已正确配置且包含 OTEL Demo 数据（OpenSearch 索引或 MModel 工作空间）。"

    total = len(entities)
    healthy = [e for e in entities if (e.get("error_rate") or 0) == 0]
    warning_svcs = [e for e in entities if 0 < (e.get("error_rate") or 0) < 0.05]
    critical_svcs = [e for e in entities if (e.get("error_rate") or 0) >= 0.05]

    lines = [
        f"当前共有 **{total}** 个 otel.service 实体：\n",
    ]

    # Status summary
    status_parts = [f"{len(healthy)} 个健康"]
    if warning_svcs:
        status_parts.append(f"{len(warning_svcs)} 个告警（error_rate < 5%）")
    if critical_svcs:
        status_parts.append(f"{len(critical_svcs)} 个异常（error_rate ≥ 5%）")
    lines.append("、".join(status_parts) + "。\n")

    # Full entity table (sorted by name)
    lines.append("| 服务名 | 请求数 | 错误率 | P95 延迟 | 状态 |")
    lines.append("|---|---:|---:|---:|---|")
    for e in entities:
        svc = e.get("service_name", "?")
        req = e.get("request_count", 0)
        rate = e.get("error_rate", 0)
        p95 = e.get("p95_latency_ms")
        p95_str = f"{p95:.0f}ms" if p95 is not None else "N/A"

        if rate == 0:
            status = "✅ 健康"
        elif rate < 0.05:
            status = "⚠️ 告警"
        else:
            status = "🔴 异常"

        lines.append(f"| {svc} | {req} | {rate:.2%} | {p95_str} | {status} |")

    # Follow-up hints
    if critical_svcs:
        top = critical_svcs[0]["service_name"]
        lines.append(f"\n💡 发现 {len(critical_svcs)} 个异常服务。可以追问：")
        lines.append(f"- 过去15分钟哪些服务异常最高？")
        lines.append(f"- 分析 {top} 的根因")
    else:
        lines.append("\n💡 所有服务运行正常。可以追问：")
        lines.append("- 过去15分钟哪些服务异常最高？")

    return "\n".join(lines)


def _format_log(log: dict[str, Any]) -> str:
    service = log.get("serviceName") or log.get("resource.attributes.service@name") or "unknown-service"
    severity = log.get("severityText") or log.get("severity_text") or log.get("log.attributes.log@level") or ""
    message = log.get("log.attributes.message") or log.get("body") or ""
    return f"{service} {severity}: {str(message)[:180]}"


def _format_span(span: dict[str, Any]) -> str:
    service = span.get("serviceName") or span.get("resource.attributes.service@name") or "unknown-service"
    trace_id = span.get("traceId") or "unknown-trace"
    name = span.get("name") or "unknown-span"
    return f"traceId={trace_id} {service}: {name} status={span.get('status.code', '')}"


def _format_red(item: dict[str, Any]) -> str:
    error = item.get("error", {}) or {}
    duration = item.get("duration", {}) or {}
    return (
        f"{item.get('service_name')}: error_rate={error.get('error_rate', 'unknown')}, "
        f"error_count={error.get('error_count', 'unknown')}, "
        f"p95={duration.get('p95_duration_ms', duration.get('metric_p95_duration_ms', 'unknown'))}, "
        f"score={item.get('overall_anomaly_score', 'unknown')}"
    )


def _format_ranking_item(rank: int, item: dict[str, Any]) -> str:
    return (
        f"{rank}. {item.get('service_name')}: error_count={item.get('error_count')}, "
        f"log_error_count={item.get('log_error_count')}, error_rate={item.get('error_rate')}, "
        f"p95={item.get('p95_duration_ms')}, score={item.get('overall_anomaly_score')}"
    )


def _is_missing(value: Any) -> bool:
    return value is None or str(value).strip().lower() in {"", "none", "unknown", "null", "nan"}


def _display_value(value: Any, *, missing: str = "暂无数据", precision: int | None = None) -> str:
    if _is_missing(value):
        return missing
    if isinstance(value, (int, float)) and precision is not None:
        return f"{float(value):.{precision}f}"
    return str(value)


def _as_float(value: Any, default: float = 0.0) -> float:
    if _is_missing(value):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _service_label(service: str | None) -> str:
    return service if service and service.lower() not in {"unknown", "unknown-service"} else "当前服务"


def _time_phrase(message: str) -> str:
    match = re.search(r"过去\s*([0-9一二三四五六七八九十十五]+)\s*分钟", message)
    if match:
        return f"过去 {match.group(1)} 分钟内"
    if "最近" in message:
        return "最近一段时间内"
    return "当前查询窗口内"


def _judgment_for_ranking(item: dict[str, Any]) -> str:
    log_errors = _as_int(item.get("log_error_count"))
    error_rate = _as_float(item.get("error_rate"))
    error_count = _as_int(item.get("error_count"))
    p95 = _as_float(item.get("p95_duration_ms"))
    score = _as_float(item.get("overall_anomaly_score"))
    if log_errors > 0 and error_rate <= 0:
        return "日志异常突出"
    if error_rate >= 0.2 or error_count >= 5:
        return "错误率异常"
    if p95 >= 1000:
        return "延迟偏高"
    if p95 > 10 and score <= 0.2:
        return "延迟偏高但未判异常"
    if score >= 0.5:
        return "综合评分偏高"
    return "暂无明显异常"


def _top_reason(item: dict[str, Any]) -> str:
    service = _service_label(item.get("service_name"))
    log_errors = _as_int(item.get("log_error_count"))
    error_rate = _as_float(item.get("error_rate"))
    p95 = item.get("p95_duration_ms")
    if log_errors > 0 and error_rate <= 0:
        p95_text = "p95 延迟暂无可用数据" if _is_missing(p95) else f"p95 延迟为 {_display_value(p95, precision=2)}"
        return (
            f"它排第一主要是因为日志异常数量明显高于其他服务：当前窗口内 {service} 出现 {log_errors} 条异常日志。"
            f"RED error_rate 暂未显示异常，{p95_text}。"
        )
    if error_rate > 0:
        return f"它排第一主要是因为 RED error_rate 达到 {_display_value(error_rate, precision=3)}，同时异常日志数为 {log_errors} 条。"
    if not _is_missing(p95):
        return f"它排第一主要是因为 p95 延迟相对更高，当前值为 {_display_value(p95, precision=2)}。"
    score = _display_value(item.get("overall_anomaly_score"), precision=2)
    return f"它排第一主要来自综合异常评分，当前评分为 {score}，但缺少更细的 RED 或延迟数据，需要继续补查证据。"


def _ranking_table(ranking: list[dict[str, Any]]) -> str:
    rows = [
        "| 排名 | 服务 | 日志异常数 | Error Rate | P95 | 评分 | 判断 |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for rank, item in enumerate(ranking[:5], start=1):
        rows.append(
            "| "
            f"{rank} | "
            f"{_service_label(item.get('service_name'))} | "
            f"{_display_value(item.get('log_error_count'), missing='0')} | "
            f"{_display_value(item.get('error_rate'), precision=3)} | "
            f"{_display_value(item.get('p95_duration_ms'), precision=2)} | "
            f"{_display_value(item.get('overall_anomaly_score'), precision=2)} | "
            f"{_judgment_for_ranking(item)} |"
        )
    return "\n".join(rows)


def _followup_suggestions(service: str, *, rank_ref: bool = True) -> str:
    service_label = _service_label(service)
    first = "看第一名的日志" if rank_ref else f"继续看 {service_label} 的日志"
    return (
        f"我已把 {service_label} 设为当前关注服务。你可以继续问：\n"
        f"- {first}\n"
        f"- 分析 {service_label} 的根因\n"
        f"- {service_label} 影响了多少订单"
    )


def _answer_logs(service: str, output: dict[str, Any]) -> str:
    service_label = _service_label(service)
    logs = output.get("logs", [])[:20]
    if not logs:
        return f"这次只查询了 {service_label} 的日志，没有重新执行完整诊断链路。\n\n当前窗口内未查询到关键错误日志。"
    messages = [str(log.get("log.attributes.message") or log.get("body") or "未知日志内容") for log in logs]
    top_message, top_count = Counter(messages).most_common(1)[0]
    details = [_format_log(log).replace("unknown", "未知") for log in logs[:5]]
    return (
        f"这次只查询了 {service_label} 的日志，没有重新执行完整诊断链路。\n\n"
        f"{service_label} 在当前窗口内主要出现同一类日志：{top_message}，共出现 {top_count} 次。\n\n"
        "必要明细：\n"
        + "\n".join(f"- {line}" for line in details)
        + f"\n\n你可以继续问：\n- 查看 {service_label} 的指标\n- 看 {service_label} 的 trace\n- 分析 {service_label} 的根因"
    )


def _answer_metrics(service: str, output: dict[str, Any]) -> str:
    service_label = _service_label(service)
    metrics = output.get("red_metrics", [])[:5]
    if not metrics:
        return f"这次只查询了 {service_label} 的 RED Metrics，没有重新执行完整诊断链路。\n\n当前窗口内暂无可用指标数据。"
    lines = []
    for item in metrics:
        error = item.get("error", {}) or {}
        duration = item.get("duration", {}) or {}
        lines.append(
            f"- {_service_label(item.get('service_name') or service)}：Error Rate {_display_value(error.get('error_rate'), precision=3)}，"
            f"错误数 {_display_value(error.get('error_count'), missing='0')}，"
            f"P95 {_display_value(duration.get('p95_duration_ms') or duration.get('metric_p95_duration_ms'), precision=2)}，"
            f"评分 {_display_value(item.get('overall_anomaly_score'), precision=2)}。"
        )
    return "这次只查询了 RED Metrics，没有重新执行完整诊断链路。\n\n" + "\n".join(lines)


def _answer_traces(service: str, output: dict[str, Any]) -> str:
    service_label = _service_label(service)
    traces = output.get("traces", [])[:5]
    if not traces:
        return f"这次只查询了 {service_label} 的 trace，没有重新执行完整诊断链路。\n\n当前窗口内未查询到异常 trace。"
    lines = [_format_span(span.get("_source", span)).replace("unknown", "未知") for span in traces]
    return "这次只查询了 trace 证据，没有重新执行完整诊断链路。\n\n必要明细：\n" + "\n".join(f"- {line}" for line in lines)


def _answer_service_map(service: str, output: dict[str, Any]) -> str:
    upstream = output.get("upstream", {}).get("upstream_services", [])
    downstream = output.get("downstream", {}).get("downstream_services", [])
    impacted = output.get("impacted", {}).get("impacted_services", [])
    service_label = _service_label(service)
    return (
        f"这次只查询了 {service_label} 的调用关系，没有重新执行完整诊断链路。\n\n"
        f"上游服务：{', '.join(upstream) if upstream else '暂无'}。\n"
        f"下游服务：{', '.join(downstream) if downstream else '暂无'}。\n"
        f"可能受影响上游：{', '.join(impacted) if impacted else '暂无'}。"
    )


def _answer_business_impact(service: str, output: dict[str, Any]) -> str:
    impact = output.get("business_impact", {}) or {}
    service_label = _service_label(service)
    if not impact:
        return f"这次只查询了 {service_label} 的业务影响，没有重新执行完整诊断链路。\n\n当前证据无法确认业务影响。"
    failed = _display_value(impact.get("failed_transaction_count"), missing="暂无数据")
    confidence = _display_value(impact.get("confidence"), missing="未知")
    failed_label = "失败交易数" if confidence == "high" else "失败交易信号"
    return (
        f"这次只查询了 {service_label} 的业务影响，没有重新执行完整诊断链路。\n\n"
        f"{service_label} 的可观测业务影响：影响订单数 {_display_value(impact.get('affected_order_count'), missing='暂无数据')}；"
        f"{failed_label} {failed}；影响用户数 {_display_value(impact.get('affected_user_count'), missing='暂无数据')}；"
        f"预估金额影响 {_display_value(impact.get('estimated_revenue_impact', impact.get('estimated_gmv_loss')), missing='暂无数据')}；可信度 {confidence}。"
    )


def _answer_observability_query(ranking: list[dict[str, Any]], message: str, warnings: list[str] | None = None) -> str:
    if not ranking:
        warning_lines = ""
        if warnings:
            warning_lines = "\n".join(f"- {w}" for w in warnings[:5])
            warning_lines = f"\n\n⚠️ 数据源状态：\n{warning_lines}"
        return (
            "当前查询窗口内没有返回明显异常服务。"
            f"{warning_lines}"
            "\n\n你可以继续缩小服务名、接口或时间范围再查。"
        )
    top = ranking[0]
    top_service = _service_label(top.get("service_name"))
    return (
        f"{_time_phrase(message)}，{top_service} 的异常最突出。\n\n"
        f"{_top_reason(top)}\n\n"
        f"{_ranking_table(ranking)}\n\n"
        f"{_followup_suggestions(top_service)}"
    )


def _answer_switch_focus(session: DiagnosisSession, service: str) -> str:
    if not service:
        return "未能识别要切换的服务，请指定服务名。"
    cached = session.latest_skill_outputs
    evidence_bits = []
    for key in ("log", "metric", "service_map", "business_impact"):
        if cached.get(key):
            evidence_bits.append(key)
    suffix = f"当前已有证据摘要：{', '.join(evidence_bits)}。" if evidence_bits else "当前暂无该服务的已缓存证据摘要。"
    return f"已将 current_focus 切换为 {service}。{suffix}"


def _answer_case_summary(session: DiagnosisSession) -> str:
    focus = session.current_focus.service_name or "未确定"
    candidates = session.root_cause_candidates[:3]
    candidate_lines = [f"{item.get('rank')}. {item.get('service_name')} score={item.get('anomaly_score')}" for item in candidates]
    impact = session.business_impact_summary or {}
    return (
        f"当前关注对象：{focus}\n"
        f"根因候选：{'; '.join(candidate_lines) or '暂无'}\n"
        f"受影响服务：{', '.join(session.impacted_services) or '暂无'}\n"
        f"业务影响摘要：failed_transaction_count={impact.get('failed_transaction_count', 'unknown')}，"
        f"affected_order_count={impact.get('affected_order_count', 'unknown')}，confidence={impact.get('confidence', 'none')}。"
    )


def _answer_root_cause_explanation(session: DiagnosisSession, service: str) -> str:
    candidates = session.root_cause_candidates or []
    selected = next((item for item in candidates if item.get("service_name") == service), candidates[0] if candidates else {})
    if not selected:
        return "当前会话还没有根因候选，无法解释根因依据。"
    cached = session.latest_skill_outputs
    return (
        f"根因候选 {selected.get('service_name')} 的依据：score={selected.get('anomaly_score')}；"
        f"候选摘要={selected.get('evidence_summary') or '暂无'}。"
        f"关联 trace={session.related_trace_ids[-3:] or '暂无'}，metric={session.related_metric_refs[-3:] or '暂无'}，"
        f"service_map_edges={len(cached.get('service_map', {}).get('call_edges', [])) if isinstance(cached.get('service_map'), dict) else 0}。"
    )


def _summary_from_session(session: DiagnosisSession) -> DiagnosisSummary:
    rc = session.latest_skill_outputs.get("root_cause", {}) if isinstance(session.latest_skill_outputs, dict) else {}
    return DiagnosisSummary(
        root_cause_service=rc.get("root_cause_service") or session.current_focus.service_name or "",
        root_cause_api=rc.get("root_cause_api") or "",
        root_cause_type=rc.get("root_cause_type") or "",
        exception_type="",
        bad_parameter="",
        impact_api=session.request_context.get("api", ""),
        business_impact=[],
    )


def _empty_call_graph(session: DiagnosisSession) -> CallGraph:
    nodes = []
    if session.current_focus.service_name:
        from app.models.diagnosis import CallNode
        nodes.append(CallNode(id=session.current_focus.service_name, label=session.current_focus.service_name, node_type="Service"))
    return CallGraph(nodes=nodes, edges=[])


def _evidence_chain_from_session(session: DiagnosisSession, evidence_refs: dict[str, Any]) -> list[str]:
    chain = []
    if session.related_trace_ids:
        chain.append(f"Session trace refs: {session.related_trace_ids[-3:]}")
    if session.related_metric_refs:
        chain.append(f"Session metric refs: {session.related_metric_refs[-3:]}")
    if evidence_refs:
        chain.append(f"本轮证据引用：{list(evidence_refs.keys())}")
    return chain
