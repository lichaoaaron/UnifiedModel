"""Resolver for trace span input in the DCC-first pipeline.

Priority:
  1. DCC evidence.trace.items — if availability == "available" and items non-empty.
  2. Legacy adapter / repository / case loader — fallback for all other cases.

Produces a TraceInputResolution so that TraceAnalysisSkill can decide its data
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
class TraceInputResolution:
    """Resolved trace input ready for Trace Skill consumption.

    Attributes
    ----------
    spans:
        Span records to analyse.  Non-empty only when skipped_adapter=True.
    topology_seed:
        DCC topology nodes/edges for optional enrichment (may be empty).
    entity_seed:
        DCC entity list for optional enrichment (may be empty).
    data_source_label:
        Human-readable label recorded in SkillResult.input.
    warnings:
        Non-fatal warnings about data availability or quality.
    skipped_adapter:
        True  → use ``spans`` directly; caller must NOT call adapter.get_traces().
        False → ``spans`` is empty; caller must fall back to adapter/case loader.
    """

    spans: list[dict[str, Any]] = field(default_factory=list)
    topology_seed: dict[str, Any] = field(default_factory=dict)
    entity_seed: list[dict[str, Any]] = field(default_factory=list)
    data_source_label: str = "adapter"
    warnings: list[str] = field(default_factory=list)
    skipped_adapter: bool = False


def resolve_trace_input(ctx: "DiagnosisContext") -> TraceInputResolution:
    """Resolve trace spans for the current DiagnosisContext using DCC-first priority.

    1. If ``ctx.dcc_context`` has ``evidence.trace.availability == "available"``
       and ``items`` is a non-empty list → return those spans, ``skipped_adapter=True``.
    2. If DCC is present but trace availability is empty / insufficient / unavailable →
       emit a warning and return ``skipped_adapter=False`` so the caller falls back.
    3. If no DCC → return ``skipped_adapter=False`` unconditionally.

    In all cases, topology and entity seeds from DCC are extracted and returned
    as hints (the caller may use them regardless of which span source is chosen).
    """
    dcc = (
        ctx.dcc_context
        if isinstance(getattr(ctx, "dcc_context", None), dict) and ctx.dcc_context
        else None
    )

    if dcc is None:
        return TraceInputResolution(data_source_label="adapter")

    # ── Extract topology / entity seed regardless of trace availability ──────
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

    # ── Inspect the trace evidence bucket ────────────────────────────────────
    evidence = dcc.get("evidence") or {}
    trace_bucket = evidence.get("trace")

    if not isinstance(trace_bucket, dict):
        warnings.append(
            "[TraceInputResolver] DCC present but evidence.trace bucket is missing "
            "or malformed; falling back to adapter/case loader"
        )
        return TraceInputResolution(
            topology_seed=topology_seed,
            entity_seed=entity_seed,
            data_source_label="adapter",
            warnings=warnings,
            skipped_adapter=False,
        )

    availability: str = trace_bucket.get("availability") or "unavailable"
    raw_items = trace_bucket.get("items")
    items: list[dict[str, Any]] = (
        [i for i in raw_items if isinstance(i, dict)]
        if isinstance(raw_items, list)
        else []
    )

    # Forward any warnings already declared inside the DCC bucket.
    dcc_bucket_warnings = trace_bucket.get("warnings") or []
    if isinstance(dcc_bucket_warnings, list):
        warnings.extend(str(w) for w in dcc_bucket_warnings if w)

    # ── DCC-first: spans available and non-empty ──────────────────────────────
    if availability == "available" and items:
        logger.info(
            "[TraceInputResolver] DCC-first: using DCC evidence.trace.items "
            "(n=%d), skipping adapter",
            len(items),
        )
        return TraceInputResolution(
            spans=items,
            topology_seed=topology_seed,
            entity_seed=entity_seed,
            data_source_label="dcc:evidence.trace.items",
            warnings=warnings,
            skipped_adapter=True,
        )

    # ── Fallback: DCC present but trace data not usable ───────────────────────
    if availability == "available" and not items:
        warnings.append(
            "[TraceInputResolver] DCC trace availability=available but items=[] "
            "(empty); falling back to adapter/case loader"
        )
    elif availability == "insufficient":
        warnings.append(
            f"[TraceInputResolver] DCC trace availability={availability!r}: "
            "items present but marked insufficient; falling back to adapter/case loader"
        )
    else:
        warnings.append(
            f"[TraceInputResolver] DCC trace availability={availability!r}: "
            "no usable trace data in DCC; falling back to adapter/case loader"
        )

    return TraceInputResolution(
        topology_seed=topology_seed,
        entity_seed=entity_seed,
        data_source_label="adapter",
        warnings=warnings,
        skipped_adapter=False,
    )
