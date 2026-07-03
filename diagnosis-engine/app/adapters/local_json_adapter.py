"""
LocalJsonAdapter: loads trace/log/metric data from local JSON files.
This adapter can be replaced with OpenSearchAdapter, ARMSAdapter, etc.

DATA_DIR resolution order:
    1. Request data_dir
    2. Request case_id under examples/evaluation_cases/<collection>
    3. Request api/symptom matched against evaluation case index.json files
    4. Environment variable MMODEL_DATA_DIR

Set MMODEL_DATA_DIR in backend/.env or shell environment to point at
an evaluation case directory without modifying code.
"""
import json
import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import unquote

logger = logging.getLogger(__name__)

_EVALUATION_ROOT_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "examples", "evaluation_cases")
)

if os.environ.get("MMODEL_DATA_DIR"):
    logger.info("[LocalJsonAdapter] DATA_DIR overridden by MMODEL_DATA_DIR env var: %s", os.environ["MMODEL_DATA_DIR"])


import re as _re

_SAFE_CASE_ID_RE = _re.compile(r"^[A-Za-z0-9_-]+$")
_TOKEN_RE = _re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]+")
_AUTO_MATCH_MIN_SCORE = 100


def _normalize_path(path: str) -> str:
    return os.path.normcase(os.path.abspath(os.path.normpath(path)))


def _ensure_under(path: str, allowed_roots: tuple[str, ...]) -> str:
    resolved = _normalize_path(path)
    normalized_roots = tuple(_normalize_path(root) for root in allowed_roots)
    if not any(os.path.commonpath([resolved, root]) == root for root in normalized_roots):
        raise ValueError(f"data directory is outside allowed roots: {path}")
    return resolved


def _resolve_case_dir(case_id: str) -> str:
    decoded = unquote(case_id or "")
    if not _SAFE_CASE_ID_RE.fullmatch(decoded):
        raise ValueError("case_id must match ^[A-Za-z0-9_-]+$")
    evaluation_root = _ensure_under(_EVALUATION_ROOT_DIR, (_EVALUATION_ROOT_DIR,))
    matches = []
    for collection in sorted(Path(evaluation_root).iterdir()):
        if not collection.is_dir():
            continue
        candidate = _ensure_under(str(collection / decoded), (evaluation_root,))
        if os.path.isdir(candidate):
            matches.append(candidate)
    if not matches:
        raise ValueError("case_id not found in evaluation_cases")
    if len(matches) > 1:
        raise ValueError("ambiguous case_id in evaluation_cases; pass data_dir to select a collection")
    return matches[0]

def resolve_data_dir(data_dir: str | None = None, case_id: str | None = None) -> str:
    if data_dir:
        if case_id:
            raise ValueError("data_dir and case_id cannot be used together")
        return _ensure_under(data_dir, (_EVALUATION_ROOT_DIR,))
    if case_id:
        return _resolve_case_dir(case_id)
    env_dir = os.environ.get("MMODEL_DATA_DIR")
    if env_dir:
        return _ensure_under(env_dir, (_EVALUATION_ROOT_DIR,))
    raise ValueError("no evaluation case selected; pass case_id, data_dir, or an API/symptom that matches examples/evaluation_cases")


def resolve_request_context(
    api: str,
    symptom: str,
    case_id: str | None = None,
    data_dir: str | None = None,
) -> tuple[str | None, str | None]:
    if data_dir or case_id or os.environ.get("MMODEL_DATA_DIR"):
        return case_id, data_dir

    try:
        matched_case_id = _match_case_id_from_indexes(api=api, symptom=symptom)
        if matched_case_id:
            logger.info("[LocalJsonAdapter] auto matched case_id=%s from request context", matched_case_id)
            return matched_case_id, None
    except (FileNotFoundError, OSError):
        pass
    return case_id, data_dir


def _match_case_id_from_indexes(api: str, symptom: str) -> str | None:
    query_api = (api or "").strip().lower()
    query_text = f"{api or ''} {symptom or ''}".lower()
    query_tokens = set(_TOKEN_RE.findall(query_text))
    best_case_id = None
    best_score = 0

    evaluation_root = Path(_ensure_under(_EVALUATION_ROOT_DIR, (_EVALUATION_ROOT_DIR,)))
    for collection in sorted(evaluation_root.iterdir()):
        index_path = collection / "index.json"
        if not index_path.is_file():
            continue
        try:
            index_items = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for item in index_items if isinstance(index_items, list) else []:
            if not isinstance(item, dict):
                continue
            candidate_api = str(item.get("alert_api") or "").strip().lower()
            candidate_text = " ".join(
                str(item.get(field) or "")
                for field in ("alert_api", "alert_symptom", "name", "category", "evidence_mode")
            ).lower()
            candidate_tokens = set(_TOKEN_RE.findall(candidate_text))
            score = 0
            if query_api and candidate_api:
                if query_api == candidate_api:
                    score += 100
                elif query_api in candidate_api or candidate_api in query_api:
                    score += 50
            score += 8 * len(query_tokens & candidate_tokens)
            if symptom and str(item.get("alert_symptom") or "").lower() in query_text:
                score += 20
            if score > best_score:
                best_score = score
                best_case_id = str(item.get("case_id") or "")

    if best_case_id and best_score >= _AUTO_MATCH_MIN_SCORE:
        return best_case_id
    return None


def _load(filename: str, data_dir: str | None = None, case_id: str | None = None) -> Any:
    # Re-read DATA_DIR each call so that runtime changes to the env var take effect
    resolved_dir = resolve_data_dir(data_dir=data_dir, case_id=case_id)
    path = os.path.normpath(os.path.join(resolved_dir, filename))
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # log.json may contain literal unescaped newlines/tabs inside string values
        def fix_string(m: _re.Match) -> str:  # type: ignore[type-arg]
            return m.group(0).replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
        cleaned = _re.sub(r'"(?:[^"\\]|\\.)*"', fix_string, content, flags=_re.DOTALL)
        return json.loads(cleaned)


def get_traces(data_dir: str | None = None, case_id: str | None = None) -> list[dict]:
    data = _load("trace.json", data_dir=data_dir, case_id=case_id)
    if isinstance(data, list):
        return [item.get("_source", item) for item in data]
    return [data.get("_source", data)]


def get_logs(data_dir: str | None = None, case_id: str | None = None) -> list[dict]:
    data = _load("log.json", data_dir=data_dir, case_id=case_id)
    if isinstance(data, list):
        return [item.get("_source", item) for item in data]
    return [data]


def get_metrics(data_dir: str | None = None, case_id: str | None = None) -> list[dict]:
    data = _load("metric.json", data_dir=data_dir, case_id=case_id)
    if isinstance(data, list):
        return [item.get("_source", item) for item in data]
    return [data]
