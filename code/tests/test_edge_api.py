from __future__ import annotations

import asyncio
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
from srasta_csi.contract import CaptureProfile, FrameValidator
from srasta_csi.edge import EdgeRuntime, StateMachine, create_app, stream_csi
from srasta_csi.preprocess import PreprocessConfig
from srasta_csi.serial_reader import SerialJSONLReader
from run_demo_console import render


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
    def test_demo_console_is_video_friendly_and_discloses_manual_trigger(self):
        status = {
            "state": "confirmed_fall", "state_source": "demo_spacebar_mock",
            "model_state": "normal", "demo_override": True,
            "fall_probability": 0.42, "motion_energy": 0.001,
            "accepted_frames": 123, "transport": {"connected": True},
        }
        csi = {"frames": [{"sequence": 9, "rssi_dbm": -44, "channel": 1, "amplitude": list(range(52))}]}
        output = render(status, csi, "Staged fall cue activated by operator.", color=False)
        self.assertIn("FALL DETECTED", output)
        self.assertIn("STAGED DEMO | MANUAL TRIGGER", output)
        self.assertIn("LIVE WIFI CSI", output)
        self.assertNotIn("DEMO_SPACEBAR_MOCK", output)

    def test_serial_reader_reassembles_jsonl_and_ignores_logs(self):
        lines = []
        reader = SerialJSONLReader("test", 115200, lines.append)
        reader.feed(b"I (1) boot log\n{\"version\":")
        reader.feed(b"1}\n")
        self.assertEqual(lines, ['{"version":1}'])
        self.assertEqual(reader.status()["ignored_lines"], 1)
        self.assertFalse(reader.status()["connected"])

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
            runtime.ingest_json_line(json.dumps(frame(1, 10_000)))
            status = client.get("/status").json()
            self.assertEqual(status["quarantine_count"], 1)
            events = client.get("/events").json()["events"]
            self.assertEqual({event["state"] for event in events}, {"suspected_fall", "confirmed_fall"})
            self.assertNotIn("iq_bytes", json.dumps(events))
            csi = client.get("/csi?limit=1").json()
            self.assertEqual(csi["representation"], "decoded_amplitude")
            self.assertEqual(csi["feature_count"], 52)
            self.assertEqual(len(csi["usable_subcarrier_indices"]), 52)
            self.assertEqual(len(csi["frames"][0]["amplitude"]), 52)
            self.assertNotIn("iq_bytes", json.dumps(csi))
            self.assertNotIn("sender_mac", json.dumps(csi))
            self.assertIn("/csi/stream", client.get("/openapi.json").json()["paths"])
            async def read_event() -> str:
                stream = stream_csi(runtime, 0)
                try:
                    return await anext(stream)
                finally:
                    await stream.aclose()
            event = asyncio.run(read_event())
            self.assertIn("event: csi", event)
            self.assertIn('"amplitude"', event)
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

    def test_serial_producer_can_enqueue_without_running_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = EdgeRuntime(write_model(root), root / "events.sqlite3", ring_size=16, auto_process_frames=False)
            calls = []
            original = runtime.inference.probability
            runtime.inference.probability = lambda window: calls.append(window.copy()) or original(window)
            for sequence in range(1, 9):
                runtime.ingest_json_line(json.dumps(frame(sequence, sequence * 10_000)))
            self.assertEqual(len(calls), 0)
            self.assertEqual(runtime.frame_queue.qsize(), 8)
            self.assertEqual(runtime.csi(8)["frame_count"], 8)
            self.assertIsNotNone(runtime.process_queue())
            self.assertEqual(len(calls), 1)
            self.assertEqual(runtime.frame_queue.qsize(), 0)
            self.assertIsNone(runtime.process_queue())
            runtime.ingest_json_line(json.dumps(frame(9, 90_000)))
            runtime.reset_capture_session()
            self.assertIsNone(runtime.process_queue())
            self.assertEqual(len(runtime.frames), 0)
            runtime.close()

    def test_timestamp_gap_starts_a_new_inference_window(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = EdgeRuntime(write_model(root), root / "events.sqlite3", ring_size=8)
            result = None
            for sequence, timestamp_us in enumerate((10_000, 20_000, 100_000, 110_000, 120_000, 130_000), 1):
                result = runtime.ingest_json_line(json.dumps(frame(sequence, timestamp_us))) or result
            self.assertIsNotNone(result)
            self.assertIsNotNone(runtime.status()["inference_latency_ms"])
            self.assertEqual(runtime.status()["quarantine_count"], 1)
            runtime.close()

    def test_rf_rejects_live_gap_override(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "TFLite engineering candidate"):
                EdgeRuntime(write_model(root), root / "events.sqlite3", max_gap_s=0.15)

    def test_rf_rejects_capture_profile_override(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            validator = FrameValidator(CaptureProfile(channel=11))
            with self.assertRaisesRegex(ValueError, "active runtime profile"):
                EdgeRuntime(write_model(root), root / "events.sqlite3", validator=validator, allow_capture_profile_override=True)

    def test_demo_override_is_explicit_and_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = EdgeRuntime(write_model(root), root / "events.sqlite3", demo_mode=True)
            runtime.machine.state = "normal"
            client = TestClient(create_app(runtime))
            runtime.observe(1.0, 1.0, 1.0)
            runtime.tick(20.0)
            self.assertEqual(client.get("/status").json()["state"], "normal")
            triggered = client.post("/demo/fall").json()
            self.assertEqual(triggered["state"], "confirmed_fall")
            self.assertEqual(triggered["model_state"], "normal")
            self.assertEqual(triggered["state_source"], "demo_spacebar_mock")
            self.assertTrue(triggered["demo_override"])
            runtime.observe(1.0, 1.0, 21.0)
            self.assertEqual(client.get("/status").json()["state"], "confirmed_fall")
            reset = client.post("/demo/reset").json()
            self.assertEqual(reset["state"], "normal")
            self.assertFalse(reset["demo_override"])
            self.assertEqual({event["evidence"] for event in runtime.store.list()}, {"demo_spacebar_mock", "demo_reset"})
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

    def test_demo_state_actions_and_acknowledgement_persist(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = EdgeRuntime(write_model(root), root / "events.sqlite3", demo_mode=True)
            client = TestClient(create_app(runtime))
            for state in ("standby", "normal", "inactive", "anomaly", "critical"):
                response = client.post(f"/demo/state/{state}")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["public_state"], state)
            self.assertTrue(client.get("/status").json()["local_alarm_on"])
            self.assertTrue(client.post("/acknowledge").json()["acknowledged"])
            self.assertTrue(client.post("/assistance").json()["assistance_requested"])
            self.assertFalse(client.get("/actions").json()["actions"][0]["action"] == "auto_call")
            self.assertEqual(client.get("/events").json()["events"][0]["ack_source"], "local_dashboard")
            runtime.close()


if __name__ == "__main__":
    unittest.main()
