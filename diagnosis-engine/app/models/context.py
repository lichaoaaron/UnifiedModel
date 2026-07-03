"""
DiagnosisContext: shared state passed between skills.
Each skill reads from and writes to this context.
"""
from typing import Any


class DiagnosisContext:
    def __init__(self, api: str, time: str, symptom: str, case_id: str | None = None, data_dir: str | None = None):
        # Input
        self.api = api
        self.time = time
        self.symptom = symptom
        self.case_id = case_id
        self.data_dir = data_dir

        # Populated by skills
        self.query_context: dict[str, Any] = {}
        self.scenario_metadata: dict[str, Any] = {}  # set by EntityBindingSkill for unifiedmodel source
        self.trace_result: dict[str, Any] = {}
        self.entity_result: dict[str, Any] = {}
        self.log_result: dict[str, Any] = {}
        self.metric_result: dict[str, Any] = {}
        self.graph_result: dict[str, Any] = {}
        self.root_cause_result: dict[str, Any] = {}
        self.impact_result: dict[str, Any] = {}
        self.report_result: dict[str, Any] = {}
        # Populated by orchestrator session memory before Skill execution.
        self.resolved_context: dict[str, Any] = {}
        # Optional incoming Diagnosis Context Contract payload.
        self.dcc_context: dict[str, Any] = {}
        # Populated by orchestrator error-handling — never by skills directly
        self.failed_skills: list[dict] = []
        # Populated by RootCauseSkill evidence consistency check
        self.evidence_consistency: dict[str, Any] = {}
