from __future__ import annotations

from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, Query

from app.runtime.agent_gateway import RuntimeAgentGateway
from app.runtime.models import (
    AgentGatewayDiscovery,
    AgentToolCallRequest,
    AgentToolCallResult,
    EntityQuery,
    RuntimeEvidenceQueryResult,
    RuntimeQueryExplain,
    RuntimeQueryResult,
)
from app.runtime.query_service import RuntimeQueryService


router = APIRouter(prefix="/runtime")

RelationDirectionParam = Literal["downstream", "upstream", "both"]


@lru_cache(maxsize=1)
def get_runtime_query_service() -> RuntimeQueryService:
    return RuntimeQueryService()


def get_runtime_agent_gateway() -> RuntimeAgentGateway:
    return RuntimeAgentGateway(query_service=get_runtime_query_service())


@router.get("/entities", response_model=RuntimeQueryResult)
def query_entities(
    entity_type: str | None = None,
    domain: str | None = None,
    entity_id: str | None = None,
    name: str | None = None,
    limit: int | None = Query(default=None, ge=0),
) -> RuntimeQueryResult:
    service = get_runtime_query_service()
    return service.query_entities(EntityQuery(
        entity_type=entity_type,
        domain=domain,
        entity_id=entity_id,
        name=name,
        limit=limit,
    ))


@router.get("/entities/{entity_id}/relations", response_model=RuntimeQueryResult)
def query_entity_relations(
    entity_id: str,
    entity_type: str = "",
    domain: str | None = None,
    relation_type: str | None = None,
    direction: RelationDirectionParam = "downstream",
    limit: int | None = Query(default=None, ge=0),
) -> RuntimeQueryResult:
    service = get_runtime_query_service()
    return service.query_relations_by_entity_id(
        entity_id=entity_id,
        entity_type=entity_type,
        domain=domain,
        relation_type=relation_type,
        direction=direction,
        limit=limit,
    )


@router.get("/entities/{entity_id}/evidence", response_model=RuntimeEvidenceQueryResult)
def query_entity_evidence(
    entity_id: str,
    entity_type: str,
    domain: str | None = None,
    name: str | None = None,
) -> RuntimeEvidenceQueryResult:
    service = get_runtime_query_service()
    return service.query_evidence_by_entity_id(
        entity_id=entity_id,
        entity_type=entity_type,
        domain=domain,
        name=name,
    )


@router.get("/query/explain")
def explain_query(query_type: str = "entities") -> dict[str, RuntimeQueryExplain]:
    service = get_runtime_query_service()
    return {"explain": service.explain(query_type=query_type)}


@router.get("/agent/tools", response_model=AgentGatewayDiscovery)
def list_agent_tools() -> AgentGatewayDiscovery:
    gateway = get_runtime_agent_gateway()
    return gateway.discover()


@router.post("/agent/tools/{tool_name}/call", response_model=AgentToolCallResult)
def call_agent_tool(tool_name: str, request: AgentToolCallRequest | None = None) -> AgentToolCallResult:
    gateway = get_runtime_agent_gateway()
    return gateway.call_tool(tool_name, request or AgentToolCallRequest())