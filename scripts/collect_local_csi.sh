#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_dir"
python_bin="${SRASTA_PYTHON:-$repo_dir/.venv/bin/python}"
if [[ ! -x "$python_bin" ]]; then
  echo "Python proyek belum tersedia. Ikuti RUNBOOK_LOCAL.md untuk menyiapkan .venv." >&2
  exit 1
fi
if [[ "$(uname -s)" == "Darwin" ]] && command -v caffeinate >/dev/null 2>&1; then
  exec caffeinate -i "$python_bin" code/tools/record_esp32_capture.py "$@"
fi
exec "$python_bin" code/tools/record_esp32_capture.py "$@"
