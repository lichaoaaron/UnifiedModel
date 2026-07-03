import os
import sys


REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
BACKEND_ROOT = os.path.join(REPO_ROOT, "backend")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)


from app.adapters.umodel_yaml_adapter import UModelYamlAdapter
from app.runtime.link_resolver import LinkEvidenceResolver
from app.runtime.models import EntityReference


def _write(path, content: str) -> None:
    path.write_text(content.strip(), encoding="utf-8")


def _write_dataset(path, *, kind: str, name: str) -> None:
    _write(path, f"""
kind: {kind}
metadata:
  domain: alpha
  name: {name}
spec:
  time_field: event_time
  fields:
    - name: service_id
      type: string
    - name: severity
      type: string
  labels:
    keys:
      - name: service_id
        type: string
  metrics:
    - name: request_count
      type: gauge
""")


def _write_data_link(path, *, name: str, dest_kind: str, dest_name: str, data_filter: str = "") -> None:
    filter_line = f"  data_filter: {data_filter}\n" if data_filter else ""
    _write(path, f"""
kind: data_link
metadata:
  domain: alpha
  name: {name}
spec:
  src:
    kind: entity_set
    domain: alpha
    name: alpha.service
  dest:
    kind: {dest_kind}
    domain: alpha
    name: {dest_name}
  data_link_type: related_to
{filter_line}  fields_mapping:
    service_id: service_id
""")


def _write_storage_link(path, *, name: str, src_kind: str, src_name: str, dest_name: str) -> None:
    _write(path, f"""
kind: storage_link
metadata:
  domain: alpha
  name: {name}
spec:
  src:
    kind: {src_kind}
    domain: alpha
    name: {src_name}
  dest:
    kind: storage
    domain: alpha
    name: {dest_name}
  priority: 1
  filter_by_entity: tenant = 'default'
  fields_mapping:
    severity: level
""")


def _write_three_evidence_fixture(tmp_path) -> None:
    _write_dataset(tmp_path / "metric_set.yaml", kind="metric_set", name="alpha.metric.service")
    _write_dataset(tmp_path / "log_set.yaml", kind="log_set", name="alpha.log.service")
    _write_dataset(tmp_path / "trace_set.yaml", kind="trace_set", name="alpha.trace.service")
    _write_data_link(
        tmp_path / "metric_link.yaml",
        name="alpha.service_related_to_alpha.metric.service",
        dest_kind="metric_set",
        dest_name="alpha.metric.service",
    )
    _write_data_link(
        tmp_path / "log_link.yaml",
        name="alpha.service_related_to_alpha.log.service",
        dest_kind="log_set",
        dest_name="alpha.log.service",
        data_filter="severity = 'ERROR'",
    )
    _write_data_link(
        tmp_path / "trace_link.yaml",
        name="alpha.service_related_to_alpha.trace.service",
        dest_kind="trace_set",
        dest_name="alpha.trace.service",
    )
    _write_storage_link(
        tmp_path / "metric_storage.yaml",
        name="alpha.metric.service_storage",
        src_kind="metric_set",
        src_name="alpha.metric.service",
        dest_name="alpha.metric_store",
    )
    _write_storage_link(
        tmp_path / "log_storage.yaml",
        name="alpha.log.service_storage",
        src_kind="log_set",
        src_name="alpha.log.service",
        dest_name="alpha.log_store",
    )
    _write_storage_link(
        tmp_path / "trace_storage.yaml",
        name="alpha.trace.service_storage",
        src_kind="trace_set",
        src_name="alpha.trace.service",
        dest_name="alpha.trace_store",
    )


def test_link_resolver_resolves_metric_log_trace_query_hints(tmp_path):
    _write_three_evidence_fixture(tmp_path)
    resolver = LinkEvidenceResolver(UModelYamlAdapter(data_dir=str(tmp_path)))

    result = resolver.resolve(EntityReference(domain="alpha", entity_type="service", entity_id="entity-1"))

    assert result.entity.domain == "alpha"
    assert result.evidence_types == ["metric", "log", "trace"]
    assert len(result.query_hints) == 3
    assert result.warnings == []

    repositories = {hint.evidence_type: hint.repository for hint in result.query_hints}
    assert repositories == {
        "metric": "MetricRepository",
        "log": "LogRepository",
        "trace": "TraceRepository",
    }


def test_link_resolver_preserves_link_and_storage_semantics(tmp_path):
    _write_three_evidence_fixture(tmp_path)
    resolver = LinkEvidenceResolver(UModelYamlAdapter(data_dir=str(tmp_path)))

    result = resolver.resolve(EntityReference(entity_type="alpha.service"))
    log_hint = next(hint for hint in result.query_hints if hint.evidence_type == "log")

    assert log_hint.data_set == "alpha.log.service"
    assert log_hint.storage == "alpha.log_store"
    assert log_hint.storage_ref == {"kind": "storage", "domain": "alpha", "name": "alpha.log_store"}
    assert log_hint.field_mapping == {
        "data_link": {"service_id": "service_id"},
        "storage_link": {"severity": "level"},
    }
    assert log_hint.data_filter == "severity = 'ERROR'"
    assert log_hint.filter_by_entity == "tenant = 'default'"
    assert log_hint.source == "umodel_yaml"


def test_link_resolver_missing_data_link_returns_warning_without_hints(tmp_path):
    _write_dataset(tmp_path / "log_set.yaml", kind="log_set", name="alpha.log.service")
    resolver = LinkEvidenceResolver(UModelYamlAdapter(data_dir=str(tmp_path)))

    result = resolver.resolve(EntityReference(domain="alpha", entity_type="service"))

    assert result.query_hints == []
    assert result.evidence_types == []
    assert result.warnings == ["No DataLink found for entity set 'alpha.service'."]


def test_link_resolver_missing_storage_link_warns_and_keeps_evidence_type(tmp_path):
    _write_dataset(tmp_path / "log_set.yaml", kind="log_set", name="alpha.log.service")
    _write_data_link(
        tmp_path / "log_link.yaml",
        name="alpha.service_related_to_alpha.log.service",
        dest_kind="log_set",
        dest_name="alpha.log.service",
    )
    resolver = LinkEvidenceResolver(UModelYamlAdapter(data_dir=str(tmp_path)))

    result = resolver.resolve(EntityReference(domain="alpha", entity_type="service"))

    assert result.evidence_types == ["log"]
    assert result.query_hints == []
    assert result.warnings == ["No StorageLink found for data set 'alpha.log.service'."]


def test_link_resolver_requires_full_domain_name_matching(tmp_path):
    _write_dataset(tmp_path / "log_set.yaml", kind="log_set", name="alpha.log.runtime")
    _write_data_link(
        tmp_path / "log_link.yaml",
        name="alpha.service_related_to_alpha.log.runtime",
        dest_kind="log_set",
        dest_name="alpha.log.runtime",
    )
    _write_storage_link(
        tmp_path / "log_storage.yaml",
        name="alpha.log.runtime_storage",
        src_kind="log_set",
        src_name="alpha.log.runtime",
        dest_name="alpha.runtime_store",
    )
    resolver = LinkEvidenceResolver(UModelYamlAdapter(data_dir=str(tmp_path)))

    exact = resolver.resolve(EntityReference(entity_type="alpha.service"))
    short = resolver.resolve(EntityReference(entity_type="service"))

    assert len(exact.query_hints) == 1
    assert short.query_hints == []
    assert short.warnings == ["No DataLink found for entity set 'service'."]
