from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.runtime.models import (
    AgentGatewayDiscovery,
    AgentToolCallRequest,
    AgentToolCallResult,
    AgentToolDefinition,
    EntityQuery,
    EntityReference,
)
from app.runtime.query_service import RuntimeQueryService


_TOOL_ORDER = [
    "mmodel.find_entity",
    "mmodel.get_topology",
    "mmodel.get_evidence_links",
    "mmodel.explain_entity",
]


class RuntimeAgentGateway:
    """Read-only Agent tool gateway for runtime query capabilities.

    P7 exposes tool discovery and explicit tool calls over RuntimeQueryService.
    It does not implement an MCP stdio server, write stores, call diagnosis
    Skills, fetch observability rows, or generate OpenSearch DSL.
    """

    def __init__(self, query_service: RuntimeQueryService | None = None) -> None:
        self._query_service = query_service or RuntimeQueryService()
        self._tools = {tool.name: tool for tool in _tool_definitions()}

    def discover(self) -> AgentGatewayDiscovery:
        return AgentGatewayDiscovery(tools=self.list_tools(), read_only=True)

    def list_tools(self) -> list[AgentToolDefinition]:
        return [self._tools[name] for name in _TOOL_ORDER]

    def call_tool(
        self,
        tool_name: str,
        request: AgentToolCallRequest | None = None,
    ) -> AgentToolCallResult:
        request = request or AgentToolCallRequest()
        if tool_name not in self._tools:
            return _error_result(tool_name, "tool_not_found", f"Unknown runtime agent tool: {tool_name}")

        try:
            output = self._call_known_tool(tool_name, request.arguments or {})
        except _ArgumentError as exc:
            return _error_result(tool_name, "invalid_argument", str(exc))
        except Exception as exc:
            return _error_result(tool_name, "tool_error", f"Runtime agent tool failed: {type(exc).__name__}")

        return AgentToolCallResult(name=tool_name, ok=True, output=output)

    def _call_known_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "mmodel.find_entity":
            return self._find_entity(arguments)
        if tool_name == "mmodel.get_topology":
            return self._get_topology(arguments)
        if tool_name == "mmodel.get_evidence_links":
            return self._get_evidence_links(arguments)
        if tool_name == "mmodel.explain_entity":
            return self._explain_entity(arguments)
        raise _ArgumentError(f"Unsupported runtime agent tool: {tool_name}")

    def _find_entity(self, arguments: dict[str, Any]) -> dict[str, Any]:
        result = self._query_service.query_entities(EntityQuery(
            entity_type=_optional_text(arguments, "entity_type"),
            domain=_optional_text(arguments, "domain"),
            entity_id=_optional_text(arguments, "entity_id"),
            name=_optional_text(arguments, "name"),
            limit=_optional_limit(arguments),
        ))
        return {
            "items": _to_plain(result.items),
            "explain": _to_plain(result.explain),
        }

    def _get_topology(self, arguments: dict[str, Any]) -> dict[str, Any]:
        result = self._query_service.query_relations_by_entity_id(
            entity_id=_required_text(arguments, "entity_id"),
            entity_type=_required_text(arguments, "entity_type"),
            domain=_optional_text(arguments, "domain"),
            relation_type=_optional_text(arguments, "relation_type"),
            direction=_direction(arguments),
            limit=_optional_limit(arguments),
        )
        return {
            "items": _to_plain(result.items),
            "explain": _to_plain(result.explain),
        }

    def _get_evidence_links(self, arguments: dict[str, Any]) -> dict[str, Any]:
        result = self._query_service.query_evidence_by_entity_id(
            entity_id=_required_text(arguments, "entity_id"),
            entity_type=_required_text(arguments, "entity_type"),
            domain=_optional_text(arguments, "domain"),
            name=_optional_text(arguments, "name"),
        )
        return {
            "entity": _to_plain(result.entity),
            "evidence_types": _to_plain(result.evidence_types),
            "query_hints": _to_plain(result.query_hints),
            "warnings": _to_plain(result.warnings),
            "explain": _to_plain(result.explain),
        }

    def _explain_entity(self, arguments: dict[str, Any]) -> dict[str, Any]:
        entity_id = _required_text(arguments, "entity_id")
        entity_type = _required_text(arguments, "entity_type")
        domain = _optional_text(arguments, "domain")
        name = _optional_text(arguments, "name")
        entity = EntityReference(domain=domain, entity_type=entity_type, entity_id=entity_id, name=name)

        entity_result = self._query_service.query_entities(EntityQuery(
            entity_type=entity_type,
            domain=domain,
            entity_id=entity_id,
            name=name,
            limit=1,
        ))
        evidence_result = self._query_service.query_evidence_by_entity_id(
            entity_id=entity_id,
            entity_type=entity_type,
            domain=domain,
            name=name,
        )
        topology_result = self._query_service.query_relations_by_entity_id(
            entity_id=entity_id,
            entity_type=entity_type,
            domain=domain,
            relation_type=_optional_text(arguments, "relation_type"),
            direction=_direction(arguments, default="both"),
            limit=_optional_limit(arguments),
        )

        return {
            "entity": _to_plain(entity),
            "entity_matches": _to_plain(entity_result.items),
            "evidence": {
                "evidence_types": _to_plain(evidence_result.evidence_types),
                "query_hints": _to_plain(evidence_result.query_hints),
                "warnings": _to_plain(evidence_result.warnings),
                "explain": _to_plain(evidence_result.explain),
            },
            "topology": {
                "items": _to_plain(topology_result.items),
                "explain": _to_plain(topology_result.explain),
            },
            "summary": {
                "matched_entities": len(entity_result.items),
                "evidence_hint_count": len(evidence_result.query_hints),
                "relation_count": len(topology_result.items),
                "read_only": True,
            },
            "explain": {
                "entity_query": _to_plain(entity_result.explain),
                "evidence_query": _to_plain(evidence_result.explain),
                "topology_query": _to_plain(topology_result.explain),
            },
        }


