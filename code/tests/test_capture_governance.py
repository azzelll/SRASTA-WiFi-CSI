import json
from pathlib import Path
import tempfile
import unittest

from srasta_csi.capture_archive import CaptureArchive, digest, qa_capture, utc_now
from test_capture import configuration, independent_review
from test_edge_api import frame


class CaptureGovernanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = CaptureArchive(self.root, {**configuration(), "authority_ref": ""})
        for n in range(101):
            self.archive.record(json.dumps(frame(n, n * 1_000_000)))
        self.archive.annotate("nonfall_activity", 1_000_000, 100_000_000,
                              observer_id="ANN_001", confirmed=True)
        self.archive.close(completed=True)
        independent_review(self.archive)

    def approval(self):
        path = self.archive.path
        folder = self.root / "data_use_approvals"
        folder.mkdir(exist_ok=True)
        approval = {"schema_version": "srasta.capture.data-use.v1", "approval_id": "DUA_TEST",
                    "decision": "approved", "scope": "local_model_development",
                    "recorded_at_utc": utc_now(), "source": "owner_team_attestation",
                    "statement": "TEST FIXTURE: team approves use now, no prior procedure claimed",
                    "sessions": [{"session_id": path.name,
                                  "capture_config_sha256": digest(path / "capture_config.json"),
                                  "events_sha256": digest(path / "events.jsonl"),
                                  "checksums_sha256": digest(path / "checksums.json")} ]}
        target = folder / "DUA_TEST.json"
        target.write_text(json.dumps(approval))
        return target

    def test_current_data_use_approval_accepts_reviewed_archive_without_rewriting_capture(self):
        self.assertEqual(qa_capture(self.archive.path)["status"], "pending")
        before = {p.name: digest(p) for p in self.archive.path.iterdir() if p.is_file()}
        self.approval()
        report = qa_capture(self.archive.path)
        self.assertEqual(report["status"], "accepted")
        self.assertEqual(report["data_use_approval"]["approval_id"], "DUA_TEST")
        self.assertEqual(before, {p.name: digest(p) for p in self.archive.path.iterdir() if p.is_file()})

    def test_approval_cannot_replace_an_observer_review(self):
        self.approval()
        (self.archive.path / "reviews.jsonl").unlink()
        report = qa_capture(self.archive.path)
        self.assertEqual(report["status"], "pending")
        self.assertIn("independent observer review is required", report["pending_reasons"])

    def test_approval_bound_to_different_archive_is_rejected(self):
        path = self.approval()
        value = json.loads(path.read_text())
        value["sessions"][0]["events_sha256"] = "0" * 64
        path.write_text(json.dumps(value))
        self.assertEqual(qa_capture(self.archive.path)["status"], "rejected")

    def test_approved_use_does_not_hide_raw_corruption(self):
        self.approval()
        with (self.archive.path / "frames.jsonl").open("a") as stream:
            stream.write((self.archive.path / "frames.jsonl").read_text().splitlines()[-1] + "\n")
        self.assertEqual(qa_capture(self.archive.path)["status"], "rejected")

    def test_revoked_use_keeps_archive_pending(self):
        path = self.approval()
        value = json.loads(path.read_text())
        value["decision"] = "revoked"
        path.write_text(json.dumps(value))
        self.assertEqual(qa_capture(self.archive.path)["status"], "pending")

    def test_confirmed_participant_correction_is_visible_to_training_reader(self):
        from srasta_csi.capture_governance import participant_identity

        folder = self.root / "corrections"
        folder.mkdir()
        (folder / "test_participants.json").write_text(json.dumps({
            "schema_version": "srasta.local.participant-correction.v1",
            "split_override": False, "raw_or_archive_modified": False,
            "sessions": [{"session_id": self.archive.path.name,
                          "participant_group": "B", "original_recorded_subject_id": "LOC_001",
                          "original_split": "train",
                          "checksums_manifest_sha256": digest(self.archive.path / "checksums.json")}]}))
        identity = participant_identity(self.archive.path)
        self.assertEqual(identity["subject_id"], "LOC_B")
        self.assertEqual(identity["original_subject_id"], "LOC_001")
        self.assertEqual(identity["split"], "train")


if __name__ == "__main__":
    unittest.main()
