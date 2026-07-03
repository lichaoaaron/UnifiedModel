from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.runtime.entity_store import InMemoryEntityStore
from app.runtime.models import (
    EntityQuery,
    RuntimeEntity,
    RuntimeQueryExplain,
    RuntimeSearchCandidate,
    RuntimeSearchQuery,
    RuntimeSearchResult,
)
from app.runtime.query_service import RuntimeQueryService


class RuntimeSearchService:
    """Lightweight in-memory entity locator for runtime clues.

    P8 only scans RuntimeQueryService/InMemoryEntityStore results with explicit
    rules. It does not query OpenSearch, call diagnosis Skills, or write stores.
    """

    def __init__(
        self,
        *,
        query_service: RuntimeQueryService | None = None,
        entity_store: InMemoryEntityStore | None = None,
    ) -> None:
        self._query_service = query_service or RuntimeQueryService(entity_store=entity_store)

    def search(self, query: RuntimeSearchQuery | None = None, **kwargs: Any) -> RuntimeSearchResult:
        search_query = query or RuntimeSearchQuery(**kwargs)
        clues = _build_clues(search_query)
        warnings: list[str] = []
        if not clues:
            warnings.append("At least one search clue is required.")
            return RuntimeSearchResult(candidates=[], explain=_explain(warnings), warnings=warnings)

        entities = self._query_service.query_entities(EntityQuery()).items
        candidates: list[RuntimeSearchCandidate] = []
        for entity in entities:
            match = _match_entity(entity, clues)
            if match is None:
                continue
            candidates.append(RuntimeSearchCandidate(
                entity=entity,
                match_reason="; ".join(match.reasons),
                confidence=match.confidence,
                matched_fields=sorted(match.fields),
                source="runtime_search:entity_store",
            ))

        candidates.sort(key=lambda candidate: (-candidate.confidence, candidate.entity.id))
        if search_query.limit is not None:
            candidates = candidates[:max(search_query.limit, 0)]
        if not candidates:
            warnings.append("No runtime entities matched the search clues.")

        return RuntimeSearchResult(candidates=candidates, explain=_explain(warnings), warnings=warnings)


@dataclass(frozen=True)
class _Clue:
    kind: str
    value: str


@dataclass
class _MatchAccumulator:
    scores: list[float] = field(default_factory=list)
    fields: set[str] = field(default_factory=set)
    reasons: list[str] = field(default_factory=list)

    @property
    def confidence(self) -> float:
        if not self.scores:
            return 0.0
        combined = max(self.scores) + (0.05 * (len(self.scores) - 1))
        return round(min(combined, 0.99), 2)

    def add(self, *, score: float, field_name: str, reason: str) -> None:
        self.scores.append(score)
        self.fields.add(field_name)
        if reason not in self.reasons:
            self.reasons.append(reason)


@dataclass(frozen=True)
class _SearchField:
    name: str
    value: str


def _build_clues(query: RuntimeSearchQuery) -> list[_Clue]:
    clues: list[_Clue] = []
    for kind, value in [
        ("text", query.text),
        ("service_name", query.service_name),
        ("instance", query.instance),
        ("trace_id", query.trace_id),
        ("error_code", query.error_code),
        ("alert_text", query.alert_text),
    ]:
        token = _clean_text(value)
        if token:
            clues.append(_Clue(kind=kind, value=token))
    return clues


def _match_entity(entity: RuntimeEntity, clues: list[_Clue]) -> _MatchAccumulator | None:
    fields = _entity_search_fields(entity)
    match = _MatchAccumulator()
    for clue in clues:
        if clue.kind in {"text", "service_name"}:
            _match_identity_clue(match, clue, entity, fields)
        elif clue.kind == "instance":
            _match_keyed_clue(match, clue, fields, ["instance", "pod", "host", "node"])
        elif clue.kind == "trace_id":
            _match_keyed_clue(match, clue, fields, ["trace", "span"])
            _match_safe_trace_raw_refs(match, clue, entity)
        elif clue.kind == "error_code":
            _match_keyed_clue(match, clue, fields, ["error", "code", "status"])
        elif clue.kind == "alert_text":
            _match_alert_text(match, clue, fields)
    if not match.scores:
        return None
    return match


