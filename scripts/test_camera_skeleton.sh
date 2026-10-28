#!/usr/bin/env bash
# Run on the laptop: bounded Pi capture, then open the measured skeleton report.
set -euo pipefail
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${SRASTA_PYTHON:-$repo_dir/.venv/bin/python}"
if [[ ! -x "$python_bin" ]]; then
    echo 'Python proyek belum tersedia; tentukan SRASTA_PYTHON atau siapkan .venv.' >&2
    exit 1
fi
export PYTHONPATH="$repo_dir/code${PYTHONPATH:+:$PYTHONPATH}"
exec "$python_bin" -m srasta_csi.camera_diagnostic "$@"
