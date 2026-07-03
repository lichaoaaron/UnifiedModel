#!/usr/bin/env python3
"""Architecture guard for the UModel open-source project."""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys
import os


ROOT = pathlib.Path(__file__).resolve().parents[2]
TEXT_SUFFIXES = {
    ".go",
    ".yaml",
    ".yml",
    ".json",
    ".py",
    ".sh",
}

FORBIDDEN_PATTERNS = [
    (re.compile(r"/api/v1/workspaces/\{?workspace\}?/(start|stop|restart|backup|restore)"), "workspace lifecycle API is forbidden"),
    (re.compile(r"\bumodelassistant\b", re.IGNORECASE), "UModelAssistant is not part of the current open-source runtime"),
    (re.compile(r"/api/v1/(entities|relations|graph|related|neighbors)\b"), "domain read APIs must go through Query Service"),
    (re.compile(r"\bumctl\s+(entity|get|list|search|topo\s+neighbors|topo\s+subgraph)"), "CLI domain read commands are forbidden"),
]

PROVIDER_IMPORT = re.compile(r'internal/graphstore/provider/(ladybug|cloud|custom)')
ALLOWED_PROVIDER_IMPORTS = {
    "internal/bootstrap/app.go",
    "internal/graphstore/provider/ladybug/provider_stub.go",
    "internal/graphstore/provider/ladybug/provider_ladybug.go",
}


def iter_files() -> list[pathlib.Path]:
    # .claude holds gitignored local agent artifacts — nested git worktrees of
    # other branches and copies of tooling — which are not the source tree under
    # review and would otherwise trip the path-exact self-exclusion / allowlist.
    ignored_parts = {".git", ".venv", "__pycache__", "node_modules", ".claude", "dist", ".cache"}
    files: list[pathlib.Path] = []
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        result = None
    if result and result.returncode == 0:
        for rel in result.stdout.splitlines():
            path = ROOT / rel
            if path.suffix in TEXT_SUFFIXES and not ignored_parts.intersection(path.parts):
                files.append(path)
        return files

    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [dirname for dirname in dirnames if dirname not in ignored_parts]
        current = pathlib.Path(dirpath)
        for filename in filenames:
            path = current / filename
            if path.suffix in TEXT_SUFFIXES:
                files.append(path)
    return files


def main() -> int:
    errors: list[str] = []
    for path in iter_files():
        rel = path.relative_to(ROOT).as_posix()
        if rel == "tools/guards/architecture_guard.py":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern, reason in FORBIDDEN_PATTERNS:
            if pattern.search(text):
                errors.append(f"{rel}: {reason}")
        if PROVIDER_IMPORT.search(text) and rel not in ALLOWED_PROVIDER_IMPORTS:
            errors.append(f"{rel}: business modules must not import provider implementation packages")

    if errors:
        print("Architecture guard failed:")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("Architecture guard passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
