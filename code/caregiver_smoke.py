#!/usr/bin/env python3
"""Exercise the running local caregiver API in explicitly enabled simulator mode."""
from __future__ import annotations

import json
import argparse
import time
import uuid
import urllib.request
from pathlib import Path


BASE_URL = "http://127.0.0.1:8000"


def request(path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(BASE_URL + path, data=data, headers={"Content-Type": "application/json"}, method="GET" if data is None else "POST")
    with urllib.request.urlopen(req, timeout=5) as response:
        return json.load(response)


def main():
    global BASE_URL
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535: parser.error("port must be in 1..65535")
    BASE_URL = f"http://127.0.0.1:{args.port}"
    initial = request("/api/caregiver")
    if initial["source"] != "simulator":
        raise RuntimeError("smoke refuses to inject states into a live/replay service")
    checked = []
    for state in ("standby", "normal", "inactive", "anomaly", "critical"):
        request("/demo/state/" + state, {})
        snapshot = request("/api/caregiver")
        assert snapshot["state"] == state and snapshot["simulation"] is True
        assert all(field not in json.dumps(snapshot) for field in ("iq_bytes", "sender_mac", "amplitude"))
        checked.append(state)
    event = snapshot["events"][0]
    cmd = {"id": str(uuid.uuid4()), "event_uid": event["event_uid"], "action": "acknowledge", "expires_at_s": time.time() + 120}
    receipt = request("/api/commands", cmd)
    assert receipt["status"] == "applied"
    assert request("/api/commands", cmd) == receipt
    assert request("/api/caregiver")["state"] == "critical"
    assistance = {**cmd, "id": str(uuid.uuid4()), "action": "assistance"}
    assisted = request("/api/commands", assistance)
    assert assisted["status"] == "applied" and assisted["auto_call"] is False
    assert request("/api/commands", assistance) == assisted
    with urllib.request.urlopen(BASE_URL + "/api/caregiver/stream", timeout=5) as stream:
        assert stream.readline().decode().strip() == "event: snapshot"
        streamed = json.loads(stream.readline().decode().removeprefix("data: "))
        assert streamed["state"] == "critical" and streamed["source"] == "simulator"
    request("/demo/state/normal", {})
    report = {"checked_at_s": time.time(), "source": "simulator", "states": checked, "targeted_ack": "pass", "idempotence": "pass", "assistance": "pass", "auto_call": False, "sse": "pass", "raw_data_excluded": True, "hardware_or_remote_proof": False}
    path = Path("artifacts/caregiver_api_smoke.json")
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
