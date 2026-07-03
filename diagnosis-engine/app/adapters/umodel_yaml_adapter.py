"""
UModelYamlAdapter parses the supported UModel YAML subset under
examples/ontology/umodel_data/.

P2 supports model definitions only:
    - entity_set, entity_set_link
    - metric_set, log_set, trace_set
    - data_link, storage_link

It does not parse runtime entity instances, evaluation cases, or perform full
schema validation.
"""
import os
import yaml
from typing import Any

_UMODEL_DATA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "examples", "otel-demo")
)

_DATA_SET_KINDS = {"metric_set", "log_set", "trace_set"}


def _localized(value: Any, default: str = "") -> str:
    if isinstance(value, dict):
        return str(value.get("zh_cn") or value.get("en_us") or default)
    if value is None:
        return default
    return str(value)


def _ref_key(ref: dict[str, Any] | None) -> str:
    if not isinstance(ref, dict):
        return ""
    domain = str(ref.get("domain") or "")
    name = str(ref.get("name") or "")
    return _qualified_key(domain, name)


def _qualified_key(domain: str, name: str) -> str:
    if not name:
        return ""
    if domain and not name.startswith(f"{domain}."):
        return f"{domain}.{name}"
    return name


def _normalize_ref_key(value: str) -> str:
    return value.strip()


def _matches_ref(value: str, candidate: str | None) -> bool:
    if not candidate:
        return True
    return _normalize_ref_key(value) == _normalize_ref_key(candidate)


