"""
Skill Registry: declares meta-information for all 8 MModel diagnosis Skills.

This module provides a read-only, JSON-serializable registry of every Skill
so that LLM prompts can include structured descriptions of available tools.

No Skill is imported or executed here. No data files are read.

Public API:
  get_skill_registry()              -> dict[str, dict]
  get_skill_schema(skill_name: str) -> dict | None
  list_skill_names()                -> list[str]
  format_skill_registry_for_llm()   -> str
"""
from __future__ import annotations
from typing import Any

# ---------------------------------------------------------------------------
# Registry data — ordered by default execution pipeline
# ---------------------------------------------------------------------------

_REGISTRY: list[dict[str, Any]] = [
    {
        "name": "alert_context",
        "tool_key": "set_time_range",
        "display_name": "告警上下文构建",
        "description": "将原始故障告警（接口、时间、现象）转换为统一的诊断查询上下文，确定排查时间窗口。",
        "when_to_use": "诊断流水线第一步，始终执行。用于锁定故障时间范围和目标接口。",
        "input_schema": {
            "api": "string — 故障接口路径，如 /product/getOrderById",
            "time": "string — 告警时间，如 2026-04-10 10:51:14",
            "symptom": "string — 故障现象描述，如 接口 500 报错",
        },
        "output_schema": {
            "query_context.alert_api": "string — 目标接口",
            "query_context.alert_time": "string — 告警时间",
            "query_context.symptom": "string — 故障现象",
            "query_context.time_window.start": "string — 查询起始时间",
            "query_context.time_window.end": "string — 查询截止时间",
        },
        "dependencies": [],
        "evidence_fields": ["query_context.alert_api", "query_context.time_window"],
    },
    {
        "name": "trace",
        "tool_key": "analyze_trace",
        "display_name": "调用链分析",
        "description": "读取 trace 数据，解析调用链 Span，识别异常传播路径、首次异常节点、异常类型及问题参数。",
        "when_to_use": "在告警上下文构建后执行。用于识别调用链中哪个服务/接口最先出错，以及出错时的请求参数。",
        "input_schema": {
            "ctx.api": "string — 来自 alert_context 的目标接口",
            "ctx.query_context": "dict — 来自 alert_context 的查询上下文",
        },
        "output_schema": {
            "trace_id": "string — Trace ID",
            "call_path": "list[string] — 调用链路径（serviceName: spanName）",
            "abnormal_spans": "list[dict] — 状态码为 500 或 status=2 的 Span 列表",
            "first_error_service": "string — 首次出错的服务名",
            "first_error_api": "string — 首次出错的接口名",
            "first_error_exception": "string — 首次出错的异常类型",
            "bad_parameter": "string | null — 触发异常的请求参数值",
            "summary": "string — 一句话摘要",
        },
        "dependencies": ["alert_context"],
        "evidence_fields": ["trace_id", "first_error_service", "first_error_exception", "bad_parameter"],
    },
    {
        "name": "entity_binding",
        "tool_key": "bind_entities",
        "display_name": "实体绑定",
        "description": "将 trace/log/metric 中的字段按照本体配置（runtime_domain_model.yaml）和绑定规则（binding_rules.yaml）映射到 MModel 实体，如 Service、Instance、Interface、BusinessFlow。",
        "when_to_use": "在告警上下文构建后立即执行。对象中心化流程中，先识别实体再按实体收集证据。",
        "input_schema": {
            "ctx.trace_result": "dict — 来自 trace 的分析结果",
            "binding_rules.yaml": "规则配置文件（自动读取）",
            "runtime_domain_model.yaml": "本体配置文件（自动读取）",
        },
        "output_schema": {
            "services": "list[string] — 识别到的服务名列表",
            "instances": "list[string] — 识别到的实例名列表",
            "interfaces": "list[string] — 识别到的接口名列表",
            "containers": "list[string] — 识别到的容器名列表",
            "entity_types": "list[string] — 本体实体类型",
            "binding_rules_applied": "list[string] — 应用的绑定规则名称",
        },
        "dependencies": ["alert_context"],
        "evidence_fields": ["services", "instances", "interfaces"],
    },
    {
        "name": "log",
        "tool_key": "analyze_log",
        "display_name": "日志分析",
        "description": "读取 log 数据，定位 ERROR 级别日志，提取异常类型、错误参数、上游服务和下游 URL 等关键证据。",
        "when_to_use": "在 Trace 分析后执行，用于从日志角度确认异常语义，尤其是 FeignException 传播路径和异常参数。",
        "input_schema": {
            "ctx.trace_result": "dict — 来自 trace 的分析结果（提供候选服务和参数）",
        },
        "output_schema": {
            "upstream_service": "string — 出现 FeignException 的上游服务名",
            "upstream_error_type": "string — 上游异常类型",
            "downstream_url": "string — Feign 调用的下游 URL",
            "error_param": "string | null — 提取到的异常参数值",
            "log_evidence": "list[string] — 关键日志证据片段",
            "summary": "string — 一句话摘要",
        },
        "dependencies": ["alert_context", "trace"],
        "evidence_fields": ["upstream_service", "downstream_url", "error_param", "log_evidence"],
    },
    {
        "name": "metric",
        "tool_key": "check_metrics",
        "display_name": "指标检查",
        "description": "读取 metric 数据，核查服务容器运行指标，排除 CPU/内存/延迟等资源类异常。",
        "when_to_use": "在日志分析后执行，用于排除资源类问题，为根因推断提供反向证据（确认非资源问题）。",
        "input_schema": {
            "ctx.entity_result": "dict — 来自 entity_binding 的服务/实例列表（可选）",
        },
        "output_schema": {
            "checked_metrics": "list[dict] — 已查询的指标列表，含 metric_name/service/container/unit",
            "services_checked": "list[string] — 已检查的服务名",
            "conclusion": "string — 资源检查结论",
            "summary": "string — 一句话摘要",
        },
        "dependencies": ["alert_context"],
        "evidence_fields": ["checked_metrics", "conclusion"],
    },
    {
        "name": "graph",
        "tool_key": "analyze_graph",
        "display_name": "关系图分析",
        "description": "基于 MModel 本体（runtime_domain_model.yaml）和 trace 调用关系构建服务调用图，查询服务依赖拓扑，为根因传播和影响面分析提供图结构支撑。",
        "when_to_use": "在实体绑定后执行，用于构建服务调用拓扑图，供根因传播路径推断和影响面分析使用。",
        "input_schema": {
            "ctx.trace_result": "dict — 来自 trace 的首次异常服务",
            "ctx.entity_result": "dict — 来自 entity_binding 的服务列表",
        },
        "output_schema": {
            "nodes": "list[dict] — 图节点，含 id/label/type/status",
            "edges": "list[dict] — 图边，含 source/target/label",
            "engine_stats": "dict — 图引擎统计，含 nodes/edges 数量",
            "summary": "string — 一句话摘要",
        },
        "dependencies": ["alert_context", "entity_binding"],
        "evidence_fields": ["nodes", "edges"],
    },
    {
        "name": "root_cause",
        "tool_key": "infer_root_cause",
        "display_name": "根因定位",
        "description": "综合 trace/log/metric 证据，按照根因规则（root_cause_rules.yaml）推断根因服务、根因接口、异常类型和异常参数。",
        "when_to_use": "在 trace、log、metric、graph 分析完成后执行。是诊断链路的核心推断步骤。",
        "input_schema": {
            "ctx.trace_result": "dict — 来自 trace，包含 first_error_service/first_error_exception",
            "ctx.log_result": "dict — 来自 log，包含 upstream_service/upstream_error_type",
            "ctx.metric_result": "dict — 来自 metric，包含 conclusion",
            "root_cause_rules.yaml": "规则配置文件（自动读取）",
        },
        "output_schema": {
            "root_cause_service": "string — 根因服务名",
            "root_cause_api": "string — 根因接口名",
            "root_cause_type": "string — 根因类型描述",
            "exception_type": "string — 异常类型（如 NumberFormatException）",
            "bad_param": "string | null — 触发异常的参数值",
            "rule_matched": "string — 命中的根因规则名",
            "evidence_summary": "string — 证据摘要",
            "summary": "string — 一句话摘要",
        },
        "dependencies": ["alert_context", "trace", "log", "metric", "graph"],
        "evidence_fields": ["root_cause_service", "root_cause_api", "exception_type", "bad_param", "rule_matched"],
    },
    {
        "name": "impact",
        "tool_key": "analyze_impact",
        "display_name": "影响面分析",
        "description": "从根因服务出发，沿服务调用图向上推导影响范围，并基于 trace/log/metric 聚合可观测业务影响。",
        "when_to_use": "在根因定位后执行，用于评估故障的传播范围和业务影响。",
        "input_schema": {
            "ctx.root_cause_result": "dict — 来自 root_cause，包含 root_cause_service",
            "ctx.graph_result": "dict — 来自 graph，包含 call_edges/edges",
        },
        "output_schema": {
            "affected_services": "list[string] — 受影响服务名列表",
            "affected_apis": "list[string] — 受影响接口列表",
            "affected_business": "list[string] — 受影响业务流程列表",
            "business_impact": "dict — 从 trace/log/metric 推导的订单、交易、用户、金额影响及证据链接",
            "summary": "string — 一句话摘要",
        },
        "dependencies": ["alert_context", "trace", "graph", "root_cause"],
        "evidence_fields": ["affected_services", "affected_apis", "affected_business", "business_impact"],
    },
]

