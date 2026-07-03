from __future__ import annotations

from app.runtime.models import EntityReference, RelationQuery, RuntimeRelation, StoreWriteResult


class InMemoryGraphStore:
    """Storage-neutral in-memory one-hop graph store for the P4 runtime boundary."""

    def __init__(self, relations: list[RuntimeRelation] | None = None) -> None:
        self._relations: dict[str, RuntimeRelation] = {}
        if relations:
            self.write_relations(relations)

    def write_relations(self, relations: list[RuntimeRelation]) -> StoreWriteResult:
        ids: list[str] = []
        for relation in relations:
            self._relations[relation.id] = _clone_relation(relation)
            ids.append(relation.id)
        return StoreWriteResult(accepted=len(ids), ids=ids)

    def query_relations(self, query: RelationQuery | None = None) -> list[RuntimeRelation]:
        query = query or RelationQuery()
        results = [
            _clone_relation(relation)
            for relation in self._relations.values()
            if _matches_relation(relation, query)
        ]
        if query.limit is not None:
            return results[:max(query.limit, 0)]
        return results

    def get_upstream(
        self,
        entity: EntityReference,
        relation_type: str | None = None,
    ) -> list[RuntimeRelation]:
        return self.query_relations(RelationQuery(relation_type=relation_type, target_entity=entity))

    def get_downstream(
        self,
        entity: EntityReference,
        relation_type: str | None = None,
    ) -> list[RuntimeRelation]:
        return self.query_relations(RelationQuery(relation_type=relation_type, source_entity=entity))


def _clone_relation(relation: RuntimeRelation) -> RuntimeRelation:
    if hasattr(relation, "model_copy"):
        return relation.model_copy(deep=True)
    return relation.copy(deep=True)


def _matches_relation(relation: RuntimeRelation, query: RelationQuery) -> bool:
    if query.relation_type is not None and relation.relation_type != query.relation_type:
        return False
    if query.source_entity is not None and not _matches_reference(relation.source_entity, query.source_entity):
        return False
    if query.target_entity is not None and not _matches_reference(relation.target_entity, query.target_entity):
        return False
    return True


def _matches_reference(stored: EntityReference, expected: EntityReference) -> bool:
    if stored.domain != expected.domain:
        return False
    if expected.entity_type not in _reference_type_candidates(stored):
        return False
    if expected.entity_id is not None and stored.entity_id != expected.entity_id:
        return False
    if expected.name is not None and stored.name != expected.name:
        return False
    return True


def _reference_type_candidates(entity: EntityReference) -> set[str]:
    candidates = {entity.entity_type, entity.qualified_type}
    return {candidate for candidate in candidates if candidate}