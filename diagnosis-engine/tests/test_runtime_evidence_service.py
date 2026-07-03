import os
import sys


REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
BACKEND_ROOT = os.path.join(REPO_ROOT, "backend")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)


from app.repositories.contracts import RepositoryResult
from app.runtime.evidence_service import RuntimeEvidenceService
from app.runtime.models import EntityReference, EvidenceQueryHint, LinkEvidenceResult


class RecordingMetricRepository:
    def __init__(self, result: RepositoryResult | None = None) -> None:
        self.calls: list[dict] = []
        self.result = result or RepositoryResult(
            source="fake_metric",
            query_context={},
            items=[{"value": 1}],
            raw_refs=[{"kind": "metric", "ref": "metric:1", "secret": "drop-me"}],
            semantic_context={"repository_context": "metric"},
        )

    def get_red_metrics(self, service_name=None, time_range=None, *, data_dir=None, case_id=None):
        self.calls.append({
            "service_name": service_name,
            "time_range": time_range,
            "data_dir": data_dir,
            "case_id": case_id,
        })
        return self.result


class RecordingLogRepository:
    def __init__(self, result: RepositoryResult | None = None) -> None:
        self.calls: list[dict] = []
        self.result = result or RepositoryResult(
            source="fake_log",
            query_context={},
            items=[{"message": "error"}],
            raw_refs=[{"kind": "log", "index": "logs", "id": "log-1", "payload": "drop-me"}],
        )

    def get_error_logs(self, service_name=None, time_range=None, *, data_dir=None, case_id=None):
        self.calls.append({
            "service_name": service_name,
            "time_range": time_range,
            "data_dir": data_dir,
            "case_id": case_id,
        })
        return self.result


class RecordingTraceRepository:
    def __init__(self, result: RepositoryResult | None = None) -> None:
        self.calls: list[dict] = []
        self.result = result or RepositoryResult(
            source="fake_trace",
            query_context={},
            items=[{"traceId": "trace-1"}],
            raw_refs=[{"kind": "trace", "source": "trace-store", "id": "trace-1", "body": "drop-me"}],
        )

    def get_traces(self, query=None, *, data_dir=None, case_id=None):
        self.calls.append({"query": query or {}, "data_dir": data_dir, "case_id": case_id})
        return self.result


class RaisingMetricRepository:
    def get_red_metrics(self, service_name=None, time_range=None, *, data_dir=None, case_id=None):
        raise RuntimeError("metric source unavailable")


class StaticLinkResolver:
    def __init__(self, hints: list[EvidenceQueryHint]) -> None:
        self.hints = hints

    def resolve(self, entity: EntityReference) -> LinkEvidenceResult:
        return LinkEvidenceResult(entity=entity, query_hints=self.hints)


def _hint(repository: str, evidence_type: str, data_set: str, storage: str) -> EvidenceQueryHint:
    return EvidenceQueryHint.model_construct(
        repository=repository,
        evidence_type=evidence_type,
        data_set=data_set,
        storage=storage,
    )


def _service() -> tuple[RuntimeEvidenceService, RecordingTraceRepository, RecordingLogRepository, RecordingMetricRepository]:
    trace_repository = RecordingTraceRepository()
    log_repository = RecordingLogRepository()
    metric_repository = RecordingMetricRepository()
    return (
        RuntimeEvidenceService(
            trace_repository=trace_repository,  # type: ignore[arg-type]
            log_repository=log_repository,  # type: ignore[arg-type]
            metric_repository=metric_repository,  # type: ignore[arg-type]
        ),
        trace_repository,
        log_repository,
        metric_repository,
    )


def test_metric_query_hint_calls_metric_repository_and_binds_semantic_context():
    service, _, _, metric_repository = _service()
    entity = EntityReference(domain="alpha", entity_type="component", entity_id="svc-1", name="service-one")

    result = service.fetch_hint(
        entity,
        _hint("MetricRepository", "metric", "alpha.metric.component", "alpha.metric_store"),
        time_range={"start": "2026-05-22T10:00:00Z", "end": "2026-05-22T10:05:00Z"},
    )

    assert metric_repository.calls == [{
        "service_name": "service-one",
        "time_range": {"start": "2026-05-22T10:00:00Z", "end": "2026-05-22T10:05:00Z"},
        "data_dir": None,
        "case_id": None,
    }]
    assert result.evidence_type == "metric"
    assert result.repository == "MetricRepository"
    assert result.availability == "available"
    assert result.items == [{"value": 1}]
    assert result.semantic_context == {
        "repository_context": "metric",
        "entity_id": "svc-1",
        "entity_type": "component",
        "domain": "alpha",
        "data_set": "alpha.metric.component",
        "storage": "alpha.metric_store",
        "evidence_type": "metric",
        "repository": "MetricRepository",
    }


def test_log_query_hint_calls_log_repository():
    service, _, log_repository, _ = _service()
    entity = EntityReference(domain="alpha", entity_type="component", entity_id="svc-1")

    result = service.fetch_hint(entity, _hint("LogRepository", "log", "alpha.log.component", "alpha.log_store"))

    assert log_repository.calls == [{"service_name": "svc-1", "time_range": None, "data_dir": None, "case_id": None}]
    assert result.evidence_type == "log"
    assert result.items == [{"message": "error"}]


