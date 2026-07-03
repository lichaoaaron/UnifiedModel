"""
OntologyConfigAdapter: reads backend/data/mmodel/runtime_domain_model.yaml (runtime ontology).
Falls back to specs/01_domain/mmodel_domain_spec.yaml if runtime file is missing (with warning).
Optionally scans examples/ontology/umodel_data for UModel YAML category listing.
Does NOT parse the full content of official YAML files — only lists directory names.
"""
import logging
import os
import yaml
from typing import Any

logger = logging.getLogger(__name__)

# Primary runtime ontology path (under backend/data/mmodel/)
_MMODEL_DATA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "mmodel")
)
_RUNTIME_DOMAIN_MODEL_FILE = os.path.join(_MMODEL_DATA_DIR, "runtime_domain_model.yaml")

# Fallback: specs path (for compatibility only, not the primary source)
_SPECS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "specs", "01_domain")
)
_SPECS_DOMAIN_MODEL_FILE = os.path.join(_SPECS_DIR, "mmodel_domain_spec.yaml")

_UMODEL_DATA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "examples", "ontology", "umodel_data")
)

_DEMO_BUSINESS_ONTOLOGY_FILE = os.path.join(_MMODEL_DATA_DIR, "demo_business_ontology.yaml")
_DEMO_TOPOLOGY_ONTOLOGY_FILE = os.path.join(_MMODEL_DATA_DIR, "demo_topology_ontology.yaml")


def _load_domain_model() -> dict[str, Any]:
    if os.path.isfile(_RUNTIME_DOMAIN_MODEL_FILE):
        logger.info("[Ontology] source=%s fallback_to_specs=false", _RUNTIME_DOMAIN_MODEL_FILE)
        with open(_RUNTIME_DOMAIN_MODEL_FILE, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    # Fallback to specs (compatibility only)
    logger.warning(
        "[Ontology] Runtime ontology not found at %s, falling back to specs: %s. "
        "fallback_to_specs=true",
        _RUNTIME_DOMAIN_MODEL_FILE, _SPECS_DOMAIN_MODEL_FILE,
    )
    with open(_SPECS_DOMAIN_MODEL_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class OntologyConfigAdapter:
    """
    Lightweight ontology adapter.
    Default runtime source: backend/data/mmodel/runtime_domain_model.yaml
    Fallback (compatibility): specs/01_domain/mmodel_domain_spec.yaml
    Can be upgraded to UModelYamlAdapter in the future.
    """

    def __init__(self) -> None:
        self._model: dict[str, Any] | None = None

    def _get_model(self) -> dict[str, Any]:
        if self._model is None:
            self._model = _load_domain_model()
        return self._model

    def load_domain_model(self) -> dict[str, Any]:
        """Load and return the full domain_model.yaml dict."""
        return self._get_model()

    def list_umodel_yaml_categories(self) -> list[str]:
        """
        Scan examples/ontology/umodel_data and return subdirectory names (UModel YAML types).
        Does NOT parse the YAML files — only lists directory structure.
        """
        if not os.path.isdir(_UMODEL_DATA_DIR):
            return []
        return sorted([
            d for d in os.listdir(_UMODEL_DATA_DIR)
            if os.path.isdir(os.path.join(_UMODEL_DATA_DIR, d))
        ])

    def load_entity_types(self) -> list[dict[str, Any]]:
        """Return entity_types list from domain_model.yaml."""
        return self._get_model().get("entity_types", [])

    def load_entities(self) -> list[dict[str, Any]]:
        """Return entities list from domain_model.yaml."""
        return self._get_model().get("entities", [])

    def load_relation_types(self) -> list[dict[str, Any]]:
        """Return relation_types list from domain_model.yaml."""
        return self._get_model().get("relation_types", [])

    def load_relations(self) -> list[dict[str, Any]]:
        """Return relations list from domain_model.yaml."""
        return self._get_model().get("relations", [])

    def load_demo_business_ontology(self) -> dict[str, Any]:
        """
        Load demo_business_ontology.yaml (演示业务本体，仅用于 Demo 展示).
        Returns empty dict if file does not exist.
        """
        if not os.path.isfile(_DEMO_BUSINESS_ONTOLOGY_FILE):
            logger.warning("[Ontology] demo_business_ontology.yaml not found at %s", _DEMO_BUSINESS_ONTOLOGY_FILE)
            return {}
        with open(_DEMO_BUSINESS_ONTOLOGY_FILE, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def load_demo_topology_ontology(self) -> dict[str, Any]:
        """
        Load demo_topology_ontology.yaml (演示用拓扑本体，含完整节点/边，仅用于 Demo 可视化展示).
        Returns empty dict if file does not exist (caller degrades gracefully).
        """
        if not os.path.isfile(_DEMO_TOPOLOGY_ONTOLOGY_FILE):
            logger.info("[Ontology] demo_topology_ontology.yaml not found at %s, skipping", _DEMO_TOPOLOGY_ONTOLOGY_FILE)
            return {}
        with open(_DEMO_TOPOLOGY_ONTOLOGY_FILE, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
