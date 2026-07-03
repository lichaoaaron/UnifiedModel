from __future__ import annotations

from typing import Any, Literal

from app.adapters.umodel_yaml_adapter import UModelYamlAdapter
from app.runtime.models import EntityReference, EvidenceQueryHint, LinkEvidenceResult


_DATA_SET_TO_REPOSITORY: dict[str, tuple[Literal["metric", "log", "trace"], str]] = {
    "metric_set": ("metric", "MetricRepository"),
    "log_set": ("log", "LogRepository"),
    "trace_set": ("trace", "TraceRepository"),
}
_EVIDENCE_ORDER = {"metric": 0, "log": 1, "trace": 2}


class LinkEvidenceResolver:
    """Resolve semantic evidence entry points from UModel link definitions.

    P3 builds repository query hints only. It does not call repositories,
    adapters, OpenSearch, local evaluation cases, or diagnosis Skills.
    """

    def __init__(self, adapter: UModelYamlAdapter | None = None) -> None:
        self._adapter = adapter or UModelYamlAdapter()

    def resolve(self, entity: EntityReference) -> LinkEvidenceResult:
        entity_set = self._entity_set_key(entity)
        warnings: list[str] = []
        evidence_types: list[Literal["metric", "log", "trace"]] = []
        query_hints: list[EvidenceQueryHint] = []

        data_links = self._adapter.list_data_links(entity_set=entity_set)
        if not data_links:
            return LinkEvidenceResult(
                entity=entity,
                warnings=[f"No DataLink found for entity set '{entity_set}'."],
            )

        data_sets = {item.get("key", ""): item for item in self._adapter.list_data_sets()}
        for data_link in data_links:
            data_set_key = data_link.get("dest", "")
            data_set = data_sets.get(data_set_key)
            if not data_set:
                warnings.append(f"DataLink '{data_link.get('key', '')}' targets unknown data set '{data_set_key}'.")
                continue

            mapping = _DATA_SET_TO_REPOSITORY.get(data_set.get("kind", ""))
            if not mapping:
                warnings.append(
                    f"Data set '{data_set_key}' has unsupported kind '{data_set.get('kind', '')}' for evidence resolution."
                )
                continue
            evidence_type, repository = mapping
            if evidence_type not in evidence_types:
                evidence_types.append(evidence_type)

            storage_links = self._adapter.list_storage_links(data_set=data_set_key)
            if not storage_links:
                warnings.append(f"No StorageLink found for data set '{data_set_key}'.")
                continue

            for storage_link in storage_links:
                query_hints.append(self._build_query_hint(
                    repository=repository,
                    evidence_type=evidence_type,
                    data_set_key=data_set_key,
                    data_link=data_link,
                    storage_link=storage_link,
                ))

        return LinkEvidenceResult(
            entity=entity,
            evidence_types=sorted(evidence_types, key=lambda item: _EVIDENCE_ORDER[item]),
            query_hints=sorted(query_hints, key=lambda item: _EVIDENCE_ORDER[item.evidence_type]),
            warnings=warnings,
        )

    def _build_query_hint(
        self,
        *,
        repository: str,
        evidence_type: Literal["metric", "log", "trace"],
        data_set_key: str,
        data_link: dict[str, Any],
        storage_link: dict[str, Any],
    ) -> EvidenceQueryHint:
        return EvidenceQueryHint(
            repository=repository,  # type: ignore[arg-type]
            evidence_type=evidence_type,
            data_set=data_set_key,
            storage=storage_link.get("dest", ""),
            storage_ref=storage_link.get("dest_ref", {}),
            field_mapping={
                "data_link": data_link.get("fields_mapping", {}),
                "storage_link": storage_link.get("fields_mapping", {}),
            },
            data_filter=data_link.get("data_filter", ""),
            filter_by_entity=storage_link.get("filter_by_entity", ""),
            source="umodel_yaml",
            data_link=data_link.get("key", ""),
            storage_link=storage_link.get("key", ""),
        )

    @staticmethod
    def _entity_set_key(entity: EntityReference) -> str:
        if entity.domain and not entity.entity_type.startswith(f"{entity.domain}."):
            return f"{entity.domain}.{entity.entity_type}"
        return entity.entity_type


SemanticLinkResolver = LinkEvidenceResolver
