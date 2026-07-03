import os
import sys

import pytest


REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
BACKEND_ROOT = os.path.join(REPO_ROOT, "backend")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)


from app.orchestrator import diagnosis_orchestrator
from app.runtime.runbook import (
    RunbookDefinition,
    RunbookSkillBinding,
    RunbookStep,
    default_service_exception_runbook,
    runbook_skill_sequence,
)


EXPECTED_SKILL_ORDER = [
    "AlertContextSkill",
    "TraceAnalysisSkill",
    "EntityBindingSkill",
    "LogAnalysisSkill",
    "MetricCheckSkill",
    "GraphAnalysisSkill",
    "RootCauseSkill",
    "ImpactAnalysisSkill",
    "ReportSkill",
]


def test_default_runbook_loads_observation_conclusion_evidence_and_skill_binding():
    runbook = default_service_exception_runbook()

    assert runbook.id == "default_service_exception_diagnosis"
    assert len(runbook.steps) == 9
    for step in runbook.steps:
        assert step.observation
        assert step.conclusion
        assert step.evidence
        assert step.skill_binding.skill_name
        assert step.skill_binding.tool_name.startswith("MModelSkill/")


def test_default_runbook_step_order_is_stable():
    runbook = default_service_exception_runbook()

    assert runbook.skill_names() == EXPECTED_SKILL_ORDER
    assert [step.id for step in runbook.steps] == [
        "observe_alert_context",
        "observe_trace_chain",
        "bind_runtime_entities",
        "observe_error_logs",
        "observe_red_metrics",
        "observe_runtime_topology",
        "conclude_root_cause",
        "conclude_business_impact",
        "conclude_diagnosis_report",
    ]


def test_default_runbook_skill_bindings_resolve_existing_skills():
    runbook = default_service_exception_runbook()
    available_skill_names = [skill.skill_name for skill in diagnosis_orchestrator.SKILL_PIPELINE]

    assert runbook.validate_skill_bindings(available_skill_names) == []
    sequence = runbook_skill_sequence(runbook, diagnosis_orchestrator.SKILL_PIPELINE)
    assert len(sequence) == 9
    assert [skill.skill_name for _, skill in sequence] == EXPECTED_SKILL_ORDER


def test_runbook_skill_sequence_raises_for_missing_skill_binding():
    runbook = RunbookDefinition(
        id="unit_missing_binding",
        name="Unit Missing Binding",
        steps=[RunbookStep(
            id="missing_skill_step",
            title="Missing skill step",
            observation="Observe a configured step.",
            conclusion="Missing bindings must fail explicitly.",
            skill_binding=RunbookSkillBinding(skill_name="UnknownSkill", tool_name="MModelSkill/unknown"),
        )],
    )

    with pytest.raises(ValueError) as exc_info:
        runbook_skill_sequence(runbook, diagnosis_orchestrator.SKILL_PIPELINE)

    message = str(exc_info.value)
    assert "missing_skill_step" in message
    assert "UnknownSkill" in message


def test_default_runbook_does_not_embed_ground_truth_or_demo_service_names():
    serialized = default_service_exception_runbook().model_dump_json().lower()

    assert "ground_truth" not in serialized
    assert "xiaozhou" not in serialized
    assert "trace-" not in serialized
    assert "2026-" not in serialized
