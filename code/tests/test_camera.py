from __future__ import annotations

import tempfile
import sqlite3
import time
import unittest
from pathlib import Path

import numpy as np

from srasta_csi.camera import AnomalyCamera, posture_from_keypoints
from srasta_csi.edge import EventStore
from srasta_csi.pose import validate_pose


class CameraTests(unittest.TestCase):
    def test_letterbox_preserves_full_view_and_rgb_channel_order(self):
        from srasta_csi.camera_capture import movenet_image
        rgb = np.zeros((480, 640, 3), dtype=np.uint8)
        rgb[:, :, 0] = 255
        image = np.asarray(movenet_image(rgb))
        self.assertEqual(image.shape, (192, 192, 3))
        self.assertEqual(image[0].max(), 0)
        self.assertEqual(image[23].max(), 0)
        np.testing.assert_array_equal(image[24, 0], [255, 0, 0])
        np.testing.assert_array_equal(image[167, -1], [255, 0, 0])
        self.assertEqual(image[168].max(), 0)

    def test_degenerate_torso_does_not_count_as_upright(self):
        self.assertEqual(posture_from_keypoints(np.tile([.5, .5, .9], (17, 1))),
                         "Keypoint tubuh kurang andal")

    def test_posture_geometry_and_confidence(self):
        points = np.tile([.4, .4, .9], (17, 1))
        points[[11, 12], :2] = [.4, .8]
        self.assertIn("mendatar", posture_from_keypoints(points))
        points[[11, 12], :2] = [.8, .4]
        self.assertIn("belum mendukung", posture_from_keypoints(points))
        points[11, 2] = .1
        self.assertEqual(posture_from_keypoints(points), "Keypoint tubuh kurang andal")

    def test_fresh_live_event_only_and_durable_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.sqlite3"
            store = EventStore(path)
            calls = []
            points = np.tile([.4, .4, .9], (17, 1))
            points[[11, 12], :2] = [.4, .8]
            def capture():
                calls.append(True)
                return points
            event = {"event_uid": "event-camera-a", "state": "suspected_fall", "timestamp_s": time.time(), "evidence": "model"}
            status = {"public_state": "anomaly", "simulation_mode": False, "state_source": "model",
                      "transport": {"connected": True}, "stream_age_s": .1, "inferred_at_s": time.time(), "last_event": event}
            camera = AnomalyCamera(lambda: status, capture, save_result=store.save_camera_validation,
                                   results_provider=store.camera_validations)
            for change in ({"simulation_mode": True}, {"stream_age_s": 12}, {"state_source": "demo_state_mock"}):
                original = status.copy(); status.update(change); camera.check_once(); status.update(original)
            event["evidence"] = "replay_model"; camera.check_once(); event["evidence"] = "model"
            event["timestamp_s"] -= 120; camera.check_once(); event["timestamp_s"] = time.time()
            self.assertEqual(calls, [])
            camera.check_once(); camera.check_once()
            self.assertEqual(len(calls), 1)
            row = camera.status()["validations"][0]
            self.assertEqual(row["event_uid"], event["event_uid"])
            self.assertEqual(row["outcome"], "horizontal")
            self.assertNotIn("keypoints", row)
            self.assertEqual(row["pose"]["format"], "movenet-coco17")
            np.testing.assert_allclose(row["pose"]["keypoints"], points, atol=1e-4)
            self.assertNotIn("image", row)
            store.close()
            reopened = EventStore(path)
            self.assertEqual(reopened.camera_validations(), [row])
            reopened.close()

    def test_capture_failure_is_uncertain_and_camera_becomes_inactive(self):
        status = {"public_state": "anomaly", "simulation_mode": False, "state_source": "model",
                  "transport": {"connected": True}, "stream_age_s": 0, "inferred_at_s": time.time(),
                  "last_event": {"event_uid": "camera-error", "state": "suspected_fall", "timestamp_s": time.time(), "evidence": "model"}}
        def failure():
            raise RuntimeError("sensor busy")
        camera = AnomalyCamera(lambda: status, failure)
        camera.check_once()
        self.assertFalse(camera.status()["active"])
        self.assertEqual(camera.status()["validations"][0]["outcome"], "error")
        self.assertIsNone(camera.status()["validations"][0]["pose"])

    def test_pose_summary_rejects_pixels_unbounded_coordinates_and_coercion(self):
        points = [[.2, .4, .9] for _ in range(17)]
        valid = {"format": "movenet-coco17", "keypoints": points}
        self.assertEqual(validate_pose(valid), valid)
        invalid = [dict(valid, image="pixels"), dict(valid, format="arbitrary"),
                   dict(valid, keypoints=points[:16]), dict(valid, keypoints=points + points)]
        for value in (float("nan"), float("inf"), -0.1, 1.1, True, "0.5"):
            invalid.append(dict(valid, keypoints=[[value, .4, .9]] + points[1:]))
        for item in invalid:
            with self.subTest(item=item), self.assertRaises(ValueError):
                validate_pose(item)

    def test_legacy_camera_database_migrates_without_inventing_pose(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.sqlite3"
            with sqlite3.connect(path) as connection:
                connection.execute("CREATE TABLE camera_validations (event_uid TEXT PRIMARY KEY, checked_at_s REAL NOT NULL, outcome TEXT NOT NULL, result TEXT NOT NULL, latency_ms REAL NOT NULL)")
                connection.execute("INSERT INTO camera_validations VALUES('old-event',1,'uncertain','Old summary',10)")
            store = EventStore(path)
            try:
                prior = store.camera_validations()[0]
                self.assertEqual(prior["result"], "Old summary")
                self.assertIsNone(prior["pose"])
                store.save_camera_validation(dict(prior, event_uid="new-event", pose={
                    "format": "movenet-coco17", "keypoints": [[.2, .4, .9] for _ in range(17)]}))
                self.assertEqual(len(store.camera_validations()), 2)
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
