"""Manual Pi -> authenticated summary transport; no real cloud or GPIO."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch

from srasta_csi.keyboard_demo_cloud import KeyboardDemoCloud, MODEL_LABEL, cloud_from_env, demo_snapshot


class KeyboardCloudTests(unittest.TestCase):
    def publisher(self, post):
        return KeyboardDemoCloud("https://example.supabase.co", str(uuid.uuid4()), "x" * 40, post=post)

    def test_idle_fall_reset_and_stop_follow_summary_contract_without_alert_inserts(self):
        sent = []
        publisher = self.publisher(lambda body: sent.append(body) or {"ok": True, "commands": []})
        publisher.sync_once()
        publisher.set_fallen(True)
        publisher.sync_once()
        publisher.set_fallen(False)
        publisher.sync_once()
        publisher.close()
        self.assertEqual([body["snapshot"]["state"] for body in sent], ["normal", "critical", "normal", "normal"])
        self.assertEqual(sent[-1]["snapshot"]["source"], "unavailable")
        for body in sent:
            self.assertEqual(body["events"], [])
            self.assertEqual(body["receipts"], [])
            snapshot = body["snapshot"]
            self.assertTrue(snapshot["simulation"])
            self.assertEqual(snapshot["model"]["label"], MODEL_LABEL)
            self.assertFalse(snapshot["serial_connected"])
            self.assertFalse(snapshot["monitoring_online"])
            self.assertIsNone(snapshot["fall_confidence"])
            self.assertEqual(snapshot["accepted_frames"], 0)
            self.assertFalse(snapshot["camera"]["active"])
        self.assertNotIn("device_token", json.dumps(sent))
        self.assertNotIn("iq_bytes", json.dumps(sent))

    def test_offline_error_is_sanitized_and_retry_publishes_latest_state(self):
        publisher = self.publisher(lambda _: {"ok": True, "commands": []})
        with patch.object(publisher, "post", side_effect=OSError("private-token-and-url")):
            with self.assertRaises(OSError):
                publisher.sync_once()
        self.assertFalse(publisher.status()["connected"])
        self.assertNotIn("private-token", publisher.status()["last_error"])
        publisher.set_fallen(True)
        sent = []
        publisher.post = lambda body: sent.append(body) or {"ok": True, "commands": []}
        publisher.sync_once()
        self.assertTrue(publisher.status()["connected"])
        self.assertEqual(sent[0]["snapshot"]["state"], "critical")
        self.assertIsNone(publisher.status()["last_error"])

    def test_change_during_inflight_request_is_published_next_without_waiting_for_heartbeat(self):
        entered, release, fallen = threading.Event(), threading.Event(), threading.Event()
        def post(body):
            if not entered.is_set():
                entered.set()
                release.wait(3)
            if body["snapshot"]["state"] == "critical":
                fallen.set()
            return {"ok": True, "commands": []}
        publisher = self.publisher(post)
        publisher.interval_s = 60
        publisher.start()
        try:
            self.assertTrue(entered.wait(2))
            publisher.set_fallen(True)
            release.set()
            self.assertTrue(fallen.wait(2))
        finally:
            release.set()
            publisher.close()
        self.assertFalse(publisher.thread.is_alive())

    def test_config_fails_closed_before_startup_when_missing_or_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "edge.env"
            path.write_text("# no secrets\n")
            with patch.dict("os.environ", {}, clear=True):
                with self.assertRaisesRegex(ValueError, "belum lengkap"):
                    cloud_from_env(path)
        with self.assertRaises(ValueError):
            KeyboardDemoCloud("http://example.supabase.co", str(uuid.uuid4()), "x" * 40)
        self.assertEqual(demo_snapshot(True, now=1)["source"], "simulator")


if __name__ == "__main__":
    unittest.main()
