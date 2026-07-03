from pydantic import BaseModel, Field
from typing import Any, List, Optional, Literal


class AlertEvent(BaseModel):
    api: str
    time: str
    symptom: str


class SkillResult(BaseModel):
    skill_name: str
    tool_name: str = ""
    title: str
    status: str                      # pending | running | success | failed
    summary: str
    started_at: str = ""
    finished_at: str = ""
    duration_ms: int = 0
    input: dict[str, Any]
    output: dict[str, Any]
    evidence: List[str]
    execution_log: List[str] = []
    explanation: str


class CallNode(BaseModel):
    id: str
    label: str
    is_root_cause: bool = False
    is_entry: bool = False
    node_type: str = "service"  # "service" | "interface" | "Service" | "Instance" | "Interface" | "Business" | "BusinessFlow"
    is_call_chain: bool = False  # True if this node is part of the diagnosed call chain


class CallEdge(BaseModel):
    source: str
    target: str
    label: str = ""
    is_call_chain: bool = False  # True if this edge is part of the diagnosed call chain


class CallGraph(BaseModel):
    nodes: List[CallNode]
    edges: List[CallEdge]
    trace_summary: str = ""
    log_summary: str = ""
    metric_summary: str = ""


class DiagnosisSummary(BaseModel):
    root_cause_service: str
    root_cause_api: str
    root_cause_type: str
    exception_type: str
    bad_parameter: str
    impact_api: str
    business_impact: List[str]


class DiagnosisMessage(BaseModel):
    role: str                          # "user" | "assistant"
    type: str                          # "text" | "skill_call" | "report" | "call_graph"
    content: Optional[str] = None      # for type=text / report
    skill_name: Optional[str] = None
    tool_name: Optional[str] = None
    status: Optional[str] = None
    summary: Optional[str] = None
    duration_ms: Optional[int] = None
    input: Optional[dict[str, Any]] = None
    output: Optional[dict[str, Any]] = None
    evidence: Optional[List[str]] = None
    execution_log: Optional[List[str]] = None
    explanation: Optional[str] = None
    call_graph: Optional["CallGraph"] = None


class DiagnosisResponse(BaseModel):
    case_id: str
    summary: DiagnosisSummary
    skills: List[SkillResult]
    call_graph: CallGraph
    evidence_chain: List[str]
    final_report: str
    messages: List[DiagnosisMessage] = Field(default_factory=list)
    session_id: str | None = None
    mode: str | None = None
    intent: str = "initial_diagnosis"
    executed_skills: List[str] = Field(default_factory=list)
    answer: str = ""
    evidence_refs: dict = Field(default_factory=dict)
    diagnosis_explain: dict = Field(default_factory=dict)
    current_focus: dict = Field(default_factory=dict)
    resolved_context: dict = Field(default_factory=dict)
    memory_summary: dict = Field(default_factory=dict)
    data_source_status: dict = Field(default_factory=dict)
