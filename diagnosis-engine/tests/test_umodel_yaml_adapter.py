import os
import sys


REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
BACKEND_ROOT = os.path.join(REPO_ROOT, "backend")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)


from app.adapters.umodel_yaml_adapter import UModelYamlAdapter


def test_umodel_yaml_adapter_loads_entity_sets_and_links():
    adapter = UModelYamlAdapter()

    stats = adapter.stats()
    entity_set_names = adapter.list_entity_set_names()
    entity_links = adapter.list_entity_links()

    assert stats["entity_sets"] > 0
    assert stats["entity_links"] > 0
    assert len(entity_set_names) == stats["entity_sets"]
    assert len(entity_links) == stats["entity_links"]

    graph = adapter.get_call_graph()
    assert isinstance(graph["nodes"], list)
    assert isinstance(graph["edges"], list)


def test_umodel_yaml_adapter_loads_supported_data_set_kinds():
    adapter = UModelYamlAdapter()

    data_sets = adapter.list_data_sets()
    data_set_kinds = {item["kind"] for item in data_sets}

    assert {"metric_set", "log_set", "trace_set"}.issubset(data_set_kinds)
    assert len(adapter.list_data_sets(kind="metric_set")) > 0
    assert len(adapter.list_data_sets(kind="log_set")) > 0
    assert len(adapter.list_data_sets(kind="trace_set")) > 0


def test_umodel_yaml_adapter_loads_data_links_and_storage_links():
    adapter = UModelYamlAdapter()

    data_links = adapter.list_data_links()
    storage_links = adapter.list_storage_links()

    assert len(data_links) > 0
    assert len(storage_links) > 0
    assert all("src" in item and "dest" in item for item in data_links)
    assert all("src" in item and "dest" in item for item in storage_links)


def test_umodel_yaml_adapter_stats_include_p2_fields():
    adapter = UModelYamlAdapter()

    stats = adapter.stats()

    assert set(stats) == {
        "entity_sets",
        "entity_links",
        "data_sets",
        "data_links",
        "storage_links",
        "warnings",
    }
    assert stats["data_sets"] > 0
    assert stats["data_links"] > 0
    assert stats["storage_links"] > 0
    assert stats["warnings"] >= 0


def test_umodel_yaml_adapter_bad_yaml_returns_warning(tmp_path):
    bad_file = tmp_path / "bad.yaml"
    bad_file.write_text("kind: [\n", encoding="utf-8")

    adapter = UModelYamlAdapter(data_dir=str(tmp_path))
    stats = adapter.stats()
    warnings = adapter.warnings()

    assert stats["warnings"] == 1
    assert len(warnings) == 1
    assert warnings[0]["path"] == str(bad_file)
    assert warnings[0]["error"]
    assert adapter.list_entity_set_names() == []


def test_umodel_yaml_adapter_preserves_p3_link_and_dataset_fields(tmp_path):
    (tmp_path / "log_set.yaml").write_text(
        """
kind: log_set
metadata:
  domain: alpha
  name: alpha.log.runtime
spec:
  time_field: event_time
  fields:
    - name: service_id
      type: string
    - name: severity
      type: string
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "metric_set.yaml").write_text(
        """
kind: metric_set
metadata:
  domain: alpha
  name: alpha.metric.runtime
spec:
  labels:
    keys:
      - name: service_id
        type: string
  metrics:
    - name: request_count
      type: gauge
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "data_link.yaml").write_text(
        """
kind: data_link
metadata:
  domain: alpha
  name: alpha.component_related_to_alpha.log.runtime
spec:
  src:
    kind: entity_set
    domain: alpha
    name: alpha.component
  dest:
    kind: log_set
    domain: alpha
    name: alpha.log.runtime
  data_link_type: related_to
  data_filter: severity = 'ERROR'
  fields_mapping:
    service_id: service_id
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "storage_link.yaml").write_text(
        """
kind: storage_link
metadata:
  domain: alpha
  name: alpha.log.runtime_storage
spec:
  src:
    kind: log_set
    domain: alpha
    name: alpha.log.runtime
  dest:
    kind: sls_logstore
    domain: alpha
    name: alpha.runtime_store
  filter_by_entity: enabled = true
  fields_mapping:
    severity: level
""".strip(),
        encoding="utf-8",
    )

    adapter = UModelYamlAdapter(data_dir=str(tmp_path))

    log_set = adapter.list_data_sets(kind="log_set")[0]
    metric_set = adapter.list_data_sets(kind="metric_set")[0]
    data_link = adapter.list_data_links(entity_set="alpha.component", data_set="alpha.log.runtime")[0]
    storage_link = adapter.list_storage_links(data_set="alpha.log.runtime")[0]

    assert log_set["field_names"] == ["service_id", "severity"]
    assert [item["name"] for item in log_set["fields"]] == ["service_id", "severity"]
    assert metric_set["field_names"] == ["service_id", "request_count"]
    assert data_link["fields_mapping"] == {"service_id": "service_id"}
    assert data_link["data_filter"] == "severity = 'ERROR'"
    assert storage_link["filter_by_entity"] == "enabled = true"
    assert storage_link["fields_mapping"] == {"severity": "level"}


def test_umodel_yaml_adapter_ref_filters_do_not_match_short_suffixes(tmp_path):
    (tmp_path / "data_link.yaml").write_text(
        """
kind: data_link
metadata:
  domain: alpha
  name: alpha.component_related_to_alpha.log.runtime
spec:
  src:
    kind: entity_set
    domain: alpha
    name: alpha.component
  dest:
    kind: log_set
    domain: alpha
    name: alpha.log.runtime
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "storage_link.yaml").write_text(
        """
kind: storage_link
metadata:
  domain: alpha
  name: alpha.log.runtime_storage
spec:
  src:
    kind: log_set
    domain: alpha
    name: alpha.log.runtime
  dest:
    kind: sls_logstore
    domain: alpha
    name: alpha.runtime_store
""".strip(),
        encoding="utf-8",
    )

    adapter = UModelYamlAdapter(data_dir=str(tmp_path))

    assert len(adapter.list_data_links(entity_set="alpha.component")) == 1
    assert len(adapter.list_data_links(data_set="alpha.log.runtime")) == 1
    assert adapter.list_data_links(entity_set="component") == []
    assert adapter.list_data_links(data_set="runtime") == []
    assert adapter.list_data_links(data_set="log.runtime") == []
    assert len(adapter.list_storage_links(data_set="alpha.log.runtime")) == 1
    assert adapter.list_storage_links(data_set="runtime") == []
    assert adapter.list_storage_links(data_set="log.runtime") == []
