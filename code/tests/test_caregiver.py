from __future__ import annotations

import json
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient

from srasta_csi.breathing import estimate_breathing
from srasta_csi.camera import AnomalyCamera
from srasta_csi.caregiver import caregiver_snapshot
from srasta_csi.cloud_sync import CloudSync
from srasta_csi.edge import EdgeRuntime, create_app
from srasta_csi.serial_reader import SerialJSONLReader
from test_edge_api import frame, write_model


class CaregiverTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.runtime = EdgeRuntime(write_model(self.root), self.root / "events.sqlite3", demo_mode=True)

    def tearDown(self):
        self.runtime.close()
        self.directory.cleanup()

    def test_five_states_targeted_ack_idempotence_and_durable_receipt(self):
        client = TestClient(create_app(self.runtime))
        for state in ("standby", "normal", "inactive", "anomaly", "critical"):
            self.runtime.set_demo_state(state)
            self.assertEqual(client.get("/api/caregiver").json()["state"], state)
        target = self.runtime.store.list()[1]  # anomaly, not most recent critical
        command = {"id": str(uuid.uuid4()), "event_uid": target["event_uid"], "action": "acknowledge", "expires_at_s": time.time() + 120}
        response = client.post("/api/commands", json=command)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "applied")
        self.assertEqual(client.post("/api/commands", json=command).json(), response.json())
        latest, prior = self.runtime.store.list()[:2]
        self.assertIsNone(latest["acknowledged_at_s"])
        self.assertIsNotNone(prior["acknowledged_at_s"])
        self.assertEqual(self.runtime.status()["public_state"], "critical")
        assist = {**command, "id": str(uuid.uuid4()), "action": "assistance"}
        self.assertFalse(client.post("/api/commands", json=assist).json()["auto_call"])
        client.post("/api/commands", json=assist)
        self.assertEqual(len(self.runtime.store.actions()), 1)
        expired = {**command, "id": str(uuid.uuid4()), "expires_at_s": time.time() - 1}
        self.assertEqual(client.post("/api/commands", json=expired).json()["status"], "expired")
        self.assertEqual(client.post("/api/commands", json={**command, "source": "spoofed"}).status_code, 400)

    def test_summary_never_exposes_payload_or_mac_and_stale_is_not_standby(self):
        self.runtime.demo_mode = False
        self.runtime.transport_status = lambda: {"connected": True}
        self.runtime.ingest_json_line(json.dumps(frame(1, 10_000)))
        self.runtime.last_inference_wall_s = time.time()
        snapshot = caregiver_snapshot(self.runtime)
        self.assertEqual(snapshot["source"], "live")
        self.assertTrue(snapshot["state_verified"])
        self.assertNotIn("iq_bytes", json.dumps(snapshot))
        self.assertNotIn("sender_mac", json.dumps(snapshot))
        self.assertNotIn("amplitude", json.dumps(snapshot))
        self.runtime.last_ingest_monotonic = time.monotonic() - 11
        snapshot = caregiver_snapshot(self.runtime)
        self.assertEqual(snapshot["state"], "normal")
        self.assertFalse(snapshot["monitoring_online"])
        self.assertFalse(snapshot["state_verified"])
        self.assertIsNone(snapshot["fall_confidence"])

    def test_reconnect_allows_reset_sequence_without_confirming_missing_data(self):
        self.runtime.ingest_json_line(json.dumps(frame(40, 400_000)))
        self.runtime.machine.state = "suspected_fall"
        self.runtime.machine.last_motion_s = 0.4
        self.runtime.reset_capture_session()
        result = self.runtime.ingest_json_line(json.dumps(frame(1, 10_000)))
        self.assertIsNone(result)
        self.assertNotEqual(self.runtime.machine.state, "confirmed_fall")
        self.assertEqual(self.runtime.validator.stats()["accepted_frames"], 2)

    def test_cloud_outbox_survives_failure_and_applies_commands_once(self):
        self.runtime.set_demo_state("critical")
        target = self.runtime.store.list()[0]
        seen = []
        command = {"id": str(uuid.uuid4()), "event_uid": target["event_uid"], "action": "assistance", "expires_at_s": time.time() + 120}
        def post(body):
            seen.append(body)
            return {"ok": True, "commands": [command]}
        adapter = CloudSync(self.runtime, "https://example.supabase.co", str(uuid.uuid4()), "x" * 40, post=post)
        with patch.object(adapter, "post", side_effect=OSError("offline")):
            with self.assertRaises(OSError):
                adapter.sync_once()
        self.assertEqual(len(self.runtime.store.cloud_batch()[0]), 1)
        adapter.sync_once()
        adapter.sync_once()
        self.assertEqual(len(self.runtime.store.actions()), 1)
        self.assertEqual(len(seen[1]["receipts"]), 1)
        self.assertNotIn("iq_bytes", json.dumps(seen))
        self.assertNotIn("sender_mac", json.dumps(seen))
        self.assertNotIn("device_token", json.dumps(seen))

    def test_breathing_rejects_bad_quality_and_estimates_periodic_signal(self):
        times = np.arange(3100) / 100
        values = 10 + np.sin(2 * np.pi * 0.3 * times)[:, None] * np.ones((1, 52))
        bpm, quality = estimate_breathing(values, times)
        self.assertAlmostEqual(bpm, 18, delta=1)
        self.assertGreaterEqual(quality, 65)
        self.assertIsNone(estimate_breathing(np.ones_like(values), times)[0])
        self.assertIsNone(estimate_breathing(values[:500], times[:500])[0])
        self.assertIsNone(estimate_breathing(np.random.default_rng(1).normal(size=values.shape), times)[0])

    def test_camera_is_anomaly_only_one_capture_per_event_and_never_simulated(self):
        calls = []
        status = {"public_state": "normal", "simulation_mode": False, "state_source": "model",
                  "transport": {"connected": True}, "stream_age_s": 0, "inferred_at_s": time.time(),
                  "last_event": {"event_uid": "event-a", "timestamp_s": time.time(), "state": "suspected_fall", "evidence": "model"}}
        def capture():
            calls.append(True)
            return np.tile([0.5, 0.5, 0.8], (17, 1))
        camera = AnomalyCamera(lambda: status, capture)
        camera.check_once()
        self.assertEqual(len(calls), 0)
        status["public_state"] = "anomaly"
        camera.check_once(); camera.check_once()
        self.assertEqual(len(calls), 1)
        status["last_event"]["event_uid"] = "event-b"
        status["simulation_mode"] = True
        camera.check_once()
        self.assertEqual(len(calls), 1)
        self.assertFalse(camera.status()["active"])

    def test_serial_buffer_is_bounded_on_garbled_stream(self):
        reader = SerialJSONLReader("unused", 1000000, lambda line: None)
        reader.feed(b"x" * 20000)
        self.assertEqual(len(reader._buffer), 0)

    def test_browser_cannot_trigger_actions_from_an_external_origin(self):
        client = TestClient(create_app(self.runtime))
        self.assertEqual(client.post("/demo/state/critical", headers={"Origin": "https://untrusted.example"}).status_code, 403)
        self.assertEqual(client.get("/api/caregiver", headers={"Host": "untrusted.example"}).status_code, 403)
        self.assertEqual(client.post("/demo/state/normal", headers={"Origin": "http://localhost:5173"}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
