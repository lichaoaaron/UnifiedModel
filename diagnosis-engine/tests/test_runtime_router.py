import os
import sys


REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
BACKEND_ROOT = os.path.join(REPO_ROOT, "backend")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)


from fastapi.testclient import TestClient

from app.main import app
from app.runtime.entity_store import InMemoryEntityStore
from app.runtime.graph_store import InMemoryGraphStore
from app.runtime.models import EntityReference, LinkEvidenceResult, RuntimeEntity, RuntimeRelation
from app.runtime.query_service import RuntimeQueryService


class EmptyEvidenceResolver:
    def resolve(self, entity: EntityReference) -> LinkEvidenceResult:
        return LinkEvidenceResult(entity=entity, warnings=["No test evidence."])


def _test_query_service() -> RuntimeQueryService:
    source = EntityReference(domain="alpha", entity_type="component", entity_id="1")
    target = EntityReference(domain="alpha", entity_type="component", entity_id="2")
    return RuntimeQueryService(
        entity_store=InMemoryEntityStore([
            RuntimeEntity(id="1", domain="alpha", entity_type="component", name="component-one")
        ]),
        graph_store=InMemoryGraphStore([
            RuntimeRelation(id="relation-1", relation_type="calls", source_entity=source, target_entity=target)
        ]),
        evidence_resolver=EmptyEvidenceResolver(),  # type: ignore[arg-type]
    )


def test_runtime_router_entities_returns_items_and_explain(monkeypatch):
    from app.routers import runtime as runtime_router

    monkeypatch.setattr(runtime_router, "get_runtime_query_service", _test_query_service)
    client = TestClient(app)

    response = client.get("/api/runtime/entities", params={"domain": "alpha", "entity_type": "component"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["id"] == "1"
    assert payload["explain"]["provider"] == "in_memory"


def test_runtime_router_relations_returns_items_and_explain(monkeypatch):
    from app.routers import runtime as runtime_router

    monkeypatch.setattr(runtime_router, "get_runtime_query_service", _test_query_service)
    client = TestClient(app)

    response = client.get(
        "/api/runtime/entities/1/relations",
        params={"domain": "alpha", "entity_type": "component", "direction": "downstream"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["id"] == "relation-1"
    assert payload["explain"]["operators"] == ["query_relations", "get_downstream"]


def test_runtime_router_rejects_invalid_relation_direction(monkeypatch):
    from app.routers import runtime as runtime_router

    monkeypatch.setattr(runtime_router, "get_runtime_query_service", _test_query_service)
    client = TestClient(app)

    response = client.get(
        "/api/runtime/entities/1/relations",
        params={"domain": "alpha", "entity_type": "component", "direction": "invalid"},
    )

    assert response.status_code == 422


def test_default_runtime_query_service_is_reused():
    from app.routers import runtime as runtime_router

    runtime_router.get_runtime_query_service.cache_clear()

    first = runtime_router.get_runtime_query_service()
    second = runtime_router.get_runtime_query_service()

    assert first is second


def test_runtime_router_evidence_returns_query_hints_and_explain(monkeypatch):
    from app.routers import runtime as runtime_router

    monkeypatch.setattr(runtime_router, "get_runtime_query_service", _test_query_service)
    client = TestClient(app)

    response = client.get("/api/runtime/entities/1/evidence", params={"domain": "alpha", "entity_type": "component"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["query_hints"] == []
    assert payload["explain"]["operators"] == ["resolve_evidence"]


def test_runtime_router_explain_returns_explain(monkeypatch):
    from app.routers import runtime as runtime_router

    monkeypatch.setattr(runtime_router, "get_runtime_query_service", _test_query_service)
    client = TestClient(app)

    response = client.get("/api/runtime/query/explain", params={"query_type": "relations"})

    assert response.status_code == 200
    assert response.json()["explain"]["operators"] == ["query_relations"]


def test_runtime_router_agent_tools_returns_discovery(monkeypatch):
    from app.routers import runtime as runtime_router

    monkeypatch.setattr(runtime_router, "get_runtime_query_service", _test_query_service)
    client = TestClient(app)

    response = client.get("/api/runtime/agent/tools")

    assert response.status_code == 200
    payload = response.json()
    assert [tool["name"] for tool in payload["tools"]] == [
        "mmodel.find_entity",
        "mmodel.get_topology",
        "mmodel.get_evidence_links",
        "mmodel.explain_entity",
    ]
    assert all(tool["read_only"] for tool in payload["tools"])


def test_runtime_router_agent_find_entity_call_returns_result(monkeypatch):
    from app.routers import runtime as runtime_router

    monkeypatch.setattr(runtime_router, "get_runtime_query_service", _test_query_service)
    client = TestClient(app)

    response = client.post(
        "/api/runtime/agent/tools/mmodel.find_entity/call",
        json={"arguments": {"domain": "alpha", "entity_type": "component"}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["output"]["items"][0]["id"] == "1"
    assert payload["output"]["explain"]["operators"] == ["query_entities"]


def test_runtime_router_agent_unknown_tool_returns_structured_error(monkeypatch):
    from app.routers import runtime as runtime_router

    monkeypatch.setattr(runtime_router, "get_runtime_query_service", _test_query_service)
    client = TestClient(app)

    response = client.post("/api/runtime/agent/tools/mmodel.unknown/call", json={"arguments": {}})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "tool_not_found"


def test_existing_diagnose_route_remains_registered():
    assert any(route.path == "/api/diagnose" for route in app.routes)
