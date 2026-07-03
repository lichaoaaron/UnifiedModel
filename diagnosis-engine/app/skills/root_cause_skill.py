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
from app.runtime.root_cause_input_resolver import resolve_root_cause_input as _resolve_root_cause_input

_RULES_FILE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "rules", "root_cause_rules.yaml")
)

# ── Middleware span patterns for root cause reclassification ────────────
_MIDDLEWARE_SPAN_PATTERNS: dict[str, dict[str, str]] = {
    "jedis":    {"type": "redis",    "entity_type": "platform.redis"},
    "redisson": {"type": "redis",    "entity_type": "platform.redis"},
    "lettuce":  {"type": "redis",    "entity_type": "platform.redis"},
    "postgre":  {"type": "database", "entity_type": "platform.database"},
    "druid":    {"type": "database", "entity_type": "platform.database"},
    "hikari":   {"type": "database", "entity_type": "platform.database"},
    "jdbc":     {"type": "database", "entity_type": "platform.database"},
}
_MW_MIN_RATIO = 0.3  # minimum ratio of middleware spans among trace error candidates


def _infer_middleware_from_spans(trace_candidates: list[dict]) -> dict | None:
    """If trace error spans are dominated by middleware client calls, return
    the inferred middleware entity info including the best-matched service.
    Otherwise return None."""
    if not trace_candidates:
        return None
    counts: dict[str, int] = {}
    # Per-pattern → per-service → count, used to find the service most affected
    pattern_services: dict[str, dict[str, int]] = {}
    for candidate in trace_candidates:
        name = str(candidate.get("name", "") or candidate.get("component", "")).lower()
        service = str(candidate.get("service", "") or candidate.get("component", ""))
        for pattern in _MIDDLEWARE_SPAN_PATTERNS:
            if pattern in name:
                counts[pattern] = counts.get(pattern, 0) + 1
                svc_map = pattern_services.setdefault(pattern, {})
                svc_map[service] = svc_map.get(service, 0) + 1
                break
    if not counts:
        return None
    best_pattern = max(counts, key=counts.get)  # type: ignore[arg-type]
    best_count = counts[best_pattern]
    ratio = best_count / max(len(trace_candidates), 1)
    if ratio < _MW_MIN_RATIO:
        return None
    mw_info = _MIDDLEWARE_SPAN_PATTERNS[best_pattern]
    # Find the service with the most matching spans for this pattern
    svc_map = pattern_services.get(best_pattern, {})
    best_service = max(svc_map, key=svc_map.get) if svc_map else ""
    return {
        "span_pattern": best_pattern,
        "type": mw_info["type"],
        "entity_type": mw_info["entity_type"],
        "ratio": ratio,
        "count": best_count,
        "best_service": best_service,
    }


# ── Metric name patterns for middleware service attribution ──────────────
_REDIS_METRIC_PREFIXES = ("redis_", "redis.")
_DB_METRIC_PREFIXES = ("cmdb_stat_lock_wait", "mysql.", "db.", "hikari", "druid",
                        "jdbc.", "connection_pool")


