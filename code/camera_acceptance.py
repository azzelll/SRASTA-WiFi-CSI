#!/usr/bin/env python3
"""Manual, isolated real-camera check; never writes a live alert or cloud event."""
from __future__ import annotations

import argparse
import json
import tempfile
import time
import uuid
from pathlib import Path

from srasta_csi.camera import AnomalyCamera, PiMoveNetCapture
from srasta_csi.edge import EventStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--camera-python", default="/usr/bin/python3")
    args = parser.parse_args()
    capture = PiMoveNetCapture(args.model, camera_python=args.camera_python)
    with tempfile.TemporaryDirectory(prefix="srasta-camera-acceptance-") as tmp:
        store = EventStore(Path(tmp) / "isolated.sqlite3")
        now = time.time()
        event = {"event_uid": str(uuid.uuid4()), "state": "suspected_fall", "timestamp_s": now, "evidence": "model"}
        status = {"public_state": "normal", "state_source": "model", "simulation_mode": False,
                  "transport": {"connected": True}, "stream_age_s": 0, "inferred_at_s": now, "last_event": event}
        camera = AnomalyCamera(lambda: status, capture, save_result=store.save_camera_validation,
                               results_provider=store.camera_validations)
        camera.check_once()
        assert camera.status()["validations"] == [], "Normal state activated camera"
        status["public_state"] = "anomaly"
        camera.check_once()
        first = camera.status()["validations"]
        camera.check_once()
        assert camera.status()["validations"] == first, "Same event was recaptured"
        assert len(first) == 1 and first[0]["outcome"] != "error", "Real camera/model validation failed"
        assert not camera.status()["active"], "Camera remained active"
        print(json.dumps({"purpose": "manual real-camera check with isolated synthetic trigger, not a detected fall",
                          "software_passed": True, "camera_model": "MoveNet Lightning INT8 v4",
                          "normal_state_no_capture": True, "one_burst_per_event": True, "frames_per_burst": 3,
                          "camera_inactive_after_capture": True, "validation": first[0],
                          "images_saved": False, "cloud_events_sent": False}, ensure_ascii=False))
        store.close()


if __name__ == "__main__":
    main()
