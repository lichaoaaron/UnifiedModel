import json
import os
from app.adapters import local_json_adapter as adapter


def test_entity_binding_from_observability():
    # Ensure adapter reads traces and returns non-empty list
    repo_root = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
    index_path = os.path.join(repo_root, "examples", "evaluation_cases", "basic_root_cause_19", "index.json")
    case_id = json.load(open(index_path, encoding="utf-8"))[0]["case_id"]
    traces = adapter.get_traces(case_id=case_id)
    assert isinstance(traces, list)
    assert len(traces) > 0
    # Check that binding extracts at least one service name
    services = set()
    for s in traces:
        src = s.get("_source", s)
        svc = src.get("serviceName") or src.get("resource.attributes.service@name")
        if svc:
            services.add(svc)
    assert len(services) > 0, "No services extracted from trace observability data"
