"""
LLMDiagnosisOrchestrator: lightweight agentic streaming diagnosis.

Responsibilities:
  1. Receive user question.
  2. Stream LLM intro analysis.
  3. Call LLM to generate Skill execution plan v2 (strict JSON array).
  4. Validate plan (whitelist + dependencies + args); fall back to DEFAULT_PLAN on any error.
  5. Execute Skills in plan order using existing Skill instances.
  6. Stream LLM pre/post Skill explanations.
  7. Collect Skill results.
  8. Execute ReportSkill last.
  9. Yield SSE-compatible dicts to the router.

Does NOT modify any Skill's internal logic.
Does NOT call LLM inside any Skill.

Plan format (v2):
  [{"skill": "<tool_key>", "args": {...}}, ...]
  - skill must be a key in _SKILL_REGISTRY (tool_key values)
  - args must be a dict; only fields declared in registry input_schema are allowed
  - dangerous fields (file_path, command, sql, shell, url) are always stripped
"""
from __future__ import annotations

import json
import logging
import threading
import time as _time
from collections.abc import Iterator
from typing import Any

from app.adapters.local_json_adapter import resolve_request_context
from app.adapters.llm_provider import get_llm_provider
from app.models.context import DiagnosisContext
from app.models.context_summary import get_mmodel_context_summary, format_mmodel_context_for_llm
from app.skills.registry import format_skill_registry_for_llm, get_skill_registry, get_skill_schema
from app.skills.alert_context_skill import AlertContextSkill
from app.skills.trace_analysis_skill import TraceAnalysisSkill
from app.skills.entity_binding_skill import EntityBindingSkill
from app.skills.log_analysis_skill import LogAnalysisSkill
from app.skills.metric_check_skill import MetricCheckSkill
from app.skills.graph_analysis_skill import GraphAnalysisSkill
from app.skills.root_cause_skill import RootCauseSkill
from app.skills.impact_analysis_skill import ImpactAnalysisSkill
from app.skills.report_skill import ReportSkill
from app.orchestrator.diagnosis_orchestrator import _build_call_graph
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
from app.adapters.observability_adapter import clear_data_source_warnings, get_data_source_status

logger = logging.getLogger(__name__)

# Demo-only pacing so the first assistant response does not look mocked.
# Remove or disable this before production rollout.
_DEMO_INITIAL_LLM_DELAY_SECONDS = 2.0

# ---------------------------------------------------------------------------
# Streaming helpers
# ---------------------------------------------------------------------------

def _stream_text_chars(text: str, delay: float = 0.02) -> Iterator[dict]:
    """Yield assistant_delta events character-by-character to simulate streaming."""
    for char in text:
        yield {"type": "assistant_delta", "content": char}
        _time.sleep(delay)
    yield {"type": "assistant_message_done"}


def _stream_replace_text_chars(text: str, delay: float = 0.035, done: bool = True) -> Iterator[dict]:
    """Replace the current assistant status line, then stream the new text."""
    yield {"type": "assistant_replace", "content": ""}
    for char in text:
        yield {"type": "assistant_delta", "content": char}
        _time.sleep(delay)
    if done:
        yield {"type": "assistant_message_done"}

# ---------------------------------------------------------------------------
# Skill whitelist — only these tool names are allowed in LLM-generated plans
# ---------------------------------------------------------------------------
_SKILL_REGISTRY: dict[str, Any] = {
    "set_time_range":   AlertContextSkill(),
    "analyze_trace":    TraceAnalysisSkill(),
    "bind_entities":    EntityBindingSkill(),
    "analyze_log":      LogAnalysisSkill(),
    "check_metrics":    MetricCheckSkill(),
    "analyze_graph":    GraphAnalysisSkill(),
    "infer_root_cause": RootCauseSkill(),
    "analyze_impact":   ImpactAnalysisSkill(),
    "generate_report":  ReportSkill(),
}

_DEFAULT_PLAN = [
    "set_time_range",
    "bind_entities",
    "analyze_trace",
    "analyze_log",
    "check_metrics",
    "analyze_graph",
    "infer_root_cause",
    "analyze_impact",
    "generate_report",
]

_SKILL_TITLES: dict[str, str] = {
    "set_time_range":   "告警上下文构建",
    "analyze_trace":    "Trace 分析",
    "bind_entities":    "实体绑定",
    "analyze_log":      "日志分析",
    "check_metrics":    "指标检查",
    "analyze_graph":    "关系图分析",
    "infer_root_cause": "根因推断",
    "analyze_impact":   "影响面分析",
    "generate_report":  "诊断报告生成",
}

# Skills required for a meaningful diagnosis — always auto-inserted if missing
_REQUIRED_SKILLS = ("set_time_range", "analyze_trace", "analyze_log", "analyze_graph", "infer_root_cause", "generate_report")

# Dangerous arg field names that LLM is never allowed to inject regardless of schema
_DANGEROUS_ARG_FIELDS = frozenset({"file_path", "command", "sql", "shell", "url", "exec", "eval", "path", "filepath"})


# ---------------------------------------------------------------------------
# Plan v2: normalize / validate / default  (new format: list of {skill, args})
# ---------------------------------------------------------------------------

def get_default_plan() -> list[dict]:
    """Return the fixed 8+1 Skill default plan as list[{skill, args}]."""
    return [{"skill": k, "args": {}} for k in _DEFAULT_PLAN]


def normalize_llm_plan(raw_text: str) -> list[dict]:
    """
    Parse raw LLM output into list[{skill, args}].
    Accepts both the new array format and the old {plan:[...]} wrapper.
    Strips markdown fences. Returns [] on any parse error.
    """
    if not raw_text or not raw_text.strip():
        return []
    try:
        stripped = raw_text.strip()
        # Strip markdown code fences
        if stripped.startswith("```"):
            stripped = "\n".join(
                line for line in stripped.splitlines()
                if not line.strip().startswith("```")
            ).strip()
        data = json.loads(stripped)
        # New format: JSON array
        if isinstance(data, list):
            return data
        # Old format compatibility: {"plan": [...]}
        if isinstance(data, dict) and "plan" in data:
            items = data["plan"]
            # Old format uses {"skill": key, "reason": ...} — map to new
            result = []
            for item in items:
                if isinstance(item, dict) and item.get("skill"):
                    result.append({"skill": item["skill"], "args": item.get("args", {})})
            return result
    except Exception as e:
        logger.debug("[PlanV2] normalize_llm_plan parse error: %s", e)
    return []


def _sanitize_args(skill_key: str, raw_args: dict) -> dict:
    """
    Return a safe subset of raw_args.
    - Only keep fields declared in the skill's registry input_schema.
    - Always strip _DANGEROUS_ARG_FIELDS.
    - Ensure result is a plain dict of scalar-safe values.
    """
    schema_info = get_skill_schema(skill_key)
    if not schema_info:
        return {}
    allowed_keys = set(schema_info.get("input_schema", {}).keys()) - _DANGEROUS_ARG_FIELDS
    return {
        k: v for k, v in raw_args.items()
        if k in allowed_keys and k not in _DANGEROUS_ARG_FIELDS
        and isinstance(v, (str, int, float, bool, type(None)))
    }


