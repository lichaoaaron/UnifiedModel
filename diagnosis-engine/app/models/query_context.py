"""
QueryContext: unified optional query parameters for observability retrieval.
Current phase only defines interface boundary for future data sources.
"""
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class QueryContext:
    time_start: str | None = None
    time_end: str | None = None
    api: str | None = None
    service: str | None = None
    instance: str | None = None
    trace_id: str | None = None
    level: str | None = None
    keyword: str | None = None
    limit: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