# Build lookup index by both `name` and `tool_key`
_BY_NAME: dict[str, dict[str, Any]] = {}
for _s in _REGISTRY:
    _BY_NAME[_s["name"]] = _s
    _BY_NAME[_s["tool_key"]] = _s


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_skill_registry() -> dict[str, dict[str, Any]]:
    """Return complete skill registry keyed by canonical `name`."""
    return {s["name"]: s for s in _REGISTRY}


def get_skill_schema(skill_name: str) -> dict[str, Any] | None:
    """
    Return schema for a single skill.
    Accepts both canonical name (e.g. 'trace') and tool_key (e.g. 'analyze_trace').
    Returns None if not found.
    """
    return _BY_NAME.get(skill_name)


def list_skill_names() -> list[str]:
    """Return canonical skill names in default execution order."""
    return [s["name"] for s in _REGISTRY]


def format_skill_registry_for_llm() -> str:
    """
    Return a concise text summary of all Skills suitable for inclusion in an LLM prompt.
    Output is ordered by default execution pipeline, ≤1500 characters.
    """
    lines: list[str] = ["## 可用 Skill 列表（按执行顺序）\n"]
    for s in _REGISTRY:
        deps = "、".join(s["dependencies"]) if s["dependencies"] else "无"
        in_keys = "、".join(list(s["input_schema"].keys())[:2])
        out_keys = "、".join(list(s["output_schema"].keys())[:3])
        lines.append(
            f"- **{s['tool_key']}**（{s['display_name']}）：{s['description']}"
            f"  适用：{s['when_to_use']}"
            f"  输入：{in_keys}  输出：{out_keys}  依赖：{deps}"
        )
    return "\n".join(lines)
