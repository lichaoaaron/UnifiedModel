"""
PRD-aligned Diagnosis API v2.

These endpoints match the contract defined in the MModel Diagnosis PRD
(Section 5.3: Diagnosis API Contract).

  POST /diagnosis/analyze  — full RCA pipeline (delegates to orchestrator)
  POST /diagnosis/impact   — standalone impact propagation from stored context
  POST /diagnosis/report   — standalone report generation from stored context

Original /api/diagnose endpoints remain available for backward compatibility.
"""

import json
import logging
import time as _time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from app.models.context import DiagnosisContext
from app.orchestrator.diagnosis_orchestrator import run_diagnosis
from app.repositories import (
    get_service_map_repository,
    get_trace_repository,
)
from app.session.diagnosis_session import get_session_store
from app.skills.impact_analysis_skill import ImpactAnalysisSkill
from app.skills.report_skill import ReportSkill

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/diagnosis", tags=["diagnosis-v2"])


# ── Request/Response models (PRD-aligned) ──────────────────────────────────


class AnalyzeRequest(BaseModel):
    """PRD Section 5.3: POST /diagnosis/analyze

    entity_id, time_range, and evidence_types match the PRD contract.
    For backward compatibility the legacy fields (api, time, symptom,
    case_id, etc.) are also accepted and forwarded to the orchestrator.
    """
    # PRD fields
    entity_id: str | None = None
    time_range: dict[str, str] | None = None
    evidence_types: list[str] | None = None
    # Legacy / internal fields
    api: str = ""
    time: str = ""
    symptom: str = ""
    case_id: str | None = None
    data_dir: str | None = None
    session_id: str | None = None
    message: str | None = None
    mode: str | None = None
    dcc: dict[str, Any] | None = None


class ImpactRequest(BaseModel):
    """PRD Section 5.3: POST /diagnosis/impact

    Given a diagnosis_id and root_cause_entity, run impact propagation
    against the dependency graph WITHOUT re-running the full pipeline.
    """
    diagnosis_id: str
    root_cause_entity: str


class ReportRequest(BaseModel):
    """PRD Section 5.3: POST /diagnosis/report"""
    diagnosis_id: str


# ── Internal helpers ───────────────────────────────────────────────────────


def _reconstruct_context_from_session(diagnosis_id: str) -> DiagnosisContext | None:
    """Build a DiagnosisContext from stored session data.

    Returns None if the session does not exist or has insufficient data.
    """
    store = get_session_store()
    session = store.get_session(diagnosis_id)
    if session is None:
        logger.warning("[diagnosis_v2] session not found: %s", diagnosis_id)
        return None

    req_ctx = session.request_context or {}
    api = req_ctx.get("api", "")
    time_val = req_ctx.get("time", "")
    symptom = req_ctx.get("symptom", "")

    ctx = DiagnosisContext(
        api=api,
        time=time_val,
        symptom=symptom,
    )
    ctx.resolved_context = req_ctx

    latest = session.latest_skill_outputs or {}

    # ── Reconstruct root_cause_result from session ──────────────────────
    rc = latest.get("root_cause", {})
    if rc:
        ctx.root_cause_result = {
            "root_cause_service": rc.get("root_cause_service", ""),
            "root_cause_api": rc.get("root_cause_api", ""),
            "root_cause_type": rc.get("root_cause_type", ""),
            "confidence": rc.get("confidence", "medium"),
            "evidence_by_source": rc.get("evidence_by_source", {}),
            "is_confirmed": True,
        }

    # ── Reconstruct graph_result from session ───────────────────────────
    sm = latest.get("service_map", {})
    call_edges = sm.get("call_edges", [])
    if call_edges:
        nodes: list[dict[str, Any]] = []
        node_ids: set[str] = set()
        for edge in call_edges:
            src = edge.get("source", "") or edge.get("source_service", "")
            tgt = edge.get("target", "") or edge.get("target_service", "")
            for nid in (src, tgt):
                if nid and nid not in node_ids:
                    node_ids.add(nid)
                    nodes.append({"id": nid, "type": "Service", "label": nid})
        ctx.graph_result = {
            "nodes": nodes,
            "edges": [
                {
                    "source": e.get("source", "") or e.get("source_service", ""),
                    "target": e.get("target", "") or e.get("target_service", ""),
                    "label": "calls",
                }
                for e in call_edges
            ],
            "call_edges": call_edges,
        }

    # ── Reconstruct trace_result from session ───────────────────────────
    trace_info = latest.get("trace", {})
    if trace_info:
        ctx.trace_result = {
            "trace_id": trace_info.get("trace_id", ""),
            "entry_trace_id": trace_info.get("entry_trace_id", ""),
            "service_call": trace_info.get("service_call", ""),
            "root_candidates": trace_info.get("root_candidates", []),
        }

    # ── Reconstruct log_result from session ─────────────────────────────
    log_info = latest.get("log", {})
    if log_info:
        ctx.log_result = {
            "upstream_service": log_info.get("upstream_service"),
            "upstream_error_type": log_info.get("upstream_error_type"),
            "root_candidates": log_info.get("root_candidates", []),
            "log_evidence": log_info.get("log_evidence", []),
        }

    # ── Reconstruct metric_result from session ──────────────────────────
    metric_info = latest.get("metric", {})
    if metric_info:
        ctx.metric_result = {
            "red_metrics": metric_info.get("red_metrics", []),
            "red_anomaly_scores": metric_info.get("red_anomaly_scores", []),
            "conclusion": metric_info.get("conclusion", ""),
        }

    # ── Reconstruct impact_result if previously computed ─────────────────
    bi = session.business_impact_summary or {}
    if bi:
        ctx.impact_result = {
            "impacted_services": session.impacted_services or [],
            "business_impact": bi,
        }

    # ── If graph_result is still empty, try lazy-fetch from adapter ─────
    if not ctx.graph_result.get("edges"):
        try:
            repo = get_service_map_repository()
            sm_result = repo.get_service_map()
            if sm_result.items:
                g = sm_result.items[0]
                nodes = g.get("nodes", [])
                edges = g.get("edges", []) or g.get("call_edges", [])
                ctx.graph_result = {
                    "nodes": nodes,
                    "edges": edges,
                    "call_edges": edges,
                }
        except Exception as exc:
            logger.warning("[diagnosis_v2] lazy-fetch graph_result failed: %s", exc)

    return ctx


