import os
import sys
from dataclasses import dataclass

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
BACKEND_ROOT = os.path.join(REPO_ROOT, "backend")
for path in (REPO_ROOT, BACKEND_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.orchestrator.diagnosis_orchestrator import run_diagnosis


REQUIRED_DATA_SOURCE = "unifiedmodel"
REQUIRED_SAMPLE_DIR = os.path.normpath(
    os.path.join(REPO_ROOT, "..", "UnifiedModel", "outputs", "mmodel-fault-samples")
)


@dataclass
class AcceptanceCase:
    name: str
    case_id: str
    api: str
    time: str
    symptom: str
    expected_root_cause_type: str


CASES = [
    AcceptanceCase(
        name="Redis",
        case_id="fault-redis-saturation-001",
        api="/ais/configure/sysMetaPropDefs/dbFiledTranslationBasicFiled",
        time="2026-06-03T01:05:45.556Z",
        symptom="Redis saturation and rejected calls",
        expected_root_cause_type="platform.redis",
    ),
    AcceptanceCase(
        name="Database",
        case_id="fault-database-lock-wait-001",
        api="/ais/app/open/app/getAppListByAppCode",
        time="2026-06-03T01:05:19.343Z",
        symptom="Database lock wait contention",
        expected_root_cause_type="platform.database",
    ),
]


def _ensure_unifiedmodel_env() -> None:
    print("[ENV] Required DATA_SOURCE=unifiedmodel")
    print(f"[ENV] Required UNIFIEDMODEL_SAMPLE_DIR={REQUIRED_SAMPLE_DIR}")

    data_source = os.environ.get("DATA_SOURCE")
    sample_dir = os.environ.get("UNIFIEDMODEL_SAMPLE_DIR")

    if data_source != REQUIRED_DATA_SOURCE:
        print(f"[ENV] Override DATA_SOURCE: {data_source!r} -> {REQUIRED_DATA_SOURCE!r}")
        os.environ["DATA_SOURCE"] = REQUIRED_DATA_SOURCE
    else:
        print(f"[ENV] DATA_SOURCE already set: {data_source!r}")

    normalized_sample = os.path.normpath(sample_dir) if sample_dir else None
    if normalized_sample != REQUIRED_SAMPLE_DIR:
        print(f"[ENV] Override UNIFIEDMODEL_SAMPLE_DIR: {sample_dir!r} -> {REQUIRED_SAMPLE_DIR!r}")
        os.environ["UNIFIEDMODEL_SAMPLE_DIR"] = REQUIRED_SAMPLE_DIR
    else:
        print(f"[ENV] UNIFIEDMODEL_SAMPLE_DIR already set: {sample_dir!r}")

    if not os.path.isdir(REQUIRED_SAMPLE_DIR):
        print(f"[FAIL] UnifiedModel sample directory not found: {REQUIRED_SAMPLE_DIR}")
        sys.exit(2)


def _is_not_service_level_root(response, root_cause_service: str) -> bool:
    service_set = set()
    entity_result = getattr(response, "skills", None) or []
    for skill in entity_result:
        if getattr(skill, "skill_name", "") == "EntityBindingSkill":
            output = getattr(skill, "output", {}) or {}
            for svc in output.get("services", []) or []:
                if svc:
                    service_set.add(str(svc))
            break
    return bool(root_cause_service) and root_cause_service not in service_set


def _run_case(case: AcceptanceCase) -> bool:
    response = run_diagnosis(
        api=case.api,
        time=case.time,
        symptom=case.symptom,
        case_id=case.case_id,
    )

    root_cause_service = response.summary.root_cause_service or ""
    root_cause_type = response.summary.root_cause_type or ""

    type_ok = root_cause_type == case.expected_root_cause_type
    entity_level_ok = _is_not_service_level_root(response, root_cause_service)
    passed = type_ok and entity_level_ok

    print("-" * 72)
    print(f"Case: {case.name} ({case.case_id})")
    print(f"PASS: {passed}")
    print(f"root_cause_service: {root_cause_service}")
    print(f"root_cause_type: {root_cause_type}")
    print(f"expect_type: {case.expected_root_cause_type}, type_ok={type_ok}")
    print(f"entity_level_ok: {entity_level_ok}")

    return passed


def main() -> int:
    print("Running UnifiedModel closed-loop acceptance...")
    _ensure_unifiedmodel_env()

    total = len(CASES)
    passed = 0
    for case in CASES:
        if _run_case(case):
            passed += 1

    print("=" * 72)
    print(f"Summary: {passed}/{total} cases passed")

    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