def validate_skill_plan(plan: list[dict]) -> tuple[bool, str]:
    """
    Validate a normalized plan list[{skill, args}].
    Returns (True, "") on success or (False, reason) on failure.
    Checks:
      - plan is a non-empty list
      - each item has skill (str) and args (dict)
      - skill is in _SKILL_REGISTRY whitelist
      - no duplicate skills (except generate_report)
      - dependencies declared in registry are satisfied by earlier skills
      - at least the core required skills are present (or can be auto-fixed)
    """
    if not isinstance(plan, list) or len(plan) == 0:
        return False, "plan is empty or not a list"

    seen_skills: list[str] = []
    for i, item in enumerate(plan):
        if not isinstance(item, dict):
            return False, f"item[{i}] is not a dict"
        skill = item.get("skill")
        args = item.get("args")
        if not isinstance(skill, str) or not skill:
            return False, f"item[{i}] missing valid skill"
        if skill not in _SKILL_REGISTRY:
            return False, f"skill '{skill}' not in whitelist"
        if not isinstance(args, dict):
            return False, f"item[{i}].args is not a dict"
        # Dependency check against registry
        schema = get_skill_schema(skill)
        if schema:
            for dep_name in schema.get("dependencies", []):
                # Convert canonical name → tool_key for comparison
                dep_schema = get_skill_schema(dep_name)
                dep_tool_key = dep_schema["tool_key"] if dep_schema else dep_name
                if dep_tool_key not in seen_skills:
                    return False, f"skill '{skill}' requires '{dep_tool_key}' to run first"
        seen_skills.append(skill)

    skill_keys = [item["skill"] for item in plan]
    # Check core required skills present
    for req in _REQUIRED_SKILLS:
        if req not in skill_keys:
            return False, f"required skill '{req}' is missing from plan"

    return True, ""


def _build_validated_plan(raw_text: str) -> tuple[list[str], dict[str, dict], str]:
    """
    Parse, validate and return the final skill execution order + args map.
    Returns (skill_key_list, args_map, source) where source is 'llm' or 'default'.
    Falls back to DEFAULT_PLAN on any validation failure.
    """
    plan = normalize_llm_plan(raw_text)
    if plan:
        ok, reason = validate_skill_plan(plan)
        if ok:
            skill_keys = [item["skill"] for item in plan]
            args_map = {
                item["skill"]: _sanitize_args(item["skill"], item.get("args") or {})
                for item in plan
            }
            logger.info("[PlanV2] LLM plan validated OK: %s", skill_keys)
            return skill_keys, args_map, "llm"
        else:
            logger.warning("[PlanV2] LLM plan invalid (%s), falling back to DEFAULT_PLAN", reason)
    else:
        logger.warning("[PlanV2] LLM plan empty/unparseable, falling back to DEFAULT_PLAN")

    return list(_DEFAULT_PLAN), {}, "default"


# ---------------------------------------------------------------------------
# Plan validation (legacy — kept for _parse_plan_from_llm compatibility)
# ---------------------------------------------------------------------------

def _validate_plan(raw_plan: list[dict]) -> list[str]:
    """
    Validate the raw plan from LLM, return ordered list of skill keys.
    - Filter to whitelist only.
    - Ensure set_time_range is first.
    - Ensure analyze_trace, analyze_log, infer_root_cause are present.
    - Ensure generate_report is last.
    - Fall back to default if empty after filter.
    """
    keys = [item.get("skill", "") for item in raw_plan if item.get("skill") in _SKILL_REGISTRY]
    # Remove duplicates, preserve order
    seen: set[str] = set()
    deduped: list[str] = []
    for k in keys:
        if k not in seen:
            seen.add(k)
            deduped.append(k)

    if not deduped:
        logger.warning("[LLMOrchestrator] 计划为空或全部非法，回退默认 9 Skill")
        return list(_DEFAULT_PLAN)

    # Ensure set_time_range is first
    if "set_time_range" in deduped:
        deduped.remove("set_time_range")
    deduped.insert(0, "set_time_range")

    # Ensure analyze_trace, analyze_log, analyze_graph are present
    for required in ("analyze_trace", "analyze_log", "analyze_graph"):
        if required not in deduped:
            logger.warning("[LLMOrchestrator] 计划缺少 %s，自动补入", required)
            # Insert before infer_root_cause if it exists, else before generate_report
            anchor = "infer_root_cause" if "infer_root_cause" in deduped else "generate_report"
            if anchor in deduped:
                deduped.insert(deduped.index(anchor), required)
            else:
                deduped.append(required)

    # Ensure infer_root_cause is present
    if "infer_root_cause" not in deduped:
        logger.warning("[LLMOrchestrator] 计划缺少 infer_root_cause，自动补入")
        deduped.append("infer_root_cause")

    # Ensure generate_report is last
    if "generate_report" in deduped:
        deduped.remove("generate_report")
    deduped.append("generate_report")

    return deduped


def _parse_plan_from_llm(text: str) -> tuple[str, list[str]]:
    """
    Parse LLM JSON plan response.
    Returns (intro, [skill_key, ...]).
    Falls back to defaults on any parse error.
    """
    try:
        # LLM may wrap JSON in markdown code fences — strip them
        stripped = text.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            stripped = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            )
        data = json.loads(stripped)
        intro: str = data.get("intro", "好的，我将开始系统化故障排查。")
        raw_plan: list[dict] = data.get("plan", [])
        logger.info("[LLMOrchestrator] LLM 计划解析成功，原始 plan 长度=%d", len(raw_plan))
        return intro, _validate_plan(raw_plan)
    except Exception as e:
        logger.error("[LLMOrchestrator] 计划 JSON 解析失败，回退默认顺序: %s", e)
        return "好的，我将开始系统化故障排查。", list(_DEFAULT_PLAN)


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

_PLAN_SYSTEM = (
    "你是一名可观测性智能诊断专家。"
    "你只能从以下 Skill 白名单中选择：\n"
    "set_time_range, analyze_trace, bind_entities, analyze_log, "
    "check_metrics, analyze_graph, infer_root_cause, analyze_impact, generate_report\n"
    "请严格输出 JSON，不要添加任何 markdown 格式或额外说明。"
)

_INTRO_SYSTEM = "你是一名可观测性智能诊断专家，请用中文简洁描述排查思路，不超过40字。"


def _build_intro_prompt(api: str, time: str, symptom: str) -> str:
    return (
        f"用户报告：接口 {api} 在 {time} 出现 {symptom}。"
        "请用一句话（40字以内）描述你的排查思路，不要生成 JSON，直接输出中文文字。"
    )


def _build_plan_prompt(api: str, time: str, symptom: str) -> str:
    skill_summary = format_skill_registry_for_llm()
    # Append MModel context summary so the LLM understands current entities/relations/evidence
    try:
        ctx_dict = get_mmodel_context_summary(user_query=f"{api} 出现 {symptom}")
        ctx_text = format_mmodel_context_for_llm(ctx_dict)
    except Exception:
        ctx_text = ""
    return f"""{skill_summary}

{ctx_text}
用户报告故障如下：
接口：{api}
时间：{time}
现象：{symptom}

请生成诊断计划，严格输出如下 JSON 数组格式（不加 markdown，不加任何额外说明）：
[
  {{"skill": "set_time_range", "args": {{}}}},
  {{"skill": "analyze_trace", "args": {{}}}},
  {{"skill": "analyze_log", "args": {{}}}},
  {{"skill": "infer_root_cause", "args": {{}}}},
  {{"skill": "generate_report", "args": {{}}}}
]

约束（违反则视为无效计划）：
1. 只能使用白名单 Skill：set_time_range, analyze_trace, bind_entities, analyze_log, check_metrics, analyze_graph, infer_root_cause, analyze_impact, generate_report。
2. set_time_range 必须是第一个。
3. analyze_trace、analyze_log、analyze_graph 和 infer_root_cause 必须包含。
4. generate_report 必须是最后一个。
5. args 只能包含 Skill schema 中声明的字段，不得包含危险字段（file_path, command, sql, shell, url）。
6. 只输出 JSON 数组，不要输出任何其他内容。"""


def _build_pre_skill_prompt(skill_key: str, reason: str, api: str, symptom: str) -> str:
    title = _SKILL_TITLES.get(skill_key, skill_key)
    return (
        f"即将执行【{title}】。"
        f"理由：{reason}。"
        "请用一句话（20字以内）向用户说明现在要做什么，口吻自然，不要重复原因原文。"
        f"背景：{api} 出现 {symptom}。"
    )


