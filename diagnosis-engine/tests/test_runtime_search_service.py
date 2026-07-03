import os
import sys


REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
BACKEND_ROOT = os.path.join(REPO_ROOT, "backend")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)


from app.runtime.entity_store import InMemoryEntityStore
from app.runtime.models import RuntimeEntity, RuntimeSearchQuery
from app.runtime.search_service import RuntimeSearchService


def _service() -> RuntimeSearchService:
    return RuntimeSearchService(entity_store=InMemoryEntityStore([
        RuntimeEntity(
            id="svc-payment-main",
            domain="alpha",
            entity_type="component",
            name="payment-service",
            attributes={
                "instance": "payment-instance-01",
                "trace_id": "trace-attr-payment",
                "error_code": "ERR_PAYMENT_TIMEOUT",
                "keywords": ["checkout", "payment", "timeout"],
                "description": "Payment checkout timeout detector",
            },
            raw_refs=[{"kind": "trace", "traceId": "trace-raw-payment"}],
        ),
        RuntimeEntity(
            id="svc-payment-worker",
            domain="alpha",
            entity_type="component",
            name="payment-worker",
            attributes={
                "instance": "payment-worker-01",
                "keywords": ["payment", "queue"],
            },
        ),
        RuntimeEntity(
            id="svc-inventory-main",
            domain="alpha",
            entity_type="component",
            name="inventory-service",
            attributes={
                "instance": "inventory-instance-01",
                "error_code": "ERR_INVENTORY_STALE",
                "keywords": ["stock", "inventory"],
            },
        ),
        RuntimeEntity(
            id="svc-search-main",
            domain="alpha",
            entity_type="component",
            name="search-service",
            attributes={
                "instance": "search-instance-01",
                "keywords": ["search", "latency"],
            },
            raw_refs=[{"kind": "trace", "id": "trace-search-raw"}],
        ),
    ]))


def test_service_name_fragment_returns_candidate_entity():
    result = _service().search(RuntimeSearchQuery(service_name="payment"))

    assert result.candidates
    assert result.candidates[0].entity.id == "svc-payment-main"
    assert "name" in result.candidates[0].matched_fields


def test_instance_name_returns_candidate_entity():
    result = _service().search(instance="inventory-instance-01")

    assert [candidate.entity.id for candidate in result.candidates] == ["svc-inventory-main"]
    assert "instance" in result.candidates[0].match_reason
    assert "attributes.instance" in result.candidates[0].matched_fields


def test_trace_id_can_locate_entity_from_attributes_and_raw_refs():
    service = _service()

    by_attribute = service.search(trace_id="trace-attr-payment")
    by_raw_ref = service.search(trace_id="trace-raw-payment")
    by_safe_raw_ref_id = service.search(trace_id="trace-search-raw")

    assert by_attribute.candidates[0].entity.id == "svc-payment-main"
    assert "attributes.trace_id" in by_attribute.candidates[0].matched_fields
    assert by_raw_ref.candidates[0].entity.id == "svc-payment-main"
    assert "raw_refs[0].traceId" in by_raw_ref.candidates[0].matched_fields
    assert by_safe_raw_ref_id.candidates[0].entity.id == "svc-search-main"
    assert "raw_refs[0].id" in by_safe_raw_ref_id.candidates[0].matched_fields


def test_error_code_returns_candidate_entity():
    result = _service().search(error_code="ERR_PAYMENT_TIMEOUT")

    assert [candidate.entity.id for candidate in result.candidates] == ["svc-payment-main"]
    assert "error_code" in result.candidates[0].match_reason
    assert "attributes.error_code" in result.candidates[0].matched_fields


def test_alert_text_keywords_return_related_candidate_entities():
    result = _service().search(alert_text="checkout payment timeout spike")

    assert result.candidates[0].entity.id == "svc-payment-main"
    assert result.candidates[0].confidence > 0
    assert any("keywords" in field or "description" in field for field in result.candidates[0].matched_fields)


def test_alert_text_does_not_match_runtime_source_metadata_only():
    result = _service().search(alert_text="runtime timeout")

    assert [candidate.entity.id for candidate in result.candidates] == ["svc-payment-main"]
    assert all("source" not in candidate.matched_fields for candidate in result.candidates)


def test_multiple_candidates_are_sorted_by_confidence_descending():
    result = _service().search(service_name="payment-service", alert_text="payment checkout timeout")

    confidences = [candidate.confidence for candidate in result.candidates]
    assert len(confidences) >= 2
    assert confidences == sorted(confidences, reverse=True)
    assert result.candidates[0].entity.id == "svc-payment-main"


def test_not_found_returns_empty_candidates_without_fabricating_entity():
    result = _service().search(service_name="not-a-known-runtime-entity")

    assert result.candidates == []
    assert result.warnings == ["No runtime entities matched the search clues."]
    assert result.explain.warnings == ["No runtime entities matched the search clues."]


def test_each_candidate_has_match_reason_and_confidence():
    result = _service().search(service_name="payment")

    for candidate in result.candidates:
        assert candidate.match_reason
        assert candidate.confidence > 0
        assert candidate.matched_fields
        assert candidate.source == "runtime_search:entity_store"
