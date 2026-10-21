#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
model="artifacts/releases/20261001-tcn-v8-motion-calibrated/selected/model.tflite"
mode="${1:-simulator}"
if [[ ! -x .venv/bin/python ]]; then
  printf 'Jalankan install_pi_demo.sh terlebih dahulu.\n' >&2
  exit 1
fi
case "$mode" in
  simulator)
    shift || true
    exec .venv/bin/python code/run_edge_service.py --model "$model" --db artifacts/pi/simulator.sqlite3 --demo-mode --env /dev/null --alarm disabled "$@"
    ;;
  live)
    if [[ $# -lt 2 || "$2" != /dev/* || ! -e "$2" ]]; then
      printf 'Pemakaian: bash scripts/run_pi_demo.sh live /dev/serial/by-id/PORT_RX_TERVERIFIKASI\n' >&2
      exit 1
    fi
    rx_port="$2"
    shift 2
    exec .venv/bin/python code/run_edge_service.py --model "$model" --db artifacts/pi/live.sqlite3 --serial "$rx_port" --baud 1000000 --capture-channel 6 --subcarrier-order esp_idf_native --allow-capture-profile-override --max-gap-s .15 --env .env --alarm disabled "$@"
    ;;
  *) printf 'Mode tersedia: simulator atau live.\n' >&2; exit 1 ;;
esac