def _build_post_skill_prompt(skill_key: str, summary: str, api: str) -> str:
    title = _SKILL_TITLES.get(skill_key, skill_key)
    return (
        f"刚完成【{title}】，结果摘要：{summary}。"
        f"请用 60 字以内向用户说明：发现了什么具体异常/信号、它意味着什么、对定位根因有什么帮助。"
        f"不要只写过渡句，要写出实际发现。"
        f"背景接口：{api}。"
    )


def _fallback_pre_skill_explanation(skill_key: str) -> str:
    title = _SKILL_TITLES.get(skill_key, skill_key)
    fallback_text = {
        "set_time_range": "先锁定问题时间范围，避免混入无关信号。",
        "analyze_trace": "先检查调用链，确认异常从哪里开始传播。",
        "bind_entities": "先做实体绑定，统一后续证据关联口径。",
        "analyze_log": "先核对错误日志，提取异常类型和关键信息。",
        "check_metrics": "先看核心指标，排除资源和性能异常。",
        "analyze_graph": "先梳理依赖关系，确认异常传播路径。",
        "infer_root_cause": "开始汇总现有证据，收敛最可能的根因。",
        "analyze_impact": "开始评估影响范围，确认受波及的链路。",
    }
    return fallback_text.get(skill_key, f"准备执行{title}，补充当前诊断证据。")


def _fallback_post_skill_explanation(skill_key: str) -> str:
    title = _SKILL_TITLES.get(skill_key, skill_key)
    fallback_text = {
        "set_time_range": "故障时间窗口已锁定，排除了无关时段的噪声数据，下一步将基于该窗口拉取调用链证据。",
        "analyze_trace": "已从调用链中识别出异常 span 和首个出错节点，初步锁定异常传播起点，接下来交叉验证日志侧证据。",
        "bind_entities": "已将可观测数据中的服务、实例、接口绑定到 MModel 本体实体，后续证据可以按实体统一归并和溯源。",
        "analyze_log": "已提取关键错误日志和异常类型，日志侧线索与 trace 证据形成互补，继续核对指标信号。",
        "check_metrics": "已检查核心指标，识别出偏离阈值的异常指标及其归属服务，为根因判定提供了资源层面的证据。",
        "analyze_graph": "已构建当前故障相关的运行时依赖图，确认了异常传播路径和关键节点，继续收敛根因判断。",
        "infer_root_cause": "已汇总 trace、log、metric、graph 多源证据并完成评分，根因候选已收敛，接着评估影响范围。",
        "analyze_impact": "已分析受影响的服务、接口和业务链路，明确了故障波及面，接下来生成最终诊断报告。",
    }
    return fallback_text.get(skill_key, f"{title}已完成，已从中提取关键证据，继续推进诊断。")


def _resolve_short_explanation_text(
    llm: Any,
    prompt: str,
    fallback_text: str,
    stage: str,
    skill_key: str,
) -> str:
    try:
        raw_text = llm.generate_text(prompt)
    except Exception as exc:
        logger.warning(
            "[ReAct][ExplanationFallback] stage=%s skill=%s source=fallback_rule reason=llm_exception error=%s",
            stage, skill_key, exc,
        )
        return fallback_text

    text = " ".join((raw_text or "").strip().split())
    if not text:
        logger.info(
            "[ReAct][ExplanationFallback] stage=%s skill=%s source=fallback_rule reason=empty_text",
            stage, skill_key,
        )
        return fallback_text

    try:
        parsed = json.loads(text)
    except Exception:
        logger.info(
            "[ReAct][Explanation] stage=%s skill=%s source=llm_non_stream len=%d",
            stage, skill_key, len(text),
        )
        return text

    if isinstance(parsed, (dict, list)):
        logger.info(
            "[ReAct][ExplanationFallback] stage=%s skill=%s source=fallback_rule reason=json_payload",
            stage, skill_key,
        )
        return fallback_text

    logger.info(
        "[ReAct][Explanation] stage=%s skill=%s source=llm_non_stream len=%d",
        stage, skill_key, len(text),
    )
    return text


# ---------------------------------------------------------------------------
# ReAct Agent Loop
# ---------------------------------------------------------------------------

_REACT_MAX_STEPS = 10

_REACT_SYSTEM = (
    "你是 MModel ReAct Skill Agent。"
    "你的任务是每次只选择一个 next_skill，或选择 finish。"
    "只能从可用 Skill 列表中选择，必须遵守 dependencies。"
    "必须输出纯 JSON，不要输出 markdown，不要输出解释性文字。"
    "args 只能使用 schema 中允许的字段。"
    "如果证据不足，继续选择合适 Skill；如果证据充分，输出 finish。"
)

# Core skills that must be done before finish is honoured
_CORE_SKILLS = frozenset({
    "analyze_trace",
    "bind_entities",
    "analyze_log",
    "check_metrics",
    "analyze_graph",
    "infer_root_cause",
})

# ---------------------------------------------------------------------------
# Error handling / retry / timeout constants
# ---------------------------------------------------------------------------
_MAX_RETRY_PER_SKILL = 1          # each skill may be retried at most this many times
_SKILL_TIMEOUT_SECONDS = 15       # soft timeout: warn + mark failed if exceeded


def build_react_decision_prompt(
    api: str,
    time: str,
    symptom: str,
    executed: list[str],
    results_summary: list[str],
    available: list[str],
    ctx_summary: str,
    error_context: list[str] | None = None,
) -> str:
    skill_summary = format_skill_registry_for_llm()
    executed_str = ", ".join(executed) if executed else "（无）"
    available_str = ", ".join(available) if available else "（无）"
    results_str = "\n".join(f"- {s}" for s in results_summary[-3:]) if results_summary else "（无）"
    error_str = ""
    if error_context:
        error_str = "\n最近 Skill 执行失败摘要：\n" + "\n".join(f"- {e}" for e in error_context[-3:])
    return f"""{skill_summary}

MModel 上下文摘要：
{ctx_summary}

用户故障：
接口：{api}
时间：{time}
现象：{symptom}

已执行 Skill：{executed_str}
最近执行结果摘要：
{results_str}{error_str}

当前可用 Skill（未执行或可重试）：{available_str}

请选择下一步，只输出如下 JSON，不加任何解释：

如需执行 Skill：
{{"action": "run_skill", "skill": "<skill_key>", "args": {{}}, "reason": "..."}}

如需重试失败的 Skill：
{{"action": "retry", "skill": "<skill_key>", "args": {{}}, "reason": "..."}}

如证据充分可生成报告：
{{"action": "finish", "reason": "..."}}

约束：
1. skill 必须来自可用 Skill 列表（白名单）。
2. args 只能包含 schema 中声明的字段，不得包含危险字段（file_path, command, sql, shell, url）。
3. 不允许重复执行已成功执行的 Skill。
4. 核心 Skill（analyze_trace, analyze_log, analyze_graph, infer_root_cause）未执行完不得 finish。
5. retry 只能用于之前失败的 Skill，且受最大重试次数限制。
6. 只输出 JSON，不输出任何其他内容。"""


def validate_next_skill(decision: dict, executed_set: set[str], failed_set: set[str] | None = None) -> tuple[bool, str]:
    """Validate a ReAct decision dict. Returns (ok, reason).
    Supports actions: run_skill, retry, finish.
    """
    action = decision.get("action")
    if action not in ("run_skill", "retry", "finish"):
        return False, f"action '{action}' not allowed"
    if action == "finish":
        return True, ""
    skill = decision.get("skill")
    if not isinstance(skill, str) or skill not in _SKILL_REGISTRY:
        return False, f"skill '{skill}' not in whitelist"
    # retry is allowed for skills in failed_set; run_skill must not be already executed
    if action == "run_skill" and skill in executed_set:
        return False, f"skill '{skill}' already executed"
    if action == "retry":
        if failed_set is None or skill not in failed_set:
            return False, f"skill '{skill}' has not failed; cannot retry"
    args = decision.get("args", {})
    if not isinstance(args, dict):
        return False, "args is not a dict"
    schema = get_skill_schema(skill)
    if schema:
        for dep in schema.get("dependencies", []):
            dep_schema = get_skill_schema(dep)
            dep_key = dep_schema["tool_key"] if dep_schema else dep
            if dep_key not in executed_set:
                return False, f"dependency '{dep_key}' not yet executed"
    return True, ""


