"""
ReportSkill: generates the final diagnosis report combining all skill results.
Uses MockLLMProvider (or real LLMProvider) to generate natural language output.
"""
import time as _time
from datetime import datetime, timezone
from app.skills.base_skill import BaseSkill
from app.models.context import DiagnosisContext
from app.models.diagnosis import SkillResult
from app.adapters.llm_provider import get_llm_provider
from app.skills.reasoning_chain_builder import build_reasoning_chain


def _render_reasoning_chain_markdown(rc: dict) -> str:
    """
    Render a reasoning_chain dict as a Markdown section for inclusion in the final report.
    All content comes from already-executed Skill outputs; nothing is fabricated.
    """
    lines = ["## 根因判定依据\n"]

    # 1. Symptom
    symptom = rc.get("symptom", {})
    lines.append("### 1. 异常现象")
    lines.append(symptom.get("summary", "（未知）"))
    for obs in symptom.get("observed_from", []):
        lines.append(f"- {obs}")
    lines.append("")

    # 2. Evidence
    evidence = rc.get("evidence", {})
    lines.append("### 2. 关键证据")
    for src_key, src_label in [("trace", "Trace"), ("log", "日志"), ("metric", "指标"), ("graph", "关系图")]:
        ev = evidence.get(src_key, {})
        status = ev.get("status", "unavailable")
        findings = ev.get("findings", [])
        lines.append(f"**{src_label}**（{status}）：")
        for f in findings:
            lines.append(f"  - {f}")
    lines.append("")

    # 3. Root cause candidates
    candidates = rc.get("root_cause_candidates", [])
    lines.append("### 3. 根因候选对比")
    for cand in candidates:
        cid = cand.get("candidate_id", "?")
        ctype = cand.get("candidate_type", "?")
        eref = cand.get("entity_ref", "?")
        score = cand.get("score", 0)
        conf = cand.get("confidence", "low")
        supporting = cand.get("supporting_reasons", [])
        weakening = cand.get("weakening_reasons", [])
        lines.append(f"**{cid}** — `{eref}` （{ctype}，置信度：{conf}，得分：{score}）")
        if supporting:
            lines.append("  支持证据：")
            for r in supporting:
                lines.append(f"    + {r}")
        if weakening:
            lines.append("  削弱因素：")
            for r in weakening:
                lines.append(f"    - {r}")
    lines.append("")

    # 4. Selected root cause
    sel = rc.get("selected_root_cause", {})
    lines.append("### 4. 最终选择理由")
    lines.append(f"**选定实体**：`{sel.get('entity_ref', '（未确认）')}`，"
                 f"已确认：{'是' if sel.get('is_confirmed') else '否（待确认）'}，"
                 f"置信度：{sel.get('confidence', '（未知）')}")
    lines.append(f"**选择原因**：{sel.get('selection_reason', '（未说明）')}")
    why_not = sel.get("why_not_others", [])
    if why_not:
        lines.append("**排除其他候选原因**：")
        for w in why_not:
            lines.append(f"  - {w}")
    lines.append("")

    # 5. Propagation path
    prop = rc.get("propagation_path", {})
    lines.append("### 5. 异常传播路径")
    prop_status = prop.get("status", "unavailable")
    prop_path = prop.get("path", [])
    if prop_status == "available" and prop_path:
        lines.append(" → ".join(str(p) for p in prop_path))
    else:
        lines.append(f"（{prop_status}）")
    lines.append(prop.get("explanation", ""))
    lines.append("")

    return "\n".join(lines)


