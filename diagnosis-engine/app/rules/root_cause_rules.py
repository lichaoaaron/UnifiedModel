"""
Root cause rules: YAML-driven rule engine.
Rules are loaded from backend/data/rules/root_cause_rules.yaml at import time.
No exception class names are hardcoded here — all patterns come from the YAML file.

Rule matching logic (per rule):
  1. If downstream_exception_patterns is non-empty, at least one pattern must be
     a case-insensitive substring of trace.first_error_exception.
  2. If propagation_patterns is non-empty, at least one pattern must be a
     case-insensitive substring of log.upstream_error_type.
  3. A rule with empty downstream_exception_patterns matches any exception (fallback).

Public API (unchanged):
  ROOT_CAUSE_RULES — list of callable rule functions (for backward compat with RootCauseSkill)
  run_yaml_rules(trace_result, log_result) -> Optional[dict]
"""
from __future__ import annotations

import logging
import os
import yaml
from typing import Optional

logger = logging.getLogger(__name__)

_RULES_FILE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "rules", "root_cause_rules.yaml")
)


def _load_yaml_rules() -> list[dict]:
    """Load rule definitions from YAML. Returns empty list on error."""
    try:
        with open(_RULES_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        rules = data.get("rules", [])
        # Sort by priority ascending; filter enabled
        enabled = [r for r in rules if r.get("enabled", True)]
        enabled.sort(key=lambda r: r.get("priority", 99))
        logger.debug("[RootCauseRules] Loaded %d enabled rules from %s", len(enabled), _RULES_FILE)
        return enabled
    except Exception as exc:
        logger.error("[RootCauseRules] Failed to load %s: %s", _RULES_FILE, exc)
        return []


def _match_any(text: str, patterns: list[str]) -> bool:
    """Return True if any pattern is a case-insensitive substring of text."""
    if not patterns:
        return False
    text_lower = text.lower()
    return any(p.lower() in text_lower for p in patterns)


def run_yaml_rules(trace_result: dict, log_result: dict) -> Optional[dict]:
    """
    Evaluate YAML rules against trace/log evidence.
    Returns a result dict on first match, or None if no rule matches.
    """
    downstream_exc = trace_result.get("first_error_exception") or ""
    upstream_err = log_result.get("upstream_error_type") or ""
    trace_bad_param = trace_result.get("extracted_bad_parameter") or trace_result.get("bad_param")
    log_bad_param = (
        log_result.get("extracted_bad_parameter_from_log")
        or log_result.get("error_param")
    )

    rules = _load_yaml_rules()
    for rule in rules:
        cond = rule.get("conditions", {})
        downstream_patterns: list[str] = cond.get("downstream_exception_patterns", [])
        propagation_patterns: list[str] = cond.get("propagation_patterns", [])
        require_same_bad_param = bool(cond.get("bad_parameter_sources_must_agree"))

        # Match downstream exception (empty patterns = fallback, matches anything with any exception)
        if downstream_patterns:
            if not downstream_exc or not _match_any(downstream_exc, downstream_patterns):
                continue
        else:
            # Fallback rule: only fires when there IS a downstream exception
            if not downstream_exc and not trace_result.get("first_error_service"):
                continue

        # Match propagation (optional — only required when list is non-empty)
        if propagation_patterns:
            if not upstream_err or not _match_any(upstream_err, propagation_patterns):
                continue

        if require_same_bad_param:
            if trace_bad_param is None or log_bad_param is None:
                continue
            if str(trace_bad_param) != str(log_bad_param):
                continue

        conclusion = rule.get("conclusion", {})
        root_cause_location = conclusion.get("root_cause_location", "downstream")
        root_cause_api_source = conclusion.get("root_cause_api_source", "first_error_api")

        if root_cause_location == "upstream":
            root_cause_service = log_result.get("upstream_service") or trace_result.get("first_error_service")
        else:
            root_cause_service = trace_result.get("first_error_service")

        if root_cause_api_source == "entry_api":
            root_cause_api = trace_result.get("entry_api") or trace_result.get("first_error_api")
        else:
            root_cause_api = trace_result.get("first_error_api")

        root_cause_type = conclusion.get("root_cause_type", "服务异常")
        confidence = conclusion.get("confidence", "medium")
        affected_reason = conclusion.get("affected_reason", "")

        if root_cause_location == "upstream":
            reason = (
                f"规则 [{rule['id']}] 命中：下游服务出现 {downstream_exc or '异常'}，"
                f"且 trace/log 提取到一致的异常参数 {trace_bad_param}，"
                f"上游服务 {log_result.get('upstream_service') or '（未知）'} 传入了非法参数，根因在上游。"
            )
        else:
            reason = (
                f"规则 [{rule['id']}] 命中：下游服务出现 {downstream_exc or '异常'}，"
                + (f"上游服务存在传播性异常 {upstream_err}，根因在下游。" if upstream_err and propagation_patterns else "")
            )
        if affected_reason:
            reason += f" {affected_reason}"

        return {
            "rule": rule["id"],
            "root_cause_service": root_cause_service,
            "root_cause_api": root_cause_api,
            "root_cause_type": root_cause_type,
            "root_cause_reason": reason,
            "confidence": confidence,
        }

    return None


# ---------------------------------------------------------------------------
# Backward-compatible callable wrappers consumed by RootCauseSkill._run_rule_engine
# ---------------------------------------------------------------------------

def _yaml_rule_fn(trace_result: dict, log_result: dict | None = None) -> Optional[dict]:
    """Single entry point wrapping run_yaml_rules for use in ROOT_CAUSE_RULES list."""
    return run_yaml_rules(trace_result, log_result or {})


# ROOT_CAUSE_RULES: RootCauseSkill iterates this list calling each fn.
# We expose a single YAML-driven function.  The second arg (log_result) is passed
# only when the fn name is "rule_downstream_specific_exception" (legacy check in
# RootCauseSkill._run_rule_engine).  We make our fn accept both signatures.
ROOT_CAUSE_RULES = [_yaml_rule_fn]
