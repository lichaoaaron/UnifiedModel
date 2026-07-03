from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


def qualified_name(domain: str | None, name: str) -> str:
    if domain:
        return f"{domain}.{name}"
    return name


def stable_identity_key(kind: str, domain: str | None, name: str) -> str:
    if domain:
        return f"{kind}-{domain}-{name}"
    return f"{kind}-{name}"


class RuntimeValidationIssue(BaseModel):
    field: str
    reason: str


class RuntimeValidationResult(BaseModel):
    valid: bool
    errors: list[RuntimeValidationIssue] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class EntityTypeDefinition(BaseModel):
    name: str
    domain: str | None = None
    description: str = ""
    umodel_ref: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)

    @property
    def qualified_name(self) -> str:
        return qualified_name(self.domain, self.name)

    @property
    def stable_key(self) -> str:
        return stable_identity_key("entity_type", self.domain, self.name)


class RelationTypeDefinition(BaseModel):
    name: str
    domain: str | None = None
    description: str = ""
    direction: str = ""
    source_type: str | None = None
    target_type: str | None = None
    umodel_ref: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)

    @property
    def qualified_name(self) -> str:
        return qualified_name(self.domain, self.name)

    @property
    def stable_key(self) -> str:
        return stable_identity_key("relation_type", self.domain, self.name)


class DataSetDefinition(BaseModel):
    name: str
    domain: str | None = None
    kind: str = "data_set"
    data_type: Literal["trace", "log", "metric", "event", "unknown"] = "unknown"
    description: str = ""
    umodel_ref: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)

    @property
    def qualified_name(self) -> str:
        return qualified_name(self.domain, self.name)

    @property
    def stable_key(self) -> str:
        return stable_identity_key(self.kind, self.domain, self.name)


class EvidenceLinkDefinition(BaseModel):
    name: str
    domain: str | None = None
    kind: str = "evidence_link"
    source_ref: str = ""
    target_ref: str = ""
    description: str = ""
    query_hint: dict[str, Any] = Field(default_factory=dict)
    attributes: dict[str, Any] = Field(default_factory=dict)

    @property
    def qualified_name(self) -> str:
        return qualified_name(self.domain, self.name)

    @property
    def stable_key(self) -> str:
        return stable_identity_key(self.kind, self.domain, self.name)


class SemanticModelSnapshot(BaseModel):
    source: str
    version: str = "p1"
    entity_types: list[EntityTypeDefinition] = Field(default_factory=list)
    relation_types: list[RelationTypeDefinition] = Field(default_factory=list)
    data_sets: list[DataSetDefinition] = Field(default_factory=list)
    evidence_links: list[EvidenceLinkDefinition] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class EntityReference(BaseModel):
    entity_type: str
    domain: str | None = None
    entity_id: str | None = None
    name: str | None = None

    @property
    def qualified_type(self) -> str:
        return qualified_name(self.domain, self.entity_type)

    @property
    def stable_key(self) -> str:
        identity = self.entity_id or self.name or ""
        if identity:
            return f"entity-{self.qualified_type}-{identity}"
        return stable_identity_key("entity", self.domain, self.entity_type)


class RuntimeEntity(BaseModel):
    id: str
    entity_type: str
    domain: str | None = None
    name: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)
    source: str = "runtime"
    confidence: float | None = None
    raw_refs: list[dict[str, Any]] = Field(default_factory=list)


class RuntimeRelation(BaseModel):
    id: str
    relation_type: str
    source_entity: EntityReference
    target_entity: EntityReference
    attributes: dict[str, Any] = Field(default_factory=dict)
    source: str = "runtime"
    confidence: float | None = None
    raw_refs: list[dict[str, Any]] = Field(default_factory=list)


class StoreWriteResult(BaseModel):
    accepted: int = 0
    ids: list[str] = Field(default_factory=list)


class EntityQuery(BaseModel):
    entity_type: str | None = None
    domain: str | None = None
    entity_id: str | None = None
    name: str | None = None
    limit: int | None = None


class RelationQuery(BaseModel):
    relation_type: str | None = None
    source_entity: EntityReference | None = None
    target_entity: EntityReference | None = None
    limit: int | None = None


class EvidenceEntry(BaseModel):
    entity_ref: EntityReference
    evidence_type: Literal["trace", "log", "metric", "event", "business", "unknown"] = "unknown"
    data_set: str = ""
    storage: str = ""
    query_hint: dict[str, Any] = Field(default_factory=dict)
    source: str = "semantic_runtime"


class EvidenceLookupResult(BaseModel):
    entity_ref: EntityReference
    entries: list[EvidenceEntry] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class EvidenceQueryHint(BaseModel):
    repository: Literal["MetricRepository", "LogRepository", "TraceRepository"]
    evidence_type: Literal["metric", "log", "trace"]
    data_set: str
    storage: str = ""
    storage_ref: dict[str, Any] = Field(default_factory=dict)
    field_mapping: dict[str, Any] = Field(default_factory=dict)
    data_filter: str = ""
    filter_by_entity: str = ""
    source: str = "umodel_yaml"
    data_link: str = ""
    storage_link: str = ""


class LinkEvidenceResult(BaseModel):
    entity: EntityReference
    evidence_types: list[Literal["metric", "log", "trace"]] = Field(default_factory=list)
    query_hints: list[EvidenceQueryHint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RuntimeQueryExplain(BaseModel):
    source: str
    provider: str = "none"
    operators: list[str] = Field(default_factory=list)
    fallback: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RuntimeQueryResult(BaseModel):
    items: list[Any] = Field(default_factory=list)
    explain: RuntimeQueryExplain


class RuntimeEvidenceQueryResult(BaseModel):
    entity: EntityReference
    evidence_types: list[Literal["metric", "log", "trace"]] = Field(default_factory=list)
    query_hints: list[EvidenceQueryHint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    explain: RuntimeQueryExplain


class RuntimeEvidenceFetchResult(BaseModel):
    evidence_type: Literal["metric", "log", "trace", "unknown"] = "unknown"
    repository: str
    availability: str = "available"
    items: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    semantic_context: dict[str, Any] = Field(default_factory=dict)
    raw_refs: list[dict[str, str]] = Field(default_factory=list)


class RuntimeEvidenceFetchResponse(BaseModel):
    entity: EntityReference
    results: list[RuntimeEvidenceFetchResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RuntimeSearchQuery(BaseModel):
    text: str | None = None
    service_name: str | None = None
    instance: str | None = None
    trace_id: str | None = None
    error_code: str | None = None
    alert_text: str | None = None
    limit: int | None = 10


class RuntimeSearchCandidate(BaseModel):
    entity: RuntimeEntity
    match_reason: str
    confidence: float
    matched_fields: list[str] = Field(default_factory=list)
    source: str = "runtime_search"


class RuntimeSearchResult(BaseModel):
    candidates: list[RuntimeSearchCandidate] = Field(default_factory=list)
    explain: RuntimeQueryExplain
    warnings: list[str] = Field(default_factory=list)


class AgentToolDefinition(BaseModel):
    name: str
    description: str
    read_only: bool = True
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)


class AgentGatewayDiscovery(BaseModel):
    tools: list[AgentToolDefinition] = Field(default_factory=list)
    read_only: bool = True


class AgentToolCallRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


class AgentToolCallResult(BaseModel):
    name: str
    ok: bool
    output: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None