# ── Routes ─────────────────────────────────────────────────────────────────


@router.post("/analyze")
def analyze(req: AnalyzeRequest):
    """Root cause analysis — delegates to existing orchestrator.

    Returns the full DiagnosisResponse; the Grafana frontend extracts
    root_cause fields from the DiagnosisSummary.
    """
    result = run_diagnosis(
        api=req.api,
        time=req.time,
        symptom=req.symptom,
        case_id=req.case_id,
        data_dir=req.data_dir,
        session_id=req.session_id or req.entity_id,
        message=req.message,
        mode=req.mode or "diagnosis",
        dcc=req.dcc,
    )
    data = result.model_dump()
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    return Response(content=body, media_type="application/json; charset=utf-8")


@router.post("/impact")
def analyze_impact(req: ImpactRequest):
    """Standalone impact propagation.

    Loads the stored diagnosis context from session, then runs ONLY the
    ImpactAnalysisSkill against the dependency graph.  Does NOT re-run
    the full 9-step pipeline.
    """
    ctx = _reconstruct_context_from_session(req.diagnosis_id)
    if ctx is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": "diagnosis_not_found",
                "message": f"No session found for diagnosis_id={req.diagnosis_id}. "
                           "Run /diagnosis/analyze first.",
            },
        )

    # Override root_cause_service with the caller-specified entity
    if req.root_cause_entity:
        ctx.root_cause_result["root_cause_service"] = req.root_cause_entity
        ctx.root_cause_result["root_cause_api"] = req.root_cause_entity

    # Run ONLY the impact analysis skill
    t0 = _time.monotonic()
    skill = ImpactAnalysisSkill()
    result = skill.run(ctx)
    elapsed_ms = round((_time.monotonic() - t0) * 1000)

    impact = ctx.impact_result or {}

    return JSONResponse(content={
        "diagnosis_id": req.diagnosis_id,
        "root_cause_entity": req.root_cause_entity,
        "affected_services": impact.get("impacted_services", []),
        "business_impact": impact.get("business_impact", {}),
        "topology_highlight": {
            "nodes": (ctx.graph_result or {}).get("nodes", []),
            "edges": (ctx.graph_result or {}).get("edges", []),
        },
        "skill_result": {
            "status": result.status,
            "summary": result.summary,
            "duration_ms": elapsed_ms,
            "evidence": result.evidence,
            "execution_log": result.execution_log,
        },
    })


@router.post("/report")
def generate_report(req: ReportRequest):
    """Standalone report generation.

    Loads the stored diagnosis context from session, then runs ONLY the
    ReportSkill.  Does NOT re-run the full pipeline.
    """
    ctx = _reconstruct_context_from_session(req.diagnosis_id)
    if ctx is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": "diagnosis_not_found",
                "message": f"No session found for diagnosis_id={req.diagnosis_id}. "
                           "Run /diagnosis/analyze first.",
            },
        )

    # Ensure impact is populated if we have business impact in session
    if not ctx.impact_result:
        store = get_session_store()
        session = store.get_session(req.diagnosis_id)
        if session and session.business_impact_summary:
            ctx.impact_result = {
                "impacted_services": session.impacted_services or [],
                "business_impact": session.business_impact_summary,
            }

    # Run ONLY the report skill
    t0 = _time.monotonic()
    skill = ReportSkill()
    result = skill.run(ctx)
    elapsed_ms = round((_time.monotonic() - t0) * 1000)

    report_text = ctx.report_result.get("report", "") if ctx.report_result else ""

    return JSONResponse(content={
        "diagnosis_id": req.diagnosis_id,
        "report_markdown": report_text,
        "summary": {
            "root_cause_service": (ctx.root_cause_result or {}).get("root_cause_service", ""),
            "root_cause_type": (ctx.root_cause_result or {}).get("root_cause_type", ""),
            "confidence": (ctx.root_cause_result or {}).get("confidence", ""),
        },
        "evidence_citations": result.evidence or [],
        "skill_result": {
            "status": result.status,
            "summary": result.summary,
            "duration_ms": elapsed_ms,
        },
    })
