"""
LogAnalysisSkill: reads log.json to classify root and propagation signals.
"""
import re
import time as _time
from datetime import datetime, timezone
from app.skills.base_skill import BaseSkill
from app.skills.param_extractor import extract_bad_parameter
from app.models.context import DiagnosisContext
from app.models.diagnosis import SkillResult
from app.adapters import observability_adapter as adapter
from app.adapters.local_json_adapter import resolve_data_dir
from app.skills.evidence_classifier import classify_root_cause_type, extract_exception_type, is_propagation_text, normalize_service_name


class LogAnalysisSkill(BaseSkill):
    skill_name = "LogAnalysisSkill"
    tool_name = "MModelSkill/analyze_log"
    title = "日志分析"

    def run(self, ctx: DiagnosisContext) -> SkillResult:
        t0 = _time.monotonic()
        started_at = datetime.now(timezone.utc).isoformat()
        execution_log = []

        data_dir = "opensearch" if adapter.get_data_source() == "opensearch" else resolve_data_dir(data_dir=ctx.data_dir, case_id=ctx.case_id)
        execution_log.append("查询 OpenSearch log" if data_dir == "opensearch" else f"读取 {data_dir}/log.json")
        logs = adapter.get_logs(query_context=ctx.query_context, data_dir=ctx.data_dir, case_id=ctx.case_id)
        execution_log.append(f"解析 {len(logs)} 条日志记录")

        log_evidence = []
        root_candidates = []
        propagation_logs = []
        noise_logs = []
        extracted_query_params: dict = {}
        downstream_url = None
        call_services = set()
        for path_item in (ctx.trace_result or {}).get("call_path", []):
            service_name = path_item.split(":", 1)[0].strip()
            if service_name:
                call_services.add(service_name)
                call_services.add(normalize_service_name(service_name))
        for candidate in (ctx.trace_result or {}).get("root_candidates", []):
            for service_name in [candidate.get("service"), candidate.get("component")]:
                if service_name:
                    call_services.add(service_name)
                    call_services.add(normalize_service_name(service_name))

        for log in logs:
            svc = log.get("serviceName") or log.get("resource.attributes.service@name", "")
            normalized_svc = normalize_service_name(svc)
            message = log.get("log.attributes.message", "") or log.get("body", "")
            stack_trace = log.get("log.attributes.stack_trace", "")
            severity = (log.get("severityText", "") or log.get("severity_text", "") or log.get("log.attributes.log@level", "")).upper()
            combined = (message or "") + "\n" + (stack_trace or "")
            has_signal = severity in {"ERROR", "FATAL", "CRITICAL", "WARN"} or "Exception" in combined or "Error" in combined
            if not has_signal:
                continue

            url_match = re.search(r"during \[GET\] to \[([^\]]+)\]", combined)
            if url_match:
                downstream_url = url_match.group(1)
                qp_match = re.search(r"\?(.+)$", downstream_url)
                if qp_match:
                    for pair in qp_match.group(1).split("&"):
                        if "=" in pair:
                            key, value = pair.split("=", 1)
                            extracted_query_params[key] = value.rstrip('])"\'')

            exception_type = extract_exception_type(combined) or "UnknownException"
            root_type = classify_root_cause_type(combined)
            bad_param = extract_bad_parameter(combined)
            is_propagation = is_propagation_text(combined, svc)
            is_noise = (
                "outside" in combined.lower()
                or "historical" in combined.lower()
                or "previous window" in combined.lower()
                or (call_services and svc and svc not in call_services and is_propagation)
                or (
                    adapter.get_data_source() == "opensearch"
                    and call_services
                    and normalized_svc
                    and normalized_svc not in call_services
                    and svc not in call_services
                    and not is_propagation
                    and (ctx.api or "") not in combined
                )
            )
            entry = {
                "service": svc,
                "type": root_type,
                "exception_type": exception_type,
                "message": message,
                "is_propagation": is_propagation,
            }
            log_evidence.append(f"{svc} {severity} {exception_type}: {message}")
            if is_noise:
                noise_logs.append(entry)
                execution_log.append(f"噪声日志：{svc} {exception_type}")
                continue
            if is_propagation:
                propagation_logs.append(entry)
                execution_log.append(f"传播性日志：{svc} {exception_type}")
                continue

            score = 0.65
            if "root cause" in combined.lower() or "diagnostic" in message.lower():
                score = 0.55
            root_candidates.append({
                "source": "log",
                "service": svc,
                "component": svc,
                "api": ctx.api,
                "type": root_type,
                "exception_type": exception_type,
                "bad_param": bad_param,
                "evidence": message,
                "confidence": "high" if score >= 0.65 else "medium",
                "score": score,
                "is_propagation": False,
            })
            execution_log.append(f"根因日志候选：{svc} {root_type} {exception_type}")

        chosen = root_candidates[0] if root_candidates else (propagation_logs[0] if propagation_logs else {})
        upstream_service = chosen.get("service")
        upstream_error_type = chosen.get("exception_type")
        error_param = chosen.get("bad_param") or (extracted_query_params.get("id") if extracted_query_params else None)

        ctx.log_result = {
            "upstream_service": upstream_service,
            "upstream_error_type": upstream_error_type,
            "downstream_url": downstream_url,
            "error_param": error_param,
            "log_evidence": log_evidence,
            "root_candidates": root_candidates,
            "root_signals": root_candidates,
            "propagation_logs": propagation_logs,
            "propagation_signals": propagation_logs,
            "noise_signals": noise_logs,
            "extracted_bad_parameter_from_log": error_param,
            "extracted_query_params": extracted_query_params,
            "source_field": "log.attributes.message" if error_param else "none",
        }

        execution_log.append(f"日志分析完成：根因候选 {len(root_candidates)} 个，传播性日志 {len(propagation_logs)} 条，噪声日志 {len(noise_logs)} 条")
        duration_ms = max(1, int((_time.monotonic() - t0) * 1000))
        finished_at = datetime.now(timezone.utc).isoformat()

        evidence = log_evidence[:8]
        if not evidence:
            evidence = [
                f"已查询 {len(logs)} 条日志，未发现 ERROR/FATAL/WARN 或异常日志"
            ]

        return SkillResult(
            skill_name=self.skill_name,
            tool_name=self.tool_name,
            title=self.title,
            status="success",
            summary=f"扫描 {len(logs)} 条日志，识别 {len(root_candidates)} 个日志根因候选。",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            input={"data_file": "opensearch:log" if data_dir == "opensearch" else f"{data_dir}/log.json", "candidate_services": ctx.entity_result.get("services", [])},
            output=ctx.log_result,
            evidence=evidence,
            execution_log=execution_log,
            explanation="扫描全部日志，区分传播性错误与根因日志，并按关键异常、资源、中间件信号输出候选。",
        )
