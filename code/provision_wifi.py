#!/usr/bin/env python3
"""Provision the private SRASTA AP password to one board over local USB."""

from __future__ import annotations

import argparse
import os
import select
import time
from pathlib import Path

from srasta_csi.serial_reader import configure_serial


def read_password(path: Path) -> str:
    if not path.is_file():
        raise RuntimeError("local .env is missing")
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("SRASTA_WIFI_PASSWORD="):
            password = line.partition("=")[2].strip()
            if not 8 <= len(password) <= 63 or any(ch.isspace() for ch in password):
                raise RuntimeError("SRASTA_WIFI_PASSWORD must be 8-63 non-whitespace characters")
            return password
    raise RuntimeError("SRASTA_WIFI_PASSWORD is missing from local .env")


def provision(port: str, role: str, password: str, timeout_s: float = 25.0) -> None:
    if not os.path.exists(port):
        raise RuntimeError("requested board port is unavailable")
    marker = f"SRASTA_{role.upper()}_CONFIG_REQUIRED".encode()
    ready = b"SRASTA TX ready" if role == "tx" else b"CSI JSONL ready"
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        configure_serial(fd, 115200 if role == "tx" else 1000000)
        started = time.monotonic()
        deadline = started + timeout_s
        buffer = bytearray()
        sent = False
        while time.monotonic() < deadline:
            readable, _, _ = select.select([fd], [], [], 0.25)
            if readable:
                data = os.read(fd, 4096)
                if not data:
                    raise RuntimeError("board disconnected during provisioning")
                buffer.extend(data)
                if len(buffer) > 8192:
                    del buffer[:-4096]
            if not sent and (marker in buffer or time.monotonic() - started >= 2.0):
                # The one-time prompt may have been emitted before the host opened USB.
                os.write(fd, b"CRED " + password.encode("ascii") + b"\n")
                sent = True
                buffer.clear()
            if ready in buffer:
                print(f"{role.upper()} firmware ready on {port}; credential not shown")
                return
        raise TimeoutError(f"{role.upper()} firmware did not report ready within {timeout_s:g}s")
    finally:
        os.close(fd)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--role", required=True, choices=("tx", "rx"))
    parser.add_argument("--env", type=Path, default=Path(".env"))
    args = parser.parse_args()
    provision(args.port, args.role, read_password(args.env))


if __name__ == "__main__":
    main()
