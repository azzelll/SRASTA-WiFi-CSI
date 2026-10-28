import json
from pathlib import Path
import tempfile
import unittest

from srasta_csi.capture_archive import CaptureArchive
from test_capture import configuration, independent_review
from test_edge_api import frame
from test_fall_workflow import tool


class LocalCaptureReadinessTests(unittest.TestCase):
    def test_incomplete_archive_is_reported_without_hiding_an_accepted_session(self):
        module = tool("local_capture_readiness")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = CaptureArchive(root, configuration("SES_COMPLETE"))
            for n in range(101):
                archive.record(json.dumps(frame(n, n * 1_000_000)))
            archive.annotate("nonfall_activity", 1_000_000, 100_000_000,
                             observer_id="ANN_001", confirmed=True)
            archive.close(completed=True)
            independent_review(archive)
            broken = root / "sessions" / "SES_INCOMPLETE"
            broken.mkdir()
            config_path = broken / "capture_config.json"
            config = json.loads((archive.path / "capture_config.json").read_text())
            config["session_id"] = broken.name
            config_path.write_text(json.dumps(config))
            original = config_path.read_bytes()

            report = module.readiness(root)

            statuses = {s["session_id"]: s for s in report["sessions"]}
            self.assertEqual(statuses["SES_COMPLETE"]["status"], "accepted")
            self.assertEqual(statuses["SES_INCOMPLETE"]["status"], "rejected")
            self.assertIn("checksums.json", " ".join(statuses["SES_INCOMPLETE"]["issues"]))
            self.assertEqual(report["partitions"]["train"]["subjects"], ["LOC_001"])
            self.assertFalse(report["fall_ready_for_grouped_development"])
            self.assertFalse(report["presence_ready_to_train"])
            self.assertEqual(config_path.read_bytes(), original)
            self.assertEqual([p.name for p in broken.iterdir()], ["capture_config.json"])


if __name__ == "__main__":
    unittest.main()
