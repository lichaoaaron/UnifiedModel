"""
DiagnosisOrchestrator: sequentially runs all skills and assembles the final response.
Skills are run in fixed order as defined in orchestration_flow.yaml.
Each skill records real started_at, finished_at and duration_ms.
"""
import json
import logging
import os
import time as _time
from collections.abc import Iterator
from typing import Any
from app.adapters.local_json_adapter import resolve_request_context
from app.models.context import DiagnosisContext
from app.models.diagnosis import DiagnosisResponse, DiagnosisSummary, CallGraph, CallNode, CallEdge, DiagnosisMessage
from app.skills.alert_context_skill import AlertContextSkill
from app.skills.trace_analysis_skill import TraceAnalysisSkill
from app.skills.entity_binding_skill import EntityBindingSkill
from app.skills.log_analysis_skill import LogAnalysisSkill
from app.skills.metric_check_skill import MetricCheckSkill
from app.skills.graph_analysis_skill import GraphAnalysisSkill
from app.skills.root_cause_skill import RootCauseSkill
from app.skills.impact_analysis_skill import ImpactAnalysisSkill
from app.skills.report_skill import ReportSkill
from app.session import (
    DiagnosisSessionStore,
    get_or_create_session,
    memory_summary,
    resolve_context_reference,
    update_session_from_context,
)
from app.orchestrator.intent_router import (
    classify_intent,
    is_initial_diagnosis_intent,
    run_intent_turn,
    skill_result_to_tool_key,
)
from app.runtime.dcc_mapper import map_dcc_to_context_seed, map_unifiedmodel_outputs_to_dcc
from app.runtime.dcc_validator import validate_dcc_payload
from app.runtime.runbook import attach_runbook_metadata, default_service_exception_runbook, runbook_skill_sequence
from app.adapters.observability_adapter import clear_data_source_warnings, get_data_source, get_data_source_status

logger = logging.getLogger(__name__)

# Minimum display time per skill in seconds (for realistic demo feel)
_MIN_SKILL_DISPLAY_S = 0.0

SKILL_PIPELINE = [
    AlertContextSkill(),
    EntityBindingSkill(),
    TraceAnalysisSkill(),
    LogAnalysisSkill(),
    MetricCheckSkill(),
    GraphAnalysisSkill(),
    RootCauseSkill(),
    ImpactAnalysisSkill(),
    ReportSkill(),
]

DEFAULT_RUNBOOK = default_service_exception_runbook()


def _runbook_skill_pipeline():
    return runbook_skill_sequence(DEFAULT_RUNBOOK, SKILL_PIPELINE)


def run_diagnosis(
    api: str,
    time: str,
    symptom: str,
    case_id: str | None = None,
    data_dir: str | None = None,
    session_id: str | None = None,
    message: str | None = None,
    mode: str | None = None,
    dcc: dict[str, Any] | None = None,
    session_store: DiagnosisSessionStore | None = None,
) -> DiagnosisResponse:
    # Consume the stream and return the final assembled response
    final = None
    for event_type, payload in stream_diagnosis(
        api,
        time,
        symptom,
        case_id=case_id,
        data_dir=data_dir,
        session_id=session_id,
        message=message,
        mode=mode,
        dcc=dcc,
        session_store=session_store,
    ):
        if event_type == "done":
            final = payload
    return final  # type: ignore[return-value]


def _fill_request_from_session(api: str, time: str, symptom: str, session) -> tuple[str, str, str]:
    request_context = getattr(session, "request_context", {}) or {}
    normalized_api = "" if api == "/unknown" else api
    return (
        normalized_api or request_context.get("api", ""),
        time or request_context.get("time", ""),
        symptom or request_context.get("symptom", ""),
    )


def _resolve_dcc_seed(
    dcc: dict[str, Any] | None,
    api: str,
    time: str,
    symptom: str,
) -> tuple[dict[str, Any] | None, str, str, str]:
    if dcc is None:
        return None, api, time, symptom
    validated = validate_dcc_payload(dcc)
    seed = map_dcc_to_context_seed(validated)
    resolved_api = api or seed.get("api", "")
    resolved_time = time or seed.get("time", "")
    resolved_symptom = symptom or seed.get("symptom", "")
    return seed, resolved_api, resolved_time, resolved_symptom


