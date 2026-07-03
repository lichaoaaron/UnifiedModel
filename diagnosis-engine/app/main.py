import json
import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse


def _load_backend_env() -> None:
    env_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".env"))
    if not os.path.isfile(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)


_load_backend_env()

from app.routers import diagnose, diagnosis_v2, runtime

# ---------------------------------------------------------------------------
# Logging: console + rotating file (backend/app.log)
# ---------------------------------------------------------------------------
_log_file = os.path.join(os.path.dirname(__file__), "..", "app.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),                          # uvicorn 控制台
        logging.FileHandler(_log_file, encoding="utf-8"), # backend/app.log
    ],
)


class UTF8JSONResponse(JSONResponse):
    """JSONResponse that preserves Chinese characters (ensure_ascii=False)."""
    def render(self, content) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")


app = FastAPI(title="MModel Demo API", version="1.0.0", default_response_class=UTF8JSONResponse)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(diagnose.router, prefix="/api")
app.include_router(runtime.router, prefix="/api")
# PRD-aligned diagnosis API v2 (no /api prefix — matches Grafana contract)
app.include_router(diagnosis_v2.router)


@app.get("/")
def root():
    return JSONResponse({
        "service": "MModel Demo API",
        "status": "running",
        "docs": "http://localhost:8000/docs",
        "diagnose": "POST http://localhost:8000/api/diagnose",
        "diagnosis_v2": "POST http://localhost:8000/diagnosis/analyze",
        "data_source": "examples/evaluation_cases",
        "example": {
            "api": "<alert_api>",
            "time": "<alert_time>",
            "symptom": "<alert_symptom>",
            "case_id": "<case_id>"
        }
    })
