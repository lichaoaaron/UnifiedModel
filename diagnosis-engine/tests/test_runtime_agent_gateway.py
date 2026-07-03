import os
import sys


REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
BACKEND_ROOT = os.path.join(REPO_ROOT, "backend")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)


from app.runtime.agent_gateway import RuntimeAgentGateway
from app.runtime.entity_store import InMemoryEntityStore
from app.runtime.graph_store import InMemoryGraphStore
from app.runtime.models import (
    AgentToolCallRequest,
    EntityReference,
    EvidenceQueryHint,
    LinkEvidenceResult,
    RuntimeEntity,
    RuntimeRelation,
)
from app.runtime.query_service import RuntimeQueryService


class FakeEvidenceResolver:
    def __init__(self) -> None:
        self.calls: list[EntityReference] = []

    def resolve(self, entity: EntityReference) -> LinkEvidenceResult:
        self.calls.append(entity)
        return LinkEvidenceResult(
            entity=entity,
            evidence_types=["metric", "log"],
            query_hints=[
                EvidenceQueryHint(
                    repository="MetricRepository",
                    evidence_type="metric",
                    data_set="alpha.metric.component",
                    storage="alpha.metric_store",
                ),
                EvidenceQueryHint(
                    repository="LogRepository",
                    evidence_type="log",
                    data_set="alpha.log.component",
                    storage="alpha.log_store",
                ),
            ],
        )


class RaisingEvidenceFetchService:
    def __init__(self) -> None:
        self.fetch_called = False

    def resolve_and_fetch_for_entity(self, *args, **kwargs):
        self.fetch_called = True
        raise AssertionError("Agent Gateway must not fetch real evidence rows")


def _gateway() -> tuple[RuntimeAgentGateway, FakeEvidenceResolver, RaisingEvidenceFetchService]:
    source = EntityReference(domain="alpha", entity_type="component", entity_id="source")
    target = EntityReference(domain="alpha", entity_type="component", entity_id="target")
    resolver = FakeEvidenceResolver()
    evidence_fetch_service = RaisingEvidenceFetchService()
    query_service = RuntimeQueryService(
        entity_store=InMemoryEntityStore([
            RuntimeEntity(id="source", domain="alpha", entity_type="component", name="source-service"),
            RuntimeEntity(id="target", domain="alpha", entity_type="component", name="target-service"),
        ]),
        graph_store=InMemoryGraphStore([
            RuntimeRelation(id="relation-1", relation_type="calls", source_entity=source, target_entity=target)
        ]),
        evidence_resolver=resolver,  # type: ignore[arg-type]
        evidence_service=evidence_fetch_service,  # type: ignore[arg-type]
    )
    return RuntimeAgentGateway(query_service=query_service), resolver, evidence_fetch_service


def test_tools_list_contains_four_read_only_tools_with_schemas():
    gateway, _, _ = _gateway()

    tools = gateway.list_tools()

    assert [tool.name for tool in tools] == [
        "mmodel.find_entity",
        "mmodel.get_topology",
        "mmodel.get_evidence_links",
        "mmodel.explain_entity",
    ]
    for tool in tools:
        assert tool.read_only is True
        assert tool.input_schema["type"] == "object"
        assert tool.output_schema["type"] == "object"


def test_get_topology_schema_requires_entity_id_and_entity_type():
    gateway, _, _ = _gateway()

    by_name = {tool.name: tool for tool in gateway.list_tools()}

    assert by_name["mmodel.get_topology"].input_schema["required"] == ["entity_id", "entity_type"]


def test_find_entity_calls_query_service_and_returns_explain():
    gateway, _, _ = _gateway()

    result = gateway.call_tool(
        "mmodel.find_entity",
        AgentToolCallRequest(arguments={"domain": "alpha", "entity_type": "component", "entity_id": "source"}),
    )

    assert result.ok is True
    assert result.output["items"][0]["id"] == "source"
    assert result.output["explain"]["operators"] == ["query_entities"]


def test_get_topology_returns_one_hop_relation_without_reversing_direction():
    gateway, _, _ = _gateway()

    result = gateway.call_tool(
        "mmodel.get_topology",
        AgentToolCallRequest(arguments={
            "domain": "alpha",
            "entity_type": "component",
            "entity_id": "target",
            "direction": "upstream",
        }),
    )

    relation = result.output["items"][0]
    assert result.ok is True
    assert relation["source_entity"]["entity_id"] == "source"
    assert relation["target_entity"]["entity_id"] == "target"
    assert result.output["explain"]["operators"] == ["query_relations", "get_upstream"]


def test_get_topology_missing_entity_type_returns_invalid_argument_error():
    gateway, _, _ = _gateway()

    result = gateway.call_tool(
        "mmodel.get_topology",
        AgentToolCallRequest(arguments={"domain": "alpha", "entity_id": "target", "direction": "upstream"}),
    )

    assert result.ok is False
    assert result.output == {}
    assert result.error == {
        "code": "invalid_argument",
        "message": "entity_type argument is required",
    }


def test_get_evidence_links_returns_query_hints_without_fetching_real_evidence():
    gateway, resolver, evidence_fetch_service = _gateway()

    result = gateway.call_tool(
        "mmodel.get_evidence_links",
        AgentToolCallRequest(arguments={"domain": "alpha", "entity_type": "component", "entity_id": "source"}),
    )

    assert result.ok is True
    assert len(resolver.calls) == 1
    assert result.output["query_hints"][0]["repository"] == "MetricRepository"
    assert result.output["query_hints"][1]["repository"] == "LogRepository"
    assert "results" not in result.output
    assert evidence_fetch_service.fetch_called is False


def test_explain_entity_returns_structured_summary():
    gateway, _, _ = _gateway()

    result = gateway.call_tool(
        "mmodel.explain_entity",
        AgentToolCallRequest(arguments={"domain": "alpha", "entity_type": "component", "entity_id": "source"}),
    )

    assert result.ok is True
    assert result.output["entity"]["entity_id"] == "source"
    assert result.output["summary"] == {
        "matched_entities": 1,
        "evidence_hint_count": 2,
        "relation_count": 1,
        "read_only": True,
    }
    assert result.output["evidence"]["query_hints"][0]["evidence_type"] == "metric"
    assert result.output["topology"]["explain"]["operators"] == ["query_relations", "get_downstream", "get_upstream"]
    assert result.output["explain"]["evidence_query"]["operators"] == ["resolve_evidence"]


def test_unknown_tool_returns_structured_error_without_exception():
    gateway, _, _ = _gateway()

    result = gateway.call_tool("mmodel.unknown", AgentToolCallRequest(arguments={}))

    assert result.ok is False
    assert result.output == {}
    assert result.error == {
        "code": "tool_not_found",
        "message": "Unknown runtime agent tool: mmodel.unknown",
    }


def test_all_tools_are_declared_read_only():
    gateway, _, _ = _gateway()

    assert all(tool.read_only for tool in gateway.discover().tools)
