"""Lightweight diagnosis session memory for multi-turn troubleshooting."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SessionFocus:
    type: str = "unknown"
    id: str | None = None
    name: str | None = None
    service_name: str | None = None
    confidence: str = "low"
    source_turn_id: str | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "id": self.id,
            "name": self.name,
            "service_name": self.service_name,
            "confidence": self.confidence,
            "source_turn_id": self.source_turn_id,
            "reason": self.reason,
        }


@dataclass
class DiagnosisSession:
    session_id: str
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    last_user_message: str = ""
    last_assistant_message: str = ""
    current_focus: SessionFocus = field(default_factory=SessionFocus)
    mentioned_services: list[dict[str, Any]] = field(default_factory=list)
    root_cause_candidates: list[dict[str, Any]] = field(default_factory=list)
    impacted_services: list[str] = field(default_factory=list)
    related_trace_ids: list[str] = field(default_factory=list)
    related_log_ids: list[str] = field(default_factory=list)
    related_metric_refs: list[str] = field(default_factory=list)
    related_service_map_edges: list[dict[str, Any]] = field(default_factory=list)
    business_impact_summary: dict[str, Any] = field(default_factory=dict)
    latest_skill_outputs: dict[str, Any] = field(default_factory=dict)
    observability_query_results: list[dict[str, Any]] = field(default_factory=list)
    query_context: dict[str, Any] = field(default_factory=dict)
    request_context: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_user_message": self.last_user_message,
            "last_assistant_message": self.last_assistant_message,
            "current_focus": self.current_focus.to_dict(),
            "mentioned_services": self.mentioned_services,
            "root_cause_candidates": self.root_cause_candidates,
            "impacted_services": self.impacted_services,
            "related_trace_ids": self.related_trace_ids,
            "related_log_ids": self.related_log_ids,
            "related_metric_refs": self.related_metric_refs,
            "related_service_map_edges": self.related_service_map_edges,
            "business_impact_summary": self.business_impact_summary,
            "latest_skill_outputs": self.latest_skill_outputs,
            "observability_query_results": self.observability_query_results,
            "query_context": self.query_context,
            "request_context": self.request_context,
            "history": self.history,
        }


class DiagnosisSessionStore:
    def get_session(self, session_id: str) -> DiagnosisSession | None:
        raise NotImplementedError

    def create_session(self, session_id: str | None = None) -> DiagnosisSession:
        raise NotImplementedError

    def update_session(self, session: DiagnosisSession) -> DiagnosisSession:
        raise NotImplementedError

    def append_turn(self, session_id: str, turn: dict[str, Any]) -> DiagnosisSession:
        raise NotImplementedError


class InMemoryDiagnosisSessionStore(DiagnosisSessionStore):
    def __init__(self) -> None:
        self._sessions: dict[str, DiagnosisSession] = {}
        self._lock = RLock()

    def get_session(self, session_id: str) -> DiagnosisSession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def create_session(self, session_id: str | None = None) -> DiagnosisSession:
        with self._lock:
            sid = session_id or str(uuid4())
            session = DiagnosisSession(session_id=sid)
            self._sessions[sid] = session
            return session

    def update_session(self, session: DiagnosisSession) -> DiagnosisSession:
        with self._lock:
            session.updated_at = _now()
            self._sessions[session.session_id] = session
            return session

    def append_turn(self, session_id: str, turn: dict[str, Any]) -> DiagnosisSession:
        with self._lock:
            session = self._sessions.get(session_id) or self.create_session(session_id)
            session.history.append(turn)
            session.updated_at = _now()
            self._sessions[session_id] = session
            return session

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()


_GLOBAL_SESSION_STORE = InMemoryDiagnosisSessionStore()


def get_session_store() -> InMemoryDiagnosisSessionStore:
    return _GLOBAL_SESSION_STORE


def get_or_create_session(session_id: str | None, store: DiagnosisSessionStore | None = None) -> DiagnosisSession:
    session_store = store or get_session_store()
    if session_id:
        existing = session_store.get_session(session_id)
        if existing:
            return existing
    return session_store.create_session(session_id)


_SERVICE_REFERENCE_TOKENS = ("它", "这个服务", "刚才那个服务", "这个异常服务", "root cause 服务", "根因服务", "这个错误", "刚才那个错误")
_BUSINESS_IMPACT_TOKENS = ("多少订单", "影响了多少订单", "影响多少用户", "多少用户", "损失多少金额", "金额影响", "失败了多少交易", "失败交易")


def _service_aliases(service_name: str) -> set[str]:
    lowered = (service_name or "").lower().strip()
    aliases = {lowered}
    for suffix in ("-service", "_service", " service", "服务"):
        if lowered.endswith(suffix):
            aliases.add(lowered[: -len(suffix)])
    aliases.add(lowered.replace("-service", " service"))
    aliases.add(lowered.replace("_service", " service"))
    return {alias for alias in aliases if alias}


def resolve_context_reference(message: str, session: DiagnosisSession) -> dict[str, Any]:
    """Resolve lightweight pronouns/references against orchestrator-owned session memory."""
    text = (message or "").strip()
    lowered = text.lower()
    if any(token in text for token in ("第一名", "第1名", "top1", "Top1", "排名第一")) and session.observability_query_results:
        top_item = session.observability_query_results[0]
        service = top_item.get("service_name") or top_item.get("service")
        if service:
            session.current_focus = SessionFocus(
                type="service",
                service_name=str(service),
                name=str(service),
                confidence="high",
                reason="根据上一轮观测查询结果 Top1 切换当前关注服务",
            )
            return {
                "original_reference": text,
                "resolved_type": "service",
                "resolved_value": service,
                "service_name": service,
                "confidence": "high",
                "reason": "上一轮观测查询结果 Top1",
                "needs_clarification": False,
            }
    service_names = [item.get("service_name") for item in session.mentioned_services if item.get("service_name")]
    for service in service_names:
        if any(alias in lowered for alias in _service_aliases(str(service))):
            session.current_focus = SessionFocus(
                type="service",
                service_name=str(service),
                name=str(service),
                confidence="high",
                reason="用户明确提到服务名，切换当前关注服务",
            )
            return {
                "original_reference": service,
                "resolved_type": "service",
                "resolved_value": service,
                "confidence": "high",
                "reason": "用户明确提到服务名",
                "needs_clarification": False,
            }

    asks_business_impact = any(token in text for token in _BUSINESS_IMPACT_TOKENS)
    has_service_pronoun = any(token in text for token in _SERVICE_REFERENCE_TOKENS)
    focus_service = session.current_focus.service_name
    if (asks_business_impact or has_service_pronoun) and focus_service:
        resolved_type = "business_impact" if asks_business_impact else "service"
        return {
            "original_reference": text,
            "resolved_type": resolved_type,
            "resolved_value": focus_service,
            "service_name": focus_service,
            "confidence": session.current_focus.confidence or "medium",
            "reason": f"根据 current_focus.service_name={focus_service} 解析省略指代",
            "needs_clarification": False,
        }

    if has_service_pronoun or asks_business_impact:
        return {
            "original_reference": text,
            "resolved_type": "unknown",
            "resolved_value": None,
            "confidence": "low",
            "reason": "当前会话没有明确服务焦点，无法安全解析省略指代",
            "needs_clarification": True,
            "clarification_question": "请指定要继续排查的服务，例如 payment 或 checkout。",
        }

    evidence_map = [("trace", "trace"), ("日志", "log"), ("log", "log"), ("指标", "metric"), ("metric", "metric"), ("调用链", "service_map")]
    for token, evidence_type in evidence_map:
        if token in lowered or token in text:
            refs = {
                "trace": session.related_trace_ids,
                "log": session.related_log_ids,
                "metric": session.related_metric_refs,
                "service_map": session.related_service_map_edges,
            }.get(evidence_type, [])
            if refs:
                return {
                    "original_reference": text,
                    "resolved_type": evidence_type,
                    "resolved_value": refs[0],
                    "confidence": "medium",
                    "reason": f"根据最近 {evidence_type} 证据解析指代",
                    "needs_clarification": False,
                }

    return {
        "original_reference": text,
        "resolved_type": "unknown",
        "resolved_value": None,
        "confidence": "low",
        "reason": "未检测到需要解析的省略指代",
        "needs_clarification": False,
    }


def _append_unique(items: list[Any], values: list[Any]) -> list[Any]:
    result = list(items)
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _merge_service(session: DiagnosisSession, service_name: str, role: str, turn_id: str, evidence_refs: list[str] | None = None) -> None:
    if not service_name:
        return
    for item in session.mentioned_services:
        if item.get("service_name") == service_name and item.get("role") == role:
            item["last_seen_turn_id"] = turn_id
            item["evidence_refs"] = _append_unique(item.get("evidence_refs", []), evidence_refs or [])
            return
    session.mentioned_services.append({
        "service_name": service_name,
        "role": role,
        "last_seen_turn_id": turn_id,
        "evidence_refs": evidence_refs or [],
    })


def update_session_from_context(
    session: DiagnosisSession,
    ctx: Any,
    *,
    user_message: str,
    assistant_message: str = "",
    store: DiagnosisSessionStore | None = None,
) -> DiagnosisSession:
    """Persist orchestrator-owned memory from completed skill outputs."""
    turn_id = str(uuid4())
    session.last_user_message = user_message
    session.last_assistant_message = assistant_message
    session.request_context = {
        "api": getattr(ctx, "api", ""),
        "time": getattr(ctx, "time", ""),
        "symptom": getattr(ctx, "symptom", ""),
        "case_id": getattr(ctx, "case_id", None),
        "data_dir": getattr(ctx, "data_dir", None),
    }
    session.query_context = dict(getattr(ctx, "query_context", {}) or {})

    trace = getattr(ctx, "trace_result", {}) or {}
    graph = getattr(ctx, "graph_result", {}) or {}
    rc = getattr(ctx, "root_cause_result", {}) or {}
    impact = getattr(ctx, "impact_result", {}) or {}
    metric = getattr(ctx, "metric_result", {}) or {}

    trace_ids = [trace.get("trace_id"), trace.get("entry_trace_id"), trace.get("service_map_trace_id")]
    business_impact = impact.get("business_impact", {}) or {}
    evidence_links = business_impact.get("evidence_links", {}) or {}
    trace_ids.extend(evidence_links.get("trace_ids", []) or [])
    session.related_trace_ids = _append_unique(session.related_trace_ids, [str(tid) for tid in trace_ids if tid])
    session.related_log_ids = _append_unique(session.related_log_ids, [str(log_id) for log_id in (evidence_links.get("log_ids", []) or []) if log_id])

    red_metrics = metric.get("red_metrics", []) or []
    metric_refs = [item.get("service_name") or item.get("name") for item in red_metrics if isinstance(item, dict)]
    metric_refs.extend(evidence_links.get("metric_refs", []) or [])
    session.related_metric_refs = _append_unique(session.related_metric_refs, [str(ref) for ref in metric_refs if ref])

    call_edges = graph.get("call_edges", []) or []
    edge_links = business_impact.get("related_service_map_edges", []) or evidence_links.get("service_map_edges", []) or []
    session.related_service_map_edges = _append_unique(session.related_service_map_edges, [edge for edge in call_edges + edge_links if isinstance(edge, dict)])

    root_service = rc.get("root_cause_service")
    if root_service:
        session.current_focus = SessionFocus(
            type="service",
            service_name=root_service,
            name=root_service,
            confidence="high" if rc.get("confidence") == "high" else "medium",
            source_turn_id=turn_id,
            reason="上一轮 RootCause 排名第一的服务",
        )
        _merge_service(session, root_service, "root_cause_candidate", turn_id, ["RootCauseSkill"])

    candidates = rc.get("candidates") or []
    session.root_cause_candidates = []
    for index, candidate in enumerate(candidates[:10], start=1):
        service = candidate.get("service") or candidate.get("component") or candidate.get("root_cause_service")
        if service:
            session.root_cause_candidates.append({
                "service_name": service,
                "rank": index,
                "anomaly_score": candidate.get("score"),
                "evidence_summary": candidate.get("evidence") or candidate.get("reason") or candidate.get("root_cause_reason"),
                "related_trace_ids": session.related_trace_ids,
                "related_log_ids": session.related_log_ids,
                "related_metric_refs": session.related_metric_refs,
            })
            _merge_service(session, service, "root_cause_candidate", turn_id, ["RootCauseSkill"])

    impacted_services = [str(service) for service in (impact.get("affected_services", []) or []) if service]
    session.impacted_services = _append_unique(session.impacted_services, impacted_services)
    for service in impacted_services:
        _merge_service(session, service, "impacted_service", turn_id, ["ImpactAnalysisSkill"])

    for edge in call_edges:
        if not isinstance(edge, dict):
            continue
        source = edge.get("source_service") or edge.get("source")
        target = edge.get("target_service") or edge.get("target")
        if source:
            _merge_service(session, str(source), "upstream", turn_id, ["GraphAnalysisSkill"])
        if target:
            _merge_service(session, str(target), "downstream", turn_id, ["GraphAnalysisSkill"])

    if business_impact:
        session.business_impact_summary = {
            "affected_order_count": business_impact.get("affected_order_count", "unknown"),
            "failed_transaction_count": business_impact.get("failed_transaction_count", "unknown"),
            "affected_user_count": business_impact.get("affected_user_count", "unknown"),
            "estimated_revenue_impact": business_impact.get("estimated_revenue_impact", business_impact.get("estimated_gmv_loss", "unknown")),
            "confidence": business_impact.get("confidence", "none"),
            "related_services": business_impact.get("related_services") or evidence_links.get("related_services") or [],
            "evidence_refs": evidence_links,
        }

    session.latest_skill_outputs = {
        "trace": {
            "trace_id": trace.get("trace_id"),
            "entry_trace_id": trace.get("entry_trace_id"),
            "service_call": trace.get("service_call"),
            "root_candidates": trace.get("root_candidates", [])[:5],
        },
        "log": {
            "upstream_service": (getattr(ctx, "log_result", {}) or {}).get("upstream_service"),
            "upstream_error_type": (getattr(ctx, "log_result", {}) or {}).get("upstream_error_type"),
            "root_candidates": (getattr(ctx, "log_result", {}) or {}).get("root_candidates", [])[:5],
            "log_evidence": (getattr(ctx, "log_result", {}) or {}).get("log_evidence", [])[:8],
        },
        "metric": {
            "red_metrics": red_metrics[:8],
            "red_anomaly_scores": metric.get("red_anomaly_scores", [])[:8],
            "conclusion": metric.get("conclusion"),
        },
        "service_map": {
            "call_edges": call_edges[:12],
        },
        "root_cause": {
            "root_cause_service": rc.get("root_cause_service"),
            "root_cause_api": rc.get("root_cause_api"),
            "root_cause_type": rc.get("root_cause_type"),
            "confidence": rc.get("confidence"),
            "evidence_by_source": rc.get("evidence_by_source", {}),
        },
        "business_impact": session.business_impact_summary,
    }

    session.history.append({
        "turn_id": turn_id,
        "user_message": user_message,
        "assistant_message": assistant_message,
        "current_focus": session.current_focus.to_dict(),
        "created_at": _now(),
    })
    session.updated_at = _now()
    return (store or get_session_store()).update_session(session)


def memory_summary(session: DiagnosisSession) -> dict[str, Any]:
    return {
        "current_focus": session.current_focus.to_dict(),
        "mentioned_services": session.mentioned_services[-8:],
        "root_cause_candidates": session.root_cause_candidates[:5],
        "impacted_services": session.impacted_services,
        "related_trace_ids": session.related_trace_ids[-5:],
        "related_log_ids": session.related_log_ids[-5:],
        "related_metric_refs": session.related_metric_refs[-8:],
        "business_impact_summary": session.business_impact_summary,
        "observability_query_results": session.observability_query_results[:5],
    }


def update_session_from_observability_query(
    session: DiagnosisSession,
    *,
    user_message: str,
    answer: str,
    results: list[dict[str, Any]],
    query_context: dict[str, Any] | None = None,
    store: DiagnosisSessionStore | None = None,
) -> DiagnosisSession:
    turn_id = str(uuid4())
    session.last_user_message = user_message
    session.last_assistant_message = answer
    session.observability_query_results = results[:10]
    if query_context:
        session.query_context = dict(query_context)
    top_item = results[0] if results else {}
    top_service = top_item.get("service_name") or top_item.get("service")
    if top_service:
        session.current_focus = SessionFocus(
            type="service",
            service_name=str(top_service),
            name=str(top_service),
            confidence="medium",
            source_turn_id=turn_id,
            reason="上一轮观测查询结果 Top1",
        )
        _merge_service(session, str(top_service), "observability_query_top1", turn_id, ["observability_query"])
    session.history.append({
        "turn_id": turn_id,
        "user_message": user_message,
        "assistant_message": answer,
        "intent": "observability_query",
        "current_focus": session.current_focus.to_dict(),
        "created_at": _now(),
    })
    session.updated_at = _now()
    return (store or get_session_store()).update_session(session)
