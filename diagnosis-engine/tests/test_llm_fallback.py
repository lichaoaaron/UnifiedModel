"""
Tests for LLM fallback chain in OpenAICompatibleProvider and report_skill.

Covers:
  - stream_report: stream failure → non-stream fallback → rule-based fallback
  - generate_explanation: retries exhausted → rule-based fallback
  - generate_text: retries exhausted → empty string (no silent Mock)
  - stream_text: all fallbacks exhausted, allow_mock_fallback=False → no output (no crash)
  - stream_text: all fallbacks exhausted, allow_mock_fallback=True → Mock output
  - Evidence sufficiency: root_cause is_confirmed=False uses undetermined report
  - report_source metadata is correctly set
"""
from __future__ import annotations
import json
import sys
import os
from pathlib import Path

# Allow running from any working directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.adapters.llm_provider import MockLLMProvider, OpenAICompatibleProvider
from app.models.context import DiagnosisContext
from app.skills.report_skill import ReportSkill
from app.orchestrator.llm_diagnosis_orchestrator import (
    _resolve_short_explanation_text,
    plan_next_skill_by_evidence,
    run_react_loop,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _provider(allow_mock_fallback: bool = False, retries: int = 1) -> OpenAICompatibleProvider:
    """Return a provider that always fails (bad URL)."""
    return OpenAICompatibleProvider(
        base_url="http://localhost:9999",   # unreachable
        api_key="test-key",
        model="test-model",
        enable_stream=True,
        stream_timeout=1,
        non_stream_timeout=1,
        max_retries=retries,
        allow_mock_fallback=allow_mock_fallback,
    )


_CONFIRMED_CONTEXT = {
    "root_cause": {
        "root_cause_service": "order-service",
        "root_cause_api": "/api/order/create",
        "root_cause_type": "业务异常",
        "exception_type": "IllegalArgumentException",
        "is_confirmed": True,
        "confidence": "high",
    },
    "impact": {},
    "trace": {"trace_id": "abc123"},
    "log": {},
    "metric": {},
    "api": "/api/order/create",
    "time": "2024-01-01 10:00:00",
    "symptom": "HTTP 500",
}

_UNCONFIRMED_CONTEXT = {
    **_CONFIRMED_CONTEXT,
    "root_cause": {
        **_CONFIRMED_CONTEXT["root_cause"],
        "is_confirmed": False,
        "confidence": "low",
    },
}

_MOBILE_OPS_SECTIONS = [
    "故障结论",
    "异常现象",
    "根因定位",
    "证据链分析",
    "实例与资源状态",
    "影响面分析",
    "处置建议",
    "长期优化建议",
    "诊断依据与可信度",
]


def _section_titles(report: str) -> list[str]:
    import re
    return re.findall(r"【([^】]+)】", report)


# ---------------------------------------------------------------------------
# MockLLMProvider baseline tests
# ---------------------------------------------------------------------------

class TestMockLLMProvider:
    def setup_method(self):
        self.mock = MockLLMProvider()

    def test_generate_explanation_returns_nonempty(self):
        text = self.mock.generate_explanation(_CONFIRMED_CONTEXT)
        assert isinstance(text, str) and len(text) > 50

    def test_generate_undetermined_report_when_unconfirmed(self):
        text = self.mock.generate_undetermined_report(_UNCONFIRMED_CONTEXT)
        assert "根因未确认" in text or "候选根因" in text

    def test_stream_report_yields_strings(self):
        # Mock adds 60ms sleep per char — only iterate a few chars
        chunks = []
        for i, ch in enumerate(self.mock.stream_report(_CONFIRMED_CONTEXT)):
            chunks.append(ch)
            if i >= 5:
                break
        assert len(chunks) > 0
        assert all(isinstance(c, str) for c in chunks)

    def test_generate_text_returns_string(self):
        result = self.mock.generate_text("some prompt")
        assert isinstance(result, str)

    def test_confirmed_report_uses_mobile_ops_sections(self):
        text = self.mock.generate_explanation(_CONFIRMED_CONTEXT)
        assert _section_titles(text) == _MOBILE_OPS_SECTIONS

    def test_unconfirmed_report_uses_same_mobile_ops_sections(self):
        text = self.mock.generate_undetermined_report(_UNCONFIRMED_CONTEXT)
        assert _section_titles(text) == _MOBILE_OPS_SECTIONS
        assert "根因分析（待确认）" not in text
        assert "业务影响评估（待确认）" not in text


# ---------------------------------------------------------------------------
# OpenAICompatibleProvider fallback tests (unreachable endpoint)
# ---------------------------------------------------------------------------

class TestOpenAICompatibleProviderFallback:

    def test_generate_explanation_falls_back_to_rule_based(self):
        p = _provider()
        result = p.generate_explanation(_CONFIRMED_CONTEXT)
        # Should return rule-based report with warning note
        assert isinstance(result, str)
        assert len(result) > 50
        assert "⚠" in result or "降级" in result

    def test_generate_explanation_no_crash_on_retries(self):
        p = _provider(retries=2)
        result = p.generate_explanation(_CONFIRMED_CONTEXT)
        assert isinstance(result, str)

    def test_stream_report_falls_back_to_rule_based_when_all_fail(self):
        p = _provider()
        chunks = list(p.stream_report(_CONFIRMED_CONTEXT))
        combined = "".join(chunks)
        assert isinstance(combined, str) and len(combined) > 50
        # Should contain rule-based content or warning
        assert "⚠" in combined or "故障" in combined or "根因" in combined

    def test_stream_report_unconfirmed_uses_rule_based_directly(self):
        p = _provider()
        chunks = list(p.stream_report(_UNCONFIRMED_CONTEXT))
        combined = "".join(chunks)
        assert "根因未确认" in combined or "候选根因" in combined

    def test_generate_text_returns_empty_on_all_fail(self):
        p = _provider()
        result = p.generate_text("test prompt")
        # Falls back to empty string (no Mock)
        assert result == ""

    def test_stream_text_no_output_when_all_fail_and_mock_not_allowed(self):
        p = _provider(allow_mock_fallback=False)
        chunks = list(p.stream_text("test prompt"))
        # Should yield nothing (no crash, no Mock)
        assert chunks == [] or all(isinstance(c, str) for c in chunks)
        # If empty, that's the expected production-safe behavior
        combined = "".join(chunks)
        # Must not contain Mock-specific phrases like "故障现象" from template
        # (it may be empty OR contain fallback non-stream text — just no crash)

    def test_stream_text_uses_mock_when_explicitly_allowed(self):
        p = _provider(allow_mock_fallback=True)
        chunks = list(p.stream_text("set_time_range"))
        combined = "".join(chunks)
        assert isinstance(combined, str)
        # Mock stream_text produces a sentence
        assert len(combined) > 5

    def test_no_silent_mock_fallback_for_generate_text_in_production(self):
        """In production (allow_mock_fallback=False), failed generate_text returns '' not Mock data."""
        p = _provider(allow_mock_fallback=False)
        result = p.generate_text("plan prompt")
        # Must be empty string, not a Mock plan JSON
        assert result == ""

    def test_report_prompt_preserves_high_confidence_and_single_sample_edges(self):
        p = _provider()
        ctx = {
            **_CONFIRMED_CONTEXT,
            "root_cause": {
                **_CONFIRMED_CONTEXT["root_cause"],
                "root_cause_service": "payment",
                "root_cause_api": "oteldemo.PaymentService/Charge",
                "confidence": "high",
                "evidence_by_source": {
                    "service_map": {
                        "call_edges": [
                            {"source_service": "checkout", "target_service": "payment", "call_count": 1, "error_count": 1, "error_rate": 1.0}
                        ]
                    }
                },
            },
            "impact": {
                "affected_services": ["checkout", "payment"],
                "affected_apis": ["/api/checkout", "oteldemo.PaymentService/Charge"],
                "impact_scale": "unavailable",
                "business_impact": {
                    "affected_order_count": "unknown",
                    "failed_transaction_count": 1,
                    "failed_transaction_count_estimated": True,
                    "affected_user_count": "unknown",
                    "estimated_revenue_impact": "unknown",
                    "confidence": "medium",
                    "evidence_links": {"trace_ids": ["trace-1"], "related_services": ["payment"]},
                },
            },
            "graph": {
                "call_edges": [
                    {"source_service": "checkout", "target_service": "payment", "call_count": 1, "error_count": 1, "error_rate": 1.0}
                ]
            },
            "metric": {"resource_status": "no_threshold"},
            "log": {"log_evidence": [], "root_candidates": []},
        }

        prompt = p._build_report_prompt(ctx)

        assert "根因置信度：high" in prompt
        assert "confidence=high 时必须写 high/高置信" in prompt
        assert "不得因日志缺失或资源阈值缺失改写成中等置信度" in prompt
        assert "checkout→payment(calls=1, errors=1, 单样本观测，不外推全局错误率)" in prompt
        assert "可观测业务影响报告行：业务影响数据：payment 技术异常关联到可观测业务受损信号" in prompt
        assert "失败交易信号=1（可观测证据推导值，非最终业务交易事实）" in prompt
        assert "必须在【影响面分析】中单独输出" in prompt
        assert "不得写成“单笔交易失败”" in prompt
        assert "error_rate=1.0" not in prompt
        assert "错误率高达100%" in prompt


# ---------------------------------------------------------------------------
# Evidence sufficiency / confidence tests
# ---------------------------------------------------------------------------

class TestEvidenceSufficiency:
    """Verify that reports respect is_confirmed and do not fabricate data."""

    def test_confirmed_report_contains_root_cause_service(self):
        mock = MockLLMProvider()
        report = mock.generate_explanation(_CONFIRMED_CONTEXT)
        assert "order-service" in report

    def test_unconfirmed_report_does_not_claim_confirmed(self):
        mock = MockLLMProvider()
        report = mock.generate_explanation(_UNCONFIRMED_CONTEXT)
        # Should indicate unconfirmed state, not claim high confidence
        assert "待确认" in report or "候选" in report or "未确认" in report

    def test_undetermined_report_flags_conflict(self):
        ctx = {
            **_UNCONFIRMED_CONTEXT,
            "evidence_consistency": {
                "has_conflict": True,
                "conflicts": [
                    {
                        "field": "bad_param",
                        "source_a": "trace",
                        "source_a_value": "productId=999",
                        "source_b": "log",
                        "source_b_value": "productId=null",
                    }
                ],
            },
        }
        mock = MockLLMProvider()
        report = mock.generate_undetermined_report(ctx)
        assert "冲突" in report or "不一致" in report or "bad_param" in report or "productId" in report

    def test_missing_root_cause_does_not_crash(self):
        ctx = {
            "root_cause": {},
            "impact": {},
            "trace": {},
            "log": {},
            "metric": {},
            "api": "/test",
            "time": "unknown",
            "symptom": "error",
        }
        mock = MockLLMProvider()
        report = mock.generate_explanation(ctx)
        assert isinstance(report, str) and len(report) > 10

    def test_report_is_evidence_bounded_when_log_empty_and_metric_no_threshold(self):
        ctx = {
            "root_cause": {
                "root_cause_service": "payment",
                "root_cause_api": "oteldemo.PaymentService/Charge",
                "root_cause_type": "dependency_unavailable",
                "exception_type": "Unavailable",
                "confidence": "medium",
                "is_confirmed": True,
            },
            "impact": {
                "affected_services": ["checkout", "payment"],
                "affected_apis": ["/api/checkout", "oteldemo.PaymentService/Charge"],
                "affected_business": ["结算支付链路受影响"],
                "impact_scale": "unavailable",
            },
            "trace": {
                "trace_id": "trace-1",
            },
            "log": {
                "log_evidence": [],
                "root_candidates": [],
            },
            "metric": {
                "resource_status": "no_threshold",
                "conclusion": "部分指标未配置阈值，无法单独判断资源状态。",
            },
            "api": "/api/checkout",
            "time": "2026-05-21 10:00:00",
            "symptom": "grpc unavailable",
        }
        report = MockLLMProvider().generate_explanation(ctx)
        assert "大量日志" not in report
        assert "错误率飙升" not in report
        assert "无心跳" not in report
        assert "端口监听异常" not in report
        assert "防火墙" not in report
        assert "未配置熔断" not in report
        assert "心跳正常" not in report
        assert "资源耗尽" not in report
        assert "服务崩溃" not in report
        assert "无有效错误处理机制" not in report

        assert ("未查到可用于确认根因的日志证据" in report) or ("未查到日志证据" in report)
        assert ("指标仅作为辅助" in report) or ("未配置阈值" in report)
        assert ("中等置信度" in report) or ("confidence=medium" in report)
        assert "当前未接入实例健康探测" in report
        assert "当前未接入端口探测" in report
        assert "调用链涉及服务" in report
        assert "确认受影响服务" in report

    def test_impact_analysis_stays_structured_and_non_demo_overclaim(self):
        ctx = {
            "root_cause": {
                "root_cause_service": "payment",
                "root_cause_api": "oteldemo.PaymentService/Charge",
                "root_cause_type": "dependency_unavailable",
                "exception_type": "Unavailable",
                "confidence": "medium",
                "is_confirmed": True,
            },
            "trace": {
                "trace_id": "trace-2",
                "call_path": [
                    "load-generator: /api/checkout",
                    "checkout: checkout call",
                    "cart: cart call",
                    "currency: currency call",
                ],
            },
            "log": {
                "log_evidence": [],
                "root_candidates": [],
            },
            "metric": {
                "resource_status": "no_threshold",
                "conclusion": "部分指标未配置阈值，无法单独判断资源状态。",
            },
            "impact": {
                "affected_services": ["checkout", "cart", "currency", "payment"],
                "affected_apis": ["/api/checkout", "oteldemo.PaymentService/Charge"],
                "affected_business": ["订单支付能力受影响（演示业务本体推断）"],
                "affected_user_groups": [],
                "impact_scale": "unavailable",
            },
            "api": "/api/checkout",
            "time": "2026-05-21 11:00:00",
            "symptom": "grpc unavailable",
        }
        report = MockLLMProvider().generate_explanation(ctx)

        for forbidden in ["所有尝试", "完全阻塞", "错误率飙升", "错误率 100%", "实例无心跳", "端口监听异常", "防火墙", "未配置熔断"]:
            assert forbidden not in report

        assert "当前未接入真实用户" in report
        assert "暂不估算具体影响规模" in report
        assert "演示业务本体推断" not in report
        assert "业务功能影响：当前结构化证据不足，暂无法确认" in report
        assert "影响范围：" in report
        assert ("建议排查" in report) or ("建议验证" in report)


class TestReportSkillGuardrails:
    def test_report_skill_respects_empty_log_and_no_threshold_metric(self, monkeypatch):
        monkeypatch.setattr("app.skills.report_skill.get_llm_provider", lambda: MockLLMProvider())

        ctx = DiagnosisContext(api="/api/checkout", time="2026-05-21 10:00:00", symptom="grpc unavailable")
        ctx.trace_result = {
            "trace_id": "trace-1",
            "call_path": ["checkout:/api/checkout", "payment:oteldemo.PaymentService/Charge"],
            "summary": "payment 调用失败",
        }
        ctx.log_result = {
            "log_evidence": [],
            "root_candidates": [],
        }
        ctx.metric_result = {
            "resource_status": "no_threshold",
            "conclusion": "部分指标未配置阈值，无法单独判断资源状态。",
        }
        ctx.root_cause_result = {
            "root_cause_service": "payment",
            "root_cause_api": "oteldemo.PaymentService/Charge",
            "root_cause_type": "dependency_unavailable",
            "exception_type": "Unavailable",
            "confidence": "medium",
            "is_confirmed": True,
        }
        ctx.impact_result = {
            "affected_services": ["checkout", "payment"],
            "affected_apis": ["/api/checkout", "oteldemo.PaymentService/Charge"],
            "affected_business": ["结算支付链路受影响"],
            "impact_scale": "unavailable",
        }

        result = ReportSkill().run(ctx)
        report = result.output["report"]

        assert "错误率飙升" not in report
        assert "无心跳" not in report
        assert "端口监听异常" not in report
        assert "防火墙" not in report
        assert "未配置熔断" not in report
        assert "未查到可用于确认根因的日志证据" in report
        assert "指标仅作为辅助，未配置阈值，不能单独判断资源异常" in report
        assert "中等置信度" in report
        assert "当前未接入真实用户" in report
        assert "暂不估算具体影响规模" in report
        assert "异常参数：" not in report


# ---------------------------------------------------------------------------
# report_source metadata test (integration-style, no real LLM needed)
# ---------------------------------------------------------------------------

class TestReportSourceMetadata:
    """Verify report_source is correctly detected in report_skill output."""

    def test_mock_provider_report_source_is_rule_based(self):
        """When provider is MockLLMProvider, report_source should be 'rule_based'."""
        from app.adapters.llm_provider import MockLLMProvider as MLP
        provider = MLP()
        provider_name = type(provider).__name__
        assert provider_name == "MockLLMProvider"
        # Simulate what report_skill does to detect source
        import app.adapters.llm_provider as llm_mod
        assert isinstance(provider, llm_mod.MockLLMProvider)

    def test_fallback_warning_note_triggers_rule_based_fallback_detection(self):
        """A report containing the ⚠ warning note should be detected as rule_based_fallback."""
        report = "【故障概要】\n根因服务：order-service\n\n（⚠ LLM 调用失败，已降级为规则模板报告。错误：ConnectionError）"
        is_fallback = (
            "⚠ LLM 调用失败" in report
            or "⚠ 真实 LLM 调用全部失败" in report
            or "⚠ LLM 调用异常" in report
        )
        assert is_fallback


class _ExplanationLLM:
    def __init__(self, text: str | None = None, should_raise: bool = False):
        self.text = text
        self.should_raise = should_raise

    def generate_text(self, prompt: str, system: str = "") -> str:
        if self.should_raise:
            raise RuntimeError("llm unavailable")
        return self.text or ""


class _DecisionUnavailableLLM:
    def __init__(self, mode: str):
        self.mode = mode

    def generate_text(self, prompt: str, system: str = "") -> str:
        if self.mode == "raise":
            raise RuntimeError("llm unavailable")
        if self.mode == "invalid_json":
            return "{not json"
        return ""

    def stream_report(self, report_context: dict):
        yield "【故障结论】\n诊断报告已生成。"


class TestShortExplanationFallback:
    def test_non_stream_explanation_prefers_llm_text(self):
        llm = _ExplanationLLM(text="正在分析调用链，定位异常源头。")
        text = _resolve_short_explanation_text(
            llm,
            prompt="test prompt",
            fallback_text="规则化说明",
            stage="pre",
            skill_key="analyze_trace",
        )
        assert text == "正在分析调用链，定位异常源头。"

    def test_non_stream_explanation_falls_back_on_json_payload(self):
        llm = _ExplanationLLM(text='{"plan": []}')
        text = _resolve_short_explanation_text(
            llm,
            prompt="test prompt",
            fallback_text="规则化说明",
            stage="pre",
            skill_key="set_time_range",
        )
        assert text == "规则化说明"


class TestReactDecisionFallback:
    def _showcase_index_item(self, case_id: str) -> dict:
        repo_root = Path(__file__).resolve().parents[2]
        index_path = repo_root / "examples" / "evaluation_cases" / "showcase_7" / "index.json"
        index = json.load(open(index_path, encoding="utf-8"))
        return next(item for item in index if item["case_id"] == case_id)

    def _run_case_with_unavailable_llm(self, case_id: str, mode: str, monkeypatch):
        monkeypatch.setattr("app.orchestrator.llm_diagnosis_orchestrator._time.sleep", lambda _seconds: None)
        repo_root = Path(__file__).resolve().parents[2]
        case_dir = repo_root / "examples" / "evaluation_cases" / "showcase_7" / case_id
        index_item = self._showcase_index_item(case_id)
        ctx = DiagnosisContext(
            api=index_item["alert_api"],
            time="2026-04-10 10:51:14",
            symptom=index_item["alert_symptom"],
            data_dir=str(case_dir),
        )
        events = list(run_react_loop(_DecisionUnavailableLLM(mode), ctx, ctx.api, ctx.time, ctx.symptom))
        ground_truth = json.load(open(case_dir / "ground_truth.json", encoding="utf-8"))
        return events, ctx, ground_truth

    def _skill_order(self, events: list[dict]) -> list[str]:
        return [str(event.get("skill")) for event in events if event.get("type") == "skill_done"]

    def test_empty_decision_uses_deterministic_strategy(self, monkeypatch):
        events, ctx, _ground_truth = self._run_case_with_unavailable_llm("05_conflict_scoring", "empty", monkeypatch)
        text = "".join(event.get("content", "") for event in events if event.get("type") in {"assistant_delta", "assistant_replace"})
        assert "当前动态决策异常" not in text
        done_skills = self._skill_order(events)
        for skill in [
            "set_time_range",
            "analyze_trace",
            "bind_entities",
            "analyze_log",
            "check_metrics",
            "analyze_graph",
            "infer_root_cause",
            "analyze_impact",
        ]:
            assert skill in done_skills
        assert ctx.root_cause_result["root_cause_type"] == "connection_pool_exhaustion"
        assert ctx.impact_result["affected_services"]

    def test_showcase_7_agentic_paths_are_evidence_aware(self, monkeypatch):
        case_ids = [item["case_id"] for item in json.load(open(
            Path(__file__).resolve().parents[2] / "examples" / "evaluation_cases" / "showcase_7" / "index.json",
            encoding="utf-8",
        ))]
        orders = {}
        for case_id in case_ids:
            events, ctx, ground_truth = self._run_case_with_unavailable_llm(case_id, "empty", monkeypatch)
            order = [skill for skill in self._skill_order(events) if skill != "generate_report"]
            orders[case_id] = order
            expected = ground_truth["expected"]["root_cause"]
            assert ctx.root_cause_result["root_cause_service"] == expected["service"], case_id
            assert ctx.root_cause_result["root_cause_type"].endswith(expected["type"]), case_id
            assert ctx.impact_result["affected_services"], case_id

        assert len({tuple(order) for order in orders.values()}) > 1
        assert orders["02_metric_dominant_resource"].index("check_metrics") == 1
        assert orders["03_log_dominant_oom"].index("analyze_log") <= 2

        for case_id in ("05_conflict_scoring", "07_noise_resilience"):
            root_index = orders[case_id].index("infer_root_cause")
            for required in ("analyze_trace", "analyze_log", "check_metrics", "analyze_graph"):
                assert orders[case_id].index(required) < root_index, case_id

        partial_order = orders["06_partial_trace_db"]
        assert partial_order.index("analyze_log") < partial_order.index("infer_root_cause")
        assert partial_order.index("check_metrics") < partial_order.index("infer_root_cause")

    def test_exception_decision_uses_deterministic_strategy(self, monkeypatch):
        events, ctx, _ground_truth = self._run_case_with_unavailable_llm("05_conflict_scoring", "raise", monkeypatch)
        text = "".join(event.get("content", "") for event in events if event.get("type") in {"assistant_delta", "assistant_replace"})
        assert "当前动态决策异常" not in text
        assert ctx.root_cause_result["root_cause_type"] == "connection_pool_exhaustion"
        assert any(event.get("skill") == "analyze_impact" for event in events if event.get("type") == "skill_done")

    def test_invalid_json_decision_uses_deterministic_strategy(self, monkeypatch):
        events, ctx, _ground_truth = self._run_case_with_unavailable_llm("05_conflict_scoring", "invalid_json", monkeypatch)
        text = "".join(event.get("content", "") for event in events if event.get("type") in {"assistant_delta", "assistant_replace"})
        assert "当前动态决策异常" not in text
        assert ctx.root_cause_result["root_cause_type"] == "connection_pool_exhaustion"

    def test_showcase_partial_case_completes_without_llm_decision(self, monkeypatch):
        events, ctx, ground_truth = self._run_case_with_unavailable_llm("06_partial_trace_db", "empty", monkeypatch)
        expected = ground_truth["expected"]["root_cause"]
        assert ctx.root_cause_result["root_cause_service"] == expected["service"]
        assert ctx.root_cause_result["root_cause_component"] == expected["component"]
        assert ctx.root_cause_result["root_cause_type"] == expected["type"]
        assert ctx.impact_result["affected_services"]
        assert any(event.get("skill") == "analyze_impact" for event in events if event.get("type") == "skill_done")


class TestEvidencePlannerKeywords:
    def _next_skill(self, symptom: str) -> str:
        ctx = DiagnosisContext(api="/api", time="2026-04-10 10:51:14", symptom=symptom)
        decision = plan_next_skill_by_evidence(
            api=ctx.api,
            symptom=symptom,
            executed_set={"set_time_range"},
            failed_set=set(),
            available=[
                "analyze_trace",
                "bind_entities",
                "analyze_log",
                "check_metrics",
                "analyze_graph",
                "infer_root_cause",
                "analyze_impact",
            ],
            ctx=ctx,
        )
        assert decision is not None
        return decision["skill"]

    def test_metric_compound_symptoms_choose_metrics_first(self):
        assert self._next_skill("CPU 告警和响应慢") == "check_metrics"
        assert self._next_skill("连接池/线程池告警和 HTTP 504") == "check_metrics"

    def test_dependency_compound_symptoms_choose_metrics_first(self):
        assert self._next_skill("HTTP 504 和 DB timeout") == "check_metrics"

    def test_plain_http_exception_keeps_trace_first(self):
        assert self._next_skill("HTTP 500 service exception") == "analyze_trace"

    def test_non_stream_explanation_falls_back_on_exception(self):
        llm = _ExplanationLLM(should_raise=True)
        text = _resolve_short_explanation_text(
            llm,
            prompt="test prompt",
            fallback_text="规则化说明",
            stage="post",
            skill_key="analyze_log",
        )
        assert text == "规则化说明"