def decide_next_skill(
    llm: Any,
    api: str,
    time: str,
    symptom: str,
    executed: list[str],
    results_summary: list[str],
    available: list[str],
    ctx_summary: str,
    executed_set: set[str],
    failed_set: set[str] | None = None,
    error_context: list[str] | None = None,
) -> dict | None:
    """
    Call LLM to decide the next skill. Returns a valid decision dict or None.
    Retries once on validation failure.
    """
    prompt = build_react_decision_prompt(api, time, symptom, executed, results_summary, available, ctx_summary, error_context)
    for attempt in range(2):
        try:
            raw = llm.generate_text(prompt, system=_REACT_SYSTEM)
            if not raw or not raw.strip():
                logger.warning("[ReAct] LLM 返回空 (attempt %d)", attempt)
                continue
            stripped = raw.strip()
            if stripped.startswith("```"):
                stripped = "\n".join(
                    l for l in stripped.splitlines() if not l.strip().startswith("```")
                ).strip()
            decision = json.loads(stripped)
            if not isinstance(decision, dict):
                logger.warning("[ReAct] LLM 返回非 dict (attempt %d)", attempt)
                continue
            ok, reason = validate_next_skill(decision, executed_set, failed_set)
            if ok:
                logger.info("[ReAct] 决策有效: action=%s skill=%s", decision.get("action"), decision.get("skill"))
                return decision
            logger.warning("[ReAct] 决策校验失败: %s (attempt %d)", reason, attempt)
        except Exception as e:
            logger.warning("[ReAct] 决策解析异常: %s (attempt %d)", e, attempt)
    return None


def _text_contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _is_weak_trace(ctx: DiagnosisContext) -> bool:
    trace_result = getattr(ctx, "trace_result", None) or {}
    if not trace_result:
        return False
    if not trace_result.get("first_error_service"):
        return True
    span_count = trace_result.get("span_count") or 0
    abnormal_count = len(trace_result.get("abnormal_spans") or [])
    return span_count <= 3 or abnormal_count == 0


def _has_root_evidence(executed_set: set[str], ctx: DiagnosisContext) -> bool:
    required = {"analyze_trace", "analyze_log", "check_metrics", "analyze_graph"}
    if not required <= executed_set:
        return False
    return all(
        getattr(ctx, attr, None)
        for attr in ("trace_result", "log_result", "metric_result", "graph_result")
    )


def _evidence_priority_order(api: str, symptom: str, ctx: DiagnosisContext) -> list[str]:
    """Object-centric priority: always bind entities first, then build graph, then gather evidence."""
    # Build the plan with entity binding immediately after context setup,
    # so that subsequent evidence skills can use entity information.
    base = ["set_time_range", "bind_entities"]
    # Graph builds topology from entities; evidence skills then collect per-entity data
    evidence = ["analyze_graph", "analyze_trace", "analyze_log", "check_metrics"]
    decision = ["infer_root_cause", "analyze_impact"]
    return base + evidence + decision


def plan_next_skill_by_evidence(
    api: str,
    symptom: str,
    executed_set: set[str],
    failed_set: set[str],
    available: list[str],
    ctx: DiagnosisContext,
) -> dict | None:
    """Choose the next skill from symptom class and collected evidence."""
    for skill_key in _evidence_priority_order(api, symptom, ctx):
        if skill_key not in available or skill_key in executed_set or skill_key in failed_set:
            continue
        if skill_key == "infer_root_cause" and not _has_root_evidence(executed_set, ctx):
            continue
        if skill_key == "analyze_impact" and not getattr(ctx, "root_cause_result", None):
            continue
        decision = {
            "action": "run_skill",
            "skill": skill_key,
            "args": {},
            "reason": "基于告警现象和已收集证据选择下一步分析动作。",
        }
        ok, _ = validate_next_skill(decision, executed_set, failed_set)
        if ok:
            return decision

    if _should_allow_finish(ctx, executed_set)[0]:
        return {"action": "finish", "reason": "根因与影响面证据已完成，进入报告生成。"}
    return None


def _determine_next_skill_without_llm(
    executed_set: set[str],
    failed_set: set[str],
    available: list[str],
    ctx: DiagnosisContext,
    api: str,
    symptom: str,
    retry_counts: dict[str, int] | None = None,
) -> dict | None:
    """Choose the next ReAct skill with local deterministic rules.

    This is used only when LLM decision text is unavailable or invalid. It follows
    the existing default skill order, validates dependencies, and never reads
    case-specific answers.
    """
    retry_counts = retry_counts or {}
    local_decision = plan_next_skill_by_evidence(api, symptom, executed_set, failed_set, available, ctx)
    if local_decision is not None:
        return local_decision

    for skill_key in _DEFAULT_PLAN:
        if skill_key == "generate_report":
            continue
        if skill_key not in failed_set:
            continue
        if retry_counts.get(skill_key, 0) >= _MAX_RETRY_PER_SKILL:
            continue
        decision = {
            "action": "retry",
            "skill": skill_key,
            "args": {},
            "reason": "LLM 动态决策暂不可用，已切换为确定性诊断策略，诊断继续。",
        }
        ok, _ = validate_next_skill(decision, executed_set, failed_set)
        if ok:
            return decision

    for skill_key in _DEFAULT_PLAN:
        if skill_key == "generate_report":
            break
        if skill_key not in available or skill_key in executed_set or skill_key in failed_set:
            continue
        if skill_key == "infer_root_cause" and not _has_root_evidence(executed_set, ctx):
            continue
        if skill_key == "analyze_impact" and not getattr(ctx, "root_cause_result", None):
            continue
        decision = {
            "action": "run_skill",
            "skill": skill_key,
            "args": {},
            "reason": "LLM 动态决策暂不可用，已切换为确定性诊断策略，诊断继续。",
        }
        ok, _ = validate_next_skill(decision, executed_set, failed_set)
        if ok:
            return decision

    allowed, _ = _should_allow_finish(ctx, executed_set)
    if allowed:
        return {"action": "finish", "reason": "核心诊断步骤已完成，进入报告生成。"}
    return None