def _seed_context_from_dcc(ctx: DiagnosisContext, dcc: dict[str, Any], seed: dict[str, Any]) -> None:
    ctx.dcc_context = dcc
    if seed.get("query_context"):
        ctx.query_context = seed["query_context"]
    if seed.get("entity_result"):
        ctx.entity_result = seed["entity_result"]
    if seed.get("graph_result"):
        ctx.graph_result = seed["graph_result"]
    if seed.get("trace_result"):
        ctx.trace_result = seed["trace_result"]
    if seed.get("log_result"):
        ctx.log_result = seed["log_result"]
    if seed.get("metric_result"):
        ctx.metric_result = seed["metric_result"]


def _build_call_graph(ctx: DiagnosisContext) -> CallGraph:
    """Build a CallGraph from ctx.graph_result + ctx.trace_result, used for SSE and done payloads."""
    graph = ctx.graph_result or {}
    trace = ctx.trace_result
    rc = ctx.root_cause_result or {}
    trace_first_api = (trace.get("first_error_api") or "") if trace else ""
    trace_entry_api = (trace.get("entry_api") or ctx.api or "") if trace else (ctx.api or "")
    root_cause_confirmed = bool(rc) and rc.get("is_confirmed", True)

    runtime_nodes = list(graph.get("nodes", []))
    runtime_edges = list(graph.get("edges", []))
    call_services = list(dict.fromkeys(
        p.split(":")[0].strip() for p in trace.get("call_path", []) if p
    )) if trace else []

    node_ids = {n.get("id", "") for n in runtime_nodes}
    edge_keys = {(e.get("source", ""), e.get("target", ""), e.get("label", "")) for e in runtime_edges}

    def _ensure_node(node_id: str, node_type: str) -> None:
        if not node_id or node_id in node_ids:
            return
        node_ids.add(node_id)
        runtime_nodes.append({
            "id": node_id,
            "label": node_id,
            "node_type": node_type,
            "is_root_cause": False,
            "is_entry": False,
        })

    def _ensure_edge(source: str, target: str, label: str) -> None:
        if not source or not target or source == target:
            return
        key = (source, target, label)
        if key in edge_keys:
            return
        edge_keys.add(key)
        runtime_edges.append({"source": source, "target": target, "label": label})

    for svc in call_services:
        _ensure_node(svc, "Service")
    for i in range(len(call_services) - 1):
        _ensure_edge(call_services[i], call_services[i + 1], "calls")

    if call_services and trace_entry_api:
        _ensure_node(trace_entry_api, "Interface")
        _ensure_edge(call_services[0], trace_entry_api, "exposes")

    # ── Fix entry service: ensure is_entry is on the service that exposes the entry API ──
    _entry_exposing = {
        e["source"] for e in runtime_edges
        if e.get("label") == "exposes" and e.get("target") == trace_entry_api
    }
    if _entry_exposing:
        _preferred_entry = next((svc for svc in call_services if svc in _entry_exposing), next(iter(_entry_exposing)))
        for n in runtime_nodes:
            n["is_entry"] = (n.get("id") == _preferred_entry)

    rc_service = rc.get("root_cause_service", "") if root_cause_confirmed else ""
    rc_api = rc.get("root_cause_api", "") if root_cause_confirmed else ""
    rc_type = rc.get("root_cause_type", "")
    _is_mw_rc = rc_type in ("platform.redis", "platform.database")
    if rc_service:
        _ensure_node(rc_service, "Service")
    # Middleware root causes (platform.redis / platform.database) do not
    # expose a single API — skip the false exposes edge and interface node.
    if rc_api and not _is_mw_rc:
        _ensure_node(rc_api, "Interface")
    if rc_service and rc_api and not _is_mw_rc:
        _ensure_edge(rc_service, rc_api, "exposes")
    # ── Middleware dependency node: make Redis / Database visible ─────────
    _mw_node_id: str | None = None
    if _is_mw_rc and rc_service and root_cause_confirmed:
        _mw_label = rc_type.removeprefix("platform.")
        _mw_node_id = _mw_label  # e.g. "redis" / "database"
        _ensure_node(_mw_node_id, "Dependency")
        _ensure_edge(rc_service, _mw_node_id, "depends_on")

    impact = ctx.impact_result or {}
    affected_services = impact.get("affected_services", []) or []
    affected_apis = impact.get("affected_apis", []) or []
    _chain_svc_nodes = runtime_nodes
    first_error_svc = (rc.get("root_cause_service") or next((n["id"] for n in _chain_svc_nodes if n.get("is_root_cause")), "")) if root_cause_confirmed else ""
    entry_svc = next((n["id"] for n in _chain_svc_nodes if n.get("is_entry")), "") if root_cause_confirmed else ""

    if not root_cause_confirmed:
        call_chain_node_ids: set[str] = set()
        call_chain_edge_pairs: set[tuple[str, str]] = set()
    else:
        call_chain_node_ids = set(call_services) or {n["id"] for n in _chain_svc_nodes if n.get("node_type") in ("Service", "service")}
        if trace_entry_api:
            call_chain_node_ids.add(trace_entry_api)
        if trace_first_api:
            call_chain_node_ids.add(trace_first_api)
        for item in affected_services + affected_apis:
            if item:
                call_chain_node_ids.add(item)
        for ie in graph.get("interface_edges", []):
            for key in ("source", "target"):
                v = ie.get(key, "")
                if v:
                    call_chain_node_ids.add(v)
        call_chain_edge_pairs = {
            (e["source"], e["target"]) for e in runtime_edges
            if e.get("label") in ("calls", "exposes", "depends_on")
        }

    nodes = [
        CallNode(id=n["id"], label=n.get("label", n["id"]),
                 is_root_cause=root_cause_confirmed and (n["id"] in {first_error_svc, rc.get("root_cause_api", ""), _mw_node_id}),
                 is_entry=root_cause_confirmed and (n["id"] in {entry_svc, trace_entry_api}),
                 node_type=n.get("node_type", n.get("type", "Service")),
                 is_call_chain=n["id"] in call_chain_node_ids or n["id"] == _mw_node_id)
        for n in runtime_nodes
    ]
    edges = [
        CallEdge(source=e["source"], target=e["target"], label=e.get("label", ""),
                 is_call_chain=(e["source"], e["target"]) in call_chain_edge_pairs)
        for e in runtime_edges
    ]
    existing_node_ids = {n.id for n in nodes}
    for service in affected_services:
        if service and service not in existing_node_ids:
            existing_node_ids.add(service)
            nodes.append(CallNode(id=service, label=service, node_type="Service", is_call_chain=service in call_chain_node_ids))
    for api_id in affected_apis:
        if api_id and api_id not in existing_node_ids:
            existing_node_ids.add(api_id)
            nodes.append(CallNode(
                id=api_id, label=api_id,
                is_root_cause=root_cause_confirmed and (api_id == rc.get("root_cause_api", "")),
                is_entry=root_cause_confirmed and (api_id == trace_entry_api),
                node_type="Interface", is_call_chain=api_id in call_chain_node_ids,
            ))
    for ie in graph.get("interface_edges", []):
        for api_id in [ie.get("source", ""), ie.get("target", "")]:
            if api_id and api_id not in existing_node_ids:
                existing_node_ids.add(api_id)
                nodes.append(CallNode(
                    id=api_id, label=api_id,
                    is_root_cause=root_cause_confirmed and (api_id == rc.get("root_cause_api", "")),
                    is_entry=root_cause_confirmed and (api_id == trace_entry_api),
                    node_type="Interface", is_call_chain=api_id in call_chain_node_ids,
                ))
        source = ie.get("source", "")
        target = ie.get("target", "")
        label = ie.get("label", "downstream call")
        if source and target and source != target:
            key = (source, target, label)
            if key not in edge_keys:
                edge_keys.add(key)
                runtime_edges.append({"source": source, "target": target, "label": label})
            if root_cause_confirmed:
                call_chain_edge_pairs.add((source, target))

    edges = [
        CallEdge(source=e["source"], target=e["target"], label=e.get("label", ""),
                 is_call_chain=(e["source"], e["target"]) in call_chain_edge_pairs)
        for e in runtime_edges
    ]

    trace_log = ctx.log_result
    metric = ctx.metric_result
    runtime_call_services = []
    for edge in edges:
        if edge.label != "calls":
            continue
        for service in (edge.source, edge.target):
            if service and service not in runtime_call_services:
                runtime_call_services.append(service)
    runtime_service_call = " → ".join(runtime_call_services) or (trace.get("service_call", "") if trace else "")
    return CallGraph(
        nodes=nodes,
        edges=edges,
        trace_summary=(
            f"traceId: {trace.get('trace_id', 'N/A')} | 调用链: {runtime_service_call}"
            if trace else ""
        ),
        log_summary=(
            f"上游: {trace_log.get('upstream_service', '')} | 错误类型: {trace_log.get('upstream_error_type', '')}"
            if trace_log else ""
        ),
        metric_summary=metric.get("conclusion", "") if metric else "",
    )


