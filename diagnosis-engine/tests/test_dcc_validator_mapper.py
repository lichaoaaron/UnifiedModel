import os
import sys


REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
BACKEND_ROOT = os.path.join(REPO_ROOT, "backend")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)


import pytest

from app.runtime.dcc_mapper import map_unifiedmodel_outputs_to_dcc
from app.runtime.dcc_validator import DCCValidationError, validate_dcc_payload


def _minimal_valid_dcc() -> dict:
    return {
        "protocol_version": "dcc.v0.1",
        "context_id": "dcc-001",
        "generated_at": "2026-01-01T00:00:00Z",
        "workspace": {"workspace_id": "demo"},
        "alert": {"api": "/order/create", "time": "2026-01-01 10:00:00", "symptom": "HTTP 500"},
        "objects": {
            "entities": [],
            "relations": [],
            "topology": {"nodes": [], "edges": []},
        },
        "evidence": {
            "trace": {"availability": "empty", "items": []},
            "log": {"availability": "empty", "items": []},
            "metric": {"availability": "empty", "items": []},
        },
        "candidates": {"root_cause": [], "impact_scope": []},
        "provenance": {"producer": "unit-test"},
        "meta": {"availability": "available", "warnings": []},
    }


def test_validate_dcc_payload_success() -> None:
    payload = _minimal_valid_dcc()
    validated = validate_dcc_payload(payload)
    assert validated["protocol_version"] == "dcc.v0.1"
    assert validated["alert"]["api"] == "/order/create"


def test_validate_dcc_payload_missing_required_field() -> None:
    payload = _minimal_valid_dcc()
    payload.pop("alert")

    with pytest.raises(DCCValidationError) as exc:
        validate_dcc_payload(payload)

    assert "alert is required" in str(exc.value)


def test_map_unifiedmodel_outputs_to_dcc_generates_valid_payload() -> None:
    dcc = map_unifiedmodel_outputs_to_dcc(
        workspace_id="ws-demo",
        alert_api="/pay/submit",
        alert_time="2026-05-30 12:00:00",
        alert_symptom="timeout spike",
        entity_query_result={
            "rows": [
                {
                    "__entity_id__": "svc-payment",
                    "__entity_type__": "devops.service",
                    "__domain__": "devops",
                    "display_name": "payment-service",
                }
            ]
        },
        topo_query_result={
            "rows": [
                {"src": "payment-service", "dst": "order-service", "relation": "calls"}
            ]
        },
        trace_query_result={"rows": [{"traceId": "trace-001", "serviceName": "payment-service"}]},
        log_query_result={"rows": []},
        metric_query_result=None,
    )

    validated = validate_dcc_payload(dcc)
    assert validated["workspace"]["workspace_id"] == "ws-demo"
    assert validated["alert"]["api"] == "/pay/submit"
    assert validated["evidence"]["trace"]["availability"] == "available"
    assert validated["evidence"]["metric"]["availability"] == "unavailable"
    assert validated["objects"]["entities"][0]["entity_name"] == "payment-service"
