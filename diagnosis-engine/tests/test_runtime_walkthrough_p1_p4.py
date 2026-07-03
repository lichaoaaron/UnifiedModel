import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from app.adapters.umodel_yaml_adapter import UModelYamlAdapter
from app.runtime.entity_store import InMemoryEntityStore
from app.runtime.graph_store import InMemoryGraphStore
from app.runtime.link_resolver import LinkEvidenceResolver
from app.runtime.models import EntityQuery, EntityReference, RuntimeEntity, RuntimeRelation


WALKTHROUGH_DIR = REPO_ROOT / "examples" / "ontology" / "runtime_validation" / "p1_p4_walkthrough"


def test_p1_p4_runtime_walkthrough_uses_realistic_yaml_fixture():
    assert WALKTHROUGH_DIR.is_dir(), f"walkthrough fixture missing: {WALKTHROUGH_DIR}"

    adapter = UModelYamlAdapter(data_dir=str(WALKTHROUGH_DIR))
    resolver = LinkEvidenceResolver(adapter)
    checkout = EntityReference(domain="itops", entity_type="service", entity_id="checkout-service")

    evidence = resolver.resolve(checkout)

    assert evidence.entity == checkout
    assert evidence.evidence_types == ["metric", "log", "trace"]
    assert evidence.warnings == []
    assert {hint.repository for hint in evidence.query_hints} == {
        "MetricRepository",
        "LogRepository",
        "TraceRepository",
    }
    assert {hint.data_set for hint in evidence.query_hints} == {
        "itops.metric.service_red",
        "itops.log.service_runtime",
        "itops.trace.service_call",
    }
    assert all("dsl" not in hint.model_dump() for hint in evidence.query_hints)
    assert all("query" not in hint.model_dump() for hint in evidence.query_hints)
    assert all(hint.field_mapping["data_link"]["service_id"] == "service.name" for hint in evidence.query_hints)
    assert all(hint.data_filter for hint in evidence.query_hints)
    assert all(hint.filter_by_entity == "service.name = ${service_id} and environment = 'prod'" for hint in evidence.query_hints)
    assert all(hint.storage for hint in evidence.query_hints)

    entity_store = InMemoryEntityStore()
    entity_store.write_entities([
        RuntimeEntity(
            id="checkout-service",
            domain="itops",
            entity_type="service",
            name="Checkout Service",
            source="runtime_validation_fixture",
            confidence=0.98,
            raw_refs=[{"kind": "cmdb", "ref": "cmdb:service:checkout-service"}],
        ),
        RuntimeEntity(
            id="payment-service",
            domain="itops",
            entity_type="service",
            name="Payment Service",
            source="runtime_validation_fixture",
            confidence=0.96,
            raw_refs=[{"kind": "cmdb", "ref": "cmdb:service:payment-service"}],
        ),
    ])

    services = entity_store.query_entities(EntityQuery(domain="itops", entity_type="service"))
    assert [service.id for service in services] == ["checkout-service", "payment-service"]

    graph_store = InMemoryGraphStore()
    graph_store.write_relations([
        RuntimeRelation(
            id="checkout-calls-payment",
            relation_type="calls",
            source_entity=checkout,
            target_entity=EntityReference(domain="itops", entity_type="service", entity_id="payment-service"),
            source="runtime_validation_fixture",
            confidence=0.93,
            raw_refs=[{"kind": "trace", "ref": "trace:checkout-calls-payment"}],
        )
    ])

    downstream = graph_store.get_downstream(checkout, relation_type="calls")
    upstream = graph_store.get_upstream(
        EntityReference(domain="itops", entity_type="service", entity_id="payment-service"),
        relation_type="calls",
    )

    assert [relation.target_entity.entity_id for relation in downstream] == ["payment-service"]
    assert [relation.source_entity.entity_id for relation in upstream] == ["checkout-service"]
    assert graph_store.get_downstream(EntityReference(entity_type="service", entity_id="checkout-service")) == []