def stream_diagnosis(
    api: str,
    time: str,
    symptom: str,
    case_id: str | None = None,
    data_dir: str | None = None,
    session_id: str | None = None,
    message: str | None = None,
    mode: str | None = None,
    dcc: dict[str, Any] | None = None,
    session_store: DiagnosisSessionStore | None = None,
) -> Iterator[tuple[str, object]]:
    """
    Generator: yields (event_type, payload) tuples.
      event_type="skill"  payload=DiagnosisMessage  (one per skill, after it finishes)
      event_type="done"   payload=DiagnosisResponse (final full response)
    """
    session = get_or_create_session(session_id, session_store)
    dcc_seed, api, time, symptom = _resolve_dcc_seed(dcc, api, time, symptom)
    api, time, symptom = _fill_request_from_session(api, time, symptom, session)
    user_message = message or f"{time}，{api} 接口出现 {symptom}，请分析根因和影响面。"
    resolved_context = resolve_context_reference(user_message, session)

    # ── Clear fallback tracking at start of each run ─────────────────────────
    clear_data_source_warnings()

    intent_decision = classify_intent(
        message=user_message,
        api=api,
        time=time,
        symptom=symptom,
        session=session,
        resolved_context=resolved_context,
        mode=mode,
    )

    if not is_initial_diagnosis_intent(intent_decision.intent):
        case_id = case_id or (session.request_context or {}).get("case_id")
        data_dir = data_dir or (session.request_context or {}).get("data_dir")
        turn = run_intent_turn(
            session=session,
            intent_decision=intent_decision,
            resolved_context=resolved_context,
            user_message=user_message,
            api=api,
            time=time,
            symptom=symptom,
            case_id=case_id,
            data_dir=data_dir,
            mode=mode,
            session_store=session_store,
        )
        yield ("session", {
            "session_id": session.session_id,
            "mode": mode,
            "intent": turn.intent,
            "current_focus": turn.response.current_focus,
            "resolved_context": resolved_context,
            "memory_summary": turn.response.memory_summary,
            "executed_skills": turn.response.executed_skills,
        })
        for result in turn.skill_results:
            yield ("skill_start", DiagnosisMessage(
                role="assistant",
                type="skill_call",
                skill_name=result.skill_name,
                tool_name=result.tool_name,
                status="running",
                summary="",
                duration_ms=0,
                input={},
                output={},
                evidence=[],
                execution_log=[],
                explanation="",
            ))
            yield ("skill", DiagnosisMessage(
                role="assistant",
                type="skill_call",
                skill_name=result.skill_name,
                tool_name=result.tool_name,
                status=result.status,
                summary=result.summary,
                duration_ms=result.duration_ms,
                input=result.input,
                output=result.output,
                evidence=result.evidence,
                execution_log=result.execution_log,
                explanation=result.explanation,
            ))
        yield ("report", DiagnosisMessage(role="assistant", type="report", content=turn.answer))
        yield ("done", turn.response)
        return

    if dcc_seed is None:
        case_id, data_dir = resolve_request_context(api=api, symptom=symptom, case_id=case_id, data_dir=data_dir)

    # ── Auto-produce DCC from MModel API when no external DCC provided ──
    if dcc is None and get_data_source() == "mmodel_api":
        try:
            from app.adapters.unifiedmodel_adapter import _mmodel_api_adapter
            workspace = os.environ.get("MMODEL_WORKSPACE", "otel-demo")
            logger.info(
                "[DCC-auto] Fetching entities/topo/evidence from MModel API "
                "(workspace=%s) to auto-construct DCC", workspace,
            )
            entity_result = _mmodel_api_adapter.query_entities(limit=50)
            topo_result = _mmodel_api_adapter.query_topo(limit=200)
            # Build minimal query_results dicts for the DCC mapper
            entity_rows = entity_result if isinstance(entity_result, list) else []
            topo_rows = topo_result if isinstance(topo_result, list) else []
            entity_query_result = {
                "rows": [
                    {"id": e.get("__entity_id__", ""), "entity_type": e.get("__entity_type__", ""),
                     "entity_name": e.get("display_name", ""), "domain": e.get("__domain__", ""),
                     **{k: v for k, v in e.items() if not k.startswith("__")}}
                    for e in entity_rows
                ],
            }
            topo_query_result = {
                "rows": [
                    {"source": r.get("src", ""), "target": r.get("dest", ""),
                     "relation": r.get("relation", r.get("type", "calls")),
                     **{k: v for k, v in r.items() if k not in ("src", "dest", "relation", "type")}}
                    for r in topo_rows
                ],
            }
            auto_dcc = map_unifiedmodel_outputs_to_dcc(
                workspace_id=workspace,
                alert_api=api,
                alert_time=time,
                alert_symptom=symptom,
                entity_query_result=entity_query_result,
                topo_query_result=topo_query_result,
                # evidence queries are on-demand via skills; seed with empty
                producer="mmodel-api-auto-dcc",
            )
            # Validate and seed the context
            validated = validate_dcc_payload(auto_dcc)
            dcc_seed = map_dcc_to_context_seed(validated)
            dcc = auto_dcc
            logger.info(
                "[DCC-auto] Constructed DCC with %d entities, %d topo edges",
                len(auto_dcc.get("objects", {}).get("entities", [])),
                len(auto_dcc.get("objects", {}).get("topology", {}).get("edges", [])),
            )
        except Exception as exc:
            logger.warning(
                "[DCC-auto] Failed to auto-construct DCC from MModel API: %s. "
                "Falling back to adapter-based evidence queries.",
                exc,
            )

    ctx = DiagnosisContext(api=api, time=time, symptom=symptom, case_id=case_id, data_dir=data_dir)
    if dcc is not None and dcc_seed is not None:
        _seed_context_from_dcc(ctx, dcc, dcc_seed)
    ctx.resolved_context = resolved_context
    skill_results = []

    yield ("session", {
        "session_id": session.session_id,
        "mode": mode,
        "intent": intent_decision.intent,
        "current_focus": session.current_focus.to_dict(),
        "resolved_context": resolved_context,
        "memory_summary": memory_summary(session),
        "executed_skills": [],
    })

    # ── Emit data source status early ────────────────────────────────────────
    yield ("data_source_status", get_data_source_status())

    for runbook_step, skill in _runbook_skill_pipeline():
        runbook_metadata = runbook_step.metadata()
        # notify frontend that this skill is starting
        yield ("skill_start", DiagnosisMessage(
            role="assistant",
            type="skill_call",
            skill_name=skill.skill_name,
            tool_name=skill.tool_name,
            status="running",
            summary="",
            duration_ms=0,
            input={"runbook": runbook_metadata},
            output={},
            evidence=[item.get("key", "") for item in runbook_metadata.get("evidence", [])],
            execution_log=[],
            explanation="",
        ))

        t0 = _time.monotonic()
        result = attach_runbook_metadata(skill.run(ctx), runbook_step)
        if skill.skill_name == "AlertContextSkill" and not resolved_context.get("needs_clarification"):
            resolved_service = resolved_context.get("service_name") or resolved_context.get("resolved_value")
            if resolved_context.get("resolved_type") in {"service", "business_impact"} and resolved_service:
                ctx.query_context["focus_service"] = resolved_service
                result.output["focus_service"] = resolved_service
                result.output["resolved_context"] = resolved_context
        elapsed = _time.monotonic() - t0
        if elapsed < _MIN_SKILL_DISPLAY_S:
            _time.sleep(_MIN_SKILL_DISPLAY_S - elapsed)
        skill_results.append(result)

        # yield skill result immediately after it finishes
        yield ("skill", DiagnosisMessage(
            role="assistant",
            type="skill_call",
            skill_name=result.skill_name,
            tool_name=result.tool_name,
            status=result.status,
            summary=result.summary,
            duration_ms=result.duration_ms,
            input=result.input,
            output=result.output,
            evidence=result.evidence,
            execution_log=result.execution_log,
            explanation=result.explanation,
        ))

        # Yield call_graph after each evidence skill so topology builds progressively.
        # The frontend re-renders on every call_graph update.
        if skill.skill_name in ("EntityBindingSkill", "TraceAnalysisSkill", "LogAnalysisSkill",
                                "MetricCheckSkill", "GraphAnalysisSkill",
                                "RootCauseSkill", "ImpactAnalysisSkill"):
            yield ("call_graph", DiagnosisMessage(
                role="assistant",
                type="call_graph",
                call_graph=_build_call_graph(ctx),
            ))

    rc = ctx.root_cause_result
    impact = ctx.impact_result
    graph = ctx.graph_result
    report = ctx.report_result
    trace = ctx.trace_result
    log = ctx.log_result
    metric = ctx.metric_result

    call_graph = _build_call_graph(ctx)

    evidence_chain = [
        f"Trace 证据：traceId={trace.get('trace_id')}，调用链 {trace.get('service_call')}",
        f"Trace 证据：识别 {len(trace.get('root_candidates', []))} 个调用链根因候选",
        f"Log 证据：识别 {len(log.get('root_candidates', []))} 个日志根因候选，传播性日志 {len(log.get('propagation_logs', []))} 条",
        f"Metric 证据：{metric.get('conclusion', '未发现资源异常')}，指标候选 {len(metric.get('metric_root_candidates', []))} 个",
        f"根因评分：{rc.get('scoring_reason', rc.get('root_cause_reason', ''))}",
        "MModel 本体证据：通过轻量本体配置和绑定规则，将 trace/log/metric 映射到 Service、Instance、Interface 和 BusinessFlow",
    ]

    summary = DiagnosisSummary(
        root_cause_service=rc.get("root_cause_service") or "",
        root_cause_api=rc.get("root_cause_api") or "",
        root_cause_type=rc.get("root_cause_type") or "未知异常类型",
        exception_type=rc.get("exception_type") or "",
        bad_parameter=rc.get("bad_param") or "",
        impact_api=api,
        business_impact=impact.get("affected_business", []),
    )

    final_report = report.get("report", "")
    diagnosis_explain = report.get("object_centered_explain", {}) if isinstance(report, dict) else {}
    session = update_session_from_context(
        session,
        ctx,
        user_message=user_message,
        assistant_message=final_report,
        store=session_store,
    )

    # yield final report message
    yield ("report", DiagnosisMessage(
        role="assistant",
        type="report",
        content=final_report,
    ))

    # yield done with full response (for non-SSE callers)
    yield ("done", DiagnosisResponse(
        case_id=case_id or "evaluation-case",
        summary=summary,
        skills=skill_results,
        call_graph=call_graph,
        evidence_chain=evidence_chain,
        final_report=final_report,
        messages=_build_messages(api, time, symptom, skill_results, final_report),
        session_id=session.session_id,
        mode=mode,
        intent=intent_decision.intent,
        executed_skills=[skill_result_to_tool_key(result) for result in skill_results],
        answer=final_report,
        evidence_refs={
            "evidence_chain": evidence_chain,
            "reasoning_chain": report.get("reasoning_chain", {}) if isinstance(report, dict) else {},
        },
        diagnosis_explain=diagnosis_explain,
        current_focus=session.current_focus.to_dict(),
        resolved_context=resolved_context,
        memory_summary=memory_summary(session),
        data_source_status=get_data_source_status(),
    ))


