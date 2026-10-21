#!/usr/bin/env python3
"""Predict one actual public-source recording, with explicit research provenance."""
import argparse
import json
from pathlib import Path

from srasta_csi.public_occupancy import PublicOccupancyInference, load_amplitude, source_rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--source", type=Path, default=Path("data/csi-bench"))
    p.add_argument("--task", choices=["BreathingDetection", "HumanActivityRecognition"], default="BreathingDetection")
    p.add_argument("--recording-id", required=True)
    args = p.parse_args()
    model = PublicOccupancyInference(args.model)
    if model.payload["task"] == "breathing" and args.task != "BreathingDetection":
        p.error("sleep/empty head cannot classify awake HAR recordings")
    rows, allowed = source_rows(args.source, args.task)
    row = next((r for r in rows if r["id"] == args.recording_id), None)
    if row is None:
        p.error("recording must belong to official source-train")
    values, rate = load_amplitude(args.source, row, allowed, model.payload["layout"])
    print(json.dumps(dict(model.predict(values, rate), recording_id=row["id"], source_label=row["label"]), indent=2))


if __name__ == "__main__":
    main()
