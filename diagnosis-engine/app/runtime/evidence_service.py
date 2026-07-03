from __future__ import annotations

from typing import Any

from app.repositories.contracts import LogRepository, MetricRepository, RepositoryResult, TraceRepository
from app.repositories.default_repositories import DefaultLogRepository, DefaultMetricRepository, DefaultTraceRepository
from app.runtime.link_resolver import LinkEvidenceResolver
from app.runtime.models import (
    EntityReference,
    EvidenceQueryHint,
    LinkEvidenceResult,
    RuntimeEvidenceFetchResponse,
    RuntimeEvidenceFetchResult,
)


_SAFE_RAW_REF_KEYS = {"kind", "ref", "source", "index", "id"}


class RuntimeEvidenceService:
    """Fetch runtime evidence through repository boundaries from query hints.

    P6 maps Link/Evidence query hints to existing repository interfaces. It does
    not generate OpenSearch DSL, call adapters directly, or interact with
    diagnosis Skills.
    """

    def __init__(
        self,
        *,
        trace_repository: TraceRepository | None = None,
        log_repository: LogRepository | None = None,
        metric_repository: MetricRepository | None = None,
        link_resolver: LinkEvidenceResolver | None = None,
    ) -> None:
        self._trace_repository = trace_repository or DefaultTraceRepository()
        self._log_repository = log_repository or DefaultLogRepository()
        self._metric_repository = metric_repository or DefaultMetricRepository(
            trace_repository=self._trace_repository,
            log_repository=self._log_repository,
        )
        self._link_resolver = link_resolver or LinkEvidenceResolver()

    def resolve_and_fetch_for_entity(
        self,
        entity_ref: EntityReference,
        *,
        time_range: dict[str, Any] | None = None,
        query_context: dict[str, Any] | None = None,
    ) -> RuntimeEvidenceFetchResponse:
        resolved = self._link_resolver.resolve(entity_ref)
        response = self.fetch_for_entity(
            entity_ref,
            resolved,
            time_range=time_range,
            query_context=query_context,
        )
        return RuntimeEvidenceFetchResponse(
            entity=response.entity,
            results=response.results,
            warnings=[*resolved.warnings, *response.warnings],
        )

    def fetch_for_entity(
        self,
        entity_ref: EntityReference,
        query_hints: LinkEvidenceResult | list[EvidenceQueryHint],
        *,
        time_range: dict[str, Any] | None = None,
        query_context: dict[str, Any] | None = None,
    ) -> RuntimeEvidenceFetchResponse:
        hints = query_hints.query_hints if isinstance(query_hints, LinkEvidenceResult) else query_hints
        results = [
            self.fetch_hint(entity_ref, hint, time_range=time_range, query_context=query_context)
            for hint in hints
        ]
        return RuntimeEvidenceFetchResponse(entity=entity_ref, results=results)

    def fetch_hint(
        self,
        entity_ref: EntityReference,
        hint: EvidenceQueryHint,
        *,
        time_range: dict[str, Any] | None = None,
        query_context: dict[str, Any] | None = None,
    ) -> RuntimeEvidenceFetchResult:
        semantic_context = _semantic_context(entity_ref, hint)
        service_name = entity_ref.name or entity_ref.entity_id
        if not service_name:
            return RuntimeEvidenceFetchResult(
                evidence_type=hint.evidence_type,
                repository=hint.repository,
                availability="insufficient",
                warnings=["entity_id or name is required to build repository query parameters."],
                semantic_context=semantic_context,
            )

        repository_result = self._dispatch(
            hint=hint,
            service_name=service_name,
            time_range=time_range,
            query_context=_repository_query_context(query_context, semantic_context, time_range),
        )
        if isinstance(repository_result, RuntimeEvidenceFetchResult):
            return repository_result
        if repository_result is None:
            return RuntimeEvidenceFetchResult(
                evidence_type=getattr(hint, "evidence_type", "unknown"),
                repository=str(getattr(hint, "repository", "unknown")),
                availability="insufficient",
                warnings=[f"Unsupported evidence repository: {getattr(hint, 'repository', 'unknown')}"],
                semantic_context=semantic_context,
            )

        merged_semantic_context = {**repository_result.semantic_context, **semantic_context}
        repository_result.semantic_context = merged_semantic_context
        return RuntimeEvidenceFetchResult(
            evidence_type=hint.evidence_type,
            repository=hint.repository,
            availability=repository_result.availability,
            items=repository_result.items,
            warnings=repository_result.warnings,
            semantic_context=merged_semantic_context,
            raw_refs=_safe_raw_refs(repository_result.raw_refs),
        )

    def _dispatch(
        self,
        *,
        hint: EvidenceQueryHint,
        service_name: str,
        time_range: dict[str, Any] | None,
        query_context: dict[str, Any],
    ) -> RepositoryResult | RuntimeEvidenceFetchResult | None:
        data_dir = _string_or_none(query_context.get("data_dir"))
        case_id = _string_or_none(query_context.get("case_id"))
        try:
            if hint.repository == "MetricRepository":
                return self._metric_repository.get_red_metrics(
                    service_name=service_name,
                    time_range=time_range,
                    data_dir=data_dir,
                    case_id=case_id,
                )
            if hint.repository == "LogRepository":
                return self._log_repository.get_error_logs(
                    service_name=service_name,
                    time_range=time_range,
                    data_dir=data_dir,
                    case_id=case_id,
                )
            if hint.repository == "TraceRepository":
                return self._trace_repository.get_traces(
                    query=query_context,
                    data_dir=data_dir,
                    case_id=case_id,
                )
        except Exception as exc:
            return RuntimeEvidenceFetchResult(
                evidence_type=hint.evidence_type,
                repository=hint.repository,
                availability="unavailable",
                items=[],
                warnings=[f"repository unavailable: {hint.repository} raised {type(exc).__name__}"],
                semantic_context=query_context.get("semantic_context") or {},
            )
        return None


def _semantic_context(entity_ref: EntityReference, hint: EvidenceQueryHint) -> dict[str, Any]:
    return {
        "entity_id": entity_ref.entity_id,
        "entity_type": entity_ref.entity_type,
        "domain": entity_ref.domain,
        "data_set": hint.data_set,
        "storage": hint.storage,
        "evidence_type": hint.evidence_type,
        "repository": hint.repository,
    }


def _repository_query_context(
    query_context: dict[str, Any] | None,
    semantic_context: dict[str, Any],
    time_range: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(query_context or {})
    if time_range:
        merged.setdefault("time_window", dict(time_range))
    merged["semantic_context"] = {**semantic_context, **dict(merged.get("semantic_context") or {})}
    return merged


def _safe_raw_refs(raw_refs: list[dict[str, str]]) -> list[dict[str, str]]:
    safe_refs: list[dict[str, str]] = []
    for raw_ref in raw_refs:
        safe_refs.append({key: str(value) for key, value in raw_ref.items() if key in _SAFE_RAW_REF_KEYS})
    return safe_refs


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    token = str(value).strip()
    return token or None