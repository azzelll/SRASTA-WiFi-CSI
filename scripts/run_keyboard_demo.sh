#!/usr/bin/env bash
# Interactive, isolated Pi hardware demo. Restore the live panel on exit.
set -euo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$repo_dir/code${PYTHONPATH:+:$PYTHONPATH}"

if [[ ! -t 0 ]]; then
    echo 'Jalankan dari terminal Pi, atau gunakan ssh -t untuk tombol Space.' >&2
    exit 1
fi

# Share the physical-panel lock with test_devices.sh.
lock_dir="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
exec 9>"$lock_dir/srasta-device-test.lock"
if ! flock -n 9; then
    echo 'Demo/tes perangkat lain masih berjalan.' >&2
    exit 1
fi

/usr/bin/python3 -c 'import RPi.GPIO; import luma.oled; import PIL'
panel_unit=srasta-device-panel.service
panel_was_active="$(systemctl --user is-active "$panel_unit" || true)"
edge_was_active=inactive
for arg in "$@"; do
    if [[ "$arg" == --cloud-env || "$arg" == --cloud-env=* ]]; then
        edge_was_active="$(systemctl --user is-active srasta-edge.service || true)"
    fi
done
demo_pid=

restore_panel() {
    local result=$?
    trap - EXIT INT TERM HUP
    if [[ -n "$demo_pid" ]] && kill -0 "$demo_pid" 2>/dev/null; then
        kill -TERM "$demo_pid" 2>/dev/null || true
        wait "$demo_pid" || true
    fi
    if [[ "$edge_was_active" == active ]]; then
        if ! systemctl --user start srasta-edge.service; then
            echo 'Gagal memulihkan edge: systemctl --user start srasta-edge.service' >&2
            result=1
        fi
    fi
    if [[ "$panel_was_active" == active ]]; then
        if systemctl --user start "$panel_unit"; then
            echo 'Panel otomatis dipulihkan.'
        else
            echo 'Gagal memulihkan panel: systemctl --user start srasta-device-panel.service' >&2
            result=1
        fi
    fi
    exit "$result"
}
trap restore_panel EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

if [[ "$panel_was_active" == active ]]; then
    systemctl --user stop "$panel_unit"
fi
if [[ "$edge_was_active" == active ]]; then
    # One cloud writer per device: the live publisher must not race this demo.
    systemctl --user stop srasta-edge.service
fi
# Explicit stdin redirection preserves keyboard access for the waited child.
/usr/bin/python3 -u -m srasta_csi.keyboard_demo "$@" <&0 &
demo_pid=$!
wait "$demo_pid"
demo_pid=
