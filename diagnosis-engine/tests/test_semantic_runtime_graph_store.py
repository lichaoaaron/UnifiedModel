import os
import sys


REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
BACKEND_ROOT = os.path.join(REPO_ROOT, "backend")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)


from app.runtime.entity_store import InMemoryEntityStore
from app.runtime.graph_store import InMemoryGraphStore
from app.runtime.models import EntityQuery, EntityReference, RuntimeEntity, RuntimeRelation


def _component_ref(entity_id: str, name: str = "") -> EntityReference:
    return EntityReference(domain="alpha", entity_type="component", entity_id=entity_id, name=name or entity_id)


def _domain_component_ref(domain: str, entity_id: str) -> EntityReference:
    return EntityReference(domain=domain, entity_type="component", entity_id=entity_id)


def test_entity_store_writes_multiple_entities_and_queries_by_type():
    store = InMemoryEntityStore()

    result = store.write_entities([
        RuntimeEntity(
            id="component-1",
            domain="alpha",
            entity_type="component",
            name="entity-one",
            source="unit-test-source",
            confidence=0.91,
            raw_refs=[{"system": "inventory", "id": "raw-component-1"}],
        ),
        RuntimeEntity(id="component-2", domain="beta", entity_type="component", name="entity-two"),
        RuntimeEntity(id="node-1", domain="alpha", entity_type="node", name="entity-three"),
    ])

    entities = store.query_entities(EntityQuery(entity_type="component"))

    assert result.accepted == 3
    assert result.ids == ["component-1", "component-2", "node-1"]
    assert {entity.id for entity in entities} == {"component-1", "component-2"}
    assert entities[0].source == "unit-test-source"
    assert entities[0].confidence == 0.91
    assert entities[0].raw_refs == [{"system": "inventory", "id": "raw-component-1"}]


def test_entity_store_queries_by_domain_entity_type_and_entity_id():
    store = InMemoryEntityStore([
        RuntimeEntity(id="component-1", domain="alpha", entity_type="component", name="entity-one"),
        RuntimeEntity(id="component-1", domain="beta", entity_type="component", name="entity-two"),
    ])

    entities = store.query_entities(EntityQuery(domain="alpha", entity_type="component", entity_id="component-1"))

    assert [entity.name for entity in entities] == ["entity-one"]


def test_graph_store_writes_relation_and_queries_downstream():
    source = _component_ref("component-source", "source-entity")
    target = _component_ref("component-target", "target-entity")
    store = InMemoryGraphStore()

    result = store.write_relations([
        RuntimeRelation(
            id="relation-1",
            relation_type="invokes",
            source_entity=source,
            target_entity=target,
            source="unit-test-topology",
            confidence=0.82,
            raw_refs=[{"system": "topology", "id": "raw-relation-1"}],
        )
    ])

    relations = store.get_downstream(source, relation_type="invokes")

    assert result.accepted == 1
    assert result.ids == ["relation-1"]
    assert len(relations) == 1
    assert relations[0].source_entity.entity_id == "component-source"
    assert relations[0].target_entity.entity_id == "component-target"
    assert relations[0].source == "unit-test-topology"
    assert relations[0].confidence == 0.82
    assert relations[0].raw_refs == [{"system": "topology", "id": "raw-relation-1"}]


def test_graph_store_queries_upstream():
    source = _component_ref("component-source")
    target = _component_ref("component-target")
    store = InMemoryGraphStore([
        RuntimeRelation(id="relation-1", relation_type="depends_on", source_entity=source, target_entity=target)
    ])

    relations = store.get_upstream(target, relation_type="depends_on")
    assert len(relations) == 1
    assert relations[0].source_entity.entity_id == "component-source"
    assert relations[0].target_entity.entity_id == "component-target"


def test_graph_store_preserves_source_to_target_direction_without_reversing():
    source = _component_ref("component-source")
    target = _component_ref("component-target")
    store = InMemoryGraphStore([
        RuntimeRelation(id="relation-1", relation_type="calls", source_entity=source, target_entity=target)
    ])

    assert [relation.target_entity.entity_id for relation in store.get_downstream(source)] == ["component-target"]
    assert store.get_downstream(target) == []
    assert [relation.source_entity.entity_id for relation in store.get_upstream(target)] == ["component-source"]
    assert store.get_upstream(source) == []


def test_graph_store_requires_domain_match_for_domain_scoped_references():
    alpha_source = _domain_component_ref("alpha", "1")
    alpha_target = _domain_component_ref("alpha", "target")
    beta_source = _domain_component_ref("beta", "1")
    beta_target = _domain_component_ref("beta", "target")
    store = InMemoryGraphStore([
        RuntimeRelation(id="alpha-relation", relation_type="calls", source_entity=alpha_source, target_entity=alpha_target),
        RuntimeRelation(id="beta-relation", relation_type="calls", source_entity=beta_source, target_entity=beta_target),
    ])

    unscoped_source = EntityReference(entity_type="component", entity_id="1")
    scoped_source = EntityReference(domain="alpha", entity_type="component", entity_id="1")

    assert store.get_downstream(unscoped_source) == []
    assert [relation.id for relation in store.get_downstream(scoped_source)] == ["alpha-relation"]


def test_entity_and_graph_store_return_empty_lists_for_missing_data():
    entity_store = InMemoryEntityStore()
    graph_store = InMemoryGraphStore()
    missing_entity = EntityReference(domain="alpha", entity_type="component", entity_id="missing")

    assert entity_store.query_entities(EntityQuery(domain="alpha", entity_type="component")) == []
    assert graph_store.get_downstream(missing_entity) == []
    assert graph_store.get_upstream(missing_entity) == []