def _run_skill_step(
    skill_key: str,
    sanitized_args: dict,
    ctx: DiagnosisContext,
    llm: Any,
    api: str,
    symptom: str,
    reason: str = "",
) -> Iterator[dict]:
    """Execute one skill with pre/post LLM explanations. Yields SSE dicts. Mutates ctx.
    Last yielded item is a sentinel dict with key '_skill_failed' for the loop to inspect.
    """
    skill = _SKILL_REGISTRY.get(skill_key)
    if skill is None:
        logger.warning("[ReAct] 跳过未知 Skill: %s", skill_key)
        yield {"_skill_failed": True, "_error_type": "UnknownSkill", "_error_message": "unknown skill"}
        return
    title = _SKILL_TITLES.get(skill_key, skill_key)
    if not reason:
        reason = f"执行 {title}"

    def _compact_skill_output() -> dict[str, Any] | None:
        if skill_key == "bind_entities":
            return ctx.entity_result or None
        if skill_key == "analyze_trace":
            trace = ctx.trace_result or {}
            return {
                "trace_id": trace.get("trace_id"),
                "entry_api": trace.get("entry_api"),
                "entry_service": trace.get("entry_service"),
                "service_call": trace.get("service_call"),
                "interface_call": trace.get("interface_call"),
                "first_error_service": trace.get("first_error_service"),
                "first_error_api": trace.get("first_error_api"),
                "first_error_exception": trace.get("first_error_exception"),
            }
        if skill_key == "infer_root_cause":
            rc = ctx.root_cause_result or {}
            return {
                "root_cause_service": rc.get("root_cause_service"),
                "root_cause_component": rc.get("root_cause_component"),
                "root_cause_api": rc.get("root_cause_api"),
                "root_cause_type": rc.get("root_cause_type"),
                "confidence": rc.get("confidence"),
                "is_confirmed": rc.get("is_confirmed"),
                "evidence_chain": rc.get("evidence_chain"),
            }
        if skill_key == "analyze_impact":
            impact = ctx.impact_result or {}
            return {
                "affected_services": impact.get("affected_services"),
                "affected_interfaces": impact.get("affected_interfaces") or impact.get("affected_apis"),
                "affected_business": impact.get("affected_business"),
                "root_cause_service": impact.get("root_cause_service"),
            }
        return None

    # Apply sanitized args to ctx
    for arg_key, arg_val in sanitized_args.items():
        try:
            setattr(ctx, arg_key, arg_val)
        except Exception:
            pass

    yield {"type": "skill_start", "skill": skill_key, "title": title, "reason": reason}
    logger.info("[ReAct] 执行 Skill: %s", skill_key)

    try:
        t0 = _time.monotonic()
        if skill_key == "generate_report":
            report_context = {
                "root_cause": ctx.root_cause_result,
                "impact": ctx.impact_result,
                "trace": ctx.trace_result,
                "log": ctx.log_result,
                "metric": ctx.metric_result,
                "api": api,
                "time": getattr(ctx, "time", ""),
                "symptom": symptom,
                "failed_skills": ctx.failed_skills,
                "evidence_consistency": getattr(ctx, "evidence_consistency", {}),
            }
            try:
                for chunk in llm.stream_report(report_context):
                    yield {"type": "report_delta", "content": chunk}
            except Exception as e:
                logger.error("[ReAct] stream_report 异常: %s", e)
            elapsed_ms = int((_time.monotonic() - t0) * 1000)
            rc = ctx.root_cause_result or {}
            is_confirmed = rc.get("is_confirmed", True)
            if is_confirmed:
                report_summary_text = "Mobile Ops 故障诊断报告已生成，包含故障结论、根因定位、影响面分析和处置建议。"
                skill_done_evidence = [
                    f"根因服务：{rc.get('root_cause_service')}",
                    f"根因接口：{rc.get('root_cause_api')}",
                    f"根因类型：{rc.get('root_cause_type')}",
                ]
                report_summary_payload = f"根因：{rc.get('root_cause_service')} / {rc.get('root_cause_type')}"
            else:
                report_summary_text = "根因未确认（证据冲突），已生成「根因待确认」专项报告，未输出影响面。"
                skill_done_evidence = [
                    f"候选根因服务：{rc.get('root_cause_service')}",
                    f"候选根因类型：{rc.get('root_cause_type')}",
                    f"置信度：{rc.get('confidence')}",
                    "is_confirmed=False — 根因细节不可信，请人工核查",
                ]
                report_summary_payload = f"根因待确认：{rc.get('root_cause_service')} / {rc.get('root_cause_type')}（证据冲突）"
            yield {
                "type": "report_done",
                "report": {"summary": report_summary_payload},
            }
            yield {
                "type": "skill_done",
                "skill": skill_key,
                "result": {
                    "summary": report_summary_text,
                    "evidence": skill_done_evidence,
                    "execution_log": ["汇总所有 Skill 输出", "调用 LLM 流式生成诊断报告", "报告生成完成"],
                    "duration_ms": elapsed_ms,
                },
            }
            yield {"_skill_failed": False}
        else:
            # Soft-timeout: run skill in a thread, wait up to _SKILL_TIMEOUT_SECONDS
            result_holder: list[Any] = []
            error_holder: list[Exception] = []

            def _run():
                try:
                    result_holder.append(skill.run(ctx))
                except Exception as exc:
                    error_holder.append(exc)

            t = threading.Thread(target=_run, daemon=True)
            t.start()
            t.join(timeout=_SKILL_TIMEOUT_SECONDS)
            elapsed_ms = int((_time.monotonic() - t0) * 1000)

            if t.is_alive():
                # Thread still running: soft timeout — mark as failed, log warning
                logger.warning("[ReAct][Timeout] skill=%s elapsed_ms=%d (exceeded %ds)",
                               skill_key, elapsed_ms, _SKILL_TIMEOUT_SECONDS)
                recovery_action = "已标记超时并继续后续可执行分析"
                yield {"type": "assistant_delta", "content": f"{title} 执行超时，已标记为失败并继续分析。"}
                yield {"type": "assistant_message_done"}
                yield {
                    "type": "skill_error",
                    "skill": skill_key,
                    "error": f"TimeoutError: exceeded {_SKILL_TIMEOUT_SECONDS}s",
                    "recovery_action": recovery_action,
                    "result": {"summary": f"执行超时（>{_SKILL_TIMEOUT_SECONDS}s）", "evidence": [], "execution_log": [], "recovery_action": recovery_action},
                }
                yield {"_skill_failed": True, "_error_type": "TimeoutError",
                       "_error_message": f"exceeded {_SKILL_TIMEOUT_SECONDS}s"}
                return

            if error_holder:
                raise error_holder[0]

            result = result_holder[0]
            logger.info("[ReAct] Skill 完成: %s (%d ms)", skill_key, elapsed_ms)
            payload: dict[str, Any] = {
                "type": "skill_done",
                "skill": skill_key,
                "result": {
                    "summary": result.summary,
                    "evidence": result.evidence,
                    "execution_log": result.execution_log,
                    "duration_ms": result.duration_ms,
                    "output": _compact_skill_output(),
                },
            }
            if skill_key == "infer_root_cause":
                rc = ctx.root_cause_result or {}
                is_confirmed = rc.get("is_confirmed", True)
                payload["result"].update({
                    "root_cause_status": "根因已确认" if is_confirmed else "根因待确认",
                    "confidence": rc.get("confidence", "unknown"),
                })
            if skill_key in ("bind_entities", "analyze_trace", "analyze_log", "check_metrics",
                            "analyze_graph", "infer_root_cause", "analyze_impact"):
                cg = _build_call_graph(ctx)
                payload["call_graph"] = cg.model_dump()
            yield payload
            post_prompt = _build_post_skill_prompt(skill_key, result.summary, api)
            post_text = _resolve_short_explanation_text(
                llm,
                post_prompt,
                _fallback_post_skill_explanation(skill_key),
                stage="post",
                skill_key=skill_key,
            )
            yield {"_skill_failed": False, "_post_text": post_text}
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)[:200]
        logger.error("[ReAct][SkillError] skill=%s error_type=%s error_message=%.200s",
                     skill_key, error_type, error_msg)
        yield {"type": "assistant_delta", "content": f"{title} 执行失败，已将错误信息反馈给分析引擎。"}
        yield {"type": "assistant_message_done"}
        recovery_action = "已记录失败并继续后续可执行分析"
        yield {
            "type": "skill_error",
            "skill": skill_key,
            "error": f"{error_type}: {error_msg}",
            "recovery_action": recovery_action,
            "result": {"summary": f"执行失败: {error_msg}", "evidence": [], "execution_log": [], "recovery_action": recovery_action},
        }
        yield {"_skill_failed": True, "_error_type": error_type, "_error_message": error_msg}


def _dispatch_skill_step(
    skill_key: str,
    sanitized_args: dict,
    ctx: DiagnosisContext,
    llm: Any,
    api: str,
    symptom: str,
    reason: str = "",
    sentinel_out: dict | None = None,
) -> Iterator[dict]:
    """
    Wraps _run_skill_step, yields SSE events in real-time and writes the
    failure sentinel into sentinel_out (a mutable dict supplied by the caller).
    sentinel_out will contain: _skill_failed, _error_type, _error_message.
    If sentinel_out is None a local dict is used (sentinel result is discarded).
    """
    if sentinel_out is None:
        sentinel_out = {}
    sentinel_out["_skill_failed"] = False
    for item in _run_skill_step(skill_key, sanitized_args, ctx, llm, api, symptom, reason):
        if "_skill_failed" in item:
            sentinel_out.update(item)
        else:
            yield item


