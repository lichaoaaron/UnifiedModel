"""Resolver for log record input in the DCC-first pipeline.

Priority:
  1. DCC evidence.log.items — if availability == "available" and items non-empty.
  2. Legacy / replay adapter path — fallback for all other cases.
     The local_json adapter is a replay path for demo evaluation cases;
     it is NOT the default production path.

Produces a LogInputResolution so that LogAnalysisSkill can decide its data
source without knowing anything about DCC internals.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.models.context import DiagnosisContext

logger = logging.getLogger(__name__)


@dataclass
class LogInputResolution:
    """Resolved log input ready for Log Skill consumption.

    Attributes
    ----------
    logs:
        Log records to analyse.  Non-empty only when skipped_adapter=True.
    topology_seed:
        DCC topology nodes/edges as optional context hint (may be empty).
    entity_seed:
        DCC entity list as optional filtering hint (may be empty).
    data_source_label:
        Human-readable label recorded in SkillResult.input.
    warnings:
        Non-fatal warnings about data availability or quality.
    skipped_adapter:
        True  → use ``logs`` directly; caller must NOT call adapter.get_logs().
        False → ``logs`` is empty; caller must fall back to adapter/case loader.
    """

    logs: list[dict[str, Any]] = field(default_factory=list)
    topology_seed: dict[str, Any] = field(default_factory=dict)
    entity_seed: list[dict[str, Any]] = field(default_factory=list)
    data_source_label: str = "adapter"
    warnings: list[str] = field(default_factory=list)
    skipped_adapter: bool = False


def resolve_log_input(ctx: "DiagnosisContext") -> LogInputResolution:
    """Resolve log records for the current DiagnosisContext using DCC-first priority.

    1. If ``ctx.dcc_context`` has ``evidence.log.availability == "available"``
       and ``items`` is a non-empty list → return those records, ``skipped_adapter=True``.
    2. If DCC is present but log availability is empty / insufficient / unavailable →
       emit a warning and return ``skipped_adapter=False`` so the caller falls back
       to the legacy / replay adapter path.
    3. If no DCC → return ``skipped_adapter=False`` unconditionally.

    In all cases, topology and entity seeds from DCC are extracted and returned
    as hints (the caller may use them regardless of which log source is chosen).
    """
    dcc = (
        ctx.dcc_context
        if isinstance(getattr(ctx, "dcc_context", None), dict) and ctx.dcc_context
        else None
    )

    if dcc is None:
        return LogInputResolution(data_source_label="adapter")

    # ── Extract topology / entity seed regardless of log availability ─────────
    topology_seed: dict[str, Any] = {}
    entity_seed: list[dict[str, Any]] = []
    warnings: list[str] = []

    objects = dcc.get("objects") or {}
    topology = objects.get("topology") or {}
    raw_nodes = topology.get("nodes")
    raw_edges = topology.get("edges")
    if isinstance(raw_nodes, list) or isinstance(raw_edges, list):
        topology_seed = {
            "nodes": raw_nodes if isinstance(raw_nodes, list) else [],
            "edges": raw_edges if isinstance(raw_edges, list) else [],
        }
    raw_entities = objects.get("entities")
    if isinstance(raw_entities, list):
        entity_seed = [e for e in raw_entities if isinstance(e, dict)]

    # ── Inspect the log evidence bucket ──────────────────────────────────────
    evidence = dcc.get("evidence") or {}
    log_bucket = evidence.get("log")

    if not isinstance(log_bucket, dict):
        warnings.append(
            "[LogInputResolver] DCC present but evidence.log bucket is missing "
            "or malformed; falling back to legacy/replay adapter path"
        )
        return LogInputResolution(
            topology_seed=topology_seed,
            entity_seed=entity_seed,
            data_source_label="adapter",
            warnings=warnings,
            skipped_adapter=False,
        )

    availability: str = log_bucket.get("availability") or "unavailable"
    raw_items = log_bucket.get("items")
    items: list[dict[str, Any]] = (
        [i for i in raw_items if isinstance(i, dict)]
        if isinstance(raw_items, list)
        else []
    )

    # Forward any warnings already declared inside the DCC bucket.
    dcc_bucket_warnings = log_bucket.get("warnings") or []
    if isinstance(dcc_bucket_warnings, list):
        warnings.extend(str(w) for w in dcc_bucket_warnings if w)

    # ── DCC-first: log records available and non-empty ────────────────────────
    if availability == "available" and items:
        logger.info(
            "[LogInputResolver] DCC-first: using DCC evidence.log.items "
            "(n=%d), skipping legacy/replay adapter",
            len(items),
        )
        return LogInputResolution(
            logs=items,
            topology_seed=topology_seed,
            entity_seed=entity_seed,
            data_source_label="dcc:evidence.log.items",
            warnings=warnings,
            skipped_adapter=True,
        )

    # ── Fallback: DCC present but log data not usable ─────────────────────────
    if availability == "available" and not items:
        warnings.append(
            "[LogInputResolver] DCC log availability=available but items=[] "
            "(empty); falling back to legacy/replay adapter path"
        )
    elif availability == "insufficient":
        warnings.append(
            f"[LogInputResolver] DCC log availability={availability!r}: "
            "items present but marked insufficient; "
            "falling back to legacy/replay adapter path"
        )
    else:
        warnings.append(
            f"[LogInputResolver] DCC log availability={availability!r}: "
            "no usable log data in DCC; falling back to legacy/replay adapter path"
        )

    return LogInputResolution(
        topology_seed=topology_seed,
        entity_seed=entity_seed,
        data_source_label="adapter",
        warnings=warnings,
        skipped_adapter=False,
    )
