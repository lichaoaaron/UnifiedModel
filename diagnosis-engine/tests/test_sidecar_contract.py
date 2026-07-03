from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DIAG_ROOT = REPO_ROOT / "diagnosis-engine"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_sidecar_contains_runtime_model_and_evaluation_case_data() -> None:
    assert (DIAG_ROOT / "data" / "mmodel" / "runtime_domain_model.yaml").is_file()
    assert (DIAG_ROOT / "examples" / "evaluation_cases" / "basic_root_cause_19" / "index.json").is_file()


def test_min_checks_uses_diagnosis_engine_root_not_repo_backend() -> None:
    script = _read(DIAG_ROOT / "tests" / "run_min_checks.py")

    assert 'REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))' in script
    assert 'BACKEND_ROOT = os.path.join(REPO_ROOT, "backend")' not in script
    assert "examples', 'evaluation_cases'" in script


def test_status_and_stop_scripts_manage_diagnosis_process() -> None:
    status_script = _read(REPO_ROOT / "scripts" / "status.sh")
    stop_script = _read(REPO_ROOT / "scripts" / "stop-dev.sh")

    assert 'DIAG_PORT="${DIAG_PORT:-8000}"' in status_script
    assert "openumodel-dev-diagnosis.pid" in status_script
    assert "Diagnosis health:" in status_script
    assert "Diagnosis ${DIAG_PORT}" in status_script

    assert 'DIAG_PORT="${DIAG_PORT:-8000}"' in stop_script
    assert "diagnosis)" in stop_script
    assert "openumodel-dev-diagnosis.pid" in stop_script
    assert 'stop_port diagnosis "${DIAG_PORT}"' in stop_script


def test_dev_output_reports_diagnosis_url_and_local_files_are_ignored() -> None:
    dev_script = _read(REPO_ROOT / "scripts" / "dev.sh")
    gitignore = _read(REPO_ROOT / ".gitignore")

    assert "Diagnosis: http://localhost:${DIAG_PORT}" in dev_script
    assert "Diagnosis log: ${DIAG_LOG}" in dev_script
    assert "diagnosis-engine/.env" in gitignore
    assert "diagnosis-engine/app.log" in gitignore


def test_makefile_and_readme_expose_diagnosis_quickstart_without_replacing_default() -> None:
    makefile = _read(REPO_ROOT / "Makefile")
    readme = _read(REPO_ROOT / "README.md")
    script = _read(REPO_ROOT / "scripts" / "quickstart-diagnosis.sh")

    assert "quickstart-diagnosis:" in makefile
    assert "quickstart: GRAPHSTORE = memory" in makefile
    assert "QUICKSTART_SAMPLE ?= multi-domain-quickstart" in makefile
    assert "scripts/quickstart-diagnosis.sh" in makefile
    assert "make quickstart-diagnosis" in readme
    assert "mmodel-faults" in readme
    assert "otel-demo" in readme
    assert 'workspace="mmodel-faults"' in script
    assert 'workspace="otel-demo"' in script
    assert "outputs/mmodel-fault-samples/sample-data/entities.json" in script
    assert "examples/otel-demo/sample-data/entities.json" in script


def test_diagnosis_page_mounts_mmodel_workbench_feature_island() -> None:
    page = _read(REPO_ROOT / "web" / "src" / "features" / "diagnosis" / "DiagnosisPage.tsx")
    workbench = REPO_ROOT / "web" / "src" / "features" / "diagnosis" / "workbench" / "DiagnosisWorkbench.tsx"
    css = REPO_ROOT / "web" / "src" / "features" / "diagnosis" / "workbench" / "diagnosisWorkbench.css"

    assert workbench.is_file()
    assert css.is_file()
    assert "DiagnosisWorkbench" in page
    assert "HistoryPanel" in _read(workbench)
    assert "DataSourceIndicator" in _read(workbench)
    assert "streamStormDemoDiagnosis" in _read(workbench)
    assert (workbench.parent / "components" / "AgentChatPanel.tsx").is_file()
