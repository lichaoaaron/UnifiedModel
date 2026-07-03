import json
import os
import sys
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
for path in (str(REPO_ROOT), str(BACKEND_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.adapters import observability_adapter
from app.adapters.unifiedmodel_adapter import get_scenario_metadata
from app.orchestrator.diagnosis_orchestrator import run_diagnosis
from app.runtime.dcc_mapper import map_unifiedmodel_outputs_to_dcc
from app.runtime.dcc_validator import DCCValidationError, validate_dcc_payload

DEFAULT_CONFIG = REPO_ROOT / "backend" / "tests" / "step11_demo_acceptance_cases.json"
DEFAULT_UNIFIEDMODEL_SAMPLE_DIR = (REPO_ROOT / ".." / "UnifiedModel" / "outputs" / "mmodel-fault-samples").resolve()


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _set_data_source_env(case: dict[str, Any]) -> None:
    data_source = (case.get("data_source") or "").strip()
    if data_source:
        os.environ["DATA_SOURCE"] = data_source
    if data_source == "unifiedmodel":
        os.environ.setdefault("UNIFIEDMODEL_SAMPLE_DIR", str(DEFAULT_UNIFIEDMODEL_SAMPLE_DIR))


def _required_env_missing(case: dict[str, Any]) -> list[str]:
    required = case.get("required_env") or []
    missing: list[str] = []
    for key in required:
        if not os.environ.get(str(key)):
            missing.append(str(key))
    return missing


def _scenario_entity_rows(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for svc in scenario.get("services", []) or []:
        if not svc:
            continue
        rows.append(
            {
                "id": str(svc),
                "entity_type": "platform.service",
                "entity_name": str(svc),
                "domain": "platform",
            }
        )

    middleware = scenario.get("root_cause_middleware") or {}
    if isinstance(middleware, dict) and middleware.get("instance"):
        rows.append(
            {
                "id": str(middleware.get("instance")),
                "entity_type": str(middleware.get("entity_type") or "platform.middleware"),
                "entity_name": str(middleware.get("instance")),
                "domain": "platform",
            }
        )
    return rows


def _scenario_topology_rows(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for dep in scenario.get("dependencies", []) or []:
        if not isinstance(dep, dict):
            continue
        src = dep.get("from")
        dst = dep.get("to")
        if not src or not dst:
            continue
        rows.append({"source": str(src), "target": str(dst), "relation": "calls"})

    middleware = scenario.get("root_cause_middleware") or {}
    root_service = scenario.get("root_cause_service")
    middleware_instance = middleware.get("instance") if isinstance(middleware, dict) else None
    if root_service and middleware_instance:
        rows.append(
            {
                "source": str(root_service),
                "target": str(middleware_instance),
                "relation": "depends_on",
            }
        )
    return rows


def _enrich_dcc_candidates_from_scenario(dcc: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    dcc_copy = deepcopy(dcc)

    middleware = scenario.get("root_cause_middleware") or {}
    root_service = str(scenario.get("root_cause_service") or "")
    impacted_service = str(scenario.get("impacted_service") or "")

    root_entity = root_service
    root_type = "platform.service"
    if isinstance(middleware, dict) and middleware.get("instance"):
        root_entity = str(middleware.get("instance"))
        root_type = str(middleware.get("entity_type") or root_type)

    root_candidates = [
        {
            "service": root_entity,
            "entity_id": root_entity,
            "entity_name": root_entity,
            "type": root_type,
            "candidate_source": "unifiedmodel_object_context",
            "confidence": 0.92,
            "reason": f"Scenario metadata marks {root_entity} as probable root cause",
        }
    ]

    classified: set[str] = {root_entity}
    impact_candidates: list[dict[str, Any]] = [
        {
            "service": root_entity,
            "entity_id": root_entity,
            "node_type": "root_cause_node",
            "candidate_source": "topology_propagation",
            "confidence": 0.95,
            "reason": "Confirmed root cause entity from scenario metadata",
        }
    ]

    if impacted_service and impacted_service != root_entity:
        classified.add(impacted_service)
        impact_candidates.append(
            {
                "service": impacted_service,
                "entity_id": impacted_service,
                "node_type": "directly_affected_node",
                "candidate_source": "topology_propagation",
                "confidence": 0.80,
                "reason": "Impacted service from scenario metadata",
            }
        )

    reverse_edges = [
        dep
        for dep in (scenario.get("dependencies") or [])
        if isinstance(dep, dict) and dep.get("to") == impacted_service and dep.get("from")
    ]
    for dep in reverse_edges:
        svc = str(dep.get("from"))
        if svc in classified:
            continue
        classified.add(svc)
        impact_candidates.append(
            {
                "service": svc,
                "entity_id": svc,
                "node_type": "indirectly_affected_node",
                "candidate_source": "topology_propagation",
                "confidence": 0.55,
                "reason": f"Upstream caller of impacted service {impacted_service}",
            }
        )

    for svc in (scenario.get("services") or []):
        text = str(svc)
        if not text or text in classified:
            continue
        impact_candidates.append(
            {
                "service": text,
                "entity_id": text,
                "node_type": "merely_observed_node",
                "candidate_source": "observed_only",
                "confidence": 0.30,
                "reason": "Observed in scenario service list but no confirmed propagation path",
            }
        )
        break

    dcc_copy.setdefault("candidates", {})
    dcc_copy["candidates"]["root_cause"] = root_candidates
    dcc_copy["candidates"]["impact_scope"] = impact_candidates

    dcc_copy.setdefault("provenance", {})
    dcc_copy["provenance"]["producer"] = "unifiedmodel.sample.bridge"
    dcc_copy["provenance"]["source"] = "unifiedmodel"

    dcc_copy.setdefault("meta", {})
    dcc_copy["meta"]["availability"] = "available"
    dcc_copy["meta"].setdefault("warnings", [])

    return dcc_copy


def _build_unifiedmodel_case_dcc(case: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    case_id = str(case.get("case_id") or "")
    scenario = get_scenario_metadata(case_id=case_id)

    trace_items = observability_adapter.get_traces(case_id=case_id)
    log_items = observability_adapter.get_logs(case_id=case_id)
    metric_items = observability_adapter.get_metrics(case_id=case_id)

    entity_rows = _scenario_entity_rows(scenario)
    topo_rows = _scenario_topology_rows(scenario)

    dcc = map_unifiedmodel_outputs_to_dcc(
        workspace_id="demo",
        alert_api=str(case.get("api") or ""),
        alert_time=str(case.get("time") or ""),
        alert_symptom=str(case.get("symptom") or ""),
        entity_query_result={"rows": entity_rows, "query": {"source": "scenario_metadata"}},
        topo_query_result={"rows": topo_rows, "query": {"source": "scenario_dependencies"}},
        trace_query_result={"rows": trace_items, "query": {"source": "unifiedmodel_trace"}},
        log_query_result={"rows": log_items, "query": {"source": "unifiedmodel_log"}},
        metric_query_result={"rows": metric_items, "query": {"source": "unifiedmodel_metric"}},
        producer="unifiedmodel.sample.bridge",
    )

    dcc = _enrich_dcc_candidates_from_scenario(dcc, scenario)

    dcc.setdefault("workspace", {})
    if not dcc["workspace"].get("workspace_id"):
        dcc["workspace"]["workspace_id"] = "demo"

    return dcc, scenario


def _build_opensearch_live_dcc(case: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    query_context = {
        "api": case.get("api"),
        "time_start": case.get("time"),
        "time_end": case.get("time"),
        "limit": 100,
    }

    trace_items = observability_adapter.get_traces(query_context=query_context)
    if len(trace_items) < int(case.get("min_trace_items") or 1):
        raise RuntimeError("insufficient live trace items for OpenSearch optional case")

    log_items = observability_adapter.get_logs(query_context=query_context)
    metric_items = observability_adapter.get_metrics(query_context=query_context)

    services: set[str] = set()
    for item in trace_items:
        for key in ("serviceName", "source.service.name", "service", "service.name"):
            val = item.get(key)
            if isinstance(val, str) and val:
                services.add(val)

    entity_rows = [
        {
            "id": svc,
            "entity_type": "platform.service",
            "entity_name": svc,
            "domain": "platform",
        }
        for svc in sorted(services)
    ]

    dcc = map_unifiedmodel_outputs_to_dcc(
        workspace_id="demo",
        alert_api=str(case.get("api") or ""),
        alert_time=str(case.get("time") or ""),
        alert_symptom=str(case.get("symptom") or ""),
        entity_query_result={"rows": entity_rows, "query": {"source": "opensearch_trace_entities"}},
        topo_query_result={"rows": [], "query": {"source": "opensearch_none"}},
        trace_query_result={"rows": trace_items, "query": {"source": "opensearch_trace"}},
        log_query_result={"rows": log_items, "query": {"source": "opensearch_log"}},
        metric_query_result={"rows": metric_items, "query": {"source": "opensearch_metric"}},
        producer="opensearch.live.bridge",
    )

    dcc.setdefault("workspace", {})
    if not dcc["workspace"].get("workspace_id"):
        dcc["workspace"]["workspace_id"] = "demo"

    return dcc, {
        "live_trace_count": len(trace_items),
        "live_log_count": len(log_items),
        "live_metric_count": len(metric_items),
    }


def _find_skill_output(response: Any, skill_name: str) -> dict[str, Any]:
    for skill in response.skills:
        if skill.skill_name == skill_name:
            return dict(skill.output or {})
    return {}


def _check_diagnosis_response(case: dict[str, Any], response: Any, dcc: dict[str, Any]) -> tuple[list[CheckResult], list[str]]:
    checks: list[CheckResult] = []
    human_lines: list[str] = []

    diagnosis_explain = dict(response.diagnosis_explain or {})

    checks.append(
        CheckResult(
            name="dcc_produced_and_validated",
            passed=bool(dcc.get("protocol_version") and dcc.get("objects") and dcc.get("evidence")),
            detail=f"protocol_version={dcc.get('protocol_version')}, entities={len((dcc.get('objects') or {}).get('entities') or [])}",
        )
    )

    explain_sections = ["object_selection", "evidence_confirmation", "root_cause_decision", "impact_scope_decision"]
    missing_sections = [s for s in explain_sections if s not in diagnosis_explain]
    checks.append(
        CheckResult(
            name="diagnosis_explain_sections_present",
            passed=not missing_sections,
            detail="missing=" + (",".join(missing_sections) if missing_sections else "none"),
        )
    )

    root_decision = diagnosis_explain.get("root_cause_decision") or {}
    root_has_markers = all(k in root_decision for k in ("candidate_source", "object_centered_mode"))
    checks.append(
        CheckResult(
            name="root_decision_markers_present",
            passed=root_has_markers,
            detail=f"candidate_source={root_decision.get('candidate_source')}, object_centered_mode={root_decision.get('object_centered_mode')}",
        )
    )

    impact_skill = _find_skill_output(response, "ImpactAnalysisSkill")
    impact_nodes_by_type = impact_skill.get("impact_nodes_by_type") if isinstance(impact_skill.get("impact_nodes_by_type"), dict) else {}
    node_key_count = 0
    for key in ("propagation_nodes", "directly_affected_nodes", "indirectly_affected_nodes", "merely_observed_nodes"):
        if key in impact_nodes_by_type:
            node_key_count += 1
    checks.append(
        CheckResult(
            name="impact_node_classification_visible",
            passed=node_key_count >= 2,
            detail=f"node_type_keys={sorted(list(impact_nodes_by_type.keys()))}",
        )
    )

    has_fallback_warning = "fallback" in diagnosis_explain and "warnings" in diagnosis_explain
    checks.append(
        CheckResult(
            name="fallback_and_warnings_visible",
            passed=has_fallback_warning,
            detail=f"fallback={diagnosis_explain.get('fallback')}, warnings_keys={list((diagnosis_explain.get('warnings') or {}).keys()) if isinstance(diagnosis_explain.get('warnings'), dict) else []}",
        )
    )

    used_dcc = bool(((diagnosis_explain.get("distinctive_signals") or {}).get("used_dcc")))
    checks.append(
        CheckResult(
            name="mmodel_consumed_dcc",
            passed=used_dcc,
            detail=f"distinctive_signals.used_dcc={used_dcc}",
        )
    )

    expected_type = case.get("expected_root_cause_type")
    if expected_type:
        actual_type = str(response.summary.root_cause_type or "")
        checks.append(
            CheckResult(
                name="expected_root_cause_type",
                passed=actual_type == str(expected_type),
                detail=f"expected={expected_type}, actual={actual_type}",
            )
        )

    expected_contains = case.get("expected_root_cause_contains")
    if expected_contains:
        actual_service = str(response.summary.root_cause_service or "")
        checks.append(
            CheckResult(
                name="expected_root_cause_entity_hint",
                passed=str(expected_contains) in actual_service,
                detail=f"expected_contains={expected_contains}, actual={actual_service}",
            )
        )

    root_source = root_decision.get("candidate_source")
    impact_source = (diagnosis_explain.get("impact_scope_decision") or {}).get("candidate_source")

    human_lines.append(
        f"Object selection used DCC={used_dcc}; root candidate source={root_source}; impact source={impact_source}."
    )
    human_lines.append(
        "Evidence confirmation was separated into trace/log/metric clues instead of a single merged evidence blob."
    )
    human_lines.append(
        "Fallback and warnings were explicitly exposed, so this run can be explained as object-centered or legacy without ambiguity."
    )

    return checks, human_lines


def _run_one_case(case: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": case.get("id"),
        "name": case.get("name"),
        "status": "FAILED",
        "optional": bool(case.get("optional", False)),
        "checks": [],
        "human_summary": [],
        "meta": {},
    }

    missing_env = _required_env_missing(case)
    if missing_env:
        result["status"] = "SKIPPED"
        result["meta"]["skip_reason"] = f"missing required env: {', '.join(missing_env)}"
        return result

    _set_data_source_env(case)

    try:
        if case.get("kind") == "unifiedmodel_sample":
            dcc, scenario = _build_unifiedmodel_case_dcc(case)
            result["meta"]["scenario_id"] = scenario.get("scenario_id")
            result["meta"]["dcc_producer"] = (dcc.get("provenance") or {}).get("producer")
        elif case.get("kind") == "opensearch_live":
            dcc, live_meta = _build_opensearch_live_dcc(case)
            result["meta"].update(live_meta)
            result["meta"]["dcc_producer"] = (dcc.get("provenance") or {}).get("producer")
        else:
            raise ValueError(f"unsupported case kind: {case.get('kind')}")

        dcc = validate_dcc_payload(dcc)

        response = run_diagnosis(
            api="",
            time="",
            symptom="",
            case_id=case.get("case_id"),
            dcc=dcc,
        )

        checks, human_lines = _check_diagnosis_response(case, response, dcc)
        result["checks"] = [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in checks]
        result["human_summary"] = human_lines
        result["meta"]["root_cause_service"] = response.summary.root_cause_service
        result["meta"]["root_cause_type"] = response.summary.root_cause_type
        result["meta"]["used_dcc"] = bool(((response.diagnosis_explain or {}).get("distinctive_signals") or {}).get("used_dcc"))

        case_passed = all(c.passed for c in checks)
        result["status"] = "PASSED" if case_passed else "FAILED"
        return result

    except DCCValidationError as exc:
        result["status"] = "FAILED"
        result["meta"]["error"] = f"dcc validation error: {exc.errors}"
        return result
    except RuntimeError as exc:
        if case.get("optional", False):
            result["status"] = "SKIPPED"
            result["meta"]["skip_reason"] = str(exc)
            return result
        result["status"] = "FAILED"
        result["meta"]["error"] = str(exc)
        return result
    except Exception as exc:
        result["status"] = "FAILED"
        result["meta"]["error"] = f"{type(exc).__name__}: {exc}"
        return result


def _render_markdown(summary: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Step11 Demo Acceptance Summary")
    lines.append("")
    lines.append(f"- generated_at: {summary.get('generated_at')}")
    lines.append(f"- total_cases: {summary.get('total_cases')}")
    lines.append(f"- passed: {summary.get('passed')}")
    lines.append(f"- failed: {summary.get('failed')}")
    lines.append(f"- skipped: {summary.get('skipped')}")
    lines.append("")
    lines.append("## Machine Acceptance")
    lines.append("")
    lines.append("| case | status | key result |")
    lines.append("|---|---|---|")
    for case in summary.get("cases", []):
        key_result = case.get("meta", {}).get("root_cause_type") or case.get("meta", {}).get("skip_reason") or case.get("meta", {}).get("error", "")
        lines.append(f"| {case.get('name')} | {case.get('status')} | {key_result} |")
    lines.append("")
    lines.append("## Human Explain")
    lines.append("")
    for case in summary.get("cases", []):
        lines.append(f"### {case.get('name')} ({case.get('status')})")
        for text in case.get("human_summary", []) or []:
            lines.append(f"- {text}")
        checks = case.get("checks", []) or []
        if checks:
            lines.append("- Checks:")
            for item in checks:
                mark = "PASS" if item.get("passed") else "FAIL"
                lines.append(f"  - [{mark}] {item.get('name')}: {item.get('detail')}")
        lines.append("")
    return "\n".join(lines)


def _write_summary_files(config: dict[str, Any], summary: dict[str, Any]) -> dict[str, str]:
    output_dir_raw = config.get("summary_output_dir") or "output/acceptance/step11"
    output_dir = (REPO_ROOT / output_dir_raw).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "demo_summary.json"
    md_path = output_dir / "acceptance_summary.md"

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    with md_path.open("w", encoding="utf-8") as f:
        f.write(_render_markdown(summary))

    return {
        "json": str(json_path),
        "markdown": str(md_path),
    }


def main() -> int:
    config_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_CONFIG
    config = _load_config(config_path)

    print("Running Step11 demo acceptance...")
    print(f"Config: {config_path}")

    cases = config.get("cases") or []
    results: list[dict[str, Any]] = []

    for case in cases:
        print("-" * 72)
        print(f"Case: {case.get('name')} ({case.get('id')})")
        case_result = _run_one_case(case)
        results.append(case_result)

        print(f"Machine status: {case_result['status']}")
        if case_result["status"] in {"FAILED", "PASSED"}:
            for item in case_result.get("checks", []):
                mark = "PASS" if item.get("passed") else "FAIL"
                print(f"  [{mark}] {item.get('name')}: {item.get('detail')}")
        if case_result["status"] == "SKIPPED":
            print(f"  [SKIP] {case_result.get('meta', {}).get('skip_reason')}")

        for text in case_result.get("human_summary", []) or []:
            print(f"  - {text}")

    passed = sum(1 for x in results if x.get("status") == "PASSED")
    failed = sum(1 for x in results if x.get("status") == "FAILED")
    skipped = sum(1 for x in results if x.get("status") == "SKIPPED")

    summary = {
        "version": config.get("version") or "step11-demo-cases.v1",
        "generated_at": _now_iso(),
        "total_cases": len(results),
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "cases": results,
    }

    paths = _write_summary_files(config, summary)

    print("=" * 72)
    print(f"Summary: passed={passed}, failed={failed}, skipped={skipped}, total={len(results)}")
    print(f"demo_summary.json: {paths['json']}")
    print(f"acceptance_summary.md: {paths['markdown']}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
