#!/usr/bin/env python3
"""Inspect a MModel model pack with the generated Python SDK."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_SDK = REPO_ROOT / "sdk" / "python"
if PYTHON_SDK.exists():
    sys.path.insert(0, str(PYTHON_SDK))

from mmodel import (  # noqa: E402
    VERSION,
    get_link_endpoints,
    get_object_metadata,
    get_object_schema,
    is_link_object,
    parse_mmodel_json,
    parse_mmodel_yaml,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect a MModel pack with the generated Python SDK.")
    parser.add_argument("--path", default=str(REPO_ROOT / "examples" / "quickstart-multidomain"), help="model file or directory")
    parser.add_argument("--limit", type=int, default=20, help="maximum rows to print; use 0 for all rows")
    args = parser.parse_args()

    root = Path(args.path)
    if not root.exists():
        parser.error(f"path does not exist: {root}")

    rows = []
    skipped = 0
    for path in iter_model_candidates(root):
        data = path.read_bytes()
        if not looks_like_mmodel(data):
            skipped += 1
            continue

        obj = parse_model(path, data)
        validation_error = obj.validate()
        if validation_error:
            raise RuntimeError(f"{path}: {validation_error}")

        metadata = get_object_metadata(obj)
        schema = get_object_schema(obj)
        row = {
            "path": path.as_posix(),
            "kind": obj.get_kind(),
            "domain": value(metadata, "domain"),
            "name": value(metadata, "name"),
            "schema": value(schema, "version"),
            "link": "",
        }
        if is_link_object(obj):
            src, dest = get_link_endpoints(obj)
            if src and dest:
                row["link"] = f"{src.kind}/{src.name} -> {dest.kind}/{dest.name}"
        rows.append(row)

    print(f"MModel Python SDK {VERSION}")
    suffix = f" ({skipped} non-model files skipped)" if skipped else ""
    print(f"Parsed {len(rows)} MModel files{suffix}")

    counts = Counter(row["kind"] for row in rows)
    for kind in sorted(counts):
        print(f"- {kind}: {counts[kind]}")

    print()
    max_rows = len(rows) if args.limit == 0 else min(args.limit, len(rows))
    for row in rows[:max_rows]:
        if row["link"]:
            print(f"{row['kind']} {row['domain']}/{row['name']} -> {row['link']} ({row['path']})")
        else:
            print(f"{row['kind']} {row['domain']}/{row['name']} schema={row['schema']} ({row['path']})")
    if max_rows < len(rows):
        print(f"... {len(rows) - max_rows} more files")

    return 0


def iter_model_candidates(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    files = []
    for suffix in ("*.json", "*.yaml", "*.yml"):
        files.extend(root.rglob(suffix))
    return sorted(path for path in files if path.is_file())


def parse_model(path: Path, data: bytes) -> Any:
    if path.suffix.lower() == ".json":
        return parse_mmodel_json(data)
    return parse_mmodel_yaml(data)


def looks_like_mmodel(data: bytes) -> bool:
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        payload = yaml.safe_load(data)
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("kind"), str)
        and isinstance(payload.get("metadata"), dict)
        and isinstance(payload.get("schema"), dict)
        and bool(payload["metadata"].get("domain"))
        and bool(payload["metadata"].get("name"))
        and bool(payload["schema"].get("version"))
    )


def value(obj: Any, key: str) -> str:
    if obj is None:
        return ""
    if isinstance(obj, dict):
        return str(obj.get(key, ""))
    return str(getattr(obj, key, ""))


if __name__ == "__main__":
    raise SystemExit(main())