def _match_identity_clue(
    match: _MatchAccumulator,
    clue: _Clue,
    entity: RuntimeEntity,
    fields: list[_SearchField],
) -> None:
    expected = _normalize(clue.value)
    for field_name, value in [("id", entity.id), ("name", entity.name)]:
        actual = _normalize(value)
        if not actual:
            continue
        if actual == expected:
            match.add(score=0.95, field_name=field_name, reason=f"{clue.kind} exactly matched entity {field_name}")
        elif expected in actual:
            match.add(score=0.82, field_name=field_name, reason=f"{clue.kind} matched entity {field_name} fragment")

    for field in fields:
        if not _path_contains_any(field.name, ["service", "display", "alias", "keyword"]):
            continue
        actual = _normalize(field.value)
        if not actual:
            continue
        if actual == expected:
            match.add(score=0.78, field_name=field.name, reason=f"{clue.kind} matched {field.name}")
        elif expected in actual:
            match.add(score=0.68, field_name=field.name, reason=f"{clue.kind} matched {field.name} fragment")


def _match_keyed_clue(
    match: _MatchAccumulator,
    clue: _Clue,
    fields: list[_SearchField],
    path_tokens: list[str],
) -> None:
    expected = _normalize(clue.value)
    for field in fields:
        if not _path_contains_any(field.name, path_tokens):
            continue
        actual = _normalize(field.value)
        if not actual:
            continue
        if actual == expected:
            match.add(score=0.76, field_name=field.name, reason=f"{clue.kind} matched {field.name}")
        elif expected in actual:
            match.add(score=0.66, field_name=field.name, reason=f"{clue.kind} matched {field.name} fragment")


def _match_safe_trace_raw_refs(match: _MatchAccumulator, clue: _Clue, entity: RuntimeEntity) -> None:
    expected = _normalize(clue.value)
    for index, raw_ref in enumerate(entity.raw_refs):
        if not isinstance(raw_ref, dict):
            continue
        kind = _normalize(raw_ref.get("kind"))
        if kind not in {"trace", "span"}:
            continue
        for key in ["id", "ref", "traceId", "trace_id", "spanId", "span_id"]:
            actual = _normalize(raw_ref.get(key))
            if actual and actual == expected:
                field_name = f"raw_refs[{index}].{key}"
                match.add(score=0.76, field_name=field_name, reason=f"trace_id matched safe {field_name}")


def _match_alert_text(match: _MatchAccumulator, clue: _Clue, fields: list[_SearchField]) -> None:
    tokens = _alert_tokens(clue.value)
    if not tokens:
        return
    for field in fields:
        if not _is_alert_search_field(field.name):
            continue
        actual = _normalize(field.value)
        if not actual:
            continue
        matched_tokens = [token for token in tokens if token in actual]
        if not matched_tokens:
            continue
        score = min(0.62, 0.36 + (0.08 * len(set(matched_tokens))))
        match.add(
            score=score,
            field_name=field.name,
            reason=f"alert_text keywords matched {field.name}: {', '.join(sorted(set(matched_tokens)))}",
        )


def _is_alert_search_field(field_name: str) -> bool:
    return field_name in {"id", "name"} or field_name.startswith("attributes.") or field_name.startswith("raw_refs[")


def _entity_search_fields(entity: RuntimeEntity) -> list[_SearchField]:
    fields = [
        _SearchField("id", entity.id),
        _SearchField("entity_type", entity.entity_type),
        _SearchField("domain", entity.domain or ""),
        _SearchField("name", entity.name),
        _SearchField("source", entity.source),
    ]
    fields.extend(_flatten_value("attributes", entity.attributes))
    fields.extend(_flatten_value("raw_refs", entity.raw_refs))
    return fields


def _flatten_value(prefix: str, value: Any) -> list[_SearchField]:
    fields: list[_SearchField] = []
    if value is None:
        return fields
    if isinstance(value, dict):
        for key, item in value.items():
            fields.extend(_flatten_value(f"{prefix}.{key}", item))
        return fields
    if isinstance(value, list):
        for index, item in enumerate(value):
            fields.extend(_flatten_value(f"{prefix}[{index}]", item))
        return fields
    fields.append(_SearchField(prefix, str(value)))
    return fields


def _alert_tokens(value: str) -> list[str]:
    normalized = _normalize(value)
    return [token for token in re.split(r"[^a-z0-9_\-]+", normalized) if len(token) >= 3]


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize(value: Any) -> str:
    return _clean_text(value).lower()


def _path_contains_any(path: str, tokens: list[str]) -> bool:
    normalized_path = _normalize(path)
    return any(token in normalized_path for token in tokens)


def _explain(warnings: list[str] | None = None) -> RuntimeQueryExplain:
    return RuntimeQueryExplain(
        source="runtime_search",
        provider="in_memory",
        operators=["query_entities", "rule_match"],
        fallback=[],
        warnings=warnings or [],
    )
