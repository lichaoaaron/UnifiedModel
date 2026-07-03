"""
MModel REST API client.

Wraps MModel's Query Service, EntityStore, and UModel APIs behind a typed
Python interface so the diagnosis pipeline can fetch runtime entities,
evidence, and model metadata without reading local files.

Usage:
    from app.adapters.mmodel_rest_client import MModelClient

    client = MModelClient()
    entities = client.query_entities(domain="otel", limit=20)
    traces = client.query_evidence(entity_id="checkout-service",
                                   kind="trace_set",
                                   from_ts="2026-06-01T00:00:00Z",
                                   to_ts="2026-06-01T01:00:00Z")
"""

import logging
import os
from typing import Any
from urllib.parse import urljoin

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_API_URL = "http://localhost:8080"
_DEFAULT_WORKSPACE = "otel-demo"
_DEFAULT_TIMEOUT = 30.0  # seconds


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default).strip()


class MModelClient:
    """Typed HTTP client for MModel REST API."""

    def __init__(
        self,
        api_url: str | None = None,
        workspace: str | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._api_url = (api_url or _env("MMODEL_API_URL", _DEFAULT_API_URL)).rstrip("/")
        self._workspace = workspace or _env("MMODEL_WORKSPACE", _DEFAULT_WORKSPACE)
        self._timeout = timeout
        self._client: httpx.Client | None = None  # lazy init

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=self._timeout,
                headers={"Content-Type": "application/json"},
            )
        return self._client

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = urljoin(self._api_url + "/", path.lstrip("/"))
        logger.debug("[MModelClient] POST %s", url)
        resp = self._http.post(url, json=body)
        resp.raise_for_status()
        return resp.json()

    def _get(self, path: str) -> dict[str, Any]:
        url = urljoin(self._api_url + "/", path.lstrip("/"))
        logger.debug("[MModelClient] GET %s", url)
        resp = self._http.get(url)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Query Service
    # ------------------------------------------------------------------

    def execute_spl(self, spl: str) -> dict[str, Any]:
        """Execute a raw SPL query and return normalized result with 'rows' key.

        The Go service returns one of two envelope shapes:
          - Assistant: {code, data: {data: [[...]], header: [...]}, message, success}
          - Agent:     {columns: [...], rows: [{...}], ...}
        This method normalizes both to a dict with a 'rows' key.
        """
        raw = self._post(
            f"/api/v1/query/{self._workspace}/execute",
            {"query": spl},
        )
        # Agent format (format=agent): already has 'rows'
        if "rows" in raw:
            return raw
        # Assistant format (default): unwrap {data: {data: [...], header: [...]}}
        inner = raw.get("data", {})
        if isinstance(inner, dict):
            array_data = inner.get("data")
            header = inner.get("header", [])
            if isinstance(array_data, list) and isinstance(header, list):
                # Convert [[val, val], ...] into [{col: val}, ...]
                rows: list[dict[str, Any]] = []
                for row in array_data:
                    if isinstance(row, list):
                        rows.append({str(header[i]): v for i, v in enumerate(row) if i < len(header)})
                    elif isinstance(row, dict):
                        rows.append(row)
                return {"rows": rows, "columns": header}
        # Fallback: return raw with rows extracted if possible
        if isinstance(inner, list):
            return {"rows": inner}
        return {"rows": []}

    def query_entities(
        self,
        domain: str | None = None,
        entity_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Query runtime entities via .entity SPL source."""
        parts = [".entity"]
        filters = []
        if domain:
            filters.append(f"domain='{domain}'")
        if entity_type:
            filters.append(f"name='{entity_type}'")
        if filters:
            parts.append(f"with({', '.join(filters)})")
        parts.append(f"| limit {limit}")

        spl = " ".join(parts)
        result = self.execute_spl(spl)
        rows = result.get("rows", [])
        return rows

    def query_evidence(
        self,
        entity_id: str,
        kind: str,  # "log_set" | "trace_set" | "metric_set"
        from_ts: str | None = None,
        to_ts: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query evidence (logs/traces/metrics) for a specific entity via evidence().

        The SPL pipeline: .entity with(__entity_id__=='...') | evidence(kind='...', from='...', to='...') | limit N
        """
        from_clause = f", from='{from_ts}'" if from_ts else ""
        to_clause = f", to='{to_ts}'" if to_ts else ""

        spl = (
            f".entity with(ids=('{entity_id}'))"
            f"| evidence(kind='{kind}'{from_clause}{to_clause})"
            f"| limit {limit}"
        )
        result = self.execute_spl(spl)
        rows = result.get("rows", [])
        return rows

    def query_topo(
        self,
        entity_id: str | None = None,
        limit: int = 100,
        depth: int = 2,
    ) -> list[dict[str, Any]]:
        """Query topology relations via .topo SPL source.

        When entity_id is provided, uses graph-call getNeighborNodes for
        entity-centric topology; otherwise returns the full topology.
        """
        if entity_id:
            # Entity-centric topology: get neighbors up to `depth` hops
            spl = (
                f".topo | graph-call getNeighborNodes('full', {depth}, "
                f"[(:'entity' {{__entity_id__: '{entity_id}'}})])"
                f"| limit {limit}"
            )
        else:
            spl = f".topo | limit {limit}"
        result = self.execute_spl(spl)
        rows = result.get("rows", [])
        return rows

    # ------------------------------------------------------------------
    # UModel (model definitions)
    # ------------------------------------------------------------------

    def list_umodel(
        self,
        kind: str | None = None,  # "entity_set" | "data_link" | etc.
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """List model definitions via .mmodel SPL source."""
        parts = [".mmodel"]
        if kind:
            parts.append(f"with(kind=='{kind}')")
        parts.append(f"| limit {limit}")
        spl = " ".join(parts)
        result = self.execute_spl(spl)
        rows = result.get("rows", [])
        return rows

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def check_connectivity(self) -> dict[str, Any]:
        """Check if MModel API is reachable. Returns dict with status."""
        try:
            self._get("/healthz")
            return {"reachable": True, "api_url": self._api_url, "workspace": self._workspace}
        except Exception as exc:
            return {"reachable": False, "api_url": self._api_url, "error": str(exc)}


# Module-level singleton (lazy)
_mmodel_client: MModelClient | None = None


def get_mmodel_client() -> MModelClient:
    global _mmodel_client
    if _mmodel_client is None:
        _mmodel_client = MModelClient()
    return _mmodel_client
