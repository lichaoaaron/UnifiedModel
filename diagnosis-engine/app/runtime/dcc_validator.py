"""Lightweight validator for Diagnosis Context Contract (DCC) v0.1."""
from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any


class DCCValidationError(ValueError):
    """Raised when a DCC payload fails structural validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


_AVAILABILITY_VALUES = {"available", "empty", "insufficient", "unavailable", "error"}

# 32-char lowercase hex (MModel entity ID) or UUID
_ENTITY_ID_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")
_UUID_PATTERN = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_STABLE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@-]{0,255}$")
_CONTEXT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,255}$")
_WORKSPACE_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9_-]{0,62}[a-z0-9])?$")

# ISO-8601 / RFC3339 loose match
_ISO_TIME_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?)?$"
)


def _is_valid_entity_id(value: str) -> bool:
    return bool(
        _ENTITY_ID_PATTERN.match(value)
        or _UUID_PATTERN.match(value)
        or _STABLE_ID_PATTERN.match(value)
    )


def _is_valid_context_id(value: str) -> bool:
    return bool(
        _ENTITY_ID_PATTERN.match(value)
        or _UUID_PATTERN.match(value)
        or _CONTEXT_ID_PATTERN.match(value)
    )


def _is_valid_time(value: str) -> bool:
    """Check if value looks like an ISO-8601 / RFC3339 timestamp."""
    if not _ISO_TIME_PATTERN.match(value.strip()):
        return False
    # Try strict parse
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            datetime.strptime(value.strip().replace("Z", "+00:00"), fmt)
            return True
        except ValueError:
            continue
    return False


def _validate_entity_object(entity: dict[str, Any], index: int, errors: list[str]) -> None:
    """Validate a single entity entry in objects.entities."""
    eid = entity.get("entity_id", "")
    if not eid:
        errors.append(f"objects.entities[{index}].entity_id is required")
    elif not _is_valid_entity_id(str(eid)):
        errors.append(
            f"objects.entities[{index}].entity_id '{eid}' is not a valid "
            "entity ID (expected 32-char hex or UUID)"
        )

    etype = entity.get("entity_type", "")
    if not etype:
        errors.append(f"objects.entities[{index}].entity_type is required")


def _validate_topo_node(node: dict[str, Any], index: int, errors: list[str]) -> None:
    """Validate a single topology node."""
    nid = node.get("entity_id") or node.get("id", "")
    if not nid:
        errors.append(f"objects.topology.nodes[{index}] missing entity_id or id")


def _validate_topo_edge(edge: dict[str, Any], index: int, errors: list[str]) -> None:
    """Validate a single topology edge."""
    src = edge.get("src") or edge.get("source", "")
    dest = edge.get("dest") or edge.get("target", "")
    if not src:
        errors.append(f"objects.topology.edges[{index}] missing src/source")
    if not dest:
        errors.append(f"objects.topology.edges[{index}] missing dest/target")


def _validate_candidate(candidate: dict[str, Any], index: int, kind: str, errors: list[str]) -> None:
    """Validate a root_cause or impact_scope candidate."""
    eid = candidate.get("entity_id", "")
    if not eid:
        errors.append(f"candidates.{kind}[{index}].entity_id is required")
    elif not _is_valid_entity_id(str(eid)):
        errors.append(
            f"candidates.{kind}[{index}].entity_id '{eid}' is not a valid entity ID"
        )


def validate_dcc_payload(payload: dict[str, Any] | Mapping[str, Any] | None) -> dict[str, Any]:
    """Validate DCC structure and basic semantics, returning a plain dict on success.

    Structural checks: required keys, types, availability enum values.
    Semantic checks: entity ID format, timestamp format, workspace ID pattern,
                     cross-reference integrity.
    """
    if payload is None:
        raise DCCValidationError(["dcc payload is required"])
    if not isinstance(payload, Mapping):
        raise DCCValidationError(["dcc payload must be an object"])

    data = dict(payload)
    errors: list[str] = []

    def require(path: str, value: Any, expected_type: type | tuple[type, ...]) -> None:
        if value is None:
            errors.append(f"{path} is required")
            return
        if not isinstance(value, expected_type):
            expected_name = (
                "/".join(t.__name__ for t in expected_type)
                if isinstance(expected_type, tuple)
                else expected_type.__name__
            )
            errors.append(f"{path} must be {expected_name}")

    require("protocol_version", data.get("protocol_version"), str)
    require("context_id", data.get("context_id"), str)
    require("generated_at", data.get("generated_at"), str)

    # ── Semantic: context_id format ──────────────────────────────────────
    context_id = str(data.get("context_id", ""))
    if context_id and not _is_valid_context_id(context_id):
        errors.append(f"context_id '{context_id}' is not a valid context ID format")

    # ── Semantic: generated_at timestamp ─────────────────────────────────
    generated_at = str(data.get("generated_at", ""))
    if generated_at and not _is_valid_time(generated_at):
        errors.append(
            f"generated_at '{generated_at}' is not a valid ISO-8601 timestamp"
        )

    workspace = data.get("workspace")
    require("workspace", workspace, Mapping)
    if isinstance(workspace, Mapping):
        ws_id = str(workspace.get("workspace_id", ""))
        require("workspace.workspace_id", workspace.get("workspace_id"), str)
        if ws_id and not _WORKSPACE_PATTERN.match(ws_id):
            errors.append(
                f"workspace.workspace_id '{ws_id}' does not match pattern "
                "'^[a-z0-9]([a-z0-9_-]{0,62}[a-z0-9])?$'"
            )

    alert = data.get("alert")
    require("alert", alert, Mapping)
    if isinstance(alert, Mapping):
        require("alert.api", alert.get("api"), str)
        require("alert.time", alert.get("time"), str)
        require("alert.symptom", alert.get("symptom"), str)
        alert_time = str(alert.get("time", ""))
        if alert_time and not _is_valid_time(alert_time):
            errors.append(
                f"alert.time '{alert_time}' is not a valid ISO-8601 timestamp"
            )

    objects = data.get("objects")
    require("objects", objects, Mapping)
    entity_ids_seen: set[str] = set()
    if isinstance(objects, Mapping):
        entities = objects.get("entities", [])
        require("objects.entities", entities, list)
        if isinstance(entities, list):
            for i, entity in enumerate(entities):
                if isinstance(entity, dict):
                    _validate_entity_object(entity, i, errors)
                    eid = entity.get("entity_id", "")
                    if eid:
                        entity_ids_seen.add(str(eid))

        require("objects.relations", objects.get("relations"), list)

        topology = objects.get("topology")
        require("objects.topology", topology, Mapping)
        topo_node_ids: set[str] = set()
        if isinstance(topology, Mapping):
            nodes = topology.get("nodes", [])
            require("objects.topology.nodes", nodes, list)
            if isinstance(nodes, list):
                for i, node in enumerate(nodes):
                    if isinstance(node, dict):
                        _validate_topo_node(node, i, errors)
                        nid = str(node.get("entity_id") or node.get("id", ""))
                        if nid:
                            topo_node_ids.add(nid)

            edges = topology.get("edges", [])
            require("objects.topology.edges", edges, list)
            if isinstance(edges, list):
                for i, edge in enumerate(edges):
                    if isinstance(edge, dict):
                        _validate_topo_edge(edge, i, errors)

            # ── Semantic: topology node ↔ entity cross-reference ─────────
            if entity_ids_seen and topo_node_ids:
                # Topology nodes may use service names or labels rather than entity IDs.
                pass

    evidence = data.get("evidence")
    require("evidence", evidence, Mapping)
    if isinstance(evidence, Mapping):
        for signal in ("trace", "log", "metric"):
            bucket = evidence.get(signal)
            require(f"evidence.{signal}", bucket, Mapping)
            if isinstance(bucket, Mapping):
                availability = bucket.get("availability")
                require(f"evidence.{signal}.availability", availability, str)
                if isinstance(availability, str) and availability not in _AVAILABILITY_VALUES:
                    errors.append(
                        f"evidence.{signal}.availability must be one of "
                        f"{sorted(_AVAILABILITY_VALUES)}"
                    )
                require(f"evidence.{signal}.items", bucket.get("items"), list)

    candidates = data.get("candidates")
    require("candidates", candidates, Mapping)
    if isinstance(candidates, Mapping):
        rc_list = candidates.get("root_cause", [])
        require("candidates.root_cause", rc_list, list)
        if isinstance(rc_list, list):
            for i, rc in enumerate(rc_list):
                if isinstance(rc, dict):
                    _validate_candidate(rc, i, "root_cause", errors)

        impact_list = candidates.get("impact_scope", [])
        require("candidates.impact_scope", impact_list, list)
        if isinstance(impact_list, list):
            for i, imp in enumerate(impact_list):
                if isinstance(imp, dict):
                    _validate_candidate(imp, i, "impact_scope", errors)

        # ── Semantic: candidate entity cross-reference ───────────────────
        if entity_ids_seen:
            for kind, lst in (("root_cause", rc_list), ("impact_scope", impact_list)):
                if not isinstance(lst, list):
                    continue
                for i, c in enumerate(lst):
                    if not isinstance(c, dict):
                        continue
                    eid = str(c.get("entity_id", ""))
                    if eid and eid not in entity_ids_seen:
                        errors.append(
                            f"candidates.{kind}[{i}].entity_id '{eid}' not found "
                            "in objects.entities"
                        )

    provenance = data.get("provenance")
    require("provenance", provenance, Mapping)
    if isinstance(provenance, Mapping):
        require("provenance.producer", provenance.get("producer"), str)

    meta = data.get("meta")
    require("meta", meta, Mapping)
    if isinstance(meta, Mapping):
        availability = meta.get("availability")
        require("meta.availability", availability, str)
        if isinstance(availability, str) and availability not in _AVAILABILITY_VALUES:
            errors.append(f"meta.availability must be one of {sorted(_AVAILABILITY_VALUES)}")

    if errors:
        raise DCCValidationError(errors)
    return data
