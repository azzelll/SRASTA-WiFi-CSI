#!/usr/bin/env python3
"""Bounded model -> shared preprocessing -> API proof using one primary train H5."""
import argparse
import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from srasta_csi.data import read_manifest, resolve_source_path
from srasta_csi.edge import EdgeRuntime, TFLiteInference, create_app


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--data-root", type=Path, default=Path("data"))
    p.add_argument("--out-dir", type=Path, required=True)
    args = p.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=False)
    rows = read_manifest(args.data_root / "curated/esp32_s3_fall_v1/manifest.csv")
    sample = next(r for r in rows if r.split == "train")
    source = resolve_source_path(sample, args.data_root)
    runtime = EdgeRuntime(args.model, args.out_dir / "replay.sqlite3")
    try:
        runtime.replay(source)
        client = TestClient(create_app(runtime))
        responses = {path: client.get(path) for path in ["/health", "/status", "/api/caregiver", "/events"]}
        assert all(r.status_code == 200 for r in responses.values())
        status = responses["/status"].json()
        snapshot = responses["/api/caregiver"].json()
        assert snapshot["source"] == "replay" and snapshot["simulation"] is True
        assert snapshot["monitoring_online"] is False
        assert snapshot["presence"] == "unknown" and snapshot["inactivity"] is None
        assert 0 <= status["fall_probability"] <= 1
        for forbidden in ["iq_bytes", "sender_mac", "amplitude"]:
            assert forbidden not in json.dumps(snapshot)
        report = {"passed": True, "evidence": "software replay only; no live CSI/new data collection", "sample_id": sample.sample_id, "source_partition": "train", "model_sha256": hashlib.sha256(args.model.read_bytes()).hexdigest(), "routes": {path: r.status_code for path, r in responses.items()}, "fall_probability": status["fall_probability"], "inference_ms": status["inference_latency_ms"], "presence": snapshot["presence"], "inactivity": snapshot["inactivity"], "breathing_condition": snapshot["breathing_condition"], "locked_test_opened": False, "hardware_accuracy_proven": False}
        (args.out_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