def _list_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _field_names(spec: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for item in _list_items(spec.get("fields")):
        name = item.get("name")
        if name and name not in names:
            names.append(str(name))
    labels = spec.get("labels", {})
    if isinstance(labels, dict):
        for item in _list_items(labels.get("keys")):
            name = item.get("name")
            if name and name not in names:
                names.append(str(name))
    for item in _list_items(spec.get("metrics")):
        name = item.get("name")
        if name and name not in names:
            names.append(str(name))
    return names


class UModelYamlAdapter:
    """
    Parses examples/ontology/umodel_data/ YAML files and builds:
      - entity_set index:      {domain.name -> metadata}
      - entity_set_link index: list of {src, relation_type, dest, priority, description}

    Designed for drop-in use wherever OntologyConfigAdapter is used, plus richer graph queries.
    To swap to Neo4j: implement GraphEngineAdapter with the same query methods.

    When DATA_SOURCE=mmodel_api, call load_from_mmodel_api() after construction to
    populate the indexes from the MModel Query Service (.mmodel SPL source) instead
    of reading local YAML files.
    """

    def __init__(self, data_dir: str | None = None) -> None:
        self._data_dir = data_dir or _UMODEL_DATA_DIR
        self._entity_sets: dict[str, dict[str, Any]] = {}
        self._entity_links: list[dict[str, Any]] = []
        self._data_sets: dict[str, dict[str, Any]] = {}
        self._data_links: list[dict[str, Any]] = []
        self._storage_links: list[dict[str, Any]] = []
        self._warnings: list[dict[str, str]] = []
        self._loaded = False
        self._api_loaded = False

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True

        for fpath, data in self._iter_yaml_files():
            kind = data.get("kind", "")
            metadata = data.get("metadata", {})
            spec = data.get("spec", {})

            if kind == "entity_set":
                domain = str(metadata.get("domain") or "")
                name = str(metadata.get("name") or "")
                key = _qualified_key(domain, name)
                self._entity_sets[key] = {
                    "kind": kind,
                    "domain": domain,
                    "name": name,
                    "key": key,
                    "path": fpath,
                    "display_name": _localized(metadata.get("display_name"), name),
                    "description": _localized(metadata.get("description")),
                    "primary_key_fields": spec.get("primary_key_fields", []),
                    "name_fields": spec.get("name_fields", []),
                }

            elif kind == "entity_set_link":
                src = spec.get("src", {}) if isinstance(spec, dict) else {}
                dest = spec.get("dest", {}) if isinstance(spec, dict) else {}
                link_type = spec.get("entity_link_type", "related_to")
                src_key = _ref_key(src)
                dest_key = _ref_key(dest)
                self._entity_links.append({
                    "kind": kind,
                    "domain": metadata.get("domain", ""),
                    "name": metadata.get("name", ""),
                    "key": _qualified_key(str(metadata.get("domain") or ""), str(metadata.get("name") or "")),
                    "path": fpath,
                    "src": src_key,
                    "src_ref": dict(src) if isinstance(src, dict) else {},
                    "dest": dest_key,
                    "dest_ref": dict(dest) if isinstance(dest, dict) else {},
                    "relation_type": link_type,
                    "priority": spec.get("priority", 0),
                    "fields_mapping": spec.get("fields_mapping", {}),
                    "display_name": _localized(metadata.get("display_name"), link_type),
                    "description": _localized(metadata.get("description")),
                })

            elif kind in _DATA_SET_KINDS:
                self._load_data_set(fpath, kind, metadata, spec)

            elif kind == "data_link":
                self._load_data_link(fpath, kind, metadata, spec)

            elif kind == "storage_link":
                self._load_storage_link(fpath, kind, metadata, spec)

    def _iter_yaml_files(self):
        """Recursively yield (path, parsed_dict), recording bad YAML warnings."""
        for root, _dirs, files in os.walk(self._data_dir):
            for fname in sorted(files):
                if not (fname.endswith(".yaml") or fname.endswith(".yml")):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                    if isinstance(data, dict):
                        yield fpath, data
                    else:
                        self._warnings.append({"path": fpath, "error": "YAML root is not a mapping"})
                except Exception as exc:
                    self._warnings.append({"path": fpath, "error": str(exc).splitlines()[0]})

    def _load_data_set(self, fpath: str, kind: str, metadata: dict[str, Any], spec: dict[str, Any]) -> None:
        safe_spec = spec if isinstance(spec, dict) else {}
        fields = _list_items(safe_spec.get("fields"))
        label_fields = _list_items(safe_spec.get("labels", {}).get("keys")) if isinstance(safe_spec.get("labels"), dict) else []
        metrics = _list_items(safe_spec.get("metrics"))
        domain = str(metadata.get("domain") or "")
        name = str(metadata.get("name") or "")
        key = _qualified_key(domain, name)
        self._data_sets[key] = {
            "kind": kind,
            "domain": domain,
            "name": name,
            "key": key,
            "path": fpath,
            "display_name": _localized(metadata.get("display_name"), name),
            "description": _localized(metadata.get("description")),
            "time_field": safe_spec.get("time_field", ""),
            "fields": fields,
            "field_names": _field_names(safe_spec),
            "label_fields": label_fields,
            "metrics": metrics,
            "field_count": len(fields),
        }

    def _load_data_link(self, fpath: str, kind: str, metadata: dict[str, Any], spec: dict[str, Any]) -> None:
        src = spec.get("src", {}) if isinstance(spec, dict) else {}
        dest = spec.get("dest", {}) if isinstance(spec, dict) else {}
        self._data_links.append({
            "kind": kind,
            "domain": metadata.get("domain", ""),
            "name": metadata.get("name", ""),
            "key": _qualified_key(str(metadata.get("domain") or ""), str(metadata.get("name") or "")),
            "path": fpath,
            "src": _ref_key(src),
            "src_ref": dict(src) if isinstance(src, dict) else {},
            "dest": _ref_key(dest),
            "dest_ref": dict(dest) if isinstance(dest, dict) else {},
            "data_link_type": spec.get("data_link_type", "related_to") if isinstance(spec, dict) else "related_to",
            "fields_mapping": spec.get("fields_mapping", {}) if isinstance(spec, dict) else {},
            "data_filter": spec.get("data_filter", "") if isinstance(spec, dict) else "",
            "display_name": _localized(metadata.get("display_name"), str(metadata.get("name") or "")),
            "description": _localized(metadata.get("description")),
        })

    def _load_storage_link(self, fpath: str, kind: str, metadata: dict[str, Any], spec: dict[str, Any]) -> None:
        src = spec.get("src", {}) if isinstance(spec, dict) else {}
        dest = spec.get("dest", {}) if isinstance(spec, dict) else {}
        self._storage_links.append({
            "kind": kind,
            "domain": metadata.get("domain", ""),
            "name": metadata.get("name", ""),
            "key": _qualified_key(str(metadata.get("domain") or ""), str(metadata.get("name") or "")),
            "path": fpath,
            "src": _ref_key(src),
            "src_ref": dict(src) if isinstance(src, dict) else {},
            "dest": _ref_key(dest),
            "dest_ref": dict(dest) if isinstance(dest, dict) else {},
            "priority": spec.get("priority", 0) if isinstance(spec, dict) else 0,
            "fields_mapping": spec.get("fields_mapping", {}) if isinstance(spec, dict) else {},
            "filter_by_entity": spec.get("filter_by_entity", "") if isinstance(spec, dict) else "",
            "display_name": _localized(metadata.get("display_name"), str(metadata.get("name") or "")),
            "description": _localized(metadata.get("description")),
        })

    # ------------------------------------------------------------------
    # MModel API loading
    # ------------------------------------------------------------------

    def load_from_mmodel_api(self) -> bool:
        """Populate indexes from the MModel Query Service (.mmodel SPL source).

        Call this after construction when DATA_SOURCE=mmodel_api.  Returns True
        if at least one element was loaded, False otherwise (falls back to YAML).
        """
        if self._api_loaded:
            return len(self._entity_sets) > 0 or len(self._data_sets) > 0
        self._api_loaded = True

        try:
            from app.adapters.mmodel_rest_client import get_mmodel_client
            client = get_mmodel_client()
            rows = client.list_umodel(limit=500)
        except Exception as exc:
            self._warnings.append({
                "source": "mmodel_api",
                "error": f"Failed to query .mmodel: {exc}",
            })
            return False

        if not rows:
            self._warnings.append({
                "source": "mmodel_api",
                "error": ".mmodel query returned no elements",
            })
            return False

        loaded_count = 0
        for row in rows:
            kind = str(row.get("kind") or row.get("__kind__") or "")
            metadata = row.get("metadata", {}) if isinstance(row.get("metadata"), dict) else {}
            spec = row.get("spec", {}) if isinstance(row.get("spec"), dict) else {}
            domain = str(metadata.get("domain") or row.get("domain") or row.get("__domain__") or "")
            name = str(metadata.get("name") or row.get("name") or "")

            if kind == "entity_set":
                key = _qualified_key(domain, name)
                self._entity_sets[key] = {
                    "kind": kind,
                    "domain": domain,
                    "name": name,
                    "key": key,
                    "path": f"mmodel://{key}",
                    "display_name": _localized(metadata.get("display_name"), name),
                    "description": _localized(metadata.get("description")),
                    "primary_key_fields": spec.get("primary_key_fields", []),
                    "name_fields": spec.get("name_fields", []),
                }
                loaded_count += 1

            elif kind == "entity_set_link":
                src = spec.get("src", {}) if isinstance(spec, dict) else {}
                dest = spec.get("dest", {}) if isinstance(spec, dict) else {}
                link_type = spec.get("entity_link_type", "related_to")
                self._entity_links.append({
                    "kind": kind,
                    "domain": domain,
                    "name": name,
                    "key": _qualified_key(domain, name),
                    "path": f"mmodel://{_qualified_key(domain, name)}",
                    "src": _ref_key(src),
                    "src_ref": dict(src) if isinstance(src, dict) else {},
                    "dest": _ref_key(dest),
                    "dest_ref": dict(dest) if isinstance(dest, dict) else {},
                    "relation_type": link_type,
                    "priority": spec.get("priority", 0),
                    "fields_mapping": spec.get("fields_mapping", {}),
                    "display_name": _localized(metadata.get("display_name"), link_type),
                    "description": _localized(metadata.get("description")),
                })
                loaded_count += 1

            elif kind in _DATA_SET_KINDS:
                key = _qualified_key(str(metadata.get("domain") or domain), str(metadata.get("name") or name))
                safe_spec = spec if isinstance(spec, dict) else {}
                self._data_sets[key] = {
                    "kind": kind,
                    "domain": domain,
                    "name": name,
                    "key": key,
                    "path": f"mmodel://{key}",
                    "display_name": _localized(metadata.get("display_name"), name),
                    "description": _localized(metadata.get("description")),
                    "time_field": safe_spec.get("time_field", ""),
                    "fields": _list_items(safe_spec.get("fields")),
                    "field_names": _field_names(safe_spec),
                    "label_fields": _list_items(safe_spec.get("labels", {}).get("keys")) if isinstance(safe_spec.get("labels"), dict) else [],
                    "metrics": _list_items(safe_spec.get("metrics")),
                    "field_count": len(_list_items(safe_spec.get("fields"))),
                }
                loaded_count += 1

            elif kind == "data_link":
                src = spec.get("src", {}) if isinstance(spec, dict) else {}
                dest = spec.get("dest", {}) if isinstance(spec, dict) else {}
                self._data_links.append({
                    "kind": kind,
                    "domain": domain,
                    "name": name,
                    "key": _qualified_key(domain, name),
                    "path": f"mmodel://{_qualified_key(domain, name)}",
                    "src": _ref_key(src),
                    "src_ref": dict(src) if isinstance(src, dict) else {},
                    "dest": _ref_key(dest),
                    "dest_ref": dict(dest) if isinstance(dest, dict) else {},
                    "data_link_type": spec.get("data_link_type", "related_to") if isinstance(spec, dict) else "related_to",
                    "fields_mapping": spec.get("fields_mapping", {}) if isinstance(spec, dict) else {},
                    "data_filter": spec.get("data_filter", "") if isinstance(spec, dict) else "",
                    "display_name": _localized(metadata.get("display_name"), name),
                    "description": _localized(metadata.get("description")),
                })
                loaded_count += 1

            elif kind == "storage_link":
                src = spec.get("src", {}) if isinstance(spec, dict) else {}
                dest = spec.get("dest", {}) if isinstance(spec, dict) else {}
                self._storage_links.append({
                    "kind": kind,
                    "domain": domain,
                    "name": name,
                    "key": _qualified_key(domain, name),
                    "path": f"mmodel://{_qualified_key(domain, name)}",
                    "src": _ref_key(src),
                    "src_ref": dict(src) if isinstance(src, dict) else {},
                    "dest": _ref_key(dest),
                    "dest_ref": dict(dest) if isinstance(dest, dict) else {},
                    "priority": spec.get("priority", 0) if isinstance(spec, dict) else 0,
                    "fields_mapping": spec.get("fields_mapping", {}) if isinstance(spec, dict) else {},
                    "filter_by_entity": spec.get("filter_by_entity", "") if isinstance(spec, dict) else "",
                    "display_name": _localized(metadata.get("display_name"), name),
                    "description": _localized(metadata.get("description")),
                })
                loaded_count += 1

        if loaded_count > 0:
            self._loaded = True  # Mark as loaded so YAML parsing is skipped
        return loaded_count > 0

    # ------------------------------------------------------------------
    # Public query API (mirrors OntologyConfigAdapter + graph extensions)
    # ------------------------------------------------------------------

    def list_entity_set_names(self) -> list[str]:
        """Return all known entity set keys (domain.name)."""
        self._ensure_loaded()
        return sorted(self._entity_sets.keys())

    def get_entity_set(self, key: str) -> dict[str, Any] | None:
        """Look up a single entity set by domain.name key."""
        self._ensure_loaded()
        return self._entity_sets.get(key)

    def list_data_sets(self, kind: str | None = None) -> list[dict[str, Any]]:
        """Return supported data set definitions, optionally filtered by kind."""
        self._ensure_loaded()
        results = list(self._data_sets.values())
        if kind:
            results = [item for item in results if item.get("kind") == kind]
        return results

    def list_data_links(
        self,
        entity_set: str | None = None,
        data_set: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return data_link definitions filtered by source entity set or destination data set."""
        self._ensure_loaded()
        results = self._data_links
        if entity_set:
            results = [item for item in results if _matches_ref(item.get("src", ""), entity_set)]
        if data_set:
            results = [item for item in results if _matches_ref(item.get("dest", ""), data_set)]
        return results

    def list_storage_links(self, data_set: str | None = None) -> list[dict[str, Any]]:
        """Return storage_link definitions filtered by source data set."""
        self._ensure_loaded()
        results = self._storage_links
        if data_set:
            results = [item for item in results if _matches_ref(item.get("src", ""), data_set)]
        return results

    def warnings(self) -> list[dict[str, str]]:
        """Return non-fatal YAML loading warnings."""
        self._ensure_loaded()
        return list(self._warnings)

    def list_entity_links(
        self,
        src: str | None = None,
        dest: str | None = None,
        relation_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return entity_set_links filtered by src / dest / relation_type."""
        self._ensure_loaded()
        results = self._entity_links
        if src:
            results = [l for l in results if l["src"] == src]
        if dest:
            results = [l for l in results if l["dest"] == dest]
        if relation_type:
            results = [l for l in results if l["relation_type"] == relation_type]
        return results

    def get_call_graph(self) -> dict[str, Any]:
        """
        Return a lightweight graph dict:
          {
            "nodes": [{"id": "apm.service", "label": "..."}],
            "edges": [{"src": "apm.service", "dest": "apm.service", "type": "calls"}],
          }
        Only includes nodes/edges that appear in entity_set_link.
        """
        self._ensure_loaded()
        node_ids: set[str] = set()
        edges = []
        for link in self._entity_links:
            node_ids.add(link["src"])
            node_ids.add(link["dest"])
            edges.append({
                "src": link["src"],
                "dest": link["dest"],
                "type": link["relation_type"],
                "label": link["display_name"],
            })
        nodes = []
        for nid in sorted(node_ids):
            meta = self._entity_sets.get(nid, {})
            nodes.append({
                "id": nid,
                "label": meta.get("display_name", nid),
                "domain": meta.get("domain", ""),
            })
        return {"nodes": nodes, "edges": edges}

    def stats(self) -> dict[str, int]:
        """Return loading statistics for execution_log display."""
        self._ensure_loaded()
        return {
            "entity_sets": len(self._entity_sets),
            "entity_links": len(self._entity_links),
            "data_sets": len(self._data_sets),
            "data_links": len(self._data_links),
            "storage_links": len(self._storage_links),
            "warnings": len(self._warnings),
        }
