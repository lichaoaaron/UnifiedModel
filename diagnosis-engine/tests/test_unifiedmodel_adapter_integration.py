import os
import sys

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
_SIDECAR_ROOT = os.path.join(_REPO_ROOT, "diagnosis-engine")
if _SIDECAR_ROOT not in sys.path:
    sys.path.insert(0, _SIDECAR_ROOT)

from app.adapters import observability_adapter
from app.adapters.unifiedmodel_adapter import MModelApiAdapter
from app.orchestrator.diagnosis_orchestrator import run_diagnosis


def _unifiedmodel_sample_dir() -> str:
    return os.path.normpath(
        os.path.join(
            _REPO_ROOT,
            "outputs",
            "mmodel-fault-samples",
        )
    )


def test_unifiedmodel_adapter_reads_fault_sample(monkeypatch):
    monkeypatch.setenv("DATA_SOURCE", "unifiedmodel")
    monkeypatch.setenv("UNIFIEDMODEL_SAMPLE_DIR", _unifiedmodel_sample_dir())

    case_id = "fault-redis-saturation-001"
    traces = observability_adapter.get_traces(case_id=case_id)
    logs = observability_adapter.get_logs(case_id=case_id)
    metrics = observability_adapter.get_metrics(case_id=case_id)

    assert traces, "unifiedmodel traces should not be empty"
    assert logs, "unifiedmodel logs should not be empty"
    assert metrics, "unifiedmodel metrics should not be empty"

    assert any(str(item.get("traceId") or "") for item in traces)
    assert all(str(item.get("sample.scenario_id") or "") == case_id for item in logs)
    assert all(str(item.get("sample.scenario_id") or "") == case_id for item in metrics)


def test_unifiedmodel_redis_scenario_runs_diagnosis(monkeypatch):
    monkeypatch.setenv("DATA_SOURCE", "unifiedmodel")
    monkeypatch.setenv("UNIFIEDMODEL_SAMPLE_DIR", _unifiedmodel_sample_dir())

    case_id = "fault-redis-saturation-001"
    response = run_diagnosis(
        api="/ais/configure/sysMetaPropDefs/dbFiledTranslationBasicFiled",
        time="2026-06-03T01:05:45.556Z",
        symptom="Redis saturation and rejected calls",
        case_id=case_id,
    )

    assert response.case_id == case_id
    # Root cause must be promoted to the middleware entity level
    assert response.summary.root_cause_service == "10.252.199.142:6389", (
        f"Expected Redis IP:port as root_cause_service, got: {response.summary.root_cause_service}"
    )
    assert response.summary.root_cause_type == "platform.redis", (
        f"Expected platform.redis, got: {response.summary.root_cause_type}"
    )
    assert any(skill.skill_name == "TraceAnalysisSkill" and skill.status == "success" for skill in response.skills)
    rc_skill = next(sk for sk in response.skills if sk.skill_name == "RootCauseSkill")
    assert rc_skill.status == "success"
    assert rc_skill.output.get("applied_rule") == "unifiedmodel_middleware_override"
    assert rc_skill.output.get("middleware_entity", {}).get("instance") == "10.252.199.142:6389"
    # Graph node for middleware must be marked as root cause
    graph_nodes = (response.call_graph.nodes if response.call_graph else [])
    mw_nodes = [n for n in graph_nodes if n.id == "10.252.199.142:6389"]
    assert mw_nodes, "Graph should contain the Redis middleware node"
    assert mw_nodes[0].is_root_cause, "Redis middleware node should be marked is_root_cause=True"


def test_mmodel_api_evidence_wide_scan_raises_after_first_failure(monkeypatch):
    monkeypatch.setenv("MMODEL_EVIDENCE_MAX_ENTITIES", "1")

    class FailingClient:
        def __init__(self):
            self.calls = 0

        def query_evidence(self, **kwargs):
            self.calls += 1
            raise RuntimeError("504 Gateway Timeout")

    adapter = MModelApiAdapter()
    client = FailingClient()
    adapter._client = client

    try:
        adapter._query_evidence_for_entities(
            ["entity-1", "entity-2", "entity-3"],
            kind="trace_set",
            from_ts=None,
            to_ts=None,
        )
    except RuntimeError as exc:
        assert "failed for all 1 attempted entities" in str(exc)
    else:
        raise AssertionError("expected all-failed evidence scan to raise")

    assert client.calls == 1


