"""
AlertContextSkill: converts raw fault event into MModel query context.
"""
import time as _time
import os
from datetime import datetime, timedelta, timezone
from app.skills.base_skill import BaseSkill
from app.models.context import DiagnosisContext
from app.models.diagnosis import SkillResult


class AlertContextSkill(BaseSkill):
    skill_name = "AlertContextSkill"
    tool_name = "MModelSkill/set_time_range"
    title = "告警上下文构建"

    def run(self, ctx: DiagnosisContext) -> SkillResult:
        t0 = _time.monotonic()
        started_at = datetime.now(timezone.utc).isoformat()
        execution_log = []

        execution_log.append("解析用户输入字符串")

        # Extract api from input
        api = ctx.api
        fault_time = ctx.time
        symptom = ctx.symptom
        execution_log.append(f"识别故障接口：{api}")
        execution_log.append(f"识别故障时间：{fault_time}")
        execution_log.append(f"识别故障现象：{symptom}")

        # Build time window ±5 min from the request timestamp.
        execution_log.append("构建查询时间窗口：±5 分钟")
        window_start, window_end = _build_time_window(
            fault_time,
            normalize_to_utc=_is_opensearch_source(),
        )
        query_context = {
            "alert_api": api,
            "alert_time": fault_time,
            "symptom": symptom,
            "case_id": ctx.case_id,
            "data_dir": ctx.data_dir,
            "time_window": {
                "start": window_start,
                "end": window_end,
            },
        }
        ctx.query_context = query_context
        execution_log.append("诊断上下文构建完成")

        duration_ms = max(1, int((_time.monotonic() - t0) * 1000))
        finished_at = datetime.now(timezone.utc).isoformat()

        return SkillResult(
            skill_name=self.skill_name,
            tool_name=self.tool_name,
            title=self.title,
            status="success",
            summary=f"已构建诊断上下文：接口 {api}，时间 {fault_time}，现象 {symptom}",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            input={"raw_input": f"{fault_time}，{api} 接口出现 {symptom}"},
            output=query_context,
            evidence=[
                f"解析用户输入，识别故障接口 {api}",
                f"故障时间 {fault_time}，构建查询窗口 ±5min",
            ],
            execution_log=execution_log,
            explanation="将用户输入的故障事件转换为 MModel 可理解的结构化诊断上下文，作为后续 Skill 的统一输入格式。",
        )


def _is_opensearch_source() -> bool:
    return os.environ.get("DATA_SOURCE", "local_json").strip().lower() == "opensearch"


def _build_time_window(raw_time: str, normalize_to_utc: bool = False) -> tuple[str, str]:
    parsed = _parse_time(raw_time)
    if parsed is None:
        return raw_time, raw_time
    if normalize_to_utc:
        parsed = parsed.astimezone(timezone.utc)
    return (
        _format_time(parsed - timedelta(minutes=5), normalize_to_utc),
        _format_time(parsed + timedelta(minutes=5), normalize_to_utc),
    )


def _format_time(value: datetime, as_utc: bool) -> str:
    text = value.isoformat()
    if as_utc:
        return text.replace("+00:00", "Z")
    return text


def _parse_time(raw_time: str) -> datetime | None:
    text = (raw_time or "").strip()
    if not text:
        return None
    candidates = [text]
    if text.endswith("Z"):
        candidates.append(text[:-1] + "+00:00")
    for candidate in candidates:
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None
