"""Semantic runtime package for MModel.

P1-P9 keep this package as a detached semantic runtime boundary. It currently
contains the semantic model loading skeleton, Link/Evidence resolver, minimal
in-memory EntityStore/GraphStore abstractions, explicit Query Service, and
repository-backed evidence fetching, read-only Agent Gateway tool entry points,
lightweight runtime entity search, and a structured Runbook protocol without
wiring runtime internals into the existing diagnosis flow.
"""

from app.runtime.agent_gateway import RuntimeAgentGateway
from app.runtime.entity_store import InMemoryEntityStore
from app.runtime.evidence_service import RuntimeEvidenceService
from app.runtime.graph_store import InMemoryGraphStore
from app.runtime.models import (
    AgentGatewayDiscovery,
    AgentToolCallRequest,
    AgentToolCallResult,
    AgentToolDefinition,
    EntityQuery,
    EntityReference,
    EntityTypeDefinition,
    EvidenceEntry,
    EvidenceLookupResult,
    EvidenceQueryHint,
    RuntimeEvidenceQueryResult,
    RuntimeEvidenceFetchResponse,
    RuntimeEvidenceFetchResult,
    RuntimeQueryExplain,
    RuntimeQueryResult,
    RuntimeSearchCandidate,
    RuntimeSearchQuery,
    RuntimeSearchResult,
    RelationQuery,
    RelationTypeDefinition,
    LinkEvidenceResult,
    RuntimeEntity,
    RuntimeRelation,
    RuntimeValidationResult,
    SemanticModelSnapshot,
    StoreWriteResult,
)
from app.runtime.link_resolver import LinkEvidenceResolver, SemanticLinkResolver
from app.runtime.query_service import RuntimeQueryService
from app.runtime.runbook import (
    RunbookDefinition,
    RunbookEvidenceRef,
    RunbookSkillBinding,
    RunbookStep,
    attach_runbook_metadata,
    default_service_exception_runbook,
    runbook_skill_sequence,
)
from app.runtime.search_service import RuntimeSearchService
from app.runtime.service import SemanticRuntimeService

__all__ = [
    "AgentGatewayDiscovery",
    "AgentToolCallRequest",
    "AgentToolCallResult",
    "AgentToolDefinition",
    "EntityQuery",
    "EntityReference",
    "EntityTypeDefinition",
    "EvidenceEntry",
    "EvidenceLookupResult",
    "EvidenceQueryHint",
    "InMemoryEntityStore",
    "InMemoryGraphStore",
    "LinkEvidenceResolver",
    "LinkEvidenceResult",
    "RelationQuery",
    "RelationTypeDefinition",
    "RuntimeEvidenceQueryResult",
    "RuntimeEvidenceFetchResponse",
    "RuntimeEvidenceFetchResult",
    "RuntimeEvidenceService",
    "RuntimeEntity",
    "RuntimeAgentGateway",
    "RuntimeQueryExplain",
    "RuntimeQueryResult",
    "RuntimeSearchCandidate",
    "RuntimeSearchQuery",
    "RuntimeSearchResult",
    "RuntimeSearchService",
    "RunbookDefinition",
    "RunbookEvidenceRef",
    "RunbookSkillBinding",
    "RunbookStep",
    "RuntimeRelation",
    "RuntimeValidationResult",
    "RuntimeQueryService",
    "SemanticModelSnapshot",
    "SemanticLinkResolver",
    "SemanticRuntimeService",
    "StoreWriteResult",
    "attach_runbook_metadata",
    "default_service_exception_runbook",
    "runbook_skill_sequence",
]
