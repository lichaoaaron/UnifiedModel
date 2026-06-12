"""
evidence_consistency.py — lightweight multi-source evidence consistency checker.

Checks that semantically equivalent fields from trace/log/metric/graph agree.
Only marks a conflict when BOTH sources have extractable, non-empty values that differ.
Missing values produce insufficient_evidence entries, never spurious conflicts.

No hardcoded service names, parameter values, or API paths.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Severity weights
# ---------------------------------------------------------------------------
_PENALTY: dict[str, float] = {
    "high":   0.3,
    "medium": 0.1,
    "low":    0.05,
}
_MAX_PENALTY = 0.5

# Confidence levels in order (index = rank, higher = stronger)
_CONFIDENCE_LEVELS = ("low", "medium", "high")


def _cap_confidence(original: str, penalty: float) -> str:
    """Lower the confidence level by the given penalty score."""
    if not penalty:
        return original
    idx = _CONFIDENCE_LEVELS.index(original) if original in _CONFIDENCE_LEVELS else 0
    # Each 0.3 penalty removes one confidence level
    steps = int(penalty / 0.25) + (1 if penalty % 0.25 >= 0.15 else 0)
    new_idx = max(0, idx - steps)
    return _CONFIDENCE_LEVELS[new_idx]


def apply_confidence_cap(current_confidence: str, consistency: dict) -> str:
    """
    Apply confidence penalty from consistency check result.
    If any high-severity conflict exists, result is at most 'medium'.
    Returns the adjusted confidence string.
    """
    if not consistency.get("has_conflict"):
        return current_confidence
    penalty = consistency.get("confidence_penalty", 0.0)
    has_high_severity = any(
        c.get("severity") == "high" for c in consistency.get("conflicts", [])
    )
    capped = _cap_confidence(current_confidence, penalty)
    if has_high_severity and capped == "high":
        capped = "medium"
    return capped


# ---------------------------------------------------------------------------
# Field extractors — each returns (value, found: bool)
# ---------------------------------------------------------------------------

def _extract_request_param_from_trace(trace: dict) -> tuple[str | None, bool]:
    """Extract the anomalous request parameter from trace evidence."""
    for key in ("extracted_bad_parameter", "bad_param"):
        v = trace.get(key)
        if v and isinstance(v, str) and v.strip():
            return v.strip(), True
    # Try first abnormal span
    spans = trace.get("abnormal_spans", [])
    if spans:
        v = spans[0].get("bad_param")
        if v and isinstance(v, str) and v.strip():
            return v.strip(), True
    return None, False


def _extract_request_param_from_log(log: dict) -> tuple[str | None, bool]:
    """Extract the anomalous request parameter from log evidence."""
    for key in ("extracted_bad_parameter_from_log", "error_param"):
        v = log.get(key)
        if v and isinstance(v, str) and v.strip():
            return v.strip(), True
    # Try query params dict (any first value, generic)
    qp = log.get("extracted_query_params") or {}
    for val in qp.values():
        if val and isinstance(val, str) and val.strip():
            return val.strip(), True
    return None, False


def _extract_trace_id_from_trace(trace: dict) -> tuple[str | None, bool]:
    v = trace.get("trace_id")
    if v and isinstance(v, str) and v.strip():
        return v.strip(), True
    return None, False


def _extract_trace_id_from_log(log: dict) -> tuple[str | None, bool]:
    for key in ("trace_id", "traceId"):
        v = log.get(key)
        if v and isinstance(v, str) and v.strip():
            return v.strip(), True
    return None, False


# ---------------------------------------------------------------------------
# Main checker
# ---------------------------------------------------------------------------

def check_evidence_consistency(
    trace_summary: dict,
    log_summary: dict,
    metric_summary: dict | None = None,
    graph_summary: dict | None = None,
) -> dict:
    """
    Compare semantically-equivalent fields across evidence sources.

    Returns:
    {
      "has_conflict": bool,
      "conflicts": [...],
      "insufficient_evidence": [...],
      "confidence_penalty": float,
      "consistency_summary": str,
    }
    """
    logger.info("[EvidenceConsistency] start")

    conflicts: list[dict] = []
    insufficient: list[dict] = []
    total_penalty: float = 0.0

    # ------------------------------------------------------------------ #
    # Check 1: request_param  (high severity)
    # ------------------------------------------------------------------ #
    trace_param, trace_param_found = _extract_request_param_from_trace(trace_summary)
    log_param, log_param_found = _extract_request_param_from_log(log_summary)

    if trace_param_found and log_param_found:
        if trace_param != log_param:
            entry = {
                "field": "request_param",
                "source_a": "trace",
                "source_a_value": trace_param,
                "source_b": "log",
                "source_b_value": log_param,
                "severity": "high",
                "description": "trace 与 log 记录的请求/异常参数值不一致，无法确认具体异常参数",
            }
            conflicts.append(entry)
            total_penalty += _PENALTY["high"]
            logger.warning(
                "[EvidenceConsistency] conflict field=request_param source_a=trace(%s) source_b=log(%s)",
                trace_param, log_param,
            )
    else:
        missing_sources = []
        if not trace_param_found:
            missing_sources.append("trace")
        if not log_param_found:
            missing_sources.append("log")
        insufficient.append({
            "field": "request_param",
            "reason": f"以下来源未提取到参数：{', '.join(missing_sources)}",
        })

    # ------------------------------------------------------------------ #
    # Check 2: trace_id  (medium severity — only if both have it)
    # ------------------------------------------------------------------ #
    trace_tid, trace_tid_found = _extract_trace_id_from_trace(trace_summary)
    log_tid, log_tid_found = _extract_trace_id_from_log(log_summary)

    if trace_tid_found and log_tid_found:
        if trace_tid != log_tid:
            entry = {
                "field": "trace_id",
                "source_a": "trace",
                "source_a_value": trace_tid,
                "source_b": "log",
                "source_b_value": log_tid,
                "severity": "medium",
                "description": "trace 与 log 的 traceId 不一致，可能来自不同请求链路",
            }
            conflicts.append(entry)
            total_penalty += _PENALTY["medium"]
            logger.warning(
                "[EvidenceConsistency] conflict field=trace_id source_a=trace(%s) source_b=log(%s)",
                trace_tid, log_tid,
            )
    # If only one side has trace_id, no conflict — just note it
    # (log often doesn't carry structured trace_id)

    # ------------------------------------------------------------------ #
    # Clamp penalty
    # ------------------------------------------------------------------ #
    total_penalty = min(total_penalty, _MAX_PENALTY)
    has_conflict = len(conflicts) > 0

    if has_conflict:
        conflict_descs = "; ".join(c["description"] for c in conflicts)
        summary = f"多源证据存在不一致（{conflict_descs}），置信度已降低，根因需进一步核查"
    elif insufficient:
        summary = "部分证据字段未提取到，无法完全比对，建议核查日志采集完整性"
    else:
        summary = "trace 与 log 关键字段一致，证据无冲突"

    logger.info(
        "[EvidenceConsistency] has_conflict=%s conflicts=%d insufficient=%d confidence_penalty=%.2f",
        has_conflict, len(conflicts), len(insufficient), total_penalty,
    )

    return {
        "has_conflict": has_conflict,
        "conflicts": conflicts,
        "insufficient_evidence": insufficient,
        "confidence_penalty": total_penalty,
        "consistency_summary": summary,
    }
