#!/usr/bin/env python3
"""Exercise replay, SQLite state transitions, and actual FastAPI routes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fastapi.testclient import TestClient

from srasta_csi.edge import EdgeRuntime, create_app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.db.exists():
        raise FileExistsError(f"refusing to reuse SQLite evidence at {args.db}")
    runtime = EdgeRuntime(args.model, args.db)
    try:
        replay_status = runtime.replay(args.replay)
        runtime.machine.state = "normal"
        runtime.machine.last_motion_s = None
        suspected = runtime.observe(0.99, runtime.machine.motion_threshold * 2, 1000.0, evidence="synthetic_state_machine_probe")
        confirmed = runtime.tick(1000.0 + runtime.machine.confirm_inactivity_s, evidence="synthetic_state_machine_probe")
        client = TestClient(create_app(runtime))
        responses = {path: client.get(path) for path in ("/health", "/status", "/events?limit=20")}
        if any(response.status_code != 200 for response in responses.values()):
            raise RuntimeError("FastAPI smoke route failed")
        events = responses["/events?limit=20"].json()["events"]
        if not {event["state"] for event in events}.issuperset({"suspected_fall", "confirmed_fall"}):
            raise RuntimeError("synthetic state-machine transitions were not persisted")
        report = {
            "replay": replay_status,
            "synthetic_state_machine_probe": {
                "evidence_scope": "state-machine/SQLite only; not a measured fall from the replay clip",
                "suspected": suspected,
                "confirmed": confirmed,
            },
            "routes": {
                "/health": {"status_code": responses["/health"].status_code, "body": responses["/health"].json()},
                "/status": {"status_code": responses["/status"].status_code, "body": responses["/status"].json()},
                "/events": {"status_code": responses["/events?limit=20"].status_code, "body": responses["/events?limit=20"].json()},
            },
            "persisted_transition_count": sum(event["state"] in {"suspected_fall", "confirmed_fall"} for event in events),
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
