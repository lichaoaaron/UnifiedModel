from __future__ import annotations

from typing import Protocol

from app.runtime.models import (
    EntityQuery,
    EntityReference,
    EntityTypeDefinition,
    EvidenceLookupResult,
    RelationQuery,
    RelationTypeDefinition,
    RuntimeEntity,
    RuntimeRelation,
    RuntimeValidationResult,
    SemanticModelSnapshot,
    StoreWriteResult,
)


class SemanticModelLoader(Protocol):
    """Loads the semantic model snapshot used by the runtime."""

    def load_model(self) -> SemanticModelSnapshot:
        """Return the current semantic model snapshot."""


class SemanticModelRegistry(Protocol):
    """Resolves semantic type definitions from the loaded model."""

    def list_entity_types(self) -> list[EntityTypeDefinition]:
        """Return all known entity type definitions."""

    def list_relation_types(self) -> list[RelationTypeDefinition]:
        """Return all known relation type definitions."""

    def get_entity_type(self, name: str, domain: str | None = None) -> EntityTypeDefinition | None:
        """Return one entity type definition by name, if present."""

    def get_relation_type(self, name: str, domain: str | None = None) -> RelationTypeDefinition | None:
        """Return one relation type definition by name, if present."""


class RuntimeEntityStore(Protocol):
    """Storage-neutral entity query boundary."""

    def write_entities(self, entities: list[RuntimeEntity]) -> StoreWriteResult:
        """Write runtime entities into the store."""

    def query_entities(self, query: EntityQuery | None = None) -> list[RuntimeEntity]:
        """Return runtime entities matching the query."""


class RuntimeRelationStore(Protocol):
    """Storage-neutral relation query boundary."""

    def write_relations(self, relations: list[RuntimeRelation]) -> StoreWriteResult:
        """Write runtime relations into the store."""

    def query_relations(self, query: RelationQuery | None = None) -> list[RuntimeRelation]:
        """Return runtime relations matching the query."""

    def get_upstream(
        self,
        entity: EntityReference,
        relation_type: str | None = None,
    ) -> list[RuntimeRelation]:
        """Return one-hop incoming relations where the entity is the target."""

    def get_downstream(
        self,
        entity: EntityReference,
        relation_type: str | None = None,
    ) -> list[RuntimeRelation]:
        """Return one-hop outgoing relations where the entity is the source."""


class EvidenceLocator(Protocol):
    """Locates evidence entries for a runtime entity reference."""

    def locate_evidence(self, entity_ref: EntityReference) -> EvidenceLookupResult:
        """Return evidence entries and non-fatal warnings for the entity."""


class SemanticRuntime(
    SemanticModelLoader,
    SemanticModelRegistry,
    RuntimeEntityStore,
    RuntimeRelationStore,
    EvidenceLocator,
    Protocol,
):
    """Aggregated P1 semantic runtime service boundary."""

    def validate_entity_type(self, name: str, domain: str | None = None) -> RuntimeValidationResult:
        """Validate whether the entity type exists in the loaded model."""

    def validate_relation_type(self, name: str, domain: str | None = None) -> RuntimeValidationResult:
        """Validate whether the relation type exists in the loaded model."""
