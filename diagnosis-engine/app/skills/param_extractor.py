"""
param_extractor: shared utility for extracting bad_parameter from text.

Built-in patterns cover Java, Python, Go and generic URL query params.
Additional patterns can be appended via backend/data/rules/root_cause_rules.yaml
under the `parameter_extraction.extra_patterns` key (optional).

No fallback to hardcoded values — returns None if nothing is found.
"""
from __future__ import annotations

import logging
import os
import re
import yaml
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Built-in extraction patterns (language-agnostic order)
# ---------------------------------------------------------------------------

# Each entry: (name, compiled_regex, capture_group)
_BUILTIN_PATTERNS: list[tuple[str, re.Pattern, int]] = [
    # Java: NumberFormatException / Long.parseLong etc.
    ("java_for_input_string",   re.compile(r'For input string:\s*"([^"]+)"'),              1),
    # Python: int() / float() ValueError
    ("python_value_error",      re.compile(r"invalid literal for \w+\(\) with base \d+: '([^']+)'"), 1),
    # Go: strconv.ParseXxx
    ("go_parse_error",          re.compile(r'parsing "([^"]+)"'),                           1),
    # Generic URL query param — any key=value (first match wins)
    ("url_query_param_any",     re.compile(r'[?&][a-zA-Z_][a-zA-Z0-9_]*=([^&\s\]"\'}{]+)'), 1),
]

# ---------------------------------------------------------------------------
# Optional YAML-defined extra patterns (loaded once at module level)
# ---------------------------------------------------------------------------

_RULES_FILE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "rules", "root_cause_rules.yaml")
)


def _load_extra_patterns() -> list[tuple[str, re.Pattern, int]]:
    """Load extra extraction patterns from YAML (parameter_extraction.extra_patterns)."""
    try:
        with open(_RULES_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        extras = (data.get("parameter_extraction") or {}).get("extra_patterns", [])
        result = []
        for entry in extras:
            name = entry.get("name", "custom")
            pattern = entry.get("pattern", "")
            group = int(entry.get("capture_group", 1))
            if pattern:
                result.append((name, re.compile(pattern), group))
        return result
    except Exception:
        return []


# Combined pattern list: built-ins first, then YAML extras
_ALL_PATTERNS: list[tuple[str, re.Pattern, int]] = _BUILTIN_PATTERNS + _load_extra_patterns()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_bad_parameter(text: str) -> Optional[str]:
    """
    Extract bad_parameter from any text string.

    Tries patterns in order: Java NFE → Python ValueError → Go parse →
    URL query param (any key) → YAML-configured extras.

    Returns None if nothing is found.
    """
    if not text:
        return None
    for _name, pattern, group in _ALL_PATTERNS:
        m = pattern.search(text)
        if m:
            try:
                val = m.group(group).rstrip('])"\'} ')
                if val:
                    return val
            except IndexError:
                pass
    return None


def extract_bad_parameter_from_fields(*texts: str) -> tuple[Optional[str], str]:
    """
    Try extracting bad_parameter from multiple text fields in order.

    Returns (value, source_description) or (None, "not found").
    """
    for i, text in enumerate(texts):
        if not text:
            continue
        val = extract_bad_parameter(text)
        if val is not None:
            return val, f"field[{i}]"
    return None, "not found"
