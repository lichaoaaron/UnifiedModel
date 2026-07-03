import os
import sys


REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
BACKEND_ROOT = os.path.join(REPO_ROOT, "backend")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)


from app.runtime.models import (
    DataSetDefinition,
    EntityQuery,
    EntityReference,
    EntityTypeDefinition,
    EvidenceLinkDefinition,
    RelationQuery,
    RelationTypeDefinition,
    SemanticModelSnapshot,
)
from app.runtime.service import P3_EVIDENCE_WARNING, SemanticRuntimeService


def test_semantic_runtime_loads_default_ontology_types():
    service = SemanticRuntimeService()

    snapshot = service.load_model()

    entity_type_names = {item.name for item in snapshot.entity_types}
    relation_type_names = {item.name for item in snapshot.relation_types}

    assert {"Service", "Instance", "Interface"}.issubset(entity_type_names)
    assert {"calls", "runs_on", "exposes"}.issubset(relation_type_names)
    assert snapshot.data_sets == []
    assert snapshot.evidence_links == []


def test_semantic_runtime_supports_domain_qualified_and_stable_keys():
    snapshot = SemanticModelSnapshot(
        source="unit-test",
        entity_types=[EntityTypeDefinition(name="service", domain="apm")],
        relation_types=[RelationTypeDefinition(name="calls", domain="apm")],
    )
    service = SemanticRuntimeService(snapshot=snapshot)

    entity_type = service.get_entity_type("service", domain="apm")
    relation_type = service.get_relation_type("calls", domain="apm")

    assert entity_type is not None
    assert entity_type.qualified_name == "apm.service"
    assert entity_type.stable_key == "entity_type-apm-service"
    assert service.get_entity_type("apm.service") == entity_type
    assert service.validate_entity_type("entity_type-apm-service").valid is True

    assert relation_type is not None
    assert relation_type.qualified_name == "apm.calls"
    assert relation_type.stable_key == "relation_type-apm-calls"
    assert service.get_relation_type("apm.calls") == relation_type
    assert service.validate_relation_type("relation_type-apm-calls").valid is True


def test_entity_reference_has_domain_qualified_stable_key():
    entity_ref = EntityReference(entity_type="service", domain="apm", entity_id="entity-1")

    assert entity_ref.qualified_type == "apm.service"
    assert entity_ref.stable_key == "entity-apm.service-entity-1"


def test_semantic_snapshot_uses_typed_dataset_and_evidence_link_models():
    snapshot = SemanticModelSnapshot(source="unit-test")

    assert snapshot.data_sets == []
    assert snapshot.evidence_links == []

    typed_snapshot = SemanticModelSnapshot(
        source="unit-test",
        data_sets=[DataSetDefinition(name="trace.common", domain="apm", kind="trace_set", data_type="trace")],
        evidence_links=[EvidenceLinkDefinition(name="service_trace", domain="apm", kind="data_link")],
    )

    assert typed_snapshot.data_sets[0].stable_key == "trace_set-apm-trace.common"
    assert typed_snapshot.evidence_links[0].stable_key == "data_link-apm-service_trace"


def test_validate_entity_type_only_checks_type_existence():
    service = SemanticRuntimeService()

    assert service.validate_entity_type("Service").valid is True

    result = service.validate_entity_type("UnknownEntityType")
    assert result.valid is False
    assert result.errors[0].field == "entity_type"
    assert "unknown entity type" in result.errors[0].reason


def test_validate_relation_type_only_checks_type_existence():
    service = SemanticRuntimeService()

    assert service.validate_relation_type("calls").valid is True

    assert service.validate_relation_type("exposes").valid is True

    assert service.validate_relation_type("unknown_relation").valid is False


def test_p1_entity_and_relation_queries_return_empty_lists():
    service = SemanticRuntimeService()

    assert service.query_entities(EntityQuery(entity_type="Service")) == []
    assert service.query_relations(RelationQuery(relation_type="calls")) == []


def test_p1_locate_evidence_returns_empty_entries_with_warning():
    service = SemanticRuntimeService()

    entity_ref = EntityReference(entity_type="Service", name="entity-under-analysis")

    result = service.locate_evidence(entity_ref)

    assert result.entries == []
    assert result.warnings == [P3_EVIDENCE_WARNING]
    assert "P3 Link/Evidence resolution" in result.warnings[0]
