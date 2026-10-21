#!/usr/bin/env python3
"""Verify the reviewed handoff snapshots without loading pickle/model code."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    manifest = json.loads((ROOT / "docs/HANDOFF_ASSETS.json").read_text())
    failures = []
    for item in manifest["files"]:
        relative = Path(item["path"])
        candidate = ROOT / relative
        if relative.is_absolute() or ".." in relative.parts or candidate.is_symlink():
            failures.append(f"unsafe path: {relative}")
            continue
        if not candidate.is_file():
            failures.append(f"missing: {relative}")
            continue
        payload = candidate.read_bytes()
        if len(payload) != item["bytes"] or hashlib.sha256(payload).hexdigest() != item["sha256"]:
            failures.append(f"changed: {relative}")
    for failure in failures:
        print(failure, file=sys.stderr)
    print(json.dumps({"status": "failed" if failures else "passed", "checked": len(manifest["files"]), "failures": len(failures)}))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
