"""BindingRuleAdapter: reads sidecar data/rules/binding_rules.yaml."""
import os
import yaml
from typing import Any

_BINDING_RULES_FILE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "rules", "binding_rules.yaml")
)


class BindingRuleAdapter:
    def __init__(self) -> None:
        self._rules: dict[str, Any] | None = None

    def _get_rules(self) -> dict[str, Any]:
        if self._rules is None:
            with open(_BINDING_RULES_FILE, "r", encoding="utf-8") as f:
                self._rules = yaml.safe_load(f) or {}
        return self._rules or {}

    def load_bindings(self) -> dict[str, Any]:
        """Return bindings dict from binding_rules.yaml."""
        return self._get_rules().get("bindings", {})

    def list_binding_names(self) -> list[str]:
        """Return list of binding rule names."""
        return list(self.load_bindings().keys())
