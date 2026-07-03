"""
Evaluation coverage for examples/evaluation_cases/basic_root_cause_19.

The runtime diagnosis receives only trace/log/metric via data_dir. ground_truth.json
is read here for assertions only and must not be used by diagnosis logic.
"""
import json
import os
import sys

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
_BACKEND = os.path.join(_REPO_ROOT, "backend")
for _path in (_REPO_ROOT, _BACKEND):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from app.models.context import DiagnosisContext
from app.skills.alert_context_skill import AlertContextSkill
from app.skills.trace_analysis_skill import TraceAnalysisSkill
from app.skills.entity_binding_skill import EntityBindingSkill
from app.skills.log_analysis_skill import LogAnalysisSkill
from app.skills.metric_check_skill import MetricCheckSkill
from app.skills.graph_analysis_skill import GraphAnalysisSkill
from app.skills.root_cause_skill import RootCauseSkill
from app.skills.impact_analysis_skill import ImpactAnalysisSkill
from app.adapters.local_json_adapter import resolve_data_dir, resolve_request_context
from app.orchestrator.diagnosis_orchestrator import run_diagnosis

_EVAL_ROOT = os.path.join(_REPO_ROOT, "examples", "evaluation_cases", "basic_root_cause_19")
_EVALUATION_PIPELINE = [
    AlertContextSkill(),
    TraceAnalysisSkill(),
    EntityBindingSkill(),
    LogAnalysisSkill(),
    MetricCheckSkill(),
    GraphAnalysisSkill(),
    RootCauseSkill(),
    ImpactAnalysisSkill(),
]


def _unique_index_case() -> dict:
    evaluation_root = os.path.dirname(_EVAL_ROOT)
    indexed_cases = []
    for collection in os.listdir(evaluation_root):
        index_path = os.path.join(evaluation_root, collection, "index.json")
        if os.path.isfile(index_path):
            indexed_cases.extend(json.load(open(index_path, encoding="utf-8")))
    api_counts = {
        item["alert_api"]: sum(1 for candidate in indexed_cases if candidate.get("alert_api") == item["alert_api"])
        for item in indexed_cases
    }
    return next(item for item in indexed_cases if api_counts[item["alert_api"]] == 1)


def _load_json(path: str) -> dict | list:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


_TYPE_ALIASES = {
    "slow_interface": {"performance/slow_interface", "slow_interface"},
    "high_cpu": {"resource_exhaustion/high_cpu", "high_cpu"},
    "memory_leak": {"resource_exhaustion/memory_leak", "memory_leak"},
    "frequent_full_gc": {"resource_exhaustion/frequent_full_gc", "frequent_full_gc"},
    "thread_pool_exhaustion": {"resource_exhaustion/thread_pool_exhaustion", "thread_pool_exhaustion"},
    "connection_pool_exhaustion": {"resource_exhaustion/connection_pool_exhaustion", "connection_pool_exhaustion"},
    "error_loop": {"application_error/error_loop", "error_loop"},
    "redis_node_down": {"dependency_unavailable/redis_node_down", "redis_node_down"},
    "redis_slow_lua": {"dependency_performance/redis_slow_lua", "redis_slow_lua"},
    "redis_keys_command": {"dependency_performance/redis_keys_command", "redis_keys_command"},
    "redis_bigkey_blocking": {"dependency_performance/redis_bigkey_blocking", "redis_bigkey_blocking"},
    "redis_lock_stuck": {"dependency_contention/redis_lock_stuck", "redis_lock_stuck"},
    "mysql_slow_query": {"database_performance/mysql_slow_query", "mysql_slow_query"},
    "mysql_row_lock": {"database_contention/mysql_row_lock", "mysql_row_lock"},
    "mysql_table_lock": {"database_contention/mysql_table_lock", "mysql_table_lock"},
    "mysql_max_connections": {"database_resource/mysql_max_connections", "mysql_max_connections"},
    "nginx_connection_exhaustion": {"ingress_resource/nginx_connection_exhaustion", "nginx_connection_exhaustion"},
    "nginx_upstream_timeout": {"ingress_timeout/nginx_upstream_timeout", "nginx_upstream_timeout"},
    "network_packet_loss_latency": {"network_degradation/network_packet_loss_latency", "network_packet_loss_latency"},
}


def _run_evaluation_context(
    api: str,
    time: str,
    symptom: str,
    *,
    case_id: str | None = None,
    data_dir: str | None = None,
) -> DiagnosisContext:
    ctx = DiagnosisContext(api=api, time=time, symptom=symptom, case_id=case_id, data_dir=data_dir)
    for skill in _EVALUATION_PIPELINE:
        skill.run(ctx)
    return ctx


def _assert_root_type_matches(actual: str, expected: str, case_id: str) -> None:
    allowed = _TYPE_ALIASES.get(expected, {expected})
    assert actual in allowed, f"{case_id}: expected {expected} compatible type, got {actual}"


def test_basic_root_cause_19_cases():
    index = _load_json(os.path.join(_EVAL_ROOT, "index.json"))
    assert len(index) == 19

    for case in index:
        case_id = case["case_id"]
        case_dir = os.path.join(_EVAL_ROOT, case_id)
        ground_truth = _load_json(os.path.join(case_dir, "ground_truth.json"))
        expected = ground_truth["expected"]
        expected_rc = expected["root_cause"]

        ctx = _run_evaluation_context(
            api=ground_truth["alert_event"]["api"],
            time=ground_truth["alert_event"]["time"],
            symptom=ground_truth["alert_event"]["symptom"],
            case_id=case_id,
        )

        assert ctx.root_cause_result["root_cause_service"] == expected_rc["service"], case_id
        _assert_root_type_matches(ctx.root_cause_result["root_cause_type"], expected_rc["type"], case_id)
        assert expected["affected_services"][0] in ctx.impact_result["affected_services"], case_id

        root_output = ctx.root_cause_result
        assert root_output["root_cause_component"], case_id
        assert root_output["evidence_by_source"], case_id
        populated_sources = [
            source for source, evidence in root_output["evidence_by_source"].items()
            if evidence
        ]
        assert len(populated_sources) >= 2, case_id


