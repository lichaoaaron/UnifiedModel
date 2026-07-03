"""
LlmConfig: reads LLM-related configuration from backend/.env and environment variables.

Config keys (all optional, with production-safe defaults):
  LLM_PROVIDER                  mock | openai        (default: mock)
  LLM_BASE_URL                  OpenAI-compatible endpoint
  LLM_API_KEY                   API key
  LLM_MODEL                     model name           (default: qwen-plus)
  LLM_ENABLE_STREAM             true | false         (default: true)
  LLM_STREAM_TIMEOUT_SECONDS    int                  (default: 60)
  LLM_NON_STREAM_TIMEOUT_SECONDS int                 (default: 30)
  LLM_MAX_RETRIES               int                  (default: 1)
  LLM_ALLOW_MOCK_FALLBACK       true | false         (default: false)
    When false: LLM failures fall back to rule-based report, NOT MockLLMProvider.
    When true:  legacy behaviour — fall back to Mock on any LLM error.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

_DOTENV_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", ".env")
)


def _load_dotenv(path: str) -> dict[str, str]:
    """Minimal .env loader — no external deps."""
    env: dict[str, str] = {}
    if not os.path.isfile(path):
        return env
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _get(key: str, default: str, dotenv: dict[str, str]) -> str:
    return os.environ.get(key) or dotenv.get(key, default)


@dataclass
class LlmConfig:
    provider: str           = "mock"
    base_url: str           = "https://api.openai.com/v1"
    api_key: str            = ""
    model: str              = "qwen-plus"
    enable_stream: bool     = True
    stream_timeout: int     = 60
    non_stream_timeout: int = 30
    max_retries: int        = 1
    allow_mock_fallback: bool = False   # production-safe default: no silent mock fallback


def load_llm_config() -> LlmConfig:
    """Load and return LlmConfig from env vars + .env file."""
    dotenv = _load_dotenv(_DOTENV_PATH)

    def _bool(key: str, default: bool) -> bool:
        raw = _get(key, str(default).lower(), dotenv).lower()
        return raw in ("true", "1", "yes")

    def _int(key: str, default: int) -> int:
        try:
            return int(_get(key, str(default), dotenv))
        except ValueError:
            return default

    return LlmConfig(
        provider=_get("LLM_PROVIDER", "mock", dotenv).lower(),
        base_url=_get("LLM_BASE_URL", "https://api.openai.com/v1", dotenv).rstrip("/"),
        api_key=_get("LLM_API_KEY", "", dotenv),
        model=_get("LLM_MODEL", "qwen-plus", dotenv),
        enable_stream=_bool("LLM_ENABLE_STREAM", True),
        stream_timeout=_int("LLM_STREAM_TIMEOUT_SECONDS", 60),
        non_stream_timeout=_int("LLM_NON_STREAM_TIMEOUT_SECONDS", 30),
        max_retries=_int("LLM_MAX_RETRIES", 1),
        allow_mock_fallback=_bool("LLM_ALLOW_MOCK_FALLBACK", False),
    )
