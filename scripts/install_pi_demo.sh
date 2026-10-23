#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 - <<'PY'
import hashlib, json, platform, struct, sys
from pathlib import Path
if platform.machine() != 'aarch64' or struct.calcsize('P') != 8:
    raise SystemExit('Install Raspberry Pi OS 64-bit for this deployment.')
if sys.version_info[:2] != (3, 13):
    raise SystemExit('This pinned demo environment requires Python 3.13; inspect before changing versions.')
root = Path.cwd().resolve()
manifest = json.loads((root / 'deployment_manifest.json').read_text())
for name, digest in manifest['sha256'].items():
    path = (root / name).resolve()
    if not path.is_relative_to(root) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise SystemExit(f'Deployment checksum mismatch: {name}')
print(f"Verified {len(manifest['sha256'])} deployment files")
PY
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi
.venv/bin/python - <<'PY'
import sys
if sys.version_info[:2] != (3, 13):
    raise SystemExit('The release venv must use Python 3.13.')
PY
if [[ -d wheelhouse ]]; then
  .venv/bin/python -m pip install --no-index --find-links wheelhouse --only-binary=:all: -r code/requirements-pi-demo.txt
else
  .venv/bin/python -m pip install --only-binary=:all: -r code/requirements-pi-demo.txt
fi
.venv/bin/python -m pip check
mkdir -p artifacts/pi
.venv/bin/python code/pi_acceptance.py --output artifacts/pi/software_acceptance.json
.venv/bin/python -m pip freeze > artifacts/pi/installed_versions.txt
printf '\nPaket siap. Uji API: bash scripts/run_pi_demo.sh simulator\n'