# ---------------------------------------------------------------------------
# Skill Result Summarizer — lightweight, no raw JSON passed to LLM
# ---------------------------------------------------------------------------

def summarize_skill_result(skill_key: str, ctx: DiagnosisContext) -> str:
    """
    Extract a compact text summary (~500 chars max) of the most recent skill
    result from ctx. Never passes raw trace/log/metric JSON to LLM.
    Returns a fallback string on any error so main flow is never interrupted.
    """
    try:
        if skill_key == "set_time_range":
            qc = getattr(ctx, "query_context", {}) or {}
            return (f"接口={qc.get('alert_api','unknown')} "
                    f"时间窗口={qc.get('time_window','unknown')} "
                    f"现象={qc.get('symptom','unknown')}")[:500]
        if skill_key == "analyze_trace":
            tr = getattr(ctx, "trace_result", {}) or {}
            return (f"异常服务={tr.get('error_service','unknown')} "
                    f"状态码={tr.get('status_code','unknown')} "
                    f"首次异常节点={tr.get('first_error_node','unknown')} "
                    f"调用链={str(tr.get('call_chain','unknown'))[:150]}")[:500]
        if skill_key == "bind_entities":
            er = getattr(ctx, "entity_result", {}) or {}
            return (f"识别服务={er.get('services','unknown')} "
                    f"实例={er.get('instances','unknown')} "
                    f"绑定数量={er.get('binding_count','unknown')}")[:500]
        if skill_key == "analyze_log":
            lr = getattr(ctx, "log_result", {}) or {}
            return (f"异常类型={lr.get('exception_type','unknown')} "
                    f"错误服务={lr.get('error_service','unknown')} "
                    f"异常参数={lr.get('bad_param','unknown')}")[:500]
        if skill_key == "check_metrics":
            mr = getattr(ctx, "metric_result", {}) or {}
            return (f"异常指标={mr.get('anomaly_metrics','none')} "
                    f"资源异常={mr.get('resource_anomaly', False)}")[:500]
        if skill_key == "analyze_graph":
            gr = getattr(ctx, "graph_result", {}) or {}
            node_ids = [n.get("id", "?") for n in gr.get("nodes", [])[:6]]
            return (f"关键节点={node_ids} "
                    f"边数={len(gr.get('edges', []))}")[:500]
        if skill_key == "infer_root_cause":
            rc = getattr(ctx, "root_cause_result", {}) or {}
            cons = getattr(ctx, "evidence_consistency", {}) or {}
            conflict_note = f" 证据冲突={cons.get('has_conflict', False)}" if cons else ""
            is_confirmed = rc.get("is_confirmed", True)
            if not is_confirmed:
                return (
                    f"候选根因服务={rc.get('root_cause_service','unknown')} "
                    f"根因类型={rc.get('root_cause_type','unknown')} "
                    f"根因接口={rc.get('root_cause_api','unknown')} "
                    f"置信度={rc.get('confidence','unknown')} "
                    f"已确认=false{conflict_note}"
                )[:500]
            return (f"根因服务={rc.get('root_cause_service','unknown')} "
                    f"根因类型={rc.get('root_cause_type','unknown')} "
                    f"根因接口={rc.get('root_cause_api','unknown')} "
                    f"异常参数={rc.get('bad_param','unknown')} "
                    f"置信度={rc.get('confidence','unknown')} "
                    f"已确认={rc.get('is_confirmed','unknown')}"
                    f"{conflict_note}")[:500]
        if skill_key == "analyze_impact":
            ir = getattr(ctx, "impact_result", {}) or {}
            return (f"影响服务={ir.get('affected_services','unknown')} "
                    f"影响业务={str(ir.get('affected_business','unknown'))[:150]}")[:500]
    except Exception as e:
        logger.debug("[ReAct] summarize_skill_result error for %s: %s", skill_key, e)
    return f"{skill_key}: 摘要不可用"


def _should_allow_finish(ctx: DiagnosisContext, executed_set: set[str]) -> tuple[bool, str]:
    """
    System-side finish gate — prevents LLM from finishing too early.
    Returns (allowed, reason_if_denied).
    """
    if not _has_root_evidence(executed_set, ctx):
        return False, "尚未收集 trace/log/metric/graph 多源证据"
    has_root_cause = ("infer_root_cause" in executed_set or
                      bool(getattr(ctx, "root_cause_result", None)))
    if not has_root_cause:
        return False, "尚未执行根因推断"
    root_cause = getattr(ctx, "root_cause_result", None) or {}
    if root_cause.get("is_confirmed", True):
        has_impact = "analyze_impact" in executed_set or bool(getattr(ctx, "impact_result", None))
        if not has_impact:
            return False, "尚未执行影响面分析"
    return True, ""


def _has_evidence_conflict(ctx: DiagnosisContext) -> bool:
    """Return True if ctx already contains evidence conflicts (not a system failure)."""
    consistency = getattr(ctx, "evidence_consistency", None)
    if consistency and consistency.get("has_conflict"):
        return True
    rc = getattr(ctx, "root_cause_result", None)
    if rc and rc.get("evidence_conflicts"):
        return True
    return False


def _run_default_fallback(
    llm: Any,
    ctx: DiagnosisContext,
    api: str,
    time: str,
    symptom: str,
    already_executed: set[str],
) -> Iterator[dict]:
    """Execute remaining DEFAULT_PLAN skills not yet executed, in default order."""
    for skill_key in _DEFAULT_PLAN:
        if skill_key in already_executed:
            continue
        sentinel: dict = {}
        yield from _dispatch_skill_step(skill_key, {}, ctx, llm, api, symptom, sentinel_out=sentinel)
        if sentinel.get("_skill_failed"):
            logger.warning("[ReAct][Fallback] skill=%s also failed in default fallback", skill_key)


