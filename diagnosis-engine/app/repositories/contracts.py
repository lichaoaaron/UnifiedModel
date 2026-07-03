"""Repository contracts for observability and business impact data access."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RepositoryResult:
    source: str
    query_context: dict[str, Any] = field(default_factory=dict)
    items: list[dict[str, Any]] = field(default_factory=list)
    availability: str = "available"
    warnings: list[str] = field(default_factory=list)
    raw_refs: list[dict[str, str]] = field(default_factory=list)
    semantic_context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "query_context": self.query_context,
            "items": self.items,
            "availability": self.availability,
            "warnings": self.warnings,
            "raw_refs": self.raw_refs,
            "semantic_context": self.semantic_context,
        }


class TraceRepository(ABC):
    @abstractmethod
    def get_traces(self, query: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        ...

    @abstractmethod
    def get_trace_by_id(self, trace_id: str, query: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        ...

    @abstractmethod
    def get_error_spans(self, service_name: str | None = None, time_range: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        ...

    @abstractmethod
    def get_span_attributes(self, trace_id: str, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        ...


class LogRepository(ABC):
    @abstractmethod
    def get_logs(self, query: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        ...

    @abstractmethod
    def get_error_logs(self, service_name: str | None = None, time_range: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        ...

    @abstractmethod
    def search_logs_by_trace_id(self, trace_id: str, query: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        ...

    @abstractmethod
    def search_logs_by_keyword(self, keyword: str, time_range: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        ...


class MetricRepository(ABC):
    @abstractmethod
    def get_service_rate(self, service_name: str, time_range: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        ...

    @abstractmethod
    def get_service_error_rate(self, service_name: str, time_range: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        ...

    @abstractmethod
    def get_service_duration(self, service_name: str, time_range: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        ...

    @abstractmethod
    def get_red_metrics(self, service_name: str | None = None, time_range: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        ...

    @abstractmethod
    def get_all_services_red_metrics(self, time_range: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        ...

    @abstractmethod
    def get_entity_red_metrics(self, time_range: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        """Entity-centered RED metrics via OpenSearch native aggregations.

        Groups by the otel.service entity key field (resource.attributes.service@name)
        and computes per-entity error_rate, P95/P99 latency, error_count, and
        anomaly_score using server-side aggregations instead of client-side sampling.
        """
        ...


class ServiceMapRepository(ABC):
    @abstractmethod
    def get_service_map(self, time_range: dict[str, Any] | None = None, *, query: dict[str, Any] | None = None, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        ...

    @abstractmethod
    def get_call_edges(self, time_range: dict[str, Any] | None = None, *, query: dict[str, Any] | None = None, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        ...

    @abstractmethod
    def get_upstream_services(self, service_name: str, time_range: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        ...

    @abstractmethod
    def get_downstream_services(self, service_name: str, time_range: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        ...

    @abstractmethod
    def get_impacted_services(self, service_name: str, time_range: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        ...


class BusinessImpactRepository(ABC):
    @abstractmethod
    def get_business_impact(self, service_name: str | None = None, time_range: dict[str, Any] | None = None, *, query: dict[str, Any] | None = None, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        ...

    @abstractmethod
    def get_business_impact_for_services(self, service_names: list[str], time_range: dict[str, Any] | None = None, *, query: dict[str, Any] | None = None, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        ...

    @abstractmethod
    def get_affected_orders(self, service_name: str | None = None, time_range: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        ...

    @abstractmethod
    def get_failed_transactions(self, service_name: str | None = None, time_range: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        ...

    @abstractmethod
    def get_affected_users(self, service_name: str | None = None, time_range: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        ...

    @abstractmethod
    def get_estimated_revenue_impact(self, service_name: str | None = None, time_range: dict[str, Any] | None = None, *, data_dir: str | None = None, case_id: str | None = None) -> RepositoryResult:
        ...