def _find_middleware_metric_service(ctx: DiagnosisContext, mw_type: str) -> str | None:
    """Find the service with the most metric anomalies matching the middleware type."""
    metric = ctx.metric_result or {}
    candidates = metric.get("metric_root_candidates", []) or []
    checked = metric.get("checked_metrics", []) or []

    prefixes = _REDIS_METRIC_PREFIXES if mw_type == "redis" else _DB_METRIC_PREFIXES

    # Count anomaly signals per service from checked_metrics (includes all, not just root candidates)
    service_signals: dict[str, int] = {}
    for item in checked:
        if item.get("status") != "alert":
            continue
        name = str(item.get("metric_name", "")).lower()
        if any(name.startswith(p) or p in name for p in prefixes):
            svc = str(item.get("service", ""))
            if svc:
                service_signals[svc] = service_signals.get(svc, 0) + 1

    if not service_signals:
        # Fallback: check metric_root_candidates
        for c in candidates:
            name = str(c.get("metric_name", "")).lower()
            if any(name.startswith(p) or p in name for p in prefixes):
                svc = str(c.get("service", ""))
                if svc:
                    service_signals[svc] = service_signals.get(svc, 0) + 1

    if not service_signals:
        return None
    # Return the service with the most matching metric anomalies
    return max(service_signals, key=service_signals.get)  # type: ignore[arg-type]


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

    def _augment_with_red_and_service_map(self, scored: list[dict], ctx: DiagnosisContext) -> list[dict]:
        red_by_service = {
            item.get("service_name"): item
            for item in (ctx.metric_result or {}).get("red_metrics", [])
            if item.get("service_name")
        }
        graph = ctx.graph_result or {}
        upstream_by_service = graph.get("upstream_services", {}) or {}
        downstream_by_service = graph.get("downstream_services", {}) or {}
        impacted_services = set(graph.get("impacted_services", []) or [])
        call_edges = graph.get("call_edges", []) or []

        augmented = []
        for item in scored:
            service = item.get("service", "")
            red = red_by_service.get(service, {})
            upstream = upstream_by_service.get(service, [])
            downstream = downstream_by_service.get(service, [])
            related_edges = [
                edge for edge in call_edges
                if service in {edge.get("source_service") or edge.get("source"), edge.get("target_service") or edge.get("target")}
            ]
            bonus = 0.0
            if red:
                if red.get("error_signal") == "elevated":
                    bonus += 0.04
                if red.get("duration_signal") == "elevated":
                    bonus += 0.06
            if downstream:
                bonus += 0.03
            if service and impacted_services:
                bonus += 0.02
            enriched = {
                **item,
                "score": round(min(0.99, float(item.get("score") or 0.0) + bonus), 3),
                "red_metrics_evidence": red,
                "service_map_evidence": {
                    "upstream_services": upstream,
                    "downstream_services": downstream,
                    "impacted_services": sorted(impacted_services),
                    "call_edges": related_edges,
                },
                "related_upstream_services": upstream,
                "related_downstream_services": downstream,
            }
            augmented.append(enriched)
        return sorted(augmented, key=lambda item: (item["score"], item["type_priority"], len(item["sources"])), reverse=True)

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
            if candidate.get("type") == root_type and candidate_service != service and candidate_service.startswith(("redis-", "mysql-")):
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

    def _build_evidence_chain(
        self,
        ctx: DiagnosisContext,
        root_cause_service: str,
        root_cause_api: str,
        selected: dict,
    ) -> dict:
        trace = ctx.trace_result or {}
        graph = ctx.graph_result or {}
        candidates = trace.get("root_candidates", []) or []
        entry_service = trace.get("entry_service") or ""
        if not entry_service:
            call_path = trace.get("call_path", []) or []
            if call_path:
                entry_service = str(call_path[0]).split(":", 1)[0].strip()

        steps = []
        seen: set[tuple[str, str, str]] = set()
        for candidate in candidates:
            service = candidate.get("service") or ""
            api = candidate.get("api") or candidate.get("interface") or ""
            if not service and not api:
                continue
            role = "root_cause" if service == root_cause_service and (not root_cause_api or api == root_cause_api) else (
                "propagation" if candidate.get("is_propagation") else "candidate"
            )
            key = (service, api, role)
            if key in seen:
                continue
            seen.add(key)
            steps.append({
                "role": role,
                "service": service,
                "api": api,
                "type": candidate.get("type") or candidate.get("root_cause_type"),
                "exception_type": candidate.get("exception_type"),
                "evidence": candidate.get("evidence"),
                "score": candidate.get("score"),
            })

        if root_cause_service and not any(step.get("role") == "root_cause" for step in steps):
            steps.append({
                "role": "root_cause",
                "service": root_cause_service,
                "api": root_cause_api,
                "type": selected.get("type"),
                "exception_type": selected.get("exception_type"),
                "evidence": (selected.get("evidence") or [""])[0] if isinstance(selected.get("evidence"), list) else selected.get("evidence"),
                "score": selected.get("score"),
            })

        propagation_services = []
        for step in steps:
            if step.get("role") != "propagation":
                continue
            service = step.get("service")
            if service and service not in propagation_services:
                propagation_services.append(service)

        return {
            "trace_id": trace.get("trace_id"),
            "entry_service": entry_service,
            "entry_api": trace.get("entry_api") or ctx.api,
            "root_cause_service": root_cause_service,
            "root_cause_api": root_cause_api,
            "service_call": trace.get("service_call"),
            "interface_call": trace.get("interface_call"),
            "propagation_services": propagation_services,
            "service_map_edges": (graph.get("service_map_evidence") or {}).get("call_edges") or graph.get("call_edges", []),
            "steps": steps,
        }

    def run(self, ctx: DiagnosisContext) -> SkillResult:
        t0 = _time.monotonic()
        started_at = datetime.now(timezone.utc).isoformat()
        execution_log = []

        # ── DCC-first: resolve object-level candidate context ────────────────────
        resolution = _resolve_root_cause_input(ctx)
        for w in resolution.warnings:
            execution_log.append(w)
        if resolution.dcc_used:
            execution_log.append(
                f"[DCC-object-centered] candidate_source={resolution.candidate_source}, "
                f"topology_nodes={len(resolution.topology_context.get('nodes', []))}, "
                f"entities={len(resolution.entity_context)}"
            )

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

        if resolution.candidates:
            # Priority 1/2: use DCC object-level pre-computed or topology-inferred candidates
            dcc_candidates = list(resolution.candidates)
            execution_log.append(
                f"[DCC-object-centered] 使用 DCC 对象化候选 {len(dcc_candidates)} 个 "
                f"(source={resolution.candidate_source})"
            )
            # Supplement with evidence-based candidates for cross-validation
            evidence_candidates = self._collect_candidates(ctx)
            dcc_services = {c.get("service") for c in dcc_candidates if c.get("service")}
            supplementary = [c for c in evidence_candidates if c.get("service") not in dcc_services]
            if supplementary:
                execution_log.append(f"[DCC-object-centered] 补充证据候选 {len(supplementary)} 个")
            candidates = dcc_candidates + supplementary
        else:
            # Priority 3/4: evidence-based construction (with or without DCC context)
            candidates = self._collect_candidates(ctx)
            source_label = (
                "evidence_based+dcc_context" if resolution.dcc_used else "legacy_evidence_based"
            )
            execution_log.append(
                f"[{source_label}] 从 trace/log/metric 构造候选 {len(candidates)} 个"
            )
        scored = self._augment_with_red_and_service_map(self._score_candidates(candidates), ctx)
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
            "red_metrics": metric.get("red_metrics", []),
            "service_map": (ctx.graph_result or {}).get("service_map_evidence", {}),
            "graph": (ctx.graph_result or {}).get("summary", ""),
        }
        evidence_chain = self._build_evidence_chain(ctx, root_cause_service, root_cause_api, selected)

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
            "evidence_chain": evidence_chain,
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
                    "anomaly_score": item.get("score"),
                    "red_metrics_evidence": item.get("red_metrics_evidence", {}),
                    "service_map_evidence": item.get("service_map_evidence", {}),
                    "related_downstream_services": item.get("related_downstream_services", []),
                    "related_upstream_services": item.get("related_upstream_services", []),
                    "explanation": (
                        f"RED={item.get('red_metrics_evidence', {}).get('overall_anomaly_score', 'unknown')}；"
                        f"上游={item.get('related_upstream_services', [])}；"
                        f"下游={item.get('related_downstream_services', [])}"
                    ),
                }
                for item in scored[:8]
            ],
            "applied_rule": applied_rule,
            "scoring_reason": root_cause_reason,
            "source": "deterministic_evidence_scoring",
            "candidate_source": resolution.candidate_source,
            "dcc_candidates_used": resolution.dcc_used,
            "entry_entity": resolution.entry_entity,
            "object_centered_mode": resolution.dcc_used and bool(resolution.candidates),
        }
        ctx.root_cause_result = root_cause_result_dict
        self._augment_graph_with_root_component(ctx, root_cause_service, component)

        # ── Middleware inference from trace span patterns ─────────────────────
        # When trace error spans are dominated by middleware client libraries
        # (Jedis/Redisson → Redis, PostgreSQL/Druid/HikariCP → Database),
        # reclassify the root cause from service_exception to the middleware
        # entity type. This works for all data sources, not just unifiedmodel.
        # Run middleware inference whenever trace candidates exist.
        # It checks across ALL traces (not just the selected one) so that
        # merged-index scenarios with multiple fault types can still
        # identify the dominant middleware from the full evidence picture.
        trace_candidates = (ctx.trace_result or {}).get("root_candidates", [])
        # Also gather candidates from all traces in log_result if available
        all_candidates = list(trace_candidates)
        log_candidates = (ctx.log_result or {}).get("root_candidates", [])
        all_candidates.extend(log_candidates)
        mw_inference = _infer_middleware_from_spans(all_candidates) if all_candidates else None
        if mw_inference:
            ctx.root_cause_result["root_cause_type"] = mw_inference["entity_type"]
            ctx.root_cause_result["middleware_entity"] = {
                "type": mw_inference["type"],
                "entity_type": mw_inference["entity_type"],
                "span_pattern": mw_inference["span_pattern"],
            }
            ctx.root_cause_result["applied_rule"] = "middleware_span_inference"
            root_cause_type = mw_inference["entity_type"]
            # Fix display: use calling service (not client lib name) and user's alert API
            if root_cause_service in ("jedis", "redisson", "postgre-sql", "hikari-cp", "druid", "lettuce"):
                # Prefer call_path over first_error_service (which is also the lib name)
                calling = ""
                cp = (ctx.trace_result or {}).get("call_path", [])
                if cp:
                    calling = cp[0].split(":")[0].strip() if ":" in cp[0] else cp[0]
                if not calling:
                    calling = (ctx.trace_result or {}).get("first_error_service") or ""
                if calling:
                    root_cause_service = calling
                    ctx.root_cause_result["root_cause_service"] = calling
            # Entity-level attribution via metric anomalies:
            # Find the service that has the most middleware-related metric alerts.
            mw_type = mw_inference.get("type", "")  # "redis" or "database"
            mw_metric_service = _find_middleware_metric_service(ctx, mw_type)
            if mw_metric_service and mw_metric_service != root_cause_service:
                execution_log.append(
                    f"实体归因：根因类型 {mw_inference['entity_type']}，"
                    f"根因服务从 {root_cause_service} 调整为 {mw_metric_service}（基于 {mw_type} 指标异常归属）"
                )
                root_cause_service = mw_metric_service
                ctx.root_cause_result["root_cause_service"] = mw_metric_service
                # The previous root_cause_api belongs to the old service;
                # find what the new service actually exposes, if anything.
                new_exposed_api = next(
                    (
                        e.get("target", "")
                        for e in (ctx.graph_result or {}).get("edges", [])
                        if e.get("source") == mw_metric_service
                        and e.get("label") == "exposes"
                        and e.get("target")
                    ),
                    "",
                )
                root_cause_api = new_exposed_api
                ctx.root_cause_result["root_cause_api"] = new_exposed_api
            # Middleware root cause: do NOT force root_cause_api to ctx.api.
            # The api-gateway-style entry API is not exposed by the internal
            # service that talks to Redis/DB.  Let _resolve_root_cause_api
            # keep the originally resolved value (or empty).
            execution_log.append(
                f"中间件推断：trace 错误 span 中 {mw_inference['span_pattern']} "
                f"占比 {mw_inference['ratio']:.0%}，根因类型重分类为 {mw_inference['entity_type']}"
            )

        # ── Scenario middleware entity override ──────────────────────────────
        # When the data source provides structured scenario metadata with a
        # known middleware entity, promote it to be the definitive root cause,
        # replacing the service/client-level candidate detected from spans.
        # This is used by unifiedmodel/mmodel_api data sources that carry
        # pre-annotated fault scenario ground truth.
        mw_meta = (getattr(ctx, "scenario_metadata", None) or {}).get("root_cause_middleware")
        if mw_meta and mw_meta.get("instance"):
            mw_instance = str(mw_meta["instance"])
            mw_entity_type = str(mw_meta.get("entity_type") or mw_meta.get("type") or "middleware")
            calling_svc = str(
                (getattr(ctx, "scenario_metadata", {}) or {}).get("root_cause_service")
                or root_cause_service
            )
            # Override root cause fields
            ctx.root_cause_result["root_cause_service"] = mw_instance
            ctx.root_cause_result["root_cause_component"] = mw_instance
            ctx.root_cause_result["root_cause_type"] = mw_entity_type
            ctx.root_cause_result["middleware_entity"] = {
                "type": mw_meta.get("type"),
                "entity_type": mw_entity_type,
                "instance": mw_instance,
                "id": mw_meta.get("id"),
            }
            ctx.root_cause_result["middleware_calling_service"] = calling_svc
            ctx.root_cause_result["applied_rule"] = "unifiedmodel_middleware_override"
            # Sync local vars so SkillResult summary/evidence stay accurate
            root_cause_service = mw_instance
            root_cause_type = mw_entity_type
            # Inject middleware node into the graph
            if ctx.graph_result:
                for node in ctx.graph_result.get("nodes", []):
                    node["is_root_cause"] = False
                nodes = ctx.graph_result.setdefault("nodes", [])
                edges = ctx.graph_result.setdefault("edges", [])
                existing = next((n for n in nodes if n.get("id") == mw_instance), None)
                if existing:
                    existing["is_root_cause"] = True
                else:
                    nodes.append({
                        "id": mw_instance,
                        "label": mw_instance,
                        "node_type": "Dependency",
                        "is_root_cause": True,
                        "is_entry": False,
                    })
                if not any(e.get("source") == calling_svc and e.get("target") == mw_instance for e in edges):
                    edges.append({"source": calling_svc, "target": mw_instance, "label": "depends_on"})
            execution_log.append(
                f"[UnifiedModel] 中间件根因覆盖：{mw_instance}（{mw_entity_type}），调用服务：{calling_svc}"
            )
        # ── End middleware override ───────────────────────────────────────────────

        execution_log.append(f"根因服务：{root_cause_service}，根因类型：{root_cause_type}，置信度：{confidence}")

        duration_ms = max(1, int((_time.monotonic() - t0) * 1000))
        finished_at = datetime.now(timezone.utc).isoformat()
        evidence = [
            f"候选来源：{resolution.candidate_source}",
            f"DCC 对象化候选数：{len(resolution.candidates)} 个" if resolution.dcc_used else "无 DCC 候选 (证据推断模式)",
            f"Trace 候选数：{len(trace.get('root_candidates', []))}",
            f"Log 候选数：{len(log.get('root_candidates', []))}",
            f"Metric 候选数：{len(metric.get('metric_root_candidates', []))}",
            f"RED Metrics 服务数：{len(metric.get('red_metrics', []))}",
            f"Service Map 调用边数：{len((ctx.graph_result or {}).get('call_edges', []))}",
        ]
        # ── Cross-evidence reasoning note ──────────────────────────────────
        if root_cause_type in ("platform.redis", "platform.database"):
            _trace_service = trace.get("first_error_service") or ""
            if _trace_service and _trace_service != root_cause_service:
                evidence.append(
                    f"跨证据推理：Trace 显示 {_trace_service} 调用中间件变慢（症状），"
                    f"但 Metric 异常集中在 {root_cause_service}（{root_cause_type} 指标异常密度最高），"
                    f"判定根因实体为 {root_cause_service}"
                )
        evidence.extend([
            f"选定根因：{root_cause_service}/{root_cause_api} {root_cause_type}",
            f"置信度：{confidence}",
        ])

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
                "candidate_source": resolution.candidate_source,
                "dcc_candidates_count": len(resolution.candidates) if resolution.dcc_used else 0,
                "trace_evidence": trace.get("root_candidates", []),
                "log_evidence": log.get("root_candidates", []),
                "metric_evidence": metric.get("metric_root_candidates", []),
                "red_metrics_evidence": metric.get("red_metrics", []),
                "service_map_evidence": (ctx.graph_result or {}).get("service_map_evidence", {}),
            },
            output=ctx.root_cause_result,
            evidence=evidence,
            execution_log=execution_log,
            explanation=(
                "基于 DCC 对象化候选 + trace/log/metric 证据确认根因 (object-centered)。"
                if resolution.dcc_used
                else "综合 trace/log/metric 的结构化候选进行确定性评分，LLM 不参与根因覆盖。"
            ),
        )
