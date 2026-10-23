#!/usr/bin/env python3
"""Interactive SRASTA video-demo console backed by the local edge API."""

from __future__ import annotations

import argparse
import json
import select
import sys
import termios
import time
import tty
import urllib.error
import urllib.request


RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"


def request_json(url: str, method: str = "GET") -> dict[str, object]:
    request = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(request, timeout=2) as response:
        return json.load(response)


def amplitude_plot(values: list[object]) -> str:
    numbers = [float(value) for value in values if isinstance(value, (int, float))]
    if not numbers:
        return "-"
    levels = " .:-=+*#%@"
    low, high = min(numbers), max(numbers)
    scale = high - low or 1.0
    return "".join(levels[min(int((value - low) / scale * (len(levels) - 1)), len(levels) - 1)] for value in numbers)


def render(status: dict[str, object], csi: dict[str, object], message: str, *, color: bool = True) -> str:
    def paint(text: str, code: str) -> str:
        return f"{code}{text}{RESET}" if color else text

    frames = csi.get("frames")
    frame = frames[-1] if isinstance(frames, list) and frames else {}
    amplitude = frame.get("amplitude", []) if isinstance(frame, dict) else []
    values = [float(value) for value in amplitude if isinstance(value, (int, float))]
    rows = ["  " + " ".join(f"{value:5.1f}" for value in values[index:index + 13]) for index in range(0, len(values), 13)]
    mocked = bool(status.get("demo_override"))
    state = str(status.get("state", "-")).upper()
    display_state = "FALL DETECTED" if state == "CONFIRMED_FALL" else state.replace("_", " ")
    state_color = RED if state == "CONFIRMED_FALL" else YELLOW if state == "SUSPECTED_FALL" else GREEN
    probability = status.get("fall_probability")
    motion = status.get("motion_energy")
    received = status.get("accepted_frames")
    transport = status.get("transport")
    connected = bool(transport.get("connected")) if isinstance(transport, dict) else False
    disclosure = "STAGED DEMO | MANUAL TRIGGER" if mocked else "LIVE MODEL INFERENCE"
    return "\n".join([
        paint(" SRASTA  |  CONTACTLESS FALL MONITORING ", BOLD + CYAN),
        "=" * 88,
        f" SYSTEM STATUS   {paint(display_state, BOLD + state_color)}",
        f" MODE            {paint(disclosure, BOLD + (YELLOW if mocked else GREEN))}",
        f" SENSOR LINK     {paint('CONNECTED' if connected else 'WAITING FOR ESP32', GREEN if connected else YELLOW)}",
        "-" * 88,
        f" MODEL OUTPUT    {str(status.get('model_state', '-')).upper().replace('_', ' '):<18}"
        f" MODEL SCORE  {(float(probability) if isinstance(probability, (int, float)) else 0.0):7.2%}",
        f" MOTION ENERGY   {(float(motion) if isinstance(motion, (int, float)) else 0.0):<18.6f}"
        f" CSI FRAMES   {(int(received) if isinstance(received, int) else 0):7d}",
        "-" * 88,
        paint(" LIVE WIFI CSI ", BOLD + CYAN),
        f" SEQUENCE        {frame.get('sequence', '-') if isinstance(frame, dict) else '-':<18}"
        f" RSSI         {frame.get('rssi_dbm', '-') if isinstance(frame, dict) else '-'} dBm",
        f" CHANNEL         {frame.get('channel', '-') if isinstance(frame, dict) else '-':<18}"
        f" SUBCARRIERS  {len(values):2d}",
        f" AMPLITUDE       {paint(amplitude_plot(amplitude if isinstance(amplitude, list) else []), CYAN)}",
        paint(" 52 SUBCARRIER AMPLITUDES", DIM),
        *(rows or ["  waiting for CSI..."]),
        "-" * 88,
        f" {paint(message, DIM)}",
        paint(" [SPACE] Stage fall  [R] Reset  [Q] Quit", DIM),
    ])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--refresh", type=float, default=0.2)
    args = parser.parse_args()
    if args.refresh <= 0 or not sys.stdin.isatty():
        parser.error("a positive refresh interval and interactive terminal are required")

    original = termios.tcgetattr(sys.stdin)
    message = "Monitoring live CSI and edge-model output."
    try:
        tty.setcbreak(sys.stdin.fileno())
        while True:
            readable, _, _ = select.select([sys.stdin], [], [], args.refresh)
            if readable:
                key = sys.stdin.read(1).lower()
                if key == "q":
                    break
                if key == " ":
                    request_json(f"{args.base_url}/demo/fall", "POST")
                    message = "Staged fall cue activated by operator."
                elif key == "r":
                    request_json(f"{args.base_url}/demo/reset", "POST")
                    message = "Staged cue reset; showing live model state."
            status = request_json(f"{args.base_url}/status")
            csi = request_json(f"{args.base_url}/csi?limit=1")
            print("\033[2J\033[H" + render(status, csi, message), end="", flush=True)
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"\nDemo service unavailable: {exc}", file=sys.stderr)
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, original)
        print()


if __name__ == "__main__":
    main()
