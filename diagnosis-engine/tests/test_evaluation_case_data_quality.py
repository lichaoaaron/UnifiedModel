import json
import re
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_EVAL_ROOT = _REPO_ROOT / "examples" / "evaluation_cases"

_FORBIDDEN_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bsynthetic\b",
        r"\bshowcase\b",
        r"\bdemo\b",
        r"feedface",
        r"abcdef012345",
        r"RootCause\.java",
        r"Root\.java",
        r"\bcase=",
        r"root cause diagnostic",
        r"propagated symptom",
        r"\b10\.(?:20|70)\.\d+\.\d+\b",
    ]
]


def _walk_values(value):
    if isinstance(value, dict):
        for nested in value.values():
            yield from _walk_values(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_values(nested)
    elif isinstance(value, str):
        yield value


def test_evaluation_json_does_not_expose_demo_markers():
    offenders = []
    for json_path in _EVAL_ROOT.rglob("*.json"):
        data = json.loads(json_path.read_text(encoding="utf-8"))
        for value in _walk_values(data):
            for pattern in _FORBIDDEN_PATTERNS:
                if pattern.search(value):
                    offenders.append((json_path.relative_to(_REPO_ROOT).as_posix(), value, pattern.pattern))
                    break

    assert not offenders, offenders[:20]