def run_react_loop(
    llm: Any,
    ctx: DiagnosisContext,
    api: str,
    time: str,
    symptom: str,
) -> Iterator[dict]:
    """
    ReAct Agent Loop (Phase 3). Each step: LLM decides next_skill → validate →
    system finish-gate → execute → collect incremental summary → repeat.
    Falls back to _run_default_fallback on consecutive failures.
    Always ends with generate_report.
    Token control: keeps only recent 6 observations, each capped at 500 chars.
    Error handling: per-skill retry limit, soft timeout, error context fed to LLM.
    """
    executed: list[str] = []
    executed_set: set[str] = set()
    # Incremental context — structured for next-round LLM prompt
    observations: list[str] = []   # capped at _REACT_OBS_WINDOW entries
    consecutive_failures = 0
    final_mode = "react"

    _MAX_CONSECUTIVE_FAILURES = 2
    _REACT_OBS_WINDOW = 6           # token control: keep last N observations

    # Error-handling state
    skill_retry_counts: dict[str, int] = {}   # skill_key → number of retries attempted
    failed_set: set[str] = set()              # skills that failed at least once
    error_context: list[str] = []            # brief error summaries for LLM prompt
    pending_post_text = ""

    logger.info("[ReAct] start loop: api=%s symptom=%s max_steps=%d", api, symptom, _REACT_MAX_STEPS)

    # MModel context summary (computed once, used in every decision prompt)
    ctx_summary = ""
    try:
        ctx_dict = get_mmodel_context_summary(user_query=f"{api} 出现 {symptom}", case_id=ctx.case_id, data_dir=ctx.data_dir)
        ctx_summary = format_mmodel_context_for_llm(ctx_dict)
    except Exception as e:
        logger.warning("[ReAct] context summary 获取失败: %s", e)

    loop_skills = [k for k in _DEFAULT_PLAN if k != "generate_report"]

    for step in range(_REACT_MAX_STEPS):
        available = [k for k in loop_skills if k not in executed_set]
        if not available:
            logger.info("[ReAct] step=%d 所有可用 Skill 已执行，退出循环", step)
            break

        logger.info("[ReAct] step=%d executed=%s available=%s", step, executed, available)

        if pending_post_text:
            yield from _stream_replace_text_chars(pending_post_text, done=False)
            _time.sleep(2.5)
            yield {"type": "assistant_replace", "content": ""}
            yield {"type": "assistant_message_done"}
            pending_post_text = ""

        # Token-controlled observations: only last N, each capped
        trimmed_obs = observations[-_REACT_OBS_WINDOW:]
        trimmed_errors = error_context[-3:]

        decision = plan_next_skill_by_evidence(api, symptom, executed_set, failed_set, available, ctx)
        if decision is not None:
            logger.info(
                "[ReAct] step=%d source=evidence_planner action=%s skill=%s",
                step, decision.get("action"), decision.get("skill"),
            )
        else:
            decision = decide_next_skill(
                llm, api, time, symptom, executed, trimmed_obs, available, ctx_summary,
                executed_set, failed_set=failed_set, error_context=trimmed_errors
            )

        if decision is None:
            decision = _determine_next_skill_without_llm(
                executed_set=executed_set,
                failed_set=failed_set,
                available=available,
                ctx=ctx,
                api=api,
                symptom=symptom,
                retry_counts=skill_retry_counts,
            )
            if decision is not None:
                consecutive_failures = 0
                logger.info(
                    "[ReAct] step=%d source=deterministic_local action=%s skill=%s",
                    step, decision.get("action"), decision.get("skill"),
                )
            else:
                consecutive_failures += 1
                logger.warning("[ReAct] step=%d 连续决策失败 %d/%d",
                               step, consecutive_failures, _MAX_CONSECUTIVE_FAILURES)
            if decision is None and consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                has_conflict = _has_evidence_conflict(ctx)
                if has_conflict:
                    logger.warning(
                        "[ReAct][Fallback] reason=连续决策失败达上限 "
                        "skipped_due_to_evidence_conflict=true — 证据冲突不是系统失败，不触发 default plan"
                    )
                    break
                final_mode = "default"
                logger.warning(
                    "[ReAct][Fallback] reason=连续决策失败达上限 final_mode=default "
                    "skipped_due_to_evidence_conflict=false"
                )
                yield from _stream_text_chars("LLM 动态决策暂不可用，已切换为确定性诊断策略，诊断继续。")
                yield from _run_default_fallback(llm, ctx, api, time, symptom, executed_set)
                logger.info("[ReAct] final_mode=%s", final_mode)
                return
            if decision is None:
                continue

        consecutive_failures = 0
        action = decision.get("action")
        reason = decision.get("reason", "")
        skill_key = decision.get("skill", "")
        logger.info("[ReAct] step=%d decision_action=%s skill=%s reason=%.120s",
                    step, action, skill_key, reason)

        if action == "finish":
            # System-side finish gate
            allowed, deny_reason = _should_allow_finish(ctx, executed_set)
            if not allowed:
                logger.info("[ReAct] step=%d finish denied by system: %s", step, deny_reason)
                # Treat as if no decision was made — force continue
                missing_core = _CORE_SKILLS - executed_set
                if missing_core:
                    for core_key in [k for k in loop_skills if k in missing_core]:
                        logger.info("[ReAct] step=%d forcing core skill: %s", step, core_key)
                        core_sentinel: dict = {}
                        yield from _dispatch_skill_step(core_key, {}, ctx, llm, api, symptom, sentinel_out=core_sentinel)
                        if core_sentinel.get("_skill_failed"):
                            _handle_skill_failure(core_key, core_sentinel, skill_retry_counts,
                                                  failed_set, error_context, ctx)
                        else:
                            executed.append(core_key)
                            executed_set.add(core_key)
                            obs = summarize_skill_result(core_key, ctx)
                            logger.info("[ReAct] skill_result_summary skill=%s summary=%.200s", core_key, obs)
                            observations.append(f"{core_key}: {obs}")
                continue

            logger.info("[ReAct] step=%d action=finish reason=%.120s，退出循环", step, reason)
            break

        # action == "run_skill" or "retry"
        is_retry = (action == "retry")

        if is_retry:
            current_retries = skill_retry_counts.get(skill_key, 0)
            if current_retries >= _MAX_RETRY_PER_SKILL:
                logger.warning("[ReAct] step=%d 超过最大重试次数 skill=%s retry_count=%d，忽略",
                               step, skill_key, current_retries)
                error_context.append(
                    f"{skill_key}: 已达最大重试次数({_MAX_RETRY_PER_SKILL})，不再重试"
                )
                consecutive_failures += 1
                continue
            skill_retry_counts[skill_key] = current_retries + 1
            logger.info("[ReAct][Retry] skill=%s retry_count=%d", skill_key, skill_retry_counts[skill_key])
        else:
            # Duplicate call guard
            if skill_key in executed_set:
                logger.warning("[ReAct] step=%d 重复调用 Skill: %s，跳过", step, skill_key)
                consecutive_failures += 1
                continue

        sanitized = _sanitize_args(skill_key, decision.get("args") or {})
        logger.info("[ReAct] selected_skill=%s step=%d is_retry=%s sanitized_args=%s",
                    skill_key, step, is_retry, sanitized)

        step_sentinel: dict = {}
        yield from _dispatch_skill_step(skill_key, sanitized, ctx, llm, api, symptom, reason, sentinel_out=step_sentinel)

        if step_sentinel.get("_skill_failed"):
            _handle_skill_failure(skill_key, step_sentinel, skill_retry_counts, failed_set, error_context, ctx)
            consecutive_failures += 1
            if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                has_conflict = _has_evidence_conflict(ctx)
                if has_conflict:
                    logger.warning(
                        "[ReAct][Fallback] reason=连续Skill失败达上限 "
                        "skipped_due_to_evidence_conflict=true — 证据冲突不是系统失败，不触发 default plan"
                    )
                    break
                final_mode = "default"
                logger.warning(
                    "[ReAct][Fallback] reason=连续Skill失败达上限 final_mode=default "
                    "skipped_due_to_evidence_conflict=false"
                )
                yield from _stream_text_chars("多次重试失败，已降级为默认诊断链路。")
                yield from _run_default_fallback(llm, ctx, api, time, symptom, executed_set)
                logger.info("[ReAct] final_mode=%s", final_mode)
                return
        else:
            consecutive_failures = 0
            # On retry success, remove from failed_set; on first success, add to executed
            failed_set.discard(skill_key)
            if skill_key not in executed_set:
                executed.append(skill_key)
                executed_set.add(skill_key)
            pending_post_text = step_sentinel.get("_post_text", "")
            obs = summarize_skill_result(skill_key, ctx)
            logger.info("[ReAct] skill_result_summary skill=%s summary=%.200s", skill_key, obs)
            observations.append(f"{skill_key}: {obs}")

            # After infer_root_cause: if root cause is not confirmed (evidence conflict),
            # skip analyze_impact and proceed directly to report generation.
            if skill_key == "infer_root_cause":
                rc = getattr(ctx, "root_cause_result", {}) or {}
                if not rc.get("is_confirmed", True):
                    logger.warning(
                        "[ReAct] infer_root_cause is_confirmed=False — "
                        "跳过 analyze_impact，直接生成「根因待确认」报告"
                    )
                    yield from _stream_text_chars(
                        "根因推断发现多源证据冲突，无法确认根因。跳过影响面分析，生成「根因待确认」专项报告。"
                    )
                    break

    logger.info("[ReAct] loop ended executed=%s final_mode=%s", executed, final_mode)

    # Always run generate_report last
    if "generate_report" not in executed_set:
        yield from _dispatch_skill_step("generate_report", {}, ctx, llm, api, symptom)

    logger.info("[ReAct] final_mode=%s", final_mode)


