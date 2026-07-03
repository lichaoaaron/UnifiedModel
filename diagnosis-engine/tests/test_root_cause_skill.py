import os
import sys

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
_BACKEND = os.path.join(_REPO_ROOT, "backend")
for _path in (_REPO_ROOT, _BACKEND):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from app.models.context import DiagnosisContext
from app.skills.root_cause_skill import RootCauseSkill


def _make_candidate(*, source: str, service: str, api: str, score: float, exception_type: str, evidence: str) -> dict:
    return {
        "source": source,
        "service": service,
        "component": service,
        "api": api,
        "type": "service_exception",
        "exception_type": exception_type,
        "score": score,
        "evidence": evidence,
        "is_propagation": False,
    }


def test_prefers_log_candidate_when_trace_exception_is_generic_and_scores_tie():
    ctx = DiagnosisContext(api="/api/checkout", time="2026-05-21T02:06:50Z", symptom="payment failure")
    ctx.trace_result = {
        "first_error_service": "frontend",
        "first_error_api": "POST /api/checkout",
        "first_error_exception": "HTTPError",
        "root_candidates": [
            _make_candidate(
                source="trace",
                service="frontend",
                api="POST /api/checkout",
                score=0.55,
                exception_type="HTTPError",
                evidence="duration=38ms status=500",
            ),
            _make_candidate(
                source="trace",
                service="frontend",
                api="POST /api/checkout",
                score=0.55,
                exception_type="HTTPError",
                evidence="duration=19ms status=500",
            ),
        ],
        "abnormal_spans": [],
    }
    ctx.log_result = {
        "upstream_service": "payment",
        "upstream_error_type": "UnknownException",
        "root_candidates": [
            _make_candidate(
                source="log",
                service="payment",
                api="/api/checkout",
                score=0.65,
                exception_type="UnknownException",
                evidence="Payment request failed. Invalid token.",
            ),
            _make_candidate(
                source="log",
                service="payment",
                api="/api/checkout",
                score=0.65,
                exception_type="UnknownException",
                evidence="Payment request failed. Invalid token.",
            ),
        ],
        "log_evidence": [],
    }

    RootCauseSkill().run(ctx)

    assert ctx.root_cause_result["root_cause_service"] == "payment"
    assert ctx.root_cause_result["root_cause_api"] == "/api/checkout"


def test_keeps_trace_candidate_when_trace_exception_is_specific():
    ctx = DiagnosisContext(api="/api/checkout", time="2026-05-21T02:06:50Z", symptom="payment failure")
    ctx.trace_result = {
        "first_error_service": "frontend",
        "first_error_api": "POST /api/checkout",
        "first_error_exception": "ValueError",
        "root_candidates": [
            _make_candidate(
                source="trace",
                service="frontend",
                api="POST /api/checkout",
                score=0.55,
                exception_type="ValueError",
                evidence="ValueError: invalid input",
            ),
            _make_candidate(
                source="trace",
                service="frontend",
                api="POST /api/checkout",
                score=0.55,
                exception_type="ValueError",
                evidence="ValueError: invalid input",
            ),
        ],
        "abnormal_spans": [],
    }
    ctx.log_result = {
        "upstream_service": "payment",
        "upstream_error_type": "UnknownException",
        "root_candidates": [
            _make_candidate(
                source="log",
                service="payment",
                api="/api/checkout",
                score=0.65,
                exception_type="UnknownException",
                evidence="Payment request failed. Invalid token.",
            ),
            _make_candidate(
                source="log",
                service="payment",
                api="/api/checkout",
                score=0.65,
                exception_type="UnknownException",
                evidence="Payment request failed. Invalid token.",
            ),
        ],
        "log_evidence": [],
    }

    RootCauseSkill().run(ctx)

    assert ctx.root_cause_result["root_cause_service"] == "frontend"
    assert ctx.root_cause_result["root_cause_api"] == "POST /api/checkout"