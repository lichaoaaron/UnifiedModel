import os
import yaml

def test_runtime_domain_model_has_no_instances():
    path = os.path.join(os.path.dirname(__file__), "..", "data", "mmodel", "runtime_domain_model.yaml")
    path = os.path.normpath(path)
    assert os.path.isfile(path), f"runtime_domain_model.yaml not found at {path}"
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    # Should contain entity_types and relation_types
    assert "entity_types" in data
    assert "relation_types" in data
    # Must not contain concrete entities/relations
    assert not data.get("entities"), "runtime_domain_model.yaml must not contain concrete entities"
    assert not data.get("relations"), "runtime_domain_model.yaml must not contain concrete relations"
