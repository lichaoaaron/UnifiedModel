import os
import sys


REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
BACKEND_ROOT = os.path.join(REPO_ROOT, "backend")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)


from app.runtime.entity_store import InMemoryEntityStore
from app.runtime.graph_store import InMemoryGraphStore
from app.runtime.models import (
    EntityQuery,
    EntityReference,
    EvidenceQueryHint,
    LinkEvidenceResult,
    RuntimeEntity,
    RuntimeRelation,
)
from app.runtime.query_service import RuntimeQueryService


class FakeEvidenceResolver:
    def __init__(self) -> None:
        self.calls: list[EntityReference] = []

    def resolve(self, entity: EntityReference) -> LinkEvidenceResult:
        self.calls.append(entity)
        return LinkEvidenceResult(
            entity=entity,
            evidence_types=["log"],
            query_hints=[
                EvidenceQueryHint(
                    repository="LogRepository",
                    evidence_type="log",
                    data_set="alpha.log.component",
                    storage="alpha.log_store",
                    source="umodel_yaml",
                )
            ],
        )


def _component_ref(entity_id: str) -> EntityReference:
    return EntityReference(domain="alpha", entity_type="component", entity_id=entity_id)


def test_query_service_queries_entities_with_explain():
    service = RuntimeQueryService(
        entity_store=InMemoryEntityStore([
            RuntimeEntity(id="1", domain="alpha", entity_type="component", name="component-one"),
            RuntimeEntity(id="2", domain="alpha", entity_type="node", name="node-one"),
        ])
    )

    result = service.query_entities(EntityQuery(domain="alpha", entity_type="component"))

    assert [item.id for item in result.items] == ["1"]
    assert result.explain.source == "graph_store"
    assert result.explain.provider == "in_memory"
    assert result.explain.operators == ["query_entities"]


def test_query_service_relation_queries_keep_one_hop_direction():
    source = _component_ref("source")
    target = _component_ref("target")
    service = RuntimeQueryService(
        graph_store=InMemoryGraphStore([
            RuntimeRelation(id="relation-1", relation_type="calls", source_entity=source, target_entity=target)
        ])
    )

    downstream = service.query_relations_by_entity_id(
        entity_id="source",
        domain="alpha",
        entity_type="component",
        direction="downstream",
    )
    upstream = service.query_relations_by_entity_id(
        entity_id="target",
        domain="alpha",
        entity_type="component",
        direction="upstream",
    )

    assert [item.target_entity.entity_id for item in downstream.items] == ["target"]
    assert downstream.explain.operators == ["query_relations", "get_downstream"]
    assert [item.source_entity.entity_id for item in upstream.items] == ["source"]
    assert upstream.explain.operators == ["query_relations", "get_upstream"]


def test_query_service_evidence_uses_link_resolver_with_explain():
    resolver = FakeEvidenceResolver()
    service = RuntimeQueryService(evidence_resolver=resolver)  # type: ignore[arg-type]

    result = service.query_evidence_by_entity_id(entity_id="1", domain="alpha", entity_type="component")

    assert len(resolver.calls) == 1
    assert resolver.calls[0] == EntityReference(domain="alpha", entity_type="component", entity_id="1")
    assert result.evidence_types == ["log"]
    assert result.query_hints[0].repository == "LogRepository"
    assert result.explain.source == "umodel_yaml"
    assert result.explain.provider == "umodel_yaml"
    assert result.explain.operators == ["resolve_evidence"]


def test_query_service_empty_store_returns_empty_items_with_explain():
    service = RuntimeQueryService()

    entities = service.query_entities(EntityQuery(domain="alpha", entity_type="component"))
    relations = service.query_relations_by_entity_id(entity_id="missing", domain="alpha", entity_type="component")

    assert entities.items == []
    assert entities.explain.provider == "in_memory"
    assert entities.explain.warnings == ["No runtime entities matched the query."]
    assert relations.items == []
    assert relations.explain.provider == "in_memory"
    assert relations.explain.warnings == ["No one-hop runtime relations matched the query."]


def test_query_service_does_not_require_opensearch_or_repository_for_runtime_queries():
    service = RuntimeQueryService(entity_store=InMemoryEntityStore(), graph_store=InMemoryGraphStore())

    assert service.query_entities().explain.provider == "in_memory"
    assert service.query_relations_by_entity_id(entity_id="1", entity_type="component").explain.source == "graph_store"
