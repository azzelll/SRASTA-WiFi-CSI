from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np
from fastapi.testclient import TestClient
from sklearn.ensemble import RandomForestClassifier

from srasta_csi.baseline import FEATURE_NAMES
from srasta_csi.blynk import DisabledBlynkAdapter
from srasta_csi.contract import CaptureProfile
from srasta_csi.edge import EdgeRuntime, StateMachine, create_app
from srasta_csi.preprocess import PreprocessConfig


def frame(sequence: int, timestamp_us: int) -> dict[str, object]:
    return {
        "version": 1, "sequence": sequence, "local_timestamp_us": timestamp_us,
        "sender_mac": "aa:bb:cc:dd:ee:ff", "rssi": -42, "noise_floor": -95,
        "channel": 1, "bandwidth": "HT20", "sig_mode": "HT", "mcs": 0,
        "rx_state": 0, "len": 128, "first_word_invalid": False,
        "iq_bytes": [value for _ in range(64) for value in (0, 10)],
    }


def write_model(root: Path, window_length: int = 4) -> Path:
    x = np.vstack([np.zeros(len(FEATURE_NAMES)), np.ones(len(FEATURE_NAMES))])
    y = np.asarray([0, 1])
    model = RandomForestClassifier(n_estimators=4, random_state=1).fit(x, y)
    profile = CaptureProfile()
    config = PreprocessConfig(capture_profile_hash=profile.hash)
    model_path = root / "model.joblib"
    joblib.dump({
        "artifact_type": "srasta_rf_baseline_v1", "model": model, "window_length": window_length,
        "feature_names": FEATURE_NAMES, "capture_profile_hash": profile.hash,
        "preprocess_config_hash": config.hash,
    }, model_path)
    (root / "preprocess_config.json").write_text(json.dumps(config.to_json()))
    (root / "capture_profile.json").write_text(json.dumps(profile.to_json()))
    return model_path


class EdgeApiTests(unittest.TestCase):
    def test_state_machine_requires_inactivity_tick(self):
        machine = StateMachine(confirm_inactivity_s=10.0)
        self.assertEqual(machine.update(0.9, 0.1, 0.0), ("suspected_fall", True))
        self.assertEqual(machine.tick(9.9), ("suspected_fall", False))
        self.assertEqual(machine.tick(10.0), ("confirmed_fall", True))

    def test_fastapi_routes_quarantine_queue_and_events(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = EdgeRuntime(write_model(root), root / "events.sqlite3", queue_size=1, ring_size=8)
            self.assertTrue(runtime.submit_amplitude(np.zeros(52), 0.0))
            self.assertFalse(runtime.submit_amplitude(np.zeros(52), 0.01))
            self.assertEqual(runtime.status()["dropped_frames"], 1)
            runtime.process_queue()
            self.assertEqual(runtime.ingest_json_line("not-json")["status"], "quarantined")
            runtime.observe(0.9, 0.1, 100.0, evidence="test")
            runtime.tick(110.0, evidence="test")
            client = TestClient(create_app(runtime))
            self.assertEqual(client.get("/health").status_code, 200)
            status = client.get("/status").json()
            self.assertEqual(status["quarantine_count"], 1)
            events = client.get("/events").json()["events"]
            self.assertEqual({event["state"] for event in events}, {"suspected_fall", "confirmed_fall"})
            self.assertNotIn("iq_bytes", json.dumps(events))
            runtime.close()

    def test_jsonl_sequence_gap_reaches_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = EdgeRuntime(write_model(root), root / "events.sqlite3", ring_size=8)
            result = None
            for sequence, timestamp_us in zip((1, 2, 4, 5), (10_000, 20_000, 30_000, 40_000)):
                result = runtime.ingest_json_line(json.dumps(frame(sequence, timestamp_us))) or result
            self.assertIsNotNone(result)
            quality = runtime.status()["packet_quality"]
            self.assertTrue(quality["available"])
            self.assertEqual(quality["accepted_frames"], 4)
            self.assertEqual(quality["missing_packets"], 1)
            self.assertAlmostEqual(quality["packet_drop_rate"], 0.2)
            runtime.close()

    def test_npz_replay_reaches_preprocessing_and_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = EdgeRuntime(write_model(root), root / "events.sqlite3", ring_size=8)
            replay = root / "replay.npz"
            np.savez(replay, amplitude=np.arange(8 * 52, dtype=np.float32).reshape(8, 52), timestamps_s=np.arange(8) / 100)
            status = runtime.replay(replay)
            self.assertEqual(status["replay_source"], "npz")
            self.assertIsNotNone(status["inference_latency_ms"])
            self.assertFalse(status["packet_quality"]["available"])
            runtime.close()

    def test_h5_replay_reaches_preprocessing_and_inference(self):
        import h5py

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = EdgeRuntime(write_model(root), root / "events.sqlite3", ring_size=8)
            replay = root / "replay.h5"
            with h5py.File(replay, "w") as handle:
                handle["CSI_amps"] = np.arange(64 * 8, dtype=np.float32).reshape(64, 8, 1)
            status = runtime.replay(replay)
            self.assertEqual(status["replay_source"], "h5")
            self.assertIsNotNone(status["inference_latency_ms"])
            self.assertFalse(status["packet_quality"]["available"])
            runtime.close()

    def test_blynk_is_rate_limited_and_fail_closed(self):
        adapter = DisabledBlynkAdapter(min_interval_s=30)
        self.assertFalse(adapter.send("event", now_s=100))
        self.assertFalse(adapter.send("event", now_s=101))
        self.assertEqual(adapter.status()["disabled_attempts"], 1)
        self.assertEqual(adapter.status()["rate_limited_attempts"], 1)
        self.assertFalse(adapter.status()["network_delivery_available"])


if __name__ == "__main__":
    unittest.main()