def _build_messages(
    api: str, time: str, symptom: str,
    skill_results: list, final_report: str,
) -> list[DiagnosisMessage]:
    msgs: list[DiagnosisMessage] = []

    # 1. User message (exactly once)
    msgs.append(DiagnosisMessage(
        role="user",
        type="text",
        content=f"{time}，{api} 接口出现 {symptom}，请分析根因和影响面。",
    ))

    # 2. Assistant opening
    msgs.append(DiagnosisMessage(
        role="assistant",
        type="text",
        content="好的，我将按照系统化故障排查流程进行分析，依次执行 trace 分析、实体绑定、日志确认、指标验证、关系图查询、根因定位、影响面分析和报告生成。",
    ))

    # 3. One message per skill — frontend shows running then success
    for sr in skill_results:
        msgs.append(DiagnosisMessage(
            role="assistant",
            type="skill_call",
            skill_name=sr.skill_name,
            tool_name=sr.tool_name,
            status=sr.status,
            summary=sr.summary,
            duration_ms=sr.duration_ms,
            input=sr.input,
            output=sr.output,
            evidence=sr.evidence,
            execution_log=sr.execution_log,
            explanation=sr.explanation,
        ))

    # 4. Final report message
    msgs.append(DiagnosisMessage(
        role="assistant",
        type="report",
        content=final_report,
    ))

    return msgs
