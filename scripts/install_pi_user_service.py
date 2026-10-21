#!/usr/bin/env python3
"""Install an unprivileged live service after the RX port has been verified."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import stat
import subprocess
import sys


def unit_argument(value: object) -> str:
    text = str(value)
    if any(ch in text for ch in "\r\n\0"):
        raise ValueError("Service arguments cannot contain line breaks or NUL")
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--rx-port", type=Path, required=True)
    parser.add_argument("--subcarrier-order", choices=("centered", "esp_idf_native"), default="centered")
    parser.add_argument("--start", action="store_true")
    parser.add_argument("--camera-model", type=Path)
    parser.add_argument("--camera-python", type=Path, default=Path("/usr/bin/python3"))
    parser.add_argument("--keep-current-rx-if-disconnected", action="store_true",
                        help="Only retain a previously managed RX path when that same device is currently unplugged")
    args = parser.parse_args()
    if sys.platform != "linux":
        parser.error("Install this unit on the Raspberry Pi")
    root = args.release.resolve()
    port = args.rx_port.absolute()
    previous_unit = Path.home() / ".config/systemd/user/srasta-edge.service"
    previous = previous_unit.read_text() if previous_unit.is_file() else ""
    retain_missing = (args.keep_current_rx_if_disconnected and not port.exists()
                      and previous.startswith("# Managed by SRASTA Pi demo installer\n")
                      and f'{unit_argument("--serial")} {unit_argument(port)}' in previous)
    if str(port.parent) != "/dev/serial/by-id" or not (retain_missing or (port.exists() and stat.S_ISCHR(port.stat().st_mode))):
        parser.error("Use a currently verified RX character device in /dev/serial/by-id")
    python = root / ".venv/bin/python"
    model = root / "artifacts/releases/20261001-tcn-v8-motion-calibrated/selected/model.tflite"
    manifest = json.loads((root / "deployment_manifest.json").read_text())
    for name, digest in manifest["sha256"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Deployment checksum mismatch: {name}")
    if not python.is_file():
        parser.error("Install the release virtual environment first")
    base = Path.home() / "srasta-edge"
    state = base / "state"
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    env = base / "edge.env"
    if env.exists() and env.stat().st_mode & 0o077:
        parser.error("edge.env must have private 0600 permissions")
    command = [python, root / "code/run_edge_service.py", "--model", model,
               "--db", state / "live.sqlite3", "--serial", port, "--baud", "1000000",
               "--capture-channel", "6", "--subcarrier-order", args.subcarrier_order,
               "--allow-capture-profile-override", "--max-gap-s", ".15",
               "--env", env, "--alarm", "disabled"]
    if args.camera_model:
        camera_model = args.camera_model.resolve()
        if not camera_model.is_relative_to(root) or str(camera_model.relative_to(root)) != manifest.get("camera_model"):
            parser.error("Use the reviewed camera model recorded in deployment_manifest.json")
        if not args.camera_python.is_file():
            parser.error("Camera Python must exist and have OS Picamera2 installed")
        command += ["--camera-model", camera_model, "--camera-python", args.camera_python]
    managed = "# Managed by SRASTA Pi demo installer\n"
    unit = managed + f"""[Unit]
Description=SRASTA CSI edge demo
StartLimitIntervalSec=120
StartLimitBurst=10

[Service]
Type=simple
WorkingDirectory={str(root).replace('%', '%%')}
ExecStart={' '.join(unit_argument(arg) for arg in command)}
Environment=PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
Restart=on-failure
RestartSec=5
TimeoutStopSec=20
UMask=0077
NoNewPrivileges=true

[Install]
WantedBy=default.target
"""
    directory = Path.home() / ".config/systemd/user"
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / "srasta-edge.service"
    if destination.exists() and not destination.read_text().startswith(managed):
        parser.error("Existing service is not managed by SRASTA; inspect it before replacing")
    if destination.exists() and destination.read_text() != unit:
        suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        destination.with_name(destination.name + ".backup-" + suffix).write_text(destination.read_text())
    destination.write_text(unit)
    destination.chmod(0o600)
    subprocess.run(["systemd-analyze", "--user", "verify", str(destination)], check=True)
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "srasta-edge.service"], check=True)
    if args.start:
        subprocess.run(["systemctl", "--user", "restart", "srasta-edge.service"], check=True)
    print(json.dumps({"service": str(destination), "enabled": True, "start_requested": args.start,
                      "rx_port": str(port), "subcarrier_order": args.subcarrier_order,
                      "alarm": "disabled", "live_presence_model": False, "camera_enabled": bool(args.camera_model),
                      "rx_currently_present": port.exists()}))
    print("For startup at boot without SSH login: sudo loginctl enable-linger srasta")


if __name__ == "__main__":
    main()