def _handle_skill_failure(
    skill_key: str,
    sentinel: dict,
    skill_retry_counts: dict,
    failed_set: set,
    error_context: list,
    ctx: DiagnosisContext,
) -> None:
    """Record skill failure into tracking structures and ctx.failed_skills."""
    error_type = sentinel.get("_error_type", "UnknownError")
    error_msg = sentinel.get("_error_message", "")
    retry_count = skill_retry_counts.get(skill_key, 0)
    can_retry = retry_count < _MAX_RETRY_PER_SKILL

    failed_set.add(skill_key)
    failure_summary = {
        "skill": skill_key,
        "status": "failed",
        "error_type": error_type,
        "error_message": error_msg[:150],
        "retry_count": retry_count,
        "can_retry": can_retry,
    }
    ctx.failed_skills.append(failure_summary)

    error_ctx_line = (
        f"{skill_key} 失败: {error_type}: {error_msg[:100]}"
        f"（已重试 {retry_count} 次，{'可继续重试' if can_retry else '不再重试'}）"
    )
    error_context.append(error_ctx_line)
    logger.error("[ReAct][SkillError] skill=%s error_type=%s retry_count=%d can_retry=%s",
                 skill_key, error_type, retry_count, can_retry)


# ---------------------------------------------------------------------------
# Main streaming generator
# ---------------------------------------------------------------------------

def _executed_skills_from_ctx(ctx: DiagnosisContext) -> list[str]:
    executed = []
    if ctx.query_context:
        executed.append("set_time_range")
    if ctx.trace_result:
        executed.append("analyze_trace")
    if ctx.entity_result:
        executed.append("bind_entities")
    if ctx.log_result:
        executed.append("analyze_log")
    if ctx.metric_result:
        executed.append("check_metrics")
    if ctx.graph_result:
        executed.append("analyze_graph")
    if ctx.root_cause_result:
        executed.append("infer_root_cause")
    if ctx.impact_result:
        executed.append("analyze_impact")
    if ctx.report_result:
        executed.append("generate_report")
    return executed

def stream_agentic_diagnosis(
    api: str,
    time: str,
    symptom: str,
    case_id: str | None = None,
    data_dir: str | None = None,
    session_id: str | None = None,
    message: str | None = None,
    mode: str | None = None,
    session_store: DiagnosisSessionStore | None = None,
) -> Iterator[dict]:
    """
    Yields dicts. Each dict has a "type" field:
      assistant_delta, assistant_message_done,
      skill_start, skill_done, skill_error,
      report_done, done
    """
    session = get_or_create_session(session_id, session_store)
    request_context = session.request_context or {}
    api = "" if api == "/unknown" else api
    api = api or request_context.get("api", "")
    time = time or request_context.get("time", "")
    symptom = symptom or request_context.get("symptom", "")
    user_message = message or f"{time}，{api} 接口出现 {symptom}，请分析根因和影响面。"
    resolved_context = resolve_context_reference(user_message, session)
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
        # ── Emit data source status for ALL intents ──────────────────────────
        yield {"type": "data_source_status", **get_data_source_status()}
        try:
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
        except Exception as exc:
            logger.exception("[AgenticStream] run_intent_turn failed: %s", exc)
            error_answer = (
                f"查询执行时遇到错误：{exc}\\n\\n"
                "可能原因：\\n"
                "- OpenSearch 服务不可达，请检查 OPENSEARCH_URL 配置\\n"
                "- 本地评测数据未配置，请设置 MMODEL_DATA_DIR 或指定 case_id\\n"
                "- 后端日志中可能有更多细节"
            )
            yield {
                "type": "session",
                "session_id": session.session_id,
                "mode": mode,
                "intent": intent_decision.intent,
                "current_focus": session.current_focus.to_dict(),
                "resolved_context": resolved_context,
                "memory_summary": memory_summary(session),
                "executed_skills": [],
            }
            yield {"type": "report_delta", "content": error_answer}
            yield {"type": "report_done", "report": {"summary": error_answer}}
            yield {
                "type": "done",
                "summary": {"root_cause_service": "", "error": str(exc)},
                "session_id": session.session_id,
                "mode": mode,
                "intent": intent_decision.intent,
                "executed_skills": [],
            }
            return
        yield {
            "type": "session",
            "session_id": turn.response.session_id,
            "mode": turn.response.mode,
            "intent": turn.intent,
            "current_focus": turn.response.current_focus,
            "resolved_context": turn.response.resolved_context,
            "memory_summary": turn.response.memory_summary,
            "executed_skills": turn.response.executed_skills,
        }
        for result in turn.skill_results:
            skill_key = skill_result_to_tool_key(result)
            yield {"type": "skill_start", "skill": skill_key, "title": result.title, "reason": intent_decision.reason}
            yield {
                "type": "skill_done",
                "skill": skill_key,
                "result": {
                    "summary": result.summary,
                    "evidence": result.evidence,
                    "execution_log": result.execution_log,
                    "duration_ms": result.duration_ms,
                },
            }
        if turn.answer:
            yield {"type": "report_delta", "content": turn.answer}
        yield {"type": "report_done", "report": {"summary": turn.answer}}
        yield {
            "type": "done",
            "summary": turn.response.summary.model_dump(),
            "session_id": turn.response.session_id,
            "mode": turn.response.mode,
            "intent": turn.intent,
            "executed_skills": turn.response.executed_skills,
            "current_focus": turn.response.current_focus,
            "resolved_context": turn.response.resolved_context,
            "memory_summary": turn.response.memory_summary,
        }
        return

    case_id, data_dir = resolve_request_context(api=api, symptom=symptom, case_id=case_id, data_dir=data_dir)
    llm = get_llm_provider()
    ctx = DiagnosisContext(api=api, time=time, symptom=symptom, case_id=case_id, data_dir=data_dir)
    ctx.resolved_context = resolved_context

    # ── Clear fallback tracking at start of each run ─────────────────────────
    clear_data_source_warnings()

    yield {
        "type": "session",
        "session_id": session.session_id,
        "mode": mode,
        "intent": intent_decision.intent,
        "current_focus": session.current_focus.to_dict(),
        "resolved_context": resolved_context,
        "memory_summary": memory_summary(session),
        "executed_skills": [],
    }

    # ── Emit data source status early ────────────────────────────────────────
    yield {"type": "data_source_status", **get_data_source_status()}

    # Demo-only delay before the first LLM request so the interaction feels less mocked.
    # Remove or disable this before production rollout.
    _time.sleep(_DEMO_INITIAL_LLM_DELAY_SECONDS)

    # ------------------------------------------------------------------ #
    # ReAct dynamic skill selection and execution
    # Falls back to default plan internally if LLM decisions fail.
    # ------------------------------------------------------------------ #
    yield from run_react_loop(llm, ctx, api, time, symptom)

    # --- done event carries summary for HistoryPanel ---
    rc = ctx.root_cause_result
    summary_payload: dict[str, Any] = {}
    if rc:
        summary_payload = {
            "root_cause_service": rc.get("root_cause_service", ""),
            "root_cause_api": rc.get("root_cause_api", ""),
            "root_cause_type": rc.get("root_cause_type", ""),
            "exception_type": rc.get("exception_type", ""),
            "bad_parameter": str(rc.get("bad_param") or ""),
            "impact_api": api,
            "business_impact": ctx.impact_result.get("affected_business", []),
        }

    final_report = (ctx.report_result or {}).get("report", "")
    session = update_session_from_context(
        session,
        ctx,
        user_message=user_message,
        assistant_message=final_report,
        store=session_store,
    )

    yield {
        "type": "done",
        "summary": summary_payload,
        "session_id": session.session_id,
        "mode": mode,
        "intent": intent_decision.intent,
        "executed_skills": _executed_skills_from_ctx(ctx),
        "current_focus": session.current_focus.to_dict(),
        "resolved_context": resolved_context,
        "memory_summary": memory_summary(session),
    }


def _extract_plan_list(text: str) -> list[dict]:
    """Helper: extract plan list from LLM JSON text for _parse_plan_from_llm wrapping."""
    try:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = "\n".join(l for l in stripped.splitlines() if not l.strip().startswith("```"))
        data = json.loads(stripped)
        return data.get("plan", [])
    except Exception:
        return []