class ReportSkill(BaseSkill):
    skill_name = "ReportSkill"
    tool_name = "MModelSkill/generate_report"
    title = "诊断报告生成"

    def run(self, ctx: DiagnosisContext) -> SkillResult:
        t0 = _time.monotonic()
        started_at = datetime.now(timezone.utc).isoformat()
        execution_log = []

        rc = ctx.root_cause_result or {}
        impact = ctx.impact_result or {}
        trace = ctx.trace_result or {}
        graph = ctx.graph_result or {}
        log = ctx.log_result or {}
        metric = ctx.metric_result or {}
        is_confirmed = rc.get("is_confirmed", True)
        root_cause_undetermined = not is_confirmed

        if root_cause_undetermined:
            execution_log.append("根因未确认（存在证据冲突），生成「根因待确认」专项报告")
        else:
            execution_log.append("汇总 Skill 的结构化输出，生成完整诊断报告")

        provider = get_llm_provider()
        provider_name = type(provider).__name__
        execution_log.append(f"调用 {provider_name} 生成自然语言报告")

        llm_context = {
            "root_cause": rc,
            "impact": impact,
            "trace": trace,
            "graph": graph,
            "log": log,
            "metric": metric,
            "api": ctx.api,
            "time": getattr(ctx, "time_range", "（未知时间）"),
            "symptom": getattr(ctx, "symptom", "故障"),
            "evidence_consistency": getattr(ctx, "evidence_consistency", {}),
            "report_guardrails": {
                "log_evidence_empty": not bool(log.get("log_evidence")) or not bool(log.get("root_candidates")),
                "metric_no_threshold": metric.get("resource_status") == "no_threshold",
                "confidence": rc.get("confidence"),
                "impact_only_from_structured": True,
            },
        }

        # Generate report — fallback chain is handled inside provider
        report_source = "llm"
        if root_cause_undetermined and hasattr(provider, "generate_undetermined_report"):
            report = provider.generate_undetermined_report(llm_context)
        else:
            report = provider.generate_explanation(llm_context)

        # Detect if report was produced by rule-based fallback (heuristic: MockLLMProvider or warning note)
        if isinstance(provider, __import__("app.adapters.llm_provider", fromlist=["MockLLMProvider"]).MockLLMProvider):
            report_source = "rule_based"
        elif "⚠ LLM 调用失败" in report or "⚠ 真实 LLM 调用全部失败" in report or "⚠ LLM 调用异常" in report:
            report_source = "rule_based_fallback"
            execution_log.append("⚠ LLM 调用失败，已降级为规则模板报告（fallback_reason 已记录）")

        # --- Build structured reasoning chain from executed skill outputs ---
        reasoning_chain = build_reasoning_chain(ctx)
        reasoning_section = _render_reasoning_chain_markdown(reasoning_chain)
        report = report + "\n\n" + reasoning_section
        llm_context["reasoning_chain"] = reasoning_chain

        execution_log.append("报告生成完成")

        report_summary: dict = {
            "root_cause_service": rc.get("root_cause_service"),
            "root_cause_api": rc.get("root_cause_api"),
            "root_cause_type": rc.get("root_cause_type"),
            "exception_type": rc.get("exception_type"),
            "is_confirmed": is_confirmed,
            "impact_api": ctx.api,
        }
        if is_confirmed:
            report_summary["bad_param"] = rc.get("bad_param")
            report_summary["business_impact"] = impact.get("affected_business", [])
        else:
            report_summary["note"] = "根因未确认，证据存在冲突，bad_param 及业务影响未输出"

        ctx.report_result = {
            "report": report,
            "llm_provider": provider_name,
            "report_source": report_source,
            "root_cause_undetermined": root_cause_undetermined,
            "summary": report_summary,
            "reasoning_chain": reasoning_chain,
        }

        duration_ms = max(1, int((_time.monotonic() - t0) * 1000))
        finished_at = datetime.now(timezone.utc).isoformat()

        if root_cause_undetermined:
            summary_text = "根因未确认（多源证据冲突），已生成「根因待确认」专项报告，未输出影响面。"
            evidence_list = [
                f"候选根因服务：{rc.get('root_cause_service')}",
                f"候选根因类型：{rc.get('root_cause_type')}",
                f"置信度：{rc.get('confidence')}",
                "is_confirmed=False — 证据冲突，根因细节不可信",
                f"LLM 提供者：{provider_name}（report_source={report_source}）",
            ]
        else:
            summary_text = "诊断报告已生成，包含根因、证据链、影响面和最终结论。"
            evidence_list = [
                f"根因服务：{rc.get('root_cause_service')}",
                f"根因接口：{rc.get('root_cause_api')}",
                f"根因类型：{rc.get('root_cause_type')}",
                f"异常类型：{rc.get('exception_type')}",
                f"异常参数：{rc.get('bad_param')}",
                f"LLM 提供者：{provider_name}（report_source={report_source}）",
            ]

        return SkillResult(
            skill_name=self.skill_name,
            tool_name=self.tool_name,
            title=self.title,
            status="success",
            summary=summary_text,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            input={"all_skill_results": "aggregated from executed skills"},
            output=ctx.report_result,
            evidence=evidence_list,
            execution_log=execution_log,
            explanation="汇总所有 Skill 的输出，通过 LLMProvider 生成面向领导和运维的可读诊断报告。",
        )
