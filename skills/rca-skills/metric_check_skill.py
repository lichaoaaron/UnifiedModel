"""
MetricCheckSkill: evaluates metric.json with generic thresholds and emits candidates.
"""
import logging
import os
import time as _time
import yaml
from datetime import datetime, timezone
from app.skills.base_skill import BaseSkill
from app.models.context import DiagnosisContext
from app.models.diagnosis import SkillResult
from app.adapters import observability_adapter as adapter
from app.adapters.local_json_adapter import resolve_data_dir
from app.skills.evidence_classifier import classify_root_cause_type, metric_threshold, value_as_float

logger = logging.getLogger(__name__)

_THRESHOLDS_FILE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "rules", "metric_thresholds.yaml")
)


def _load_thresholds() -> dict:
    try:
        with open(_THRESHOLDS_FILE, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as exc:
        logger.warning("[MetricCheck] Cannot load thresholds file: %s", exc)
        return {}


def _configured_threshold(metric_name: str, thresholds: dict) -> float | None:
    cfg = (thresholds.get("defaults") or {}).get(metric_name) or {}
    if cfg.get("type") == "cumulative_counter":
        return None
    return cfg.get("alert_threshold") or metric_threshold(metric_name)


class MetricCheckSkill(BaseSkill):
    skill_name = "MetricCheckSkill"
    tool_name = "MModelSkill/check_metrics"
    title = "指标检查"

    def run(self, ctx: DiagnosisContext) -> SkillResult:
        t0 = _time.monotonic()
        started_at = datetime.now(timezone.utc).isoformat()
        execution_log = []

        data_dir = "opensearch" if adapter.get_data_source() == "opensearch" else resolve_data_dir(data_dir=ctx.data_dir, case_id=ctx.case_id)
        execution_log.append("查询 OpenSearch metric" if data_dir == "opensearch" else f"读取 {data_dir}/metric.json")
        metrics = adapter.get_metrics(query_context=ctx.query_context, data_dir=ctx.data_dir, case_id=ctx.case_id)
        execution_log.append(f"解析 {len(metrics)} 条指标记录")

        thresholds = _load_thresholds()
        execution_log.append("加载阈值配置 backend/data/rules/metric_thresholds.yaml")

        grouped: dict[tuple[str, str], dict] = {}
        for metric in metrics:
            name = metric.get("name") or metric.get("metric_name", "")
            service = metric.get("resource.attributes.compose_service") or metric.get("serviceName") or metric.get("resource.attributes.container@name", "")
            container = metric.get("resource.attributes.container@name", "")
            value = value_as_float(metric.get("value"))
            if not name or value is None:
                continue
            key = (service, name)
            current = grouped.get(key)
            if current is None or value > current["max_value"]:
                grouped[key] = {"service": service, "container": container, "metric_name": name, "max_value": value, "unit": metric.get("unit", "")}

        checked_metrics = []
        metric_root_candidates = []
        services_checked: set[str] = set()
        anomaly_details = []
        excluded_metric_signals = []
        insufficient_details = []
        call_services = set()
        for path_item in (ctx.trace_result or {}).get("call_path", []):
            service_name = path_item.split(":", 1)[0].strip()
            if service_name:
                call_services.add(service_name)

        for item in grouped.values():
            service = item["service"]
            name = item["metric_name"]
            value = item["max_value"]
            services_checked.add(service)
            threshold = _configured_threshold(name, thresholds)
            if threshold is None:
                status = "no_threshold"
                detail = f"{service} {name}={value} 未配置可用阈值"
            elif value >= threshold:
                status = "alert"
                detail = f"{service} {name}={value} 超过告警阈值 {threshold}"
            else:
                status = "normal"
                detail = f"{service} {name}={value} 在阈值范围内"
            checked_metrics.append({**item, "value": value, "status": status, "detail": detail, "threshold_used": threshold})
            execution_log.append(f"[{status}] {detail}")
            if status == "alert":
                root_type = classify_root_cause_type("", name)
                anomaly_details.append(detail)
                if call_services and service and service not in call_services:
                    excluded_metric_signals.append({**item, "value": value, "status": "excluded_noise", "detail": detail})
                    execution_log.append(f"[excluded_noise] {detail} 不在当前 trace 调用链中")
                    continue
                score = 0.75 if name != "http.client.errors.rate" else 0.25
                metric_root_candidates.append({
                    "source": "metric",
                    "service": service,
                    "component": item.get("container") or service,
                    "api": ctx.api,
                    "type": root_type,
                    "exception_type": None,
                    "metric_name": name,
                    "metric_names": [name],
                    "value": value,
                    "threshold": threshold,
                    "evidence": detail,
                    "confidence": "high" if score >= 0.75 else "low",
                    "score": score,
                    "is_propagation": name == "http.client.errors.rate",
                })
            elif status == "no_threshold":
                insufficient_details.append(detail)

        resource_is_root_cause_hint = bool(metric_root_candidates)
        if anomaly_details:
            overall_status = "alert"
            conclusion = f"发现指标异常：{'; '.join(anomaly_details[:6])}"
        elif insufficient_details:
            overall_status = "no_threshold"
            conclusion = "部分指标未配置阈值，无法单独判断资源状态。"
        else:
            overall_status = "normal"
            conclusion = "已查询资源指标，各项指标在阈值范围内，暂无资源异常。"

        ctx.metric_result = {
            "checked_metrics": checked_metrics,
            "services_checked": sorted(s for s in services_checked if s),
            "resource_status": overall_status,
            "resource_is_root_cause_hint": resource_is_root_cause_hint,
            "conclusion": conclusion,
            "anomaly_details": anomaly_details,
            "excluded_metric_signals": excluded_metric_signals,
            "insufficient_details": insufficient_details,
            "metric_root_candidates": metric_root_candidates,
        }

        duration_ms = max(1, int((_time.monotonic() - t0) * 1000))
        finished_at = datetime.now(timezone.utc).isoformat()
        evidence = [
            f"已检查服务：{', '.join(ctx.metric_result['services_checked']) or '暂无'}",
            f"指标序列数：{len(checked_metrics)}，整体状态：{overall_status}",
            conclusion,
        ]

        return SkillResult(
            skill_name=self.skill_name,
            tool_name=self.tool_name,
            title=self.title,
            status="success",
            summary=conclusion,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            input={
                "data_file": "opensearch:metric" if data_dir == "opensearch" else f"{data_dir}/metric.json",
                "thresholds_file": "backend/data/rules/metric_thresholds.yaml",
                "services": ctx.entity_result.get("services", []),
            },
            output=ctx.metric_result,
            evidence=evidence,
            execution_log=execution_log,
            explanation="按服务和指标聚合时间序列，使用通用阈值检测资源、中间件、网络与延迟异常。",
        )
