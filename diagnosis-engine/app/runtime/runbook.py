from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, Field


class RunbookEvidenceRef(BaseModel):
    key: str
    evidence_type: str = "runtime"
    description: str = ""


class RunbookSkillBinding(BaseModel):
    skill_name: str
    tool_name: str = ""


class RunbookStep(BaseModel):
    id: str
    title: str
    observation: str
    conclusion: str
    evidence: list[RunbookEvidenceRef] = Field(default_factory=list)
    skill_binding: RunbookSkillBinding

    def metadata(self) -> dict[str, Any]:
        return {
            "runbook_step_id": self.id,
            "runbook_step_title": self.title,
            "observation": self.observation,
            "conclusion": self.conclusion,
            "evidence": [item.model_dump() for item in self.evidence],
            "skill_binding": self.skill_binding.model_dump(),
        }


class RunbookDefinition(BaseModel):
    id: str
    name: str
    version: str = "p9-default"
    description: str = ""
    steps: list[RunbookStep] = Field(default_factory=list)

    def skill_names(self) -> list[str]:
        return [step.skill_binding.skill_name for step in self.steps]

    def validate_skill_bindings(self, available_skill_names: Iterable[str]) -> list[str]:
        available = set(available_skill_names)
        return [
            f"Runbook step {step.id} binds unknown skill {step.skill_binding.skill_name}"
            for step in self.steps
            if step.skill_binding.skill_name not in available
        ]

    def step_for_skill(self, skill_name: str) -> RunbookStep | None:
        for step in self.steps:
            if step.skill_binding.skill_name == skill_name:
                return step
        return None


def default_service_exception_runbook() -> RunbookDefinition:
    return RunbookDefinition(
        id="default_service_exception_diagnosis",
        name="Default Service Exception Diagnosis",
        description="Generic service exception diagnosis protocol for the default MModel skill chain.",
        steps=[
            RunbookStep(
                id="observe_alert_context",
                title="告警上下文构建",
                observation="Parse the alert API, time, symptom, and query window.",
                conclusion="A normalized diagnosis context is available for downstream observations.",
                evidence=[_evidence("alert_context", "context", "Normalized alert and time-window context.")],
                skill_binding=RunbookSkillBinding(skill_name="AlertContextSkill", tool_name="MModelSkill/set_time_range"),
            ),
            RunbookStep(
                id="observe_trace_chain",
                title="调用链分析",
                observation="Inspect trace spans and identify abnormal call-chain nodes.",
                conclusion="Trace evidence identifies candidate abnormal services and APIs.",
                evidence=[_evidence("trace.call_chain", "trace"), _evidence("trace.error_spans", "trace")],
                skill_binding=RunbookSkillBinding(skill_name="TraceAnalysisSkill", tool_name="MModelSkill/analyze_trace"),
            ),
            RunbookStep(
                id="bind_runtime_entities",
                title="实体绑定",
                observation="Bind observed service, instance, interface, and business objects to the runtime model.",
                conclusion="Observed telemetry fields are mapped to semantic runtime entities and relationships.",
                evidence=[_evidence("entity.bindings", "semantic"), _evidence("ontology.binding_rules", "semantic")],
                skill_binding=RunbookSkillBinding(skill_name="EntityBindingSkill", tool_name="MModelSkill/bind_entities"),
            ),
            RunbookStep(
                id="observe_error_logs",
                title="日志分析",
                observation="Inspect error logs around the alert window and candidate services.",
                conclusion="Log evidence confirms or rejects exception semantics and propagation.",
                evidence=[_evidence("log.error_events", "log"), _evidence("log.root_candidates", "log")],
                skill_binding=RunbookSkillBinding(skill_name="LogAnalysisSkill", tool_name="MModelSkill/analyze_log"),
            ),
            RunbookStep(
                id="observe_red_metrics",
                title="指标检查",
                observation="Inspect RED metrics for service-level error, rate, and duration anomalies.",
                conclusion="Metric evidence confirms resource or traffic symptoms, or rules them out.",
                evidence=[_evidence("metric.red", "metric"), _evidence("metric.root_candidates", "metric")],
                skill_binding=RunbookSkillBinding(skill_name="MetricCheckSkill", tool_name="MModelSkill/check_metrics"),
            ),
            RunbookStep(
                id="observe_runtime_topology",
                title="关系图查询",
                observation="Inspect one-hop service and interface topology around the candidate entity.",
                conclusion="Topology evidence explains upstream/downstream propagation and impact paths.",
                evidence=[_evidence("topology.call_graph", "topology"), _evidence("topology.impact_paths", "topology")],
                skill_binding=RunbookSkillBinding(skill_name="GraphAnalysisSkill", tool_name="MModelSkill/query_graph"),
            ),
            RunbookStep(
                id="conclude_root_cause",
                title="根因定位",
                observation="Synthesize trace, log, metric, and topology observations into root-cause candidates.",
                conclusion="A root-cause conclusion or candidate is produced with supporting evidence.",
                evidence=[_evidence("root_cause.candidates", "conclusion"), _evidence("root_cause.scoring", "conclusion")],
                skill_binding=RunbookSkillBinding(skill_name="RootCauseSkill", tool_name="MModelSkill/locate_root_cause"),
            ),
            RunbookStep(
                id="conclude_business_impact",
                title="影响面分析",
                observation="Inspect affected services, APIs, business capabilities, and evidence references.",
                conclusion="Business and upstream/downstream impact scope is summarized.",
                evidence=[_evidence("impact.affected_services", "impact"), _evidence("impact.evidence_links", "impact")],
                skill_binding=RunbookSkillBinding(skill_name="ImpactAnalysisSkill", tool_name="MModelSkill/analyze_impact"),
            ),
            RunbookStep(
                id="conclude_diagnosis_report",
                title="诊断报告生成",
                observation="Render the structured observations, conclusions, and evidence chain into a report.",
                conclusion="A human-readable diagnosis report is generated from structured results.",
                evidence=[_evidence("report.structured_context", "report"), _evidence("report.evidence_chain", "report")],
                skill_binding=RunbookSkillBinding(skill_name="ReportSkill", tool_name="MModelSkill/generate_report"),
            ),
        ],
    )


def runbook_skill_sequence(runbook: RunbookDefinition, skills: Iterable[Any]) -> list[tuple[RunbookStep, Any]]:
    by_name = {getattr(skill, "skill_name", ""): skill for skill in skills}
    missing = [
        (step.id, step.skill_binding.skill_name)
        for step in runbook.steps
        if step.skill_binding.skill_name not in by_name
    ]
    if missing:
        details = ", ".join(f"{step_id}:{skill_name}" for step_id, skill_name in missing)
        raise ValueError(f"Runbook skill binding resolution failed: {details}")
    return [(step, by_name[step.skill_binding.skill_name]) for step in runbook.steps]


def attach_runbook_metadata(result: Any, step: RunbookStep) -> Any:
    metadata = step.metadata()
    current_input = dict(getattr(result, "input", {}) or {})
    current_input.setdefault("runbook", metadata)
    result.input = current_input
    return result


def _evidence(key: str, evidence_type: str, description: str = "") -> RunbookEvidenceRef:
    return RunbookEvidenceRef(key=key, evidence_type=evidence_type, description=description)
