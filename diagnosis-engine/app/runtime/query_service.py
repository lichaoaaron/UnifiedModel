from __future__ import annotations

from typing import Literal

from app.runtime.entity_store import InMemoryEntityStore
from app.runtime.evidence_service import RuntimeEvidenceService
from app.runtime.graph_store import InMemoryGraphStore
from app.runtime.link_resolver import LinkEvidenceResolver
from app.runtime.models import (
    EntityQuery,
    EntityReference,
    RuntimeEvidenceFetchResponse,
    RuntimeEvidenceQueryResult,
    RuntimeQueryExplain,
    RuntimeQueryResult,
)


RelationDirection = Literal["downstream", "upstream", "both"]


class RuntimeQueryService:
    """Minimal explicit query service for P5 runtime access.

    The service coordinates storage-neutral runtime stores and Link/Evidence
    resolution. It does not parse UModel DSL, query OpenSearch, or call
    diagnosis Skills.
    """

    def __init__(
        self,
        entity_store: InMemoryEntityStore | None = None,
        graph_store: InMemoryGraphStore | None = None,
        evidence_resolver: LinkEvidenceResolver | None = None,
        evidence_service: RuntimeEvidenceService | None = None,
    ) -> None:
        self._entity_store = entity_store or InMemoryEntityStore()
        self._graph_store = graph_store or InMemoryGraphStore()
        self._evidence_resolver = evidence_resolver or LinkEvidenceResolver()
        self._evidence_service = evidence_service or RuntimeEvidenceService(link_resolver=self._evidence_resolver)

    def query_entities(self, query: EntityQuery | None = None) -> RuntimeQueryResult:
        items = self._entity_store.query_entities(query or EntityQuery())
        return RuntimeQueryResult(
            items=items,
            explain=self._explain(
                source="graph_store",
                provider="in_memory",
                operators=["query_entities"],
                warnings=[] if items else ["No runtime entities matched the query."],
            ),
        )

    def query_relations_by_entity_id(
        self,
        *,
        entity_id: str,
        entity_type: str = "",
        domain: str | None = None,
        relation_type: str | None = None,
        direction: RelationDirection = "downstream",
        limit: int | None = None,
    ) -> RuntimeQueryResult:
        entity = EntityReference(domain=domain, entity_type=entity_type, entity_id=entity_id)
        operators = ["query_relations"]
        if direction == "upstream":
            items = self._graph_store.get_upstream(entity, relation_type=relation_type)
            operators.append("get_upstream")
        elif direction == "both":
            items = [
                *self._graph_store.get_downstream(entity, relation_type=relation_type),
                *self._graph_store.get_upstream(entity, relation_type=relation_type),
            ]
            operators.extend(["get_downstream", "get_upstream"])
        else:
            items = self._graph_store.get_downstream(entity, relation_type=relation_type)
            operators.append("get_downstream")

        if limit is not None:
            items = items[:max(limit, 0)]

        return RuntimeQueryResult(
            items=items,
            explain=self._explain(
                source="graph_store",
                provider="in_memory",
                operators=operators,
                warnings=[] if items else ["No one-hop runtime relations matched the query."],
            ),
        )

    def query_evidence_by_entity_id(
        self,
        *,
        entity_id: str,
        entity_type: str,
        domain: str | None = None,
        name: str | None = None,
    ) -> RuntimeEvidenceQueryResult:
        entity = EntityReference(domain=domain, entity_type=entity_type, entity_id=entity_id, name=name)
        resolved = self._evidence_resolver.resolve(entity)
        return RuntimeEvidenceQueryResult(
            entity=resolved.entity,
            evidence_types=resolved.evidence_types,
            query_hints=resolved.query_hints,
            warnings=resolved.warnings,
            explain=self._explain(
                source="umodel_yaml",
                provider="umodel_yaml",
                operators=["resolve_evidence"],
                warnings=resolved.warnings,
            ),
        )

    def fetch_evidence_by_entity_id(
        self,
        *,
        entity_id: str,
        entity_type: str,
        domain: str | None = None,
        name: str | None = None,
        time_range: dict | None = None,
        query_context: dict | None = None,
    ) -> RuntimeEvidenceFetchResponse:
        entity = EntityReference(domain=domain, entity_type=entity_type, entity_id=entity_id, name=name)
        return self._evidence_service.resolve_and_fetch_for_entity(
            entity,
            time_range=time_range,
            query_context=query_context,
        )

    def explain(self, query_type: str = "entities") -> RuntimeQueryExplain:
        if query_type == "relations":
            return self._explain("graph_store", "in_memory", ["query_relations"])
        if query_type == "evidence":
            return self._explain("umodel_yaml", "umodel_yaml", ["resolve_evidence"])
        return self._explain("graph_store", "in_memory", ["query_entities"])

    @staticmethod
    def _explain(
        source: str,
        provider: str,
        operators: list[str],
        warnings: list[str] | None = None,
    ) -> RuntimeQueryExplain:
        return RuntimeQueryExplain(
            source=source,
            provider=provider,
            operators=operators,
            fallback=[],
            warnings=warnings or [],
        )