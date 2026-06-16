#!/usr/bin/env python3
"""
MModel Manifest 一致性检查

检查 schemas/manifest.yaml 中声明的 models 与 schemas/core/ 下实际存在的
schema 文件是否一致。
"""

import os
import sys
import yaml
from pathlib import Path


def main():
    project_root = Path(__file__).parent.parent.parent
    manifest_path = project_root / "schemas" / "manifest.yaml"
    core_dir = project_root / "schemas" / "core"

    if not manifest_path.exists():
        print(f"❌ manifest.yaml 不存在: {manifest_path}")
        return 1

    if not core_dir.exists():
        print(f"❌ core 目录不存在: {core_dir}")
        return 1

    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = yaml.safe_load(f)

    manifest_kinds = set()
    for version_entry in manifest.get("versions", []):
        for model_str in version_entry.get("models", []):
            kind = model_str.split(":")[0] if ":" in model_str else model_str
            manifest_kinds.add(kind)

    schema_kinds = set()
    for schema_file in core_dir.rglob("*.schema.yaml"):
        with open(schema_file, 'r', encoding='utf-8') as f:
            try:
                schema = yaml.safe_load(f)
                if schema and "name" in schema:
                    schema_kinds.add(schema["name"])
            except yaml.YAMLError:
                print(f"⚠️  无法解析: {schema_file}")

    missing_in_manifest = schema_kinds - manifest_kinds
    missing_in_schemas = manifest_kinds - schema_kinds

    errors = 0

    print("🔍 Manifest 一致性检查")
    print(f"   manifest.yaml models: {len(manifest_kinds)}")
    print(f"   schemas/core/ files:  {len(schema_kinds)}")
    print()

    if missing_in_manifest:
        errors += len(missing_in_manifest)
        print("❌ 以下 kind 存在于 schemas/core/ 但未列入 manifest.yaml:")
        for kind in sorted(missing_in_manifest):
            print(f"   - {kind}")
        print()

    if missing_in_schemas:
        errors += len(missing_in_schemas)
        print("❌ 以下 kind 列在 manifest.yaml 但在 schemas/core/ 中无对应文件:")
        for kind in sorted(missing_in_schemas):
            print(f"   - {kind}")
        print()

    if errors == 0:
        print("✅ Manifest 与 schema 文件完全一致")
        return 0
    else:
        print(f"❌ 发现 {errors} 处不一致")
        return 1


if __name__ == "__main__":
    sys.exit(main())
