from __future__ import annotations

from typing import Any

from app.adapters.ontology_config_adapter import OntologyConfigAdapter
from app.runtime.models import (
    EntityQuery,
    EntityReference,
    EntityTypeDefinition,
    EvidenceLookupResult,
    RelationQuery,
    RelationTypeDefinition,
    RuntimeEntity,
    RuntimeRelation,
    RuntimeValidationIssue,
    RuntimeValidationResult,
    SemanticModelSnapshot,
)


P3_EVIDENCE_WARNING = (
    "P1 semantic runtime does not parse DataLink or StorageLink. "
    "Evidence location will be implemented in P3 Link/Evidence resolution."
)


class SemanticRuntimeService:
    """Detached P1 semantic runtime service.

    The service loads runtime ontology type definitions and exposes stable
    methods for later EntityStore, GraphStore, Query Service, and evidence
    resolution work. It is intentionally not wired into diagnosis flows.
    """

    def __init__(
        self,
        ontology_adapter: OntologyConfigAdapter | None = None,
        snapshot: SemanticModelSnapshot | None = None,
    ) -> None:
        self._ontology_adapter = ontology_adapter or OntologyConfigAdapter()
        self._snapshot = snapshot
        self._entity_type_index: dict[str, EntityTypeDefinition] = {}
        self._relation_type_index: dict[str, RelationTypeDefinition] = {}
        if snapshot is not None:
            self._replace_snapshot(snapshot)

    def load_model(self) -> SemanticModelSnapshot:
        if self._snapshot is None:
            domain_model = self._ontology_adapter.load_domain_model() or {}
            snapshot = SemanticModelSnapshot(
                source="backend/data/mmodel/runtime_domain_model.yaml",
                entity_types=[
                    self._entity_type_from_raw(item)
                    for item in domain_model.get("entity_types", [])
                    if isinstance(item, dict) and item.get("name")
                ],
                relation_types=[
                    self._relation_type_from_raw(item)
                    for item in domain_model.get("relation_types", [])
                    if isinstance(item, dict) and item.get("name")
                ],
            )
            self._replace_snapshot(snapshot)
        return self._snapshot

    def list_entity_types(self) -> list[EntityTypeDefinition]:
        return list(self._entity_types().values())

    def list_relation_types(self) -> list[RelationTypeDefinition]:
        return list(self._relation_types().values())

    def get_entity_type(self, name: str, domain: str | None = None) -> EntityTypeDefinition | None:
        return self._entity_types().get(self._lookup_key("entity_type", name, domain)) or self._entity_types().get(name)

    def get_relation_type(self, name: str, domain: str | None = None) -> RelationTypeDefinition | None:
        return self._relation_types().get(self._lookup_key("relation_type", name, domain)) or self._relation_types().get(name)

    def validate_entity_type(self, name: str, domain: str | None = None) -> RuntimeValidationResult:
        if not name:
            return RuntimeValidationResult(
                valid=False,
                errors=[RuntimeValidationIssue(field="entity_type", reason="entity type is required")],
            )
        if self.get_entity_type(name, domain) is None:
            return RuntimeValidationResult(
                valid=False,
                errors=[RuntimeValidationIssue(field="entity_type", reason=f"unknown entity type: {name}")],
            )
        return RuntimeValidationResult(valid=True)

    def validate_relation_type(self, name: str, domain: str | None = None) -> RuntimeValidationResult:
        if not name:
            return RuntimeValidationResult(
                valid=False,
                errors=[RuntimeValidationIssue(field="relation_type", reason="relation type is required")],
            )
        if self.get_relation_type(name, domain) is None:
            return RuntimeValidationResult(
                valid=False,
                errors=[RuntimeValidationIssue(field="relation_type", reason=f"unknown relation type: {name}")],
            )
        return RuntimeValidationResult(valid=True)

    def query_entities(self, query: EntityQuery | None = None) -> list[RuntimeEntity]:
        return []

    def query_relations(self, query: RelationQuery | None = None) -> list[RuntimeRelation]:
        return []

    def locate_evidence(self, entity_ref: EntityReference) -> EvidenceLookupResult:
        return EvidenceLookupResult(entity_ref=entity_ref, entries=[], warnings=[P3_EVIDENCE_WARNING])

    def _entity_types(self) -> dict[str, EntityTypeDefinition]:
        self.load_model()
        return self._entity_type_index

    def _relation_types(self) -> dict[str, RelationTypeDefinition]:
        self.load_model()
        return self._relation_type_index

    def _replace_snapshot(self, snapshot: SemanticModelSnapshot) -> None:
        self._snapshot = snapshot
        self._entity_type_index = self._index_entity_types(snapshot.entity_types)
        self._relation_type_index = self._index_relation_types(snapshot.relation_types)

    @staticmethod
    def _entity_type_from_raw(item: dict[str, Any]) -> EntityTypeDefinition:
        known_fields = {"name", "domain", "description", "umodel_ref"}
        return EntityTypeDefinition(
            name=str(item.get("name", "")),
            domain=item.get("domain"),
            description=str(item.get("description", "")),
            umodel_ref=str(item.get("umodel_ref", "")),
            attributes={key: value for key, value in item.items() if key not in known_fields},
        )

    @staticmethod
    def _relation_type_from_raw(item: dict[str, Any]) -> RelationTypeDefinition:
        known_fields = {"name", "domain", "description", "direction", "source_type", "target_type", "umodel_ref"}
        return RelationTypeDefinition(
            name=str(item.get("name", "")),
            domain=item.get("domain"),
            description=str(item.get("description", "")),
            direction=str(item.get("direction", "")),
            source_type=item.get("source_type"),
            target_type=item.get("target_type"),
            umodel_ref=str(item.get("umodel_ref", "")),
            attributes={key: value for key, value in item.items() if key not in known_fields},
        )

    @staticmethod
    def _lookup_key(kind: str, name: str, domain: str | None = None) -> str:
        if domain:
            return f"{kind}-{domain}-{name}"
        return name

    @staticmethod
    def _index_entity_types(items: list[EntityTypeDefinition]) -> dict[str, EntityTypeDefinition]:
        index: dict[str, EntityTypeDefinition] = {}
        for item in items:
            index[item.name] = item
            index[item.qualified_name] = item
            index[item.stable_key] = item
        return index

    @staticmethod
    def _index_relation_types(items: list[RelationTypeDefinition]) -> dict[str, RelationTypeDefinition]:
        index: dict[str, RelationTypeDefinition] = {}
        for item in items:
            index[item.name] = item
            index[item.qualified_name] = item
            index[item.stable_key] = item
        return index
