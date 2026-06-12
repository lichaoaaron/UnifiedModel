"""
TraceAnalysisSkill: reads trace.json to identify abnormal spans and root candidates.
"""
import time as _time
from datetime import datetime, timezone
from app.skills.base_skill import BaseSkill
from app.skills.param_extractor import extract_bad_parameter
from app.models.context import DiagnosisContext
from app.models.diagnosis import SkillResult
from app.adapters import observability_adapter as adapter
from app.adapters.local_json_adapter import resolve_data_dir
from app.skills.evidence_classifier import (
    classify_root_cause_type,
    extract_rpc_target_service,
    extract_exception_type,
    is_propagation_text,
    normalize_api,
    normalize_service_name,
)


class TraceAnalysisSkill(BaseSkill):
    skill_name = "TraceAnalysisSkill"
    tool_name = "MModelSkill/analyze_trace"
    title = "调用链分析"

    _UNAVAILABLE_TOKENS = (
        "code = unavailable",
        "service unavailable",
        "connection refused",
        "failed to connect",
        "deadline exceeded",
        "name resolver error",
        "zero addresses",
        "timeout",
    )

    def _parse_time(self, raw: str) -> datetime | None:
        token = (raw or "").strip()
        if not token:
            return None
        if token.endswith("Z"):
            token = token[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(token)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            return None

    def _has_unavailable_signal(self, text: str) -> bool:
        lower = (text or "").lower()
        return any(token in lower for token in self._UNAVAILABLE_TOKENS)

    def _choose_trace_id(self, spans: list[dict], entry_api: str, fault_time: str) -> str | None:
        fault_dt = self._parse_time(fault_time)
        trace_scores: dict[str, dict[str, object]] = {}
        for span in spans:
            src = span.get("_source", span)
            trace_id = src.get("traceId")
            if not trace_id:
                continue
            name = src.get("name", "")
            url = src.get("span.attributes.url", "") or src.get("span.attributes.http@url", "") or src.get("span.attributes.url@full", "")
            status_code = src.get("status.code") or (src.get("status") or {}).get("code")
            status_message = src.get("status.message") or (src.get("status") or {}).get("message", "")
            http_status_raw = src.get("span.attributes.http@status_code") or src.get("span.attributes.http@response@status_code")
            try:
                http_status = int(http_status_raw)
            except (TypeError, ValueError):
                http_status = 0
            start_time = str(src.get("startTime") or src.get("start_time") or "")
            start_dt = self._parse_time(start_time)
            bucket = trace_scores.setdefault(trace_id, {
                "entry_match": False,
                "has_error": False,
                "has_http_5xx": False,
                "has_status_message": False,
                "has_rpc": False,
                "matched_span_count": 0,
                "services": set(),
                "latest_time": "",
                "closest_delta": float("inf"),
            })
            matched_entry = bool(entry_api and (entry_api in name or entry_api in url))
            if matched_entry:
                bucket["entry_match"] = True
            if str(status_code) == "2":
                bucket["has_error"] = True
            if http_status >= 500:
                bucket["has_http_5xx"] = True
            if status_message:
                bucket["has_status_message"] = True
            if src.get("span.attributes.rpc@service"):
                bucket["has_rpc"] = True
            if matched_entry or str(status_code) == "2" or http_status >= 500:
                bucket["matched_span_count"] = int(bucket["matched_span_count"]) + 1
            service = src.get("serviceName") or src.get("resource.attributes.service@name", "")
            if service:
                bucket["services"].add(service)
            bucket["latest_time"] = max(str(bucket["latest_time"]), start_time)
            if fault_dt and start_dt:
                bucket["closest_delta"] = min(float(bucket["closest_delta"]), abs((start_dt - fault_dt).total_seconds()))
        if not trace_scores:
            return None

        def _rank(item: tuple[str, dict[str, object]]) -> tuple[int, float, str]:
            profile = item[1]
            score = 0
            if profile["entry_match"]:
                score += 4
            if profile["has_error"]:
                score += 4
            if profile["has_http_5xx"]:
                score += 3
            if profile["has_status_message"]:
                score += 2
            if profile["has_rpc"]:
                score += 1
            return (
                score,
                int(profile["matched_span_count"]),
                len(profile["services"]),
                -float(profile["closest_delta"]),
                str(profile["latest_time"]),
            )

        return max(trace_scores.items(), key=_rank)[0]

    def _hop_to_downstream_trace(self, ctx: DiagnosisContext, spans: list[dict], trace_id: str) -> tuple[list[dict], str | None]:
        if adapter.get_data_source() != "opensearch":
            return spans, None

        trace_has_unavailable_signal = False
        for span in spans:
            src = span.get("_source", span)
            event_text = " ".join(
                (event.get("attributes") or {}).get("exception@message", "") or (event.get("attributes") or {}).get("message", "")
                for event in (src.get("events") or [])
            )
            combined = " ".join([
                src.get("status.message", "") or (src.get("status") or {}).get("message", ""),
                event_text,
                src.get("name", ""),
            ])
            if self._has_unavailable_signal(combined):
                trace_has_unavailable_signal = True
                break
        if not trace_has_unavailable_signal:
            return spans, None

        downstream_api = ""
        downstream_service = ""
        for span in spans:
            src = span.get("_source", span)
            kind = src.get("kind", "")
            rpc_target_service = extract_rpc_target_service(
                src.get("span.attributes.rpc@service", ""),
                src.get("span.attributes.rpc@method", ""),
                src.get("name", ""),
            )
            if kind != "SPAN_KIND_CLIENT" or not rpc_target_service:
                continue
            if any(normalize_service_name((candidate.get("serviceName") or candidate.get("resource.attributes.service@name", ""))) == rpc_target_service for candidate in [s.get("_source", s) for s in spans]):
                continue
            downstream_api = src.get("span.attributes.rpc@method", "") or src.get("name", "")
            downstream_service = rpc_target_service
            break

        if not downstream_api:
            return spans, None

        query_context = dict(ctx.query_context)
        query_context["trace_id"] = None
        query_context["alert_api"] = None
        query_context["api"] = downstream_api
        query_context["limit"] = max(int(query_context.get("limit") or 0), 400)
        candidate_spans = adapter.get_traces(query_context=query_context, data_dir=ctx.data_dir, case_id=ctx.case_id)
        if not candidate_spans:
            return spans, None

        fault_dt = self._parse_time(ctx.time)
        grouped: dict[str, dict[str, object]] = {}
        for span in candidate_spans:
            src = span.get("_source", span)
            candidate_trace_id = src.get("traceId")
            if not candidate_trace_id or candidate_trace_id == trace_id:
                continue
            bucket = grouped.setdefault(candidate_trace_id, {
                "unavailable_hits": 0,
                "target_service_hits": 0,
                "error_hits": 0,
                "closest_delta": float("inf"),
                "latest_time": "",
            })
            service = normalize_service_name(src.get("serviceName") or src.get("resource.attributes.service@name", ""))
            if service == downstream_service:
                bucket["target_service_hits"] = int(bucket["target_service_hits"]) + 1
            status_message = src.get("status.message", "") or (src.get("status") or {}).get("message", "")
            event_text = " ".join(
                (event.get("attributes") or {}).get("exception@message", "") or (event.get("attributes") or {}).get("message", "")
                for event in (src.get("events") or [])
            )
            combined = " ".join([status_message, event_text, src.get("name", "")])
            if self._has_unavailable_signal(combined):
                bucket["unavailable_hits"] = int(bucket["unavailable_hits"]) + 1
            status_code = src.get("status.code") or (src.get("status") or {}).get("code")
            http_status = src.get("span.attributes.http@status_code") or src.get("span.attributes.http@response@status_code")
            if str(status_code) == "2" or str(http_status).startswith("5"):
                bucket["error_hits"] = int(bucket["error_hits"]) + 1
            start_time = str(src.get("startTime") or src.get("start_time") or "")
            bucket["latest_time"] = max(str(bucket["latest_time"]), start_time)
            start_dt = self._parse_time(start_time)
            if fault_dt and start_dt:
                bucket["closest_delta"] = min(float(bucket["closest_delta"]), abs((start_dt - fault_dt).total_seconds()))

        if not grouped:
            return spans, None

        hopped_trace_id = max(
            grouped.items(),
            key=lambda item: (
                int(item[1]["unavailable_hits"]),
                int(item[1]["target_service_hits"]),
                int(item[1]["error_hits"]),
                -float(item[1]["closest_delta"]),
                str(item[1]["latest_time"]),
            ),
        )[0]
        refined_query_context = dict(ctx.query_context)
        refined_query_context["trace_id"] = hopped_trace_id
        refined_query_context["alert_api"] = None
        refined_query_context["api"] = None
        hopped_spans = adapter.get_traces(query_context=refined_query_context, data_dir=ctx.data_dir, case_id=ctx.case_id)
        return (hopped_spans or spans), hopped_trace_id

    def run(self, ctx: DiagnosisContext) -> SkillResult:
        t0 = _time.monotonic()
        started_at = datetime.now(timezone.utc).isoformat()
        execution_log = []

        data_dir = "opensearch" if adapter.get_data_source() == "opensearch" else resolve_data_dir(data_dir=ctx.data_dir, case_id=ctx.case_id)
        execution_log.append("查询 OpenSearch trace" if data_dir == "opensearch" else f"读取 {data_dir}/trace.json")
        initial_query_context = ctx.query_context
        if data_dir == "opensearch":
            initial_query_context = dict(ctx.query_context)
            initial_query_context["limit"] = max(int(initial_query_context.get("limit") or 0), 1000)
        spans = adapter.get_traces(query_context=initial_query_context, data_dir=ctx.data_dir, case_id=ctx.case_id)
        selected_trace_id = self._choose_trace_id(spans, ctx.api, ctx.time) if data_dir == "opensearch" else None
        if selected_trace_id:
            refined_query_context = dict(ctx.query_context)
            refined_query_context["trace_id"] = selected_trace_id
            refined_query_context["alert_api"] = None
            refined_query_context["api"] = None
            spans = adapter.get_traces(query_context=refined_query_context, data_dir=ctx.data_dir, case_id=ctx.case_id)
            ctx.query_context["trace_id"] = selected_trace_id
            execution_log.append(f"收敛到代表性 traceId: {selected_trace_id}")
            hopped_spans, hopped_trace_id = self._hop_to_downstream_trace(ctx, spans, selected_trace_id)
            if hopped_trace_id and hopped_trace_id != selected_trace_id:
                spans = hopped_spans
                ctx.query_context["trace_id"] = hopped_trace_id
                execution_log.append(f"沿下游 RPC 跳转到 traceId: {hopped_trace_id}")
        execution_log.append(f"解析 {len(spans)} 个 span")

        trace_id = None
        span_map = {}
        for span in spans:
            src = span.get("_source", span)
            sid = src.get("spanId", "")
            if sid:
                span_map[sid] = src
            if src.get("traceId"):
                trace_id = src.get("traceId")

        children_map: dict[str, list[str]] = {}
        roots = []
        def _span_time(span: dict) -> str:
            return str(span.get("startTime") or span.get("start_time") or "")

        for sid, src in span_map.items():
            pid = src.get("parentSpanId", "")
            if pid and pid in span_map:
                children_map.setdefault(pid, []).append(sid)
            else:
                roots.append(sid)

        roots.sort(key=lambda sid: _span_time(span_map.get(sid, {})))
        for child_ids in children_map.values():
            child_ids.sort(key=lambda sid: _span_time(span_map.get(sid, {})))

        ordered_span_ids = []
        queue = list(roots)
        while queue:
            sid = queue.pop(0)
            ordered_span_ids.append(sid)
            queue.extend(children_map.get(sid, []))
        ordered_spans = [span_map[sid] for sid in ordered_span_ids] if ordered_span_ids else sorted(
            [s.get("_source", s) for s in spans], key=_span_time
        )

        call_path = []
        abnormal_spans = []
        latency_anomaly_spans = []
        root_candidates = []
        entry_api = ctx.api
        entry_service = None

        for src in ordered_spans:
            service = src.get("serviceName") or src.get("resource.attributes.service@name", "")
            name = src.get("name", "")
            kind = src.get("kind", "")
            api = normalize_api(name)
            rpc_service = src.get("span.attributes.rpc@service", "")
            rpc_method = src.get("span.attributes.rpc@method", "")
            if entry_service is None and service:
                entry_service = service
            status_code_raw = src.get("span.attributes.http@status_code", "")
            try:
                http_status = int(status_code_raw)
            except (TypeError, ValueError):
                http_status = 0
            status = src.get("status.code", 0)
            duration_ms = int((src.get("durationInNanos") or 0) / 1_000_000)
            events = src.get("events", []) or []

            if service and name:
                call_path.append(f"{service}: {name}")

            event_errors = []
            for event in events:
                attrs = event.get("attributes", {})
                error_kind = attrs.get("error@kind", "")
                message = attrs.get("message", "")
                stack = attrs.get("stack", "")
                if error_kind or str(attrs.get("event", "")).lower() == "error" or "exception" in (message + stack).lower():
                    event_errors.append((error_kind, message, stack))

            is_error = status == 2 or http_status >= 500 or bool(event_errors) or str(src.get("derived.error", "")) == "1"
            is_latency = duration_ms >= 1000 and (http_status < 500 or not event_errors)
            if is_latency:
                latency_anomaly_spans.append({"service": service, "api": api, "duration_ms": duration_ms})

            if not (is_error or is_latency):
                continue

            if event_errors:
                error_kind, message, stack = event_errors[0]
            else:
                message = src.get("status.message", "") or f"duration={duration_ms}ms status={http_status}"
                stack = ""
                error_kind = extract_exception_type(message) or ("SlowRequest" if is_latency else "HTTPError")

            combined = " ".join([error_kind or "", message or "", stack or "", name or "", src.get("span.attributes.url", "") or ""])
            root_type = classify_root_cause_type(combined)
            if root_type == "service_exception" and is_latency:
                root_type = "slow_interface"
            bad_param = extract_bad_parameter(message) or extract_bad_parameter(stack)
            propagation = is_propagation_text(combined, service)
            candidate_service = service
            candidate_api = api
            normalized_rpc_service = extract_rpc_target_service(rpc_service, rpc_method, name)
            if (
                entry_service
                and service == entry_service
                and kind != "SPAN_KIND_SERVER"
                and api != entry_api
                and (not normalized_rpc_service or normalized_rpc_service == normalize_service_name(service))
            ):
                propagation = True
            if (
                normalized_rpc_service
                and kind == "SPAN_KIND_CLIENT"
                and not propagation
                and normalized_rpc_service != normalize_service_name(service)
            ):
                candidate_service = normalized_rpc_service
                candidate_api = name or rpc_method or api
            unavailable_signal = self._has_unavailable_signal(combined)
            abnormal = {
                "service": candidate_service,
                "api": candidate_api,
                "error_kind": error_kind,
                "message": message,
                "bad_param": bad_param,
                "duration_ms": duration_ms,
                "http_status": http_status,
                "root_cause_type": root_type,
                "is_propagation": propagation,
            }
            abnormal_spans.append(abnormal)
            root_candidates.append({
                "source": "trace",
                "service": candidate_service,
                "component": candidate_service,
                "interface": candidate_api,
                "api": candidate_api,
                "type": root_type,
                "exception_type": error_kind,
                "evidence": message or f"span duration {duration_ms}ms",
                "confidence": "medium" if not propagation else "low",
                "score": 0.7 if (not propagation and unavailable_signal and candidate_service != service) else (0.55 if not propagation else 0.2),
                "is_propagation": propagation,
                "is_downstream_rpc": candidate_service != service,
            })

        downstream_rpc_services = {
            candidate.get("service")
            for candidate in root_candidates
            if candidate.get("is_downstream_rpc") and not candidate.get("is_propagation") and candidate.get("service")
        }
        if downstream_rpc_services:
            for candidate in root_candidates:
                if candidate.get("service") in downstream_rpc_services:
                    continue
                exception_type = str(candidate.get("exception_type") or "")
                if exception_type not in {"HTTPError"} and not exception_type.isdigit():
                    continue
                candidate["is_propagation"] = True
                candidate["confidence"] = "low"
                candidate["score"] = min(float(candidate.get("score") or 0.2), 0.2)

            for abnormal in abnormal_spans:
                if abnormal.get("service") in downstream_rpc_services:
                    continue
                error_kind = str(abnormal.get("error_kind") or "")
                if error_kind not in {"HTTPError"} and not error_kind.isdigit():
                    continue
                abnormal["is_propagation"] = True

        unique_services = list(dict.fromkeys(p.split(":")[0].strip() for p in call_path if p))
        service_call = " → ".join(unique_services) if unique_services else "unknown"

        chosen = next(
            (
                candidate for candidate in root_candidates
                if not candidate.get("is_propagation") and candidate.get("is_downstream_rpc")
            ),
            None,
        )
        if chosen is None:
            for candidate in root_candidates:
                if not candidate.get("is_propagation"):
                    chosen = candidate
                    break
        if chosen is None and root_candidates:
            chosen = root_candidates[0]

        first_error_service = chosen.get("service") if chosen else None
        first_error_api = chosen.get("api") if chosen else None
        first_error_exception = chosen.get("exception_type") if chosen else None
        chosen_span = next((s for s in abnormal_spans if s.get("service") == first_error_service and s.get("api") == first_error_api), None)
        extracted_bad_param = chosen_span.get("bad_param") if chosen_span else None

        downstream_api = first_error_api if first_error_api and first_error_api != entry_api else None
        interface_call = f"{entry_api} → {downstream_api}" if downstream_api else entry_api or "unknown"

        ctx.trace_result = {
            "trace_id": trace_id,
            "entry_api": entry_api,
            "entry_service": unique_services[0] if unique_services else None,
            "service_call": service_call,
            "interface_call": interface_call,
            "call_path": call_path,
            "span_count": len(spans),
            "abnormal_spans": abnormal_spans,
            "latency_anomaly_spans": latency_anomaly_spans,
            "root_candidates": root_candidates,
            "first_error_service": first_error_service or None,
            "first_error_api": first_error_api or None,
            "first_error_exception": first_error_exception or None,
            "bad_param": extracted_bad_param,
            "extracted_bad_parameter": extracted_bad_param,
            "extracted_error_kind": first_error_exception,
            "extracted_error_message": chosen_span.get("message", "") if chosen_span else "",
            "source_field": "trace.events[].attributes.message" if extracted_bad_param else "none",
        }

        execution_log.append(f"识别调用链：{service_call}")
        execution_log.append(f"异常 span 数：{len(abnormal_spans)}，延迟异常 span 数：{len(latency_anomaly_spans)}")
        if chosen:
            execution_log.append(f"根因候选：{first_error_service} {first_error_api} {chosen.get('type')} ({first_error_exception})")
        else:
            execution_log.append("未发现明确异常 span")
        execution_log.append("Trace 分析完成")

        duration_ms = max(1, int((_time.monotonic() - t0) * 1000))
        finished_at = datetime.now(timezone.utc).isoformat()
        evidence = [
            f"traceId: {trace_id}",
            f"共解析 {len(spans)} 个 span",
            f"调用链：{service_call}",
            f"候选根因服务：{first_error_service}",
            f"候选根因接口：{first_error_api}",
            f"候选异常类型：{first_error_exception}",
        ]

        return SkillResult(
            skill_name=self.skill_name,
            tool_name=self.tool_name,
            title=self.title,
            status="success",
            summary=f"发现调用链 {service_call}，识别 {len(root_candidates)} 个 trace 根因候选。",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            input={"data_file": "opensearch:trace" if data_dir == "opensearch" else f"{data_dir}/trace.json", "api": ctx.api, "time": ctx.time},
            output=ctx.trace_result,
            evidence=evidence,
            execution_log=execution_log,
            explanation="从 trace 数据中解析调用链，识别 HTTP 错误、异常事件与延迟异常，并输出结构化根因候选。",
        )