def test_trace_query_hint_calls_trace_repository_with_semantic_query_context():
    service, trace_repository, _, _ = _service()
    entity = EntityReference(domain="alpha", entity_type="component", entity_id="svc-1")

    result = service.fetch_hint(
        entity,
        _hint("TraceRepository", "trace", "alpha.trace.component", "alpha.trace_store"),
        time_range={"start": "2026-05-22T10:00:00Z", "end": "2026-05-22T10:05:00Z"},
        query_context={"limit": 10},
    )

    assert trace_repository.calls[0]["query"]["limit"] == 10
    assert trace_repository.calls[0]["query"]["time_window"] == {
        "start": "2026-05-22T10:00:00Z",
        "end": "2026-05-22T10:05:00Z",
    }
    assert trace_repository.calls[0]["query"]["semantic_context"]["data_set"] == "alpha.trace.component"
    assert result.evidence_type == "trace"
    assert result.items == [{"traceId": "trace-1"}]


def test_query_context_case_id_and_data_dir_are_forwarded_to_repositories():
    service, trace_repository, log_repository, metric_repository = _service()
    entity = EntityReference(domain="alpha", entity_type="component", entity_id="svc-1")
    query_context = {"case_id": "case-one", "data_dir": "case-dir"}

    service.fetch_hint(
        entity,
        _hint("MetricRepository", "metric", "alpha.metric.component", "alpha.metric_store"),
        query_context=query_context,
    )
    service.fetch_hint(
        entity,
        _hint("LogRepository", "log", "alpha.log.component", "alpha.log_store"),
        query_context=query_context,
    )
    service.fetch_hint(
        entity,
        _hint("TraceRepository", "trace", "alpha.trace.component", "alpha.trace_store"),
        query_context=query_context,
    )

    assert metric_repository.calls[-1]["case_id"] == "case-one"
    assert metric_repository.calls[-1]["data_dir"] == "case-dir"
    assert log_repository.calls[-1]["case_id"] == "case-one"
    assert log_repository.calls[-1]["data_dir"] == "case-dir"
    assert trace_repository.calls[-1]["case_id"] == "case-one"
    assert trace_repository.calls[-1]["data_dir"] == "case-dir"


def test_raw_refs_are_sanitized_to_safe_reference_fields():
    service, _, _, _ = _service()
    entity = EntityReference(domain="alpha", entity_type="component", entity_id="svc-1")

    result = service.fetch_hint(entity, _hint("LogRepository", "log", "alpha.log.component", "alpha.log_store"))

    assert result.raw_refs == [{"kind": "log", "index": "logs", "id": "log-1"}]


def test_unsupported_repository_returns_insufficient_warning_without_exception():
    service, _, _, _ = _service()
    entity = EntityReference(domain="alpha", entity_type="component", entity_id="svc-1")

    result = service.fetch_hint(entity, _hint("UnknownRepository", "metric", "alpha.metric.component", ""))

    assert result.availability == "insufficient"
    assert result.items == []
    assert "Unsupported evidence repository" in result.warnings[0]


def test_unavailable_repository_result_does_not_fabricate_items():
    unavailable_metric = RecordingMetricRepository(RepositoryResult(
        source="fake_metric",
        items=[],
        availability="unavailable",
        warnings=["metric backend unavailable"],
    ))
    service = RuntimeEvidenceService(
        trace_repository=RecordingTraceRepository(),  # type: ignore[arg-type]
        log_repository=RecordingLogRepository(),  # type: ignore[arg-type]
        metric_repository=unavailable_metric,  # type: ignore[arg-type]
    )

    result = service.fetch_hint(
        EntityReference(domain="alpha", entity_type="component", entity_id="svc-1"),
        _hint("MetricRepository", "metric", "alpha.metric.component", "alpha.metric_store"),
    )

    assert result.availability == "unavailable"
    assert result.items == []
    assert result.warnings == ["metric backend unavailable"]


def test_repository_exception_returns_structured_unavailable_result_with_semantic_context():
    service = RuntimeEvidenceService(
        trace_repository=RecordingTraceRepository(),  # type: ignore[arg-type]
        log_repository=RecordingLogRepository(),  # type: ignore[arg-type]
        metric_repository=RaisingMetricRepository(),  # type: ignore[arg-type]
    )
    entity = EntityReference(domain="alpha", entity_type="component", entity_id="svc-1")

    result = service.fetch_hint(
        entity,
        _hint("MetricRepository", "metric", "alpha.metric.component", "alpha.metric_store"),
    )

    assert result.availability == "unavailable"
    assert result.items == []
    assert "repository unavailable: MetricRepository raised RuntimeError" in result.warnings
    assert result.semantic_context == {
        "entity_id": "svc-1",
        "entity_type": "component",
        "domain": "alpha",
        "data_set": "alpha.metric.component",
        "storage": "alpha.metric_store",
        "evidence_type": "metric",
        "repository": "MetricRepository",
    }


def test_resolve_and_fetch_for_entity_uses_link_resolver_hints():
    hint = _hint("LogRepository", "log", "alpha.log.component", "alpha.log_store")
    service = RuntimeEvidenceService(
        trace_repository=RecordingTraceRepository(),  # type: ignore[arg-type]
        log_repository=RecordingLogRepository(),  # type: ignore[arg-type]
        metric_repository=RecordingMetricRepository(),  # type: ignore[arg-type]
        link_resolver=StaticLinkResolver([hint]),  # type: ignore[arg-type]
    )

    response = service.resolve_and_fetch_for_entity(EntityReference(domain="alpha", entity_type="component", entity_id="svc-1"))

    assert len(response.results) == 1
    assert response.results[0].repository == "LogRepository"


def test_repository_result_to_dict_remains_backward_compatible_with_semantic_context():
    result = RepositoryResult(source="unit", items=[{"id": "item-1"}], semantic_context={"entity_id": "svc-1"})

    assert result.to_dict() == {
        "source": "unit",
        "query_context": {},
        "items": [{"id": "item-1"}],
        "availability": "available",
        "warnings": [],
        "raw_refs": [],
        "semantic_context": {"entity_id": "svc-1"},
    }
