from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import joblib
import numpy as np

from srasta_csi.monitoring import InactivityMonitor
from srasta_csi.native_features import native_motion_features
from srasta_csi.presence import PresenceInference, presence_features, collect_presence_windows
from train_breathing_baseline import select_rows
from test_edge_api import write_model
from srasta_csi.edge import EdgeRuntime, TFLiteInference, create_app
from fastapi.testclient import TestClient


class MonitoringTests(unittest.TestCase):
    def test_occupancy_and_continuity_required_for_inactivity(self):
        m = InactivityMonitor(threshold_s=3, max_gap_s=1)
        for t in range(10):
            self.assertIsNone(m.observe(present=None, moving=False, timestamp_s=t)["inactive"])
        for t in range(10, 15):
            self.assertFalse(m.observe(present=False, moving=False, timestamp_s=t)["inactive"])
        for t in range(15, 18):
            self.assertFalse(m.observe(present=True, moving=False, timestamp_s=t)["inactive"])
        self.assertTrue(m.observe(present=True, moving=False, timestamp_s=18)["inactive"])
        self.assertFalse(m.observe(present=True, moving=True, timestamp_s=19)["inactive"])
        self.assertIsNone(m.stationary_since_s)

    def test_disconnect_or_clock_reset_starts_new_interval(self):
        for next_time in [50., 0.]:
            m = InactivityMonitor(threshold_s=3)
            for t in range(4):
                m.observe(present=True, moving=False, timestamp_s=t)
            self.assertTrue(m.inactive)
            self.assertFalse(m.observe(present=True, moving=False, timestamp_s=next_time)["inactive"])

    def test_invalid_measurements_are_rejected(self):
        m = InactivityMonitor()
        with self.assertRaises(ValueError):
            m.observe(present=True, moving=False, timestamp_s=float("nan"))
        with self.assertRaises(ValueError):
            m.observe(present=1, moving=False, timestamp_s=0.)

    def test_native_features_are_channel_order_invariant(self):
        rng = np.random.default_rng(42)
        x = np.abs(rng.normal(size=(300, 112)))
        np.testing.assert_allclose(native_motion_features(x, 30), native_motion_features(x[:, ::-1], 30))
        with self.assertRaises(ValueError):
            native_motion_features(-x, 30)

    def test_periodic_motion_has_more_band_energy_than_noise(self):
        t = np.arange(300) / 30
        periodic = np.tile((10 + np.sin(2 * np.pi * .3 * t))[:, None], (1, 8))
        noise = 10 + np.random.default_rng(42).normal(0, .3, (300, 8))
        self.assertGreater(native_motion_features(periodic, 30)[12], native_motion_features(noise, 30)[12] + .5)

    def test_presence_rejects_short_or_discontinuous_clock(self):
        x = np.ones((110, 52))
        times = np.arange(110) / 10
        self.assertEqual(presence_features(x, times).shape, (24,))
        with self.assertRaises(ValueError):
            presence_features(x[:90], times[:90])
        with self.assertRaises(ValueError):
            presence_features(x, times + (times >= 5) * .2)

    def test_public_breathing_artifact_cannot_claim_local_presence(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "public.joblib"
            joblib.dump({"artifact_type": "srasta_public_breathing_native_v1", "research_only": True}, path)
            with self.assertRaises(ValueError):
                PresenceInference(path)

    def test_source_test_and_validation_payloads_excluded_before_selection(self):
        import csv
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "metadata").mkdir()
            (root / "splits").mkdir()
            rows = []
            for user in ["U06", "U23"]:
                for label in ["empty", "sleep"]:
                    for suffix in ["train", "test"]:
                        rows.append({"id": f"{user}_{label}_{suffix}", "user": user, "label": label, "device": "native", "num_sub": "240"})
            with (root / "metadata/sample_metadata.csv").open("w") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            allowed = [r["id"] for r in rows if r["id"].endswith("train")]
            (root / "splits/train_id.json").write_text(json.dumps(allowed))
            selected, _ = select_rows(root, 10)
            self.assertEqual(sum(map(len, selected.values())), 4)
            self.assertTrue(all(r["id"] in allowed for rs in selected.values() for r in rs))

    def test_replay_routes_disclose_unknown_presence_and_reset(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            runtime = EdgeRuntime(write_model(root), root / "db.sqlite3", ring_size=8)
            runtime.submit_amplitude(np.ones(52) * 10, 0.)
            runtime.submit_amplitude(np.ones(52) * 10, .1)
            runtime.process_queue()
            runtime.last_replay_source = "test_fixture"
            snapshot = TestClient(create_app(runtime)).get("/api/caregiver").json()
            self.assertEqual(snapshot["source"], "replay")
            self.assertEqual(snapshot["presence"], "unknown")
            self.assertIsNone(snapshot["inactivity"])
            runtime.monitoring.observe(present=True, moving=False, timestamp_s=1.)
            runtime.reset_capture_session()
            self.assertIsNone(runtime.monitoring.stationary_since_s)
            runtime.close()

    def test_seven_class_motion_head_rejected_by_fall_runtime(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "training_config.json").write_text(json.dumps({"research_only": True, "classes": [str(k) for k in range(7)]}))
            with self.assertRaisesRegex(ValueError, "binary nonfall/fall"):
                TFLiteInference(root / "model.tflite")

    def test_presence_fitting_never_reads_local_test_payload(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            session = root / "sessions/SES_TEST"
            session.mkdir(parents=True)
            (session / "capture_config.json").write_text(json.dumps({"split": "test"}))
            with patch("srasta_csi.presence.qa_capture") as qa:
                self.assertEqual(collect_presence_windows(root), ([], []))
                qa.assert_not_called()

    def test_presence_inactivity_reaches_dashboard_and_event_ledger(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            runtime = EdgeRuntime(write_model(root), root / "db.sqlite3", ring_size=8, inactivity_s=2.)
            runtime.presence_inference = Mock()
            runtime.presence_inference.present.return_value = True
            runtime.last_replay_source = "test_fixture"
            for t in [0., 1., 2.]:
                runtime.presence_frames.append((t, np.ones(52)))
                runtime._infer(np.zeros((4, 52)), t)
            snapshot = TestClient(create_app(runtime)).get("/api/caregiver").json()
            self.assertEqual(snapshot["state"], "inactive")
            self.assertIs(snapshot["inactivity"], True)
            self.assertEqual(snapshot["presence"], "present")
            self.assertEqual(runtime.store.list()[0]["state"], "inactive")
            runtime.presence_inference.present.return_value = False
            runtime._infer(np.zeros((4, 52)), 3.)
            self.assertEqual(runtime.status()["public_state"], "standby")
            runtime.machine.state = "confirmed_fall"
            self.assertEqual(runtime.status()["public_state"], "critical")
            runtime.close()


if __name__ == "__main__":
    unittest.main()