def test_mmodel_api_resolves_grpc_api_to_matching_service_entity():
    class EntityClient:
        def query_entities(self, **kwargs):
            rows = [
                {"__entity_id__": "infra-1", "__entity_type__": "otel.infra", "display_name": "otelcol-contrib"},
                {"__entity_id__": "svc-frontend-proxy", "__entity_type__": "otel.service", "display_name": "frontend-proxy"},
            ]
            rows.extend(
                {"__entity_id__": f"svc-noise-{idx}", "__entity_type__": "otel.service", "display_name": f"noise-{idx}"}
                for idx in range(10)
            )
            rows.extend([
                {"__entity_id__": "svc-checkout", "__entity_type__": "otel.service", "display_name": "checkout"},
                {"__entity_id__": "svc-payment", "__entity_type__": "otel.service", "display_name": "payment"},
            ])
            return rows[:kwargs.get("limit", len(rows))]

    adapter = MModelApiAdapter()
    adapter._client = EntityClient()

    from app.models.query_context import QueryContext

    resolved = adapter._resolve_entity_ids(QueryContext(api="/oteldemo.CheckoutService/PlaceOrder"))

    assert resolved[0] == "svc-checkout"
    assert "infra-1" not in resolved


def test_mmodel_api_trace_query_expands_to_downstream_error_service(monkeypatch):
    monkeypatch.setenv("MMODEL_EVIDENCE_MAX_ENTITIES", "1")

    class TraceClient:
        def query_entities(self, **kwargs):
            rows = [
                {"__entity_id__": "svc-checkout", "__entity_type__": "otel.service", "display_name": "checkout"},
                {"__entity_id__": "svc-payment", "__entity_type__": "otel.service", "display_name": "payment"},
            ]
            return rows[:kwargs.get("limit", len(rows))]

        def query_evidence(self, entity_id, kind, **kwargs):
            assert kind == "trace_set"
            if entity_id == "svc-checkout":
                return [{
                    "traceId": "trace-1",
                    "spanId": "checkout-span",
                    "serviceName": "checkout",
                    "name": "oteldemo.CheckoutService/PlaceOrder",
                    "status.code": 2,
                    "status.message": "failed to charge card: Payment request failed. Invalid token.",
                }]
            if entity_id == "svc-payment":
                return [{
                    "traceId": "trace-1",
                    "spanId": "payment-span",
                    "serviceName": "payment",
                    "name": "oteldemo.PaymentService/Charge",
                    "status.code": 2,
                    "status.message": "Payment request failed. Invalid token.",
                }]
            return []

    adapter = MModelApiAdapter()
    adapter._client = TraceClient()

    from app.models.query_context import QueryContext

    result = adapter.query_trace(QueryContext(api="/oteldemo.CheckoutService/PlaceOrder"))
    services = {item.get("serviceName") for item in result["items"]}

    assert services == {"checkout", "payment"}


def test_mmodel_api_trace_id_query_expands_to_same_trace_downstream_service(monkeypatch):
    monkeypatch.setenv("MMODEL_EVIDENCE_MAX_ENTITIES", "1")

    class TraceClient:
        def query_entities(self, **kwargs):
            rows = [
                {"__entity_id__": "svc-checkout", "__entity_type__": "otel.service", "display_name": "checkout"},
                {"__entity_id__": "svc-payment", "__entity_type__": "otel.service", "display_name": "payment"},
            ]
            return rows[:kwargs.get("limit", len(rows))]

        def query_evidence(self, entity_id, kind, **kwargs):
            assert kind == "trace_set"
            if entity_id == "svc-checkout":
                return [{
                    "traceId": "trace-1",
                    "spanId": "checkout-span",
                    "serviceName": "checkout",
                    "name": "oteldemo.CheckoutService/PlaceOrder",
                    "status.code": 2,
                    "status.message": "failed to charge card: Payment request failed. Invalid token.",
                }]
            if entity_id == "svc-payment":
                return [{
                    "traceId": "trace-1",
                    "spanId": "payment-span",
                    "serviceName": "payment",
                    "name": "oteldemo.PaymentService/Charge",
                    "status.code": 2,
                    "status.message": "Payment request failed. Invalid token.",
                }]
            return []

    adapter = MModelApiAdapter()
    adapter._client = TraceClient()

    from app.models.query_context import QueryContext

    result = adapter.query_trace(QueryContext(api="/oteldemo.CheckoutService/PlaceOrder", trace_id="trace-1"))
    services = {item.get("serviceName") for item in result["items"]}

    assert services == {"checkout", "payment"}
