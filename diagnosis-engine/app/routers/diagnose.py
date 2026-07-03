import json
from typing import Any
from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel
from app.adapters.llm_provider import get_llm_provider
from app.adapters.observability_adapter import get_data_source_status
from app.orchestrator.diagnosis_orchestrator import run_diagnosis, stream_diagnosis
from app.orchestrator.llm_diagnosis_orchestrator import stream_agentic_diagnosis
from app.models.diagnosis import DiagnosisResponse

router = APIRouter()


class DiagnoseRequest(BaseModel):
    api: str = ""
    time: str = ""
    symptom: str = ""
    mode: str | None = None
    case_id: str | None = None
    data_dir: str | None = None
    session_id: str | None = None
    message: str | None = None
    dcc: dict[str, Any] | None = None


class StormReportRequest(BaseModel):
    context: dict[str, Any]


@router.post("/diagnose")
def diagnose(req: DiagnoseRequest) -> Response:
    result: DiagnosisResponse = run_diagnosis(
        api=req.api,
        time=req.time,
        symptom=req.symptom,
        case_id=req.case_id,
        data_dir=req.data_dir,
        session_id=req.session_id,
        message=req.message,
        mode=req.mode,
        dcc=req.dcc,
    )
    data = result.model_dump()
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    return Response(content=body, media_type="application/json; charset=utf-8")


@router.post("/diagnose/stream")
def diagnose_stream(req: DiagnoseRequest) -> StreamingResponse:
    def event_generator():
        for event_type, payload in stream_diagnosis(
            api=req.api,
            time=req.time,
            symptom=req.symptom,
            case_id=req.case_id,
            data_dir=req.data_dir,
            session_id=req.session_id,
            message=req.message,
            mode=req.mode,
            dcc=req.dcc,
        ):
            if event_type == "done":
                # send summary fields needed by frontend for history saving
                data = payload.model_dump()  # type: ignore[union-attr]
                yield f"event: done\ndata: {json.dumps({'case_id': data['case_id'], 'summary': data['summary'], 'call_graph': data['call_graph'], 'session_id': data.get('session_id'), 'mode': data.get('mode'), 'intent': data.get('intent'), 'executed_skills': data.get('executed_skills'), 'diagnosis_explain': data.get('diagnosis_explain', {}), 'current_focus': data.get('current_focus'), 'memory_summary': data.get('memory_summary'), 'data_source_status': data.get('data_source_status', {})}, ensure_ascii=False)}\n\n"
            elif isinstance(payload, dict):
                yield f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            else:
                msg = payload.model_dump()  # type: ignore[union-attr]
                yield f"event: {event_type}\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream; charset=utf-8")


@router.post("/diagnose/agentic-stream")
def diagnose_agentic_stream(req: DiagnoseRequest) -> StreamingResponse:
    """
    Lightweight agentic streaming endpoint.
    LLM generates intro + skill plan, then executes skills with streaming explanations.
    SSE events: assistant_delta, assistant_message_done, skill_start, skill_done,
                skill_error, report_done, done
    """
    def event_generator():
        for event in stream_agentic_diagnosis(
            api=req.api,
            time=req.time,
            symptom=req.symptom,
            case_id=req.case_id,
            data_dir=req.data_dir,
            session_id=req.session_id,
            message=req.message,
            mode=req.mode,
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream; charset=utf-8")


@router.post("/storm/report-stream")
def storm_report_stream(req: StormReportRequest) -> StreamingResponse:
    def event_generator():
        llm = get_llm_provider()
        for chunk in llm.stream_report(req.context):
            if chunk:
                yield f"data: {json.dumps({'type': 'report_delta', 'content': chunk}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'report_done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream; charset=utf-8")


@router.get("/health")
def health_check() -> JSONResponse:
    """Return data source connectivity status for monitoring and frontend."""
    status = get_data_source_status()
    return JSONResponse(content=status)
