#!/usr/bin/env bash
# Run the isolated physical panel test, then restore a previously active panel.
set -euo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
panel_unit=srasta-device-panel.service
lock_dir="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
exec 9>"$lock_dir/srasta-device-test.lock"
if ! flock -n 9; then
    echo 'Tes perangkat lain masih berjalan.' >&2
    exit 1
fi

cd "$repo_dir/code"
/usr/bin/python3 -c 'import RPi.GPIO; import luma.oled; import PIL'
panel_was_active="$(systemctl --user is-active "$panel_unit" || true)"

restore_panel() {
    local result=$?
    trap - EXIT
    if [[ "$panel_was_active" == active ]]; then
        if systemctl --user start "$panel_unit"; then
            echo 'Panel live dipulihkan.'
        else
            echo 'Gagal memulihkan panel; jalankan systemctl --user start srasta-device-panel.service.' >&2
            result=1
        fi
    fi
    exit "$result"
}
trap restore_panel EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ "$panel_was_active" == active ]]; then
    systemctl --user stop "$panel_unit"
fi
echo 'TES 10 DETIK: hijau -> kuning + beep -> merah + beep cepat -> offline.'
echo 'OLED: SIMULASI TES. Ctrl+C menghentikan tes dan memulihkan panel.'
/usr/bin/python3 -u -m srasta_csi.device_panel --buzzer passive --self-test
echo 'Tes selesai. Periksa hasil LED, tulisan OLED, dan bunyi secara langsung.'
