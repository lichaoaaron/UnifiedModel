from __future__ import annotations

from app.runtime.models import EntityQuery, RuntimeEntity, StoreWriteResult


class InMemoryEntityStore:
    """Storage-neutral in-memory entity store for the P4 runtime boundary."""

    def __init__(self, entities: list[RuntimeEntity] | None = None) -> None:
        self._entities: dict[str, RuntimeEntity] = {}
        if entities:
            self.write_entities(entities)

    def write_entities(self, entities: list[RuntimeEntity]) -> StoreWriteResult:
        ids: list[str] = []
        for entity in entities:
            self._entities[_entity_key(entity)] = _clone_entity(entity)
            ids.append(entity.id)
        return StoreWriteResult(accepted=len(ids), ids=ids)

    def query_entities(self, query: EntityQuery | None = None) -> list[RuntimeEntity]:
        query = query or EntityQuery()
        results = [_clone_entity(entity) for entity in self._entities.values() if _matches_query(entity, query)]
        if query.limit is not None:
            return results[:max(query.limit, 0)]
        return results


def _clone_entity(entity: RuntimeEntity) -> RuntimeEntity:
    if hasattr(entity, "model_copy"):
        return entity.model_copy(deep=True)
    return entity.copy(deep=True)


def _entity_key(entity: RuntimeEntity) -> str:
    return "\x1f".join([entity.domain or "", entity.entity_type, entity.id])


def _matches_query(entity: RuntimeEntity, query: EntityQuery) -> bool:
    if query.domain is not None and entity.domain != query.domain:
        return False
    if query.entity_type and query.entity_type not in _entity_type_candidates(entity):
        return False
    if query.entity_id is not None and entity.id != query.entity_id:
        return False
    if query.name is not None and entity.name != query.name:
        return False
    return True


def _entity_type_candidates(entity: RuntimeEntity) -> set[str]:
    candidates = {entity.entity_type}
    if entity.domain:
        candidates.add(f"{entity.domain}.{entity.entity_type}")
    return candidates