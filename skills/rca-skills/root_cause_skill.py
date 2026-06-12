"""
RootCauseSkill: deterministically scores structured trace/log/metric evidence.
"""
import os
import time as _time
import yaml
from datetime import datetime, timezone
from app.skills.base_skill import BaseSkill
from app.models.context import DiagnosisContext
from app.models.diagnosis import SkillResult
from app.rules.root_cause_rules import run_yaml_rules
from app.skills.evidence_consistency import check_evidence_consistency, apply_confidence_cap
from app.skills.evidence_classifier import confidence_from_score

_RULES_FILE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "rules", "root_cause_rules.yaml")
)


class RootCauseSkill(BaseSkill):
    skill_name = "RootCauseSkill"
    tool_name = "MModelSkill/locate_root_cause"
    title = "根因定位"

    _GENERIC_TRACE_EXCEPTIONS = {
        "Error",
        "Exception",
        "HTTPError",
        "UnknownException",
    }

    def _collect_candidates(self, ctx: DiagnosisContext) -> list[dict]:
        candidates = []
        for source, rows in [
            ("trace", (ctx.trace_result or {}).get("root_candidates", [])),
            ("log", (ctx.log_result or {}).get("root_candidates", [])),
            ("metric", (ctx.metric_result or {}).get("metric_root_candidates", [])),
        ]:
            for row in rows:
                candidate = dict(row)
                candidate.setdefault("source", source)
                candidate.setdefault("score", 0.3)
                candidate.setdefault("type", "service_exception")
                candidate.setdefault("api", ctx.api)
                candidates.append(candidate)
        return candidates

    def _score_candidates(self, candidates: list[dict]) -> list[dict]:
        def _type_priority(root_type: str) -> int:
            if root_type == "service_exception":
                return -1
            if root_type == "slow_interface":
                return 0
            return 1

        grouped: dict[tuple[str, str], dict] = {}
        for candidate in candidates:
            service = candidate.get("service") or ""
            root_type = candidate.get("type") or "service_exception"
            if not service:
                continue
            key = (service, root_type)
            bucket = grouped.setdefault(key, {
                "service": service,
                "type": root_type,
                "component": candidate.get("component") or service,
                "api": candidate.get("api"),
                "exception_type": candidate.get("exception_type"),
                "score": 0.0,
                "sources": set(),
                "evidence": [],
                "raw_candidates": [],
                "is_propagation": bool(candidate.get("is_propagation")),
            })
            score = float(candidate.get("score") or 0.0)
            if candidate.get("is_propagation"):
                score *= 0.5
            bucket["score"] += score
            bucket["sources"].add(candidate.get("source"))
            bucket["evidence"].append(candidate.get("evidence") or candidate.get("metric_name") or root_type)
            bucket["raw_candidates"].append(candidate)
            if not bucket.get("exception_type") and candidate.get("exception_type"):
                bucket["exception_type"] = candidate.get("exception_type")
            if candidate.get("source") == "metric" and not bucket.get("metric_name"):
                bucket["metric_name"] = candidate.get("metric_name")
            if candidate.get("component") and candidate.get("source") in {"metric", "log"}:
                bucket["component"] = candidate.get("component")

        scored = []
        for bucket in grouped.values():
            source_bonus = 0.15 * max(0, len(bucket["sources"]) - 1)
            total = min(0.99, bucket["score"] + source_bonus)
            scored.append({
                **bucket,
                "score": round(total, 3),
                "sources": sorted(bucket["sources"]),
                "type_priority": _type_priority(bucket["type"]),
            })
        return sorted(scored, key=lambda item: (item["score"], item["type_priority"], len(item["sources"])), reverse=True)

    def _is_generic_trace_exception(self, exception_type: str | None) -> bool:
        token = (exception_type or "").strip()
        return bool(token) and (token in self._GENERIC_TRACE_EXCEPTIONS or token.isdigit())

    def _select_candidate(self, scored: list[dict], trace: dict, log: dict) -> dict:
        if not scored:
            return {}

        selected = scored[0]
        top_score = selected.get("score")
        tied = [item for item in scored if item.get("score") == top_score]
        if len(tied) < 2:
            return selected

        trace_service = trace.get("first_error_service") or ""
        log_service = log.get("upstream_service") or ""
        if not trace_service or not log_service or trace_service == log_service:
            return selected
        if not self._is_generic_trace_exception(trace.get("first_error_exception")):
            return selected

        preferred = next(
            (
                item for item in tied
                if item.get("service") == log_service and "log" in (item.get("sources") or [])
            ),
            None,
        )
        current = next(
            (
                item for item in tied
                if item.get("service") == trace_service and "trace" in (item.get("sources") or [])
            ),
            None,
        )
        if preferred and current:
            return preferred
        return selected

    def _infer_component(self, selected: dict, candidates: list[dict]) -> str:
        service = selected.get("service")
        root_type = selected.get("type")
        for candidate in candidates:
            candidate_service = candidate.get("service") or ""
            if candidate.get("type") == root_type and candidate_service != service and candidate_service.startswith(("redis-", "mysql-", "nginx-")):
                return candidate_service
        return selected.get("component") or service or ""

    def _resolve_root_cause_api(self, ctx: DiagnosisContext, selected_api: str, root_cause_service: str) -> str:
        if not root_cause_service:
            return selected_api
        exposed_api = next(
            (
                edge.get("target", "")
                for edge in (ctx.graph_result or {}).get("edges", [])
                if edge.get("source") == root_cause_service
                and edge.get("label") == "exposes"
                and edge.get("target")
            ),
            "",
        )
        if exposed_api and (not selected_api or selected_api == ctx.api):
            return exposed_api
        return selected_api or exposed_api

    def _augment_graph_with_root_component(self, ctx: DiagnosisContext, service: str, component: str) -> None:
        if not service or not component or component == service or not ctx.graph_result:
            return
        lowered = component.lower()
        node_type = "Dependency" if lowered.startswith(("redis-", "mysql-")) or "network" in lowered else "Instance"
        nodes = ctx.graph_result.setdefault("nodes", [])
        edges = ctx.graph_result.setdefault("edges", [])
        if not any(node.get("id") == component for node in nodes):
            nodes.append({
                "id": component,
                "label": component,
                "node_type": node_type,
                "is_root_cause": True,
                "is_entry": False,
            })
        label = "depends_on" if node_type == "Dependency" else "runs_on"
        if not any(edge.get("source") == service and edge.get("target") == component and edge.get("label") == label for edge in edges):
            edges.append({"source": service, "target": component, "label": label})

    def run(self, ctx: DiagnosisContext) -> SkillResult:
        t0 = _time.monotonic()
        started_at = datetime.now(timezone.utc).isoformat()
        execution_log = []

        execution_log.append("读取 backend/data/rules/root_cause_rules.yaml")
        try:
            with open(_RULES_FILE, "r", encoding="utf-8") as f:
                rules_yaml = yaml.safe_load(f)
            rule_count = len((rules_yaml or {}).get("rules", []))
        except Exception:
            rule_count = 0
        execution_log.append(f"加载 {rule_count} 条根因规则元数据")

        trace = ctx.trace_result or {}
        log = ctx.log_result or {}
        metric = ctx.metric_result or {}
        consistency = check_evidence_consistency(
            trace_summary=trace,
            log_summary=log,
            metric_summary=metric,
            graph_summary=getattr(ctx, "graph_result", {}) or {},
        )
        ctx.evidence_consistency = consistency
        execution_log.append(f"证据一致性校验：has_conflict={consistency['has_conflict']}，冲突数={len(consistency['conflicts'])}")

        candidates = self._collect_candidates(ctx)
        scored = self._score_candidates(candidates)
        execution_log.append(f"聚合候选 {len(candidates)} 个，评分后候选 {len(scored)} 个")

        yaml_result = run_yaml_rules(trace, log)
        selected = self._select_candidate(scored, trace, log)
        if yaml_result and yaml_result.get("rule") == "rule_upstream_bad_parameter":
            selected = {
                "service": yaml_result.get("root_cause_service"),
                "api": yaml_result.get("root_cause_api"),
                "type": yaml_result.get("root_cause_type"),
                "component": yaml_result.get("root_cause_service"),
                "exception_type": trace.get("first_error_exception"),
                "score": 0.95,
                "sources": ["trace", "log", "yaml_rule"],
                "evidence": [yaml_result.get("root_cause_reason")],
                "raw_candidates": [],
            }
            applied_rule = yaml_result.get("rule")
            execution_log.append("命中上游非法参数规则，作为结构化规则结果输出")
        else:
            applied_rule = "deterministic_evidence_scoring"

        confidence = confidence_from_score(float(selected.get("score") or 0.0))
        confidence = apply_confidence_cap(confidence, consistency)
        root_cause_service = selected.get("service") or trace.get("first_error_service") or log.get("upstream_service") or ""
        root_cause_api = self._resolve_root_cause_api(
            ctx,
            selected.get("api") or trace.get("first_error_api") or ctx.api,
            root_cause_service,
        )
        root_cause_type = selected.get("type") or "service_exception"
        exception_type = selected.get("exception_type") or trace.get("first_error_exception") or log.get("upstream_error_type")
        bad_param = (
            trace.get("extracted_bad_parameter")
            or log.get("extracted_bad_parameter_from_log")
            or (log.get("extracted_query_params") or {}).get("id")
            or trace.get("bad_param")
            or log.get("error_param")
        )
        component = self._infer_component(selected, candidates) if selected else root_cause_service
        evidence_by_source = {
            "trace": trace.get("root_candidates", []) or trace.get("abnormal_spans", []),
            "log": log.get("root_candidates", []) or log.get("log_evidence", []),
            "metric": metric.get("metric_root_candidates", []) or metric.get("anomaly_details", []),
            "graph": (ctx.graph_result or {}).get("summary", ""),
        }

        root_cause_reason = (
            f"结构化评分选择 {root_cause_service}/{root_cause_api}：{root_cause_type}。"
            f"证据来源={selected.get('sources', [])}，得分={selected.get('score', 0)}。"
        )
        root_cause_result_dict = {
            "root_cause_service": root_cause_service,
            "root_cause_component": component,
            "root_cause_api": root_cause_api,
            "root_cause_type": root_cause_type,
            "exception_type": exception_type,
            "bad_param": bad_param,
            "root_cause_reason": root_cause_reason,
            "confidence": confidence,
            "is_confirmed": not consistency.get("has_conflict") and bool(root_cause_service),
            "evidence_conflicts": consistency.get("conflicts", []),
            "evidence_by_source": evidence_by_source,
            "candidates": [
                {
                    "service": item.get("service"),
                    "component": item.get("component"),
                    "api": item.get("api"),
                    "type": item.get("type"),
                    "score": item.get("score"),
                    "confidence": confidence_from_score(float(item.get("score") or 0.0)),
                    "sources": item.get("sources"),
                    "evidence": item.get("evidence"),
                }
                for item in scored[:8]
            ],
            "applied_rule": applied_rule,
            "scoring_reason": root_cause_reason,
            "source": "deterministic_evidence_scoring",
        }
        ctx.root_cause_result = root_cause_result_dict
        self._augment_graph_with_root_component(ctx, root_cause_service, component)
        execution_log.append(f"根因服务：{root_cause_service}，根因类型：{root_cause_type}，置信度：{confidence}")

        duration_ms = max(1, int((_time.monotonic() - t0) * 1000))
        finished_at = datetime.now(timezone.utc).isoformat()
        evidence = [
            f"Trace 候选数：{len(trace.get('root_candidates', []))}",
            f"Log 候选数：{len(log.get('root_candidates', []))}",
            f"Metric 候选数：{len(metric.get('metric_root_candidates', []))}",
            f"选定根因：{root_cause_service}/{root_cause_api} {root_cause_type}",
            f"置信度：{confidence}",
        ]

        return SkillResult(
            skill_name=self.skill_name,
            tool_name=self.tool_name,
            title=self.title,
            status="success",
            summary=f"根因服务：{root_cause_service}，根因接口：{root_cause_api}，根因类型：{root_cause_type}。",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            input={
                "rules_file": "backend/data/rules/root_cause_rules.yaml",
                "trace_evidence": trace.get("root_candidates", []),
                "log_evidence": log.get("root_candidates", []),
                "metric_evidence": metric.get("metric_root_candidates", []),
            },
            output=ctx.root_cause_result,
            evidence=evidence,
            execution_log=execution_log,
            explanation="综合 trace/log/metric 的结构化候选进行确定性评分，LLM 不参与根因覆盖。",
        )