def test_case_id_rejects_path_traversal():
    bad_case_ids = [
        "../observability",
        "..\\observability",
        "C:\\Windows\\System32",
        "01_trace_dominant_exception/../xxx",
        "/tmp/foo",
        "03_service_memory_leak/../08_redis_node_down",
        "..%2Fobservability",
        "..%5Cobservability",
    ]
    for case_id in bad_case_ids:
        try:
            resolve_data_dir(case_id=case_id)
        except ValueError:
            continue
        raise AssertionError(f"unsafe case_id was accepted: {case_id}")


def test_case_id_accepts_safe_slug_inside_evaluation_root():
    resolved = resolve_data_dir(case_id="03_service_memory_leak")
    assert resolved.startswith(os.path.normcase(os.path.abspath(os.path.join(_REPO_ROOT, "examples", "evaluation_cases"))))
    assert resolved.endswith("03_service_memory_leak")
    assert os.path.basename(os.path.dirname(resolved)) == "basic_root_cause_19"


def test_data_dir_is_limited_to_allowed_roots():
    allowed_case_dir = os.path.join(_EVAL_ROOT, "08_redis_node_down")
    assert resolve_data_dir(data_dir=allowed_case_dir).endswith("08_redis_node_down")

    for data_dir in ["C:\\Windows\\System32", "/tmp/foo"]:
        try:
            resolve_data_dir(data_dir=data_dir)
        except ValueError:
            continue
        raise AssertionError(f"unsafe data_dir was accepted: {data_dir}")


def test_data_dir_and_case_id_are_mutually_exclusive():
    try:
        resolve_data_dir(data_dir=os.path.join(_EVAL_ROOT, "01_service_slow_api"), case_id="01_service_slow_api")
    except ValueError:
        return
    raise AssertionError("data_dir and case_id should not be accepted together")


def test_auto_matched_evaluation_case_regression():
    case = _unique_index_case()
    case_dir = resolve_data_dir(case_id=case["case_id"])
    ground_truth = _load_json(os.path.join(case_dir, "ground_truth.json"))
    expected_rc = ground_truth["expected"]["root_cause"]

    case_id, data_dir = resolve_request_context(
        api=case["alert_api"],
        symptom=case["alert_symptom"],
    )
    ctx = _run_evaluation_context(
        api=ground_truth["alert_event"]["api"],
        time=ground_truth["alert_event"]["time"],
        symptom=ground_truth["alert_event"]["symptom"],
        case_id=case_id,
        data_dir=data_dir,
    )

    assert case_id == case["case_id"]
    assert ctx.root_cause_result["root_cause_service"] == expected_rc["service"]
    _assert_root_type_matches(ctx.root_cause_result["root_cause_type"], expected_rc["type"], case_id)
    assert ground_truth["expected"]["affected_services"][0] in ctx.impact_result["affected_services"]


def test_request_context_auto_matches_evaluation_case_without_case_id(monkeypatch):
    monkeypatch.delenv("MMODEL_DATA_DIR", raising=False)
    case = _unique_index_case()

    case_id, data_dir = resolve_request_context(
        api=case["alert_api"],
        symptom=case["alert_symptom"],
    )

    assert case_id == case["case_id"]
    assert data_dir is None


def test_diagnosis_auto_matched_case_without_case_id(monkeypatch):
    monkeypatch.delenv("MMODEL_DATA_DIR", raising=False)
    case = _unique_index_case()

    response = run_diagnosis(
        api=case["alert_api"],
        time="2026-05-18 00:00:00",
        symptom=case["alert_symptom"],
    )

    assert response.case_id == case["case_id"]


def test_unmatched_request_has_no_legacy_default(monkeypatch):
    monkeypatch.delenv("MMODEL_DATA_DIR", raising=False)

    case_id, data_dir = resolve_request_context(
        api="/not/mapped",
        symptom="HTTP 500",
    )

    assert case_id is None
    assert data_dir is None
    try:
        resolve_data_dir(case_id=case_id, data_dir=data_dir)
    except ValueError:
        return
    raise AssertionError("unmatched requests should not fall back to a legacy default demo")


def test_impact_without_business_mapping_does_not_invent_business():
    ctx = DiagnosisContext(api="/not/mapped", time="2026-04-10 10:51:14", symptom="HTTP 500")
    ctx.trace_result = {"call_path": ["api-gateway: GET:/not/mapped", "unknown-service: GET:/not/mapped"]}
    ctx.graph_result = {"edges": [], "summary": ""}
    ctx.root_cause_result = {
        "root_cause_service": "unknown-service",
        "root_cause_api": "/not/mapped",
        "root_cause_type": "service_exception",
    }

    ImpactAnalysisSkill().run(ctx)

    assert ctx.impact_result["affected_services"] == ["api-gateway", "unknown-service"]
    assert ctx.impact_result["affected_business"] == []
    assert ctx.impact_result["affected_businesses"] == []
    assert ctx.impact_result["affected_flows"] == []
    assert ctx.impact_result["affected_pages"] == []
    assert ctx.impact_result["confidence"]["business_semantic"] == "none"
    assert ctx.impact_result["impact_scale"] == "unavailable"
