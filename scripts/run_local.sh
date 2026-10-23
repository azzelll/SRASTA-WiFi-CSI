#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mode="${1:-simulator}"
if [[ $# -gt 0 ]]; then shift; fi
python_bin="${SRASTA_PYTHON:-.venv/bin/python}"
model_path="${SRASTA_MODEL:-artifacts/releases/20261001-tcn-v8-motion-calibrated/selected/model.tflite}"
if [[ ! -x "$python_bin" || ! -f "$model_path" ]]; then
  echo "Virtualenv/model belum tersedia. Ikuti RUNBOOK_LOCAL.md dan tentukan SRASTA_MODEL." >&2
  exit 1
fi
if [[ ! -f web/dist/index.html ]]; then (cd web && npm ci --no-audit --no-fund && npm run build); fi
case "$mode" in
  simulator)
    # Development-only DB and no external adapters by default.
    exec "$python_bin" code/run_edge_service.py --model "$model_path" --db artifacts/caregiver_simulator.sqlite3 --demo-mode --env /dev/null "$@"
    ;;
  live)
    serial_port="${1:?Usage: bash scripts/run_local.sh live /dev/cu.RX_PORT [options]}"; shift
    exec "$python_bin" code/run_edge_service.py --model "$model_path" --db artifacts/caregiver_live.sqlite3 --serial "$serial_port" --baud 1000000 --capture-channel 6 --subcarrier-order esp_idf_native --allow-capture-profile-override --max-gap-s 0.15 "$@"
    ;;
  replay)
    replay_file="${1:?Usage: bash scripts/run_local.sh replay path.h5 [options]}"; shift
    exec "$python_bin" code/run_edge_service.py --model "$model_path" --db artifacts/caregiver_replay.sqlite3 --replay "$replay_file" --env /dev/null "$@"
    ;;
  *) echo "Mode: simulator | live <RX port> | replay <file>" >&2; exit 1;;
esac