class _ArgumentError(ValueError):
    pass


def _tool_definitions() -> list[AgentToolDefinition]:
    return [
        AgentToolDefinition(
            name="mmodel.find_entity",
            description="Find runtime entities through the MModel Runtime Query Service.",
            read_only=True,
            input_schema={
                "type": "object",
                "properties": {
                    "entity_type": {"type": "string"},
                    "domain": {"type": "string"},
                    "entity_id": {"type": "string"},
                    "name": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 0},
                },
                "additionalProperties": False,
            },
            output_schema=_items_explain_output_schema(),
        ),
        AgentToolDefinition(
            name="mmodel.get_topology",
            description="Read one-hop runtime topology relations for an entity.",
            read_only=True,
            input_schema={
                "type": "object",
                "required": ["entity_id", "entity_type"],
                "properties": {
                    "entity_id": {"type": "string"},
                    "entity_type": {"type": "string"},
                    "domain": {"type": "string"},
                    "relation_type": {"type": "string"},
                    "direction": {"type": "string", "enum": ["downstream", "upstream", "both"]},
                    "limit": {"type": "integer", "minimum": 0},
                },
                "additionalProperties": False,
            },
            output_schema=_items_explain_output_schema(),
        ),
        AgentToolDefinition(
            name="mmodel.get_evidence_links",
            description="Resolve semantic evidence query hints without fetching observability rows.",
            read_only=True,
            input_schema={
                "type": "object",
                "required": ["entity_id", "entity_type"],
                "properties": {
                    "entity_id": {"type": "string"},
                    "entity_type": {"type": "string"},
                    "domain": {"type": "string"},
                    "name": {"type": "string"},
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["entity", "query_hints", "explain"],
                "properties": {
                    "entity": {"type": "object", "additionalProperties": True},
                    "evidence_types": {"type": "array", "items": {"type": "string"}},
                    "query_hints": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                    "warnings": {"type": "array", "items": {"type": "string"}},
                    "explain": {"type": "object", "additionalProperties": True},
                },
            },
        ),
        AgentToolDefinition(
            name="mmodel.explain_entity",
            description="Summarize entity matches, evidence hints, and one-hop topology explain metadata.",
            read_only=True,
            input_schema={
                "type": "object",
                "required": ["entity_id", "entity_type"],
                "properties": {
                    "entity_id": {"type": "string"},
                    "entity_type": {"type": "string"},
                    "domain": {"type": "string"},
                    "name": {"type": "string"},
                    "relation_type": {"type": "string"},
                    "direction": {"type": "string", "enum": ["downstream", "upstream", "both"]},
                    "limit": {"type": "integer", "minimum": 0},
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["entity", "evidence", "topology", "summary", "explain"],
                "properties": {
                    "entity": {"type": "object", "additionalProperties": True},
                    "entity_matches": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                    "evidence": {"type": "object", "additionalProperties": True},
                    "topology": {"type": "object", "additionalProperties": True},
                    "summary": {"type": "object", "additionalProperties": True},
                    "explain": {"type": "object", "additionalProperties": True},
                },
            },
        ),
    ]


def _items_explain_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["items", "explain"],
        "properties": {
            "items": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
            "explain": {"type": "object", "additionalProperties": True},
        },
    }


def _required_text(arguments: dict[str, Any], key: str) -> str:
    value = _optional_text(arguments, key)
    if value is None:
        raise _ArgumentError(f"{key} argument is required")
    return value


def _optional_text(arguments: dict[str, Any], key: str) -> str | None:
    value = arguments.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_limit(arguments: dict[str, Any]) -> int | None:
    value = arguments.get("limit")
    if value is None:
        return None
    try:
        limit = int(value)
    except (TypeError, ValueError) as exc:
        raise _ArgumentError("limit argument must be an integer") from exc
    if limit < 0:
        raise _ArgumentError("limit argument must be greater than or equal to 0")
    return limit


def _direction(arguments: dict[str, Any], default: str = "downstream") -> str:
    value = _optional_text(arguments, "direction") or default
    if value not in {"downstream", "upstream", "both"}:
        raise _ArgumentError("direction argument must be downstream, upstream, or both")
    return value


def _error_result(tool_name: str, code: str, message: str) -> AgentToolCallResult:
    return AgentToolCallResult(name=tool_name, ok=False, output={}, error={"code": code, "message": message})


def _to_plain(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, list):
        return [_to_plain(item) for item in value]
    if isinstance(value, tuple):
        return [_to_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_plain(item) for key, item in value.items()}
    return value
