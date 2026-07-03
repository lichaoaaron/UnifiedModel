"""
Production-like showcase coverage for examples/evaluation_cases/showcase_7.

ground_truth.json is read here for assertions only. Runtime diagnosis receives
only trace/log/metric through MMODEL_DATA_DIR so no showcase answer is encoded
in diagnosis logic.
"""
import json
import os
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = _REPO_ROOT / "backend"
for _path in (str(_REPO_ROOT), str(_BACKEND)):
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
from app.orchestrator.diagnosis_orchestrator import _build_call_graph, run_diagnosis
from app.adapters.local_json_adapter import resolve_data_dir

_SHOWCASE_ROOT = _REPO_ROOT / "examples" / "evaluation_cases" / "showcase_7"
_PIPELINE = [
    AlertContextSkill(),
    TraceAnalysisSkill(),
    EntityBindingSkill(),
    LogAnalysisSkill(),
    MetricCheckSkill(),
    GraphAnalysisSkill(),
    RootCauseSkill(),
    ImpactAnalysisSkill(),
]

_TYPE_ALIASES = {
    "service_exception": {"service_exception"},
    "high_cpu": {"resource_exhaustion/high_cpu", "high_cpu"},
    "memory_leak": {"resource_exhaustion/memory_leak", "memory_leak"},
    "redis_node_down": {"dependency_unavailable/redis_node_down", "redis_node_down"},
    "connection_pool_exhaustion": {"resource_exhaustion/connection_pool_exhaustion", "connection_pool_exhaustion"},
    "mysql_max_connections": {"database_resource/mysql_max_connections", "mysql_max_connections"},
    "redis_slow_lua": {"dependency_performance/redis_slow_lua", "redis_slow_lua"},
}

_REQUIRED_TRACE_FIELDS = {
    "traceId",
    "spanId",
    "parentSpanId",
    "serviceName",
    "name",
    "startTime",
    "endTime",
    "status.code",
    "span.attributes.http@status_code",
    "span.attributes.url",
    "resource.attributes.service@name",
    "resource.attributes.service@instance@id",
    "events",
}
_REQUIRED_LOG_FIELDS = {
    "time",
    "serviceName",
    "resource.attributes.service@name",
    "log.attributes.log@level",
    "log.attributes.message",
    "log.attributes.stack_trace",
}
_REQUIRED_METRIC_FIELDS = {
    "name",
    "value",
    "unit",
    "time",
    "resource.attributes.compose_service",
    "resource.attributes.container@name",
    "resource.attributes.container@id",
}
_REQUIRED_GT_FIELDS = {"case_id", "name", "category", "alert_event", "expected"}
_REQUIRED_EXPECTED_FIELDS = {
    "root_cause",
    "affected_services",
    "affected_interfaces",
    "business_impact",
    "primary_evidence",
    "non_root_noise",
}
_REQUIRED_ROOT_FIELDS = {"service", "component", "type", "exception_type"}
_REQUIRED_INDEX_FIELDS = {
    "case_id",
    "name",
    "category",
    "alert_api",
    "alert_symptom",
    "root_cause_service",
    "root_cause_component",
    "root_cause_type",
    "topology_shape",
    "evidence_mode",
}


