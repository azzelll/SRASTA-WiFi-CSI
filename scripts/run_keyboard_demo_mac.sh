#!/usr/bin/env bash
# Start the Pi -> phone demo from an interactive Mac terminal.
set -euo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
pi_host=srasta@192.168.1.15
pi_key="$repo_dir/artifacts/private/pi-ssh-20261022"
buzzer=passive

usage() {
    echo 'Pemakaian: bash scripts/run_keyboard_demo_mac.sh [--host srasta@IP_PI] [--key FILE] [--mute]'
    echo 'Space: jatuh | R: idle | Q / Ctrl+C: keluar dan pulihkan layanan Pi.'
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --host|--key)
            if [[ $# -lt 2 || -z "$2" ]]; then
                echo "Nilai $1 wajib diisi." >&2
                exit 2
            fi
            if [[ "$1" == --host ]]; then pi_host="$2"; else pi_key="$2"; fi
            shift 2
            ;;
        --mute) buzzer=off; shift ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done

if [[ ! "$pi_host" =~ ^[a-zA-Z0-9_.@:-]+$ || "$pi_host" == -* ]]; then
    echo 'Host SSH tidak valid; gunakan srasta@IP_PI.' >&2
    exit 2
fi
if [[ ! -f "$pi_key" ]]; then
    echo 'Key Pi tidak ditemukan. Gunakan --key dengan key yang sudah terdaftar.' >&2
    exit 1
fi
if [[ ! -t 0 ]]; then
    echo 'Jalankan dari Terminal Mac interaktif agar tombol bisa diteruskan ke Pi.' >&2
    exit 1
fi

echo "Menghubungkan ke $pi_host..."
echo 'Buka https://srasta-caregiver.vercel.app di HP.'
echo 'Tekan Space/R/Q pada terminal Mac ini setelah tulisan IDLE muncul.'
exec ssh -tt -i "$pi_key" \
    -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes \
    -o ConnectTimeout=8 -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \
    "$pi_host" \
    "bash \"\$HOME/SRASTA-WiFi-CSI/scripts/run_keyboard_demo.sh\" --cloud-env \"\$HOME/srasta-edge/edge.env\" --buzzer $buzzer"
