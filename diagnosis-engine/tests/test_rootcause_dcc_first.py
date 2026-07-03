"""
Tests for Step 7: RootCause DCC-first (object-centered) candidate resolution.

Coverage:
  - RootCauseInputResolution resolver: all four priority paths
  - RootCauseSkill.run(): DCC candidates used / supplemented / fallback
  - Explainability fields in root_cause_result_dict
  - Legacy evidence-based path unbroken when no DCC
"""
import pytest
from unittest.mock import patch

from app.models.context import DiagnosisContext
from app.runtime.root_cause_input_resolver import (
    RootCauseInputResolution,
    resolve_root_cause_input,
    _normalize_dcc_candidate,
    _infer_candidates_from_topology,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_ctx(**kwargs) -> DiagnosisContext:
    ctx = DiagnosisContext(
        api=kwargs.get("api", "/api/checkout"),
        symptom=kwargs.get("symptom", "checkout timeout"),
        time="2024-01-01T10:00:00Z",
    )
    ctx.dcc_context = kwargs.get("dcc_context", {})
    ctx.trace_result = kwargs.get("trace_result", {})
    ctx.log_result = kwargs.get("log_result", {})
    ctx.metric_result = kwargs.get("metric_result", {})
    ctx.graph_result = kwargs.get("graph_result", {})
    return ctx


def _full_dcc(extra: dict | None = None) -> dict:
    """Minimal valid DCC v0.1 payload (can be extended via extra)."""
    base = {
        "protocol_version": "dcc-v0.1",
        "generated_at": "2024-01-01T10:00:00Z",
        "workspace": "demo",
        "alert": {
            "id": "alert-001",
            "symptom": "checkout timeout",
            "api": "/api/checkout",
            "alert_time": "2024-01-01T10:00:00Z",
            "severity": "critical",
        },
        "objects": {
            "entities": [],
            "relations": [],
            "topology": {},
        },
        "evidence": {
            "trace": {"availability": "none", "spans": []},
            "log": {"availability": "none", "records": []},
            "metric": {"availability": "none", "series": []},
        },
        "candidates": {
            "root_cause": [],
            "impact_scope": [],
        },
        "provenance": [],
        "meta": {},
    }
    if extra:
        for k, v in extra.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                base[k].update(v)
            else:
                base[k] = v
    return base


# ---------------------------------------------------------------------------
# Unit tests: _normalize_dcc_candidate
# ---------------------------------------------------------------------------

class TestNormalizeDccCandidate:
    def test_uses_service_field(self):
        item = {"service": "payment-svc", "confidence": 0.9, "type": "service_exception"}
        result = _normalize_dcc_candidate(item, "/checkout")
        assert result["service"] == "payment-svc"
        assert result["score"] == 0.9
        assert result["_candidate_origin"] == "dcc_candidates"

    def test_falls_back_to_entity_name(self):
        item = {"entity_name": "order-svc", "entity_id": "eid-01"}
        result = _normalize_dcc_candidate(item, "/api/order")
        assert result["service"] == "order-svc"

    def test_falls_back_to_entity_id(self):
        item = {"entity_id": "eid-checkout"}
        result = _normalize_dcc_candidate(item, "")
        assert result["service"] == "eid-checkout"

    def test_bare_entity_type_remapped(self):
        item = {"service": "svc-x", "type": "service"}
        result = _normalize_dcc_candidate(item, "")
        assert result["type"] == "service_exception"

    def test_score_capped_at_0_99(self):
        item = {"service": "svc", "confidence": 1.5}
        result = _normalize_dcc_candidate(item, "")
        assert result["score"] == 0.99

    def test_default_score_when_absent(self):
        item = {"service": "svc"}
        result = _normalize_dcc_candidate(item, "")
        assert result["score"] == 0.85


# ---------------------------------------------------------------------------
# Unit tests: _infer_candidates_from_topology
# ---------------------------------------------------------------------------

class TestInferCandidatesFromTopology:
    def test_entry_points(self):
        topology = {"entry_points": [{"id": "frontend-svc"}, {"id": "payment-svc"}]}
        result = _infer_candidates_from_topology(topology, "/pay")
        services = [c["service"] for c in result]
        assert "frontend-svc" in services
        assert "payment-svc" in services
        assert all(c["_candidate_origin"] == "topology_inferred" for c in result)

    def test_candidate_paths_terminal_node_string(self):
        topology = {"candidate_paths": [{"nodes": ["frontend", "order", "payment"]}]}
        result = _infer_candidates_from_topology(topology, "")
        assert any(c["service"] == "payment" for c in result)

    def test_candidate_paths_terminal_node_dict(self):
        topology = {"candidate_paths": [{"nodes": [{"id": "alpha"}, {"id": "beta"}]}]}
        result = _infer_candidates_from_topology(topology, "")
        assert any(c["service"] == "beta" for c in result)

    def test_no_duplicates_between_entry_points_and_paths(self):
        topology = {
            "entry_points": [{"id": "svc-x"}],
            "candidate_paths": [{"nodes": ["svc-a", "svc-x"]}],
        }
        result = _infer_candidates_from_topology(topology, "")
        assert len([c for c in result if c["service"] == "svc-x"]) == 1

    def test_empty_topology_returns_empty(self):
        assert _infer_candidates_from_topology({}, "") == []


# ---------------------------------------------------------------------------
# Unit tests: resolve_root_cause_input
# ---------------------------------------------------------------------------

class TestResolveRootCauseInput:
    def test_priority1_dcc_candidates(self):
        dcc = _full_dcc(
            extra={
                "candidates": {
                    "root_cause": [
                        {"service": "payment-svc", "confidence": 0.88, "type": "service_exception"},
                    ],
                    "impact_scope": [],
                }
            }
        )
        ctx = _make_ctx(dcc_context=dcc)
        res = resolve_root_cause_input(ctx)
        assert res.candidate_source == "dcc_candidates"
        assert res.dcc_used is True
        assert len(res.candidates) == 1
        assert res.candidates[0]["service"] == "payment-svc"
        assert res.candidates[0]["_candidate_origin"] == "dcc_candidates"

    def test_priority1_multiple_dcc_candidates(self):
        dcc = _full_dcc(
            extra={
                "candidates": {
                    "root_cause": [
                        {"service": "svc-a", "confidence": 0.9},
                        {"entity_name": "svc-b", "confidence": 0.75},
                    ],
                    "impact_scope": [],
                }
            }
        )
        ctx = _make_ctx(dcc_context=dcc)
        res = resolve_root_cause_input(ctx)
        assert res.candidate_source == "dcc_candidates"
        assert len(res.candidates) == 2

    def test_priority2_topology_inferred(self):
        dcc = _full_dcc(
            extra={
                "objects": {
                    "entities": [],
                    "relations": [],
                    "topology": {
                        "nodes": [],
                        "edges": [],
                        "entry_points": [{"id": "order-svc"}],
                        "candidate_paths": [],
                    },
                }
            }
        )
        ctx = _make_ctx(dcc_context=dcc)
        res = resolve_root_cause_input(ctx)
        assert res.candidate_source == "topology_inferred"
        assert res.dcc_used is True
        assert len(res.candidates) >= 1
        assert res.candidates[0]["_candidate_origin"] == "topology_inferred"

    def test_priority3_dcc_context_no_candidates_no_topo(self):
        dcc = _full_dcc(
            extra={
                "objects": {
                    "entities": [{"id": "svc-x", "type": "service"}],
                    "relations": [],
                    "topology": {},
                }
            }
        )
        ctx = _make_ctx(dcc_context=dcc)
        res = resolve_root_cause_input(ctx)
        assert res.candidate_source == "evidence_based_with_dcc_context"
        assert res.dcc_used is True
        assert res.candidates == []
        assert len(res.entity_context) == 1

    def test_priority4_no_dcc(self):
        ctx = _make_ctx(dcc_context={})
        res = resolve_root_cause_input(ctx)
        assert res.candidate_source == "evidence_based"
        assert res.dcc_used is False
        assert res.candidates == []

    def test_no_dcc_context_attribute(self):
        ctx = DiagnosisContext(api="/a", symptom="s", time="2024-01-01T00:00:00Z")
        # Don't set dcc_context at all
        res = resolve_root_cause_input(ctx)
        assert res.candidate_source == "evidence_based"
        assert res.dcc_used is False

    def test_entry_entity_set_from_alert_api(self):
        dcc = _full_dcc(
            extra={
                "candidates": {
                    "root_cause": [{"service": "svc-x"}],
                    "impact_scope": [],
                }
            }
        )
        ctx = _make_ctx(dcc_context=dcc)
        res = resolve_root_cause_input(ctx)
        assert res.entry_entity == "/api/checkout"

    def test_warning_when_dcc_candidates_unnormalizable(self):
        dcc = _full_dcc(
            extra={
                "candidates": {
                    "root_cause": [{"no_service_field": "nothing"}],
                    "impact_scope": [],
                }
            }
        )
        ctx = _make_ctx(dcc_context=dcc)
        res = resolve_root_cause_input(ctx)
        # Should fall through to topology_inferred or evidence_based
        assert any("normalizable" in w for w in res.warnings)
        assert res.candidate_source in {"topology_inferred", "evidence_based_with_dcc_context", "evidence_based"}


# ---------------------------------------------------------------------------
# Integration tests: RootCauseSkill with DCC candidates
# ---------------------------------------------------------------------------

import app.skills.root_cause_skill as _rskill_module


def _run_skill(ctx: DiagnosisContext, monkeypatch) -> dict:
    """Run RootCauseSkill with yaml rules and evidence_consistency mocked."""
    monkeypatch.setattr(_rskill_module, "run_yaml_rules", lambda t, l: None)
    import app.skills.evidence_consistency as _ev
    monkeypatch.setattr(_ev, "check_evidence_consistency", lambda **kw: {"has_conflict": False, "conflicts": []})
    monkeypatch.setattr(_ev, "apply_confidence_cap", lambda conf, cons: conf)
    from app.skills.root_cause_skill import RootCauseSkill
    skill = RootCauseSkill()
    result = skill.run(ctx)
    return result


class TestRootCauseSkillDCCFirst:
    def test_skill_uses_dcc_candidates(self, monkeypatch):
        dcc = _full_dcc(
            extra={
                "candidates": {
                    "root_cause": [
                        {"service": "payment-svc", "confidence": 0.92, "type": "service_exception"},
                    ],
                    "impact_scope": [],
                }
            }
        )
        ctx = _make_ctx(dcc_context=dcc)
        result = _run_skill(ctx, monkeypatch)

        assert result.status == "success"
        out = result.output
        assert out["root_cause_service"] == "payment-svc"
        assert out["dcc_candidates_used"] is True
        assert out["candidate_source"] == "dcc_candidates"
        assert out["object_centered_mode"] is True

    def test_skill_supplements_dcc_with_evidence_candidates(self, monkeypatch):
        dcc = _full_dcc(
            extra={
                "candidates": {
                    "root_cause": [{"service": "payment-svc", "confidence": 0.88}],
                    "impact_scope": [],
                }
            }
        )
        # Add a different service from trace evidence
        ctx = _make_ctx(dcc_context=dcc)
        ctx.trace_result = {
            "root_candidates": [
                {"service": "order-svc", "score": 0.5, "type": "service_exception", "evidence": "span err"}
            ]
        }
        result = _run_skill(ctx, monkeypatch)
        # Both services should appear in candidates list
        candidate_services = [c["service"] for c in result.output.get("candidates", [])]
        assert "payment-svc" in candidate_services
        assert "order-svc" in candidate_services

    def test_skill_does_not_add_duplicate_services(self, monkeypatch):
        dcc = _full_dcc(
            extra={
                "candidates": {
                    "root_cause": [{"service": "payment-svc", "confidence": 0.88}],
                    "impact_scope": [],
                }
            }
        )
        ctx = _make_ctx(dcc_context=dcc)
        # Same service also appears in trace_result
        ctx.trace_result = {
            "root_candidates": [
                {"service": "payment-svc", "score": 0.7, "type": "service_exception", "evidence": "span err"}
            ]
        }
        result = _run_skill(ctx, monkeypatch)
        # payment-svc should not appear twice (DCC takes priority, trace is supplementary only for non-DCC services)
        payment_candidates = [
            c for c in result.output.get("candidates", []) if c["service"] == "payment-svc"
        ]
        assert len(payment_candidates) == 1

    def test_skill_input_includes_candidate_source_and_count(self, monkeypatch):
        dcc = _full_dcc(
            extra={
                "candidates": {
                    "root_cause": [
                        {"service": "svc-x", "confidence": 0.85},
                        {"service": "svc-y", "confidence": 0.75},
                    ],
                    "impact_scope": [],
                }
            }
        )
        ctx = _make_ctx(dcc_context=dcc)
        result = _run_skill(ctx, monkeypatch)

        assert result.input["candidate_source"] == "dcc_candidates"
        assert result.input["dcc_candidates_count"] == 2

    def test_skill_execution_log_contains_dcc_object_centered(self, monkeypatch):
        dcc = _full_dcc(
            extra={
                "candidates": {
                    "root_cause": [{"service": "svc-z", "confidence": 0.8}],
                    "impact_scope": [],
                }
            }
        )
        ctx = _make_ctx(dcc_context=dcc)
        result = _run_skill(ctx, monkeypatch)

        log_text = " ".join(result.execution_log)
        assert "DCC-object-centered" in log_text

    def test_skill_explanation_mentions_object_centered_when_dcc(self, monkeypatch):
        dcc = _full_dcc(
            extra={
                "candidates": {
                    "root_cause": [{"service": "svc-p", "confidence": 0.87}],
                    "impact_scope": [],
                }
            }
        )
        ctx = _make_ctx(dcc_context=dcc)
        result = _run_skill(ctx, monkeypatch)
        assert "object-centered" in result.explanation

    def test_skill_topology_inferred_path(self, monkeypatch):
        dcc = _full_dcc(
            extra={
                "objects": {
                    "entities": [],
                    "relations": [],
                    "topology": {
                        "nodes": [],
                        "edges": [],
                        "entry_points": [{"id": "payment-svc"}],
                        "candidate_paths": [],
                    },
                }
            }
        )
        ctx = _make_ctx(dcc_context=dcc)
        result = _run_skill(ctx, monkeypatch)

        assert result.output["candidate_source"] == "topology_inferred"
        assert result.output["dcc_candidates_used"] is True
        assert result.output["object_centered_mode"] is True

    def test_skill_legacy_path_unbroken_no_dcc(self, monkeypatch):
        ctx = _make_ctx(dcc_context={})
        ctx.trace_result = {
            "root_candidates": [
                {"service": "order-svc", "score": 0.65, "type": "service_exception", "evidence": "trace err"}
            ],
            "first_error_service": "order-svc",
        }
        result = _run_skill(ctx, monkeypatch)

        assert result.status == "success"
        assert result.output["root_cause_service"] == "order-svc"
        assert result.output["dcc_candidates_used"] is False
        assert result.output["candidate_source"] in {"evidence_based", "legacy_evidence_based"}
        assert "object-centered" not in result.explanation

    def test_skill_result_has_entry_entity_and_mode_fields(self, monkeypatch):
        dcc = _full_dcc(
            extra={
                "candidates": {
                    "root_cause": [{"service": "svc-a", "confidence": 0.9}],
                    "impact_scope": [],
                }
            }
        )
        ctx = _make_ctx(dcc_context=dcc)
        result = _run_skill(ctx, monkeypatch)

        out = result.output
        assert "candidate_source" in out
        assert "dcc_candidates_used" in out
        assert "entry_entity" in out
        assert "object_centered_mode" in out

    def test_evidence_list_shows_candidate_source(self, monkeypatch):
        dcc = _full_dcc(
            extra={
                "candidates": {
                    "root_cause": [{"service": "svc-b", "confidence": 0.82}],
                    "impact_scope": [],
                }
            }
        )
        ctx = _make_ctx(dcc_context=dcc)
        result = _run_skill(ctx, monkeypatch)
        evidence_text = " ".join(result.evidence)
        assert "dcc_candidates" in evidence_text

    def test_full_dcc_trace_log_metric_pipeline(self, monkeypatch):
        """Full pipeline: DCC with candidates + trace/log/metric evidence."""
        dcc = _full_dcc(
            extra={
                "candidates": {
                    "root_cause": [
                        {"service": "payment-svc", "confidence": 0.91, "type": "service_exception"},
                    ],
                    "impact_scope": [],
                },
                "evidence": {
                    "trace": {"availability": "full", "spans": [{"service": "payment-svc", "error": True}]},
                    "log": {"availability": "full", "records": [{"service": "payment-svc", "level": "ERROR"}]},
                    "metric": {"availability": "full", "series": []},
                },
            }
        )
        ctx = _make_ctx(dcc_context=dcc)
        ctx.trace_result = {
            "root_candidates": [
                {"service": "payment-svc", "score": 0.8, "type": "service_exception", "evidence": "span error"}
            ],
            "first_error_service": "payment-svc",
        }
        ctx.log_result = {
            "root_candidates": [
                {"service": "payment-svc", "score": 0.7, "type": "service_exception", "evidence": "log error"}
            ]
        }
        result = _run_skill(ctx, monkeypatch)

        assert result.status == "success"
        assert result.output["root_cause_service"] == "payment-svc"
        assert result.output["candidate_source"] == "dcc_candidates"
        assert result.output["object_centered_mode"] is True
        assert result.input["dcc_candidates_count"] == 1