def _load_json(path: Path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _run_case(case_dir: Path, ground_truth: dict, monkeypatch) -> DiagnosisContext:
    event = ground_truth["alert_event"]
    monkeypatch.setenv("MMODEL_DATA_DIR", str(case_dir))
    ctx = DiagnosisContext(api=event["api"], time=event["time"], symptom=event["symptom"])
    for skill in _PIPELINE:
        skill.run(ctx)
    return ctx


def _assert_root_type_matches(actual: str, expected: str, case_id: str) -> None:
    allowed = _TYPE_ALIASES.get(expected, {expected})
    assert actual in allowed, f"{case_id}: expected {expected} compatible type, got {actual}"


def _assert_component_compatible(actual: str, expected: str, service: str, case_id: str) -> None:
    compatible = {expected, service}
    if expected.startswith("container-"):
        compatible.add(expected.removeprefix("container-").split("-", 1)[-1])
    assert actual in compatible, f"{case_id}: expected component compatible with {expected}, got {actual}"


def test_showcase_7_json_contracts():
    index = _load_json(_SHOWCASE_ROOT / "index.json")
    assert len(index) == 7

    for case in index:
        assert _REQUIRED_INDEX_FIELDS <= set(case), case
        case_dir = _SHOWCASE_ROOT / case["case_id"]
        trace = _load_json(case_dir / "trace.json")
        logs = _load_json(case_dir / "log.json")
        metrics = _load_json(case_dir / "metric.json")
        ground_truth = _load_json(case_dir / "ground_truth.json")

        assert _REQUIRED_GT_FIELDS <= set(ground_truth), case["case_id"]
        assert _REQUIRED_EXPECTED_FIELDS <= set(ground_truth["expected"]), case["case_id"]
        assert _REQUIRED_ROOT_FIELDS <= set(ground_truth["expected"]["root_cause"]), case["case_id"]
        assert ground_truth["case_id"] == case["case_id"]
        assert case["root_cause_service"] == ground_truth["expected"]["root_cause"]["service"]
        assert case["root_cause_component"] == ground_truth["expected"]["root_cause"]["component"]
        assert case["root_cause_type"] == ground_truth["expected"]["root_cause"]["type"]

        assert trace and logs and metrics
        for span in trace:
            src = span.get("_source", span)
            assert _REQUIRED_TRACE_FIELDS <= set(src), case["case_id"]
        for log in logs:
            assert _REQUIRED_LOG_FIELDS <= set(log), case["case_id"]
        for metric in metrics:
            assert _REQUIRED_METRIC_FIELDS <= set(metric), case["case_id"]


def test_showcase_7_diagnosis_cases(monkeypatch):
    index = _load_json(_SHOWCASE_ROOT / "index.json")
    graph_shapes = {}

    for case in index:
        case_id = case["case_id"]
        case_dir = _SHOWCASE_ROOT / case_id
        ground_truth = _load_json(case_dir / "ground_truth.json")
        expected = ground_truth["expected"]
        expected_rc = expected["root_cause"]

        ctx = _run_case(case_dir, ground_truth, monkeypatch)
        root_output = ctx.root_cause_result
        impact = ctx.impact_result
        graph = ctx.graph_result

        assert root_output["root_cause_service"] == expected_rc["service"], case_id
        _assert_root_type_matches(root_output["root_cause_type"], expected_rc["type"], case_id)
        _assert_component_compatible(
            root_output["root_cause_component"],
            expected_rc["component"],
            expected_rc["service"],
            case_id,
        )

        key_affected_service = expected["affected_services"][0]
        assert key_affected_service in impact["affected_services"], case_id
        populated_sources = [
            source for source, evidence in root_output["evidence_by_source"].items()
            if evidence
        ]
        min_sources = 1 if case_id == "06_partial_trace_db" else 2
        assert len(populated_sources) >= min_sources, case_id
        assert _dominant_source(case["evidence_mode"]) in populated_sources, case_id

        assert len(graph["nodes"]) >= 6, case_id
        assert len(graph["edges"]) >= 5, case_id
        call_graph = _build_call_graph(ctx)
        call_node_types = {node.id: node.node_type for node in call_graph.nodes}
        assert not any(
            edge.label == "downstream call"
            and call_node_types.get(edge.source) == "Interface"
            and call_node_types.get(edge.target) == "Interface"
            for edge in call_graph.edges
        ), case_id
        root_api = root_output.get("root_cause_api")
        if root_api:
            assert any(
                edge["source"] == root_output["root_cause_service"]
                and edge["target"] == root_api
                and edge.get("label") == "exposes"
                for edge in graph["edges"]
            ), f"{case_id}: root cause api {root_api} must be exposed by root service {root_output['root_cause_service']}"
        interface_ids = {node["id"] for node in graph["nodes"] if node.get("node_type") == "Interface"}
        for interface_id in interface_ids:
            exposing_services = {
                edge["source"]
                for edge in graph["edges"]
                if edge.get("label") == "exposes" and edge.get("target") == interface_id
            }
            assert len(exposing_services) <= 1, (
                f"{case_id}: interface {interface_id} is shared by {sorted(exposing_services)}"
            )

        for node in graph["nodes"]:
            if node.get("node_type") == "Instance":
                assert not re.fullmatch(r"\d+\.\d+\.\d+\.\d+", node["id"]), (
                    f"{case_id}: instance node should include service/container context, got bare IP {node['id']}"
                )

        graph_shapes[case_id] = (
            tuple(sorted(node["id"] for node in graph["nodes"])),
            tuple(sorted((edge["source"], edge["target"], edge["label"]) for edge in graph["edges"])),
        )

        if case_id in {"04_dependency_redis", "06_partial_trace_db", "07_noise_resilience"}:
            node_ids = {node["id"] for node in graph["nodes"]}
            assert expected_rc["component"] in node_ids, case_id

        if case_id == "07_noise_resilience":
            assert root_output["root_cause_service"] != "unrelated-service"
            graph_node_ids = {node["id"] for node in graph["nodes"]}
            assert "unrelated-service" not in graph_node_ids
            assert "health-service" not in graph_node_ids
            metric_candidates = ctx.metric_result["metric_root_candidates"]
            assert all(candidate["service"] != "unrelated-service" for candidate in metric_candidates)
            assert ctx.metric_result["excluded_metric_signals"], case_id

    assert len(set(graph_shapes.values())) == len(graph_shapes)


def _dominant_source(evidence_mode: str) -> str:
    if evidence_mode.startswith("trace"):
        return "trace"
    if evidence_mode.startswith("metric"):
        return "metric"
    if evidence_mode.startswith("log"):
        return "log"
    if evidence_mode.startswith("partial"):
        return "metric"
    if "dependency" in evidence_mode or "noise" in evidence_mode or "conflict" in evidence_mode:
        return "metric"
    return "trace"


def test_showcase_7_data_dir_entry_and_call_graph(monkeypatch):
    index = _load_json(_SHOWCASE_ROOT / "index.json")
    case = next(item for item in index if item["case_id"] == "04_dependency_redis")
    case_dir = _SHOWCASE_ROOT / case["case_id"]
    ground_truth = _load_json(case_dir / "ground_truth.json")
    event = ground_truth["alert_event"]

    resolved = resolve_data_dir(data_dir=str(case_dir))
    assert resolved.endswith(case["case_id"])

    monkeypatch.delenv("MMODEL_DATA_DIR", raising=False)
    response = run_diagnosis(
        api=event["api"],
        time=event["time"],
        symptom=event["symptom"],
        data_dir=str(case_dir),
    )

    expected = ground_truth["expected"]["root_cause"]
    assert response.summary.root_cause_service == expected["service"]
    assert response.summary.root_cause_type in _TYPE_ALIASES[expected["type"]]
    node_by_id = {node.id: node for node in response.call_graph.nodes}
    assert expected["component"] in node_by_id
    assert node_by_id[expected["component"]].node_type == "Dependency"
    assert any(edge.label == "depends_on" for edge in response.call_graph.edges)


def test_showcase_7_case_id_entry(monkeypatch):
    case_id = "01_trace_dominant_exception"
    case_dir = _SHOWCASE_ROOT / case_id
    ground_truth = _load_json(case_dir / "ground_truth.json")
    event = ground_truth["alert_event"]

    resolved = resolve_data_dir(case_id=case_id)
    assert Path(resolved) == case_dir

    monkeypatch.delenv("MMODEL_DATA_DIR", raising=False)
    response = run_diagnosis(
        api=event["api"],
        time=event["time"],
        symptom=event["symptom"],
        case_id=case_id,
    )

    expected = ground_truth["expected"]["root_cause"]
    assert response.summary.root_cause_service == expected["service"]
    assert response.summary.root_cause_type in _TYPE_ALIASES[expected["type"]]
