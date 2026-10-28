import json
from pathlib import Path
import tempfile
import unittest

from srasta_csi.capture_archive import CaptureArchive, digest
from srasta_csi.preprocess import PreprocessConfig
from test_capture import configuration, independent_review
from test_edge_api import frame


class LocalFallTests(unittest.TestCase):
    def test_reader_preserves_event_truth_and_uses_corrected_person_before_windowing(self):
        from srasta_csi.local_fall import collect_local_fall_windows

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = CaptureArchive(root, configuration())
            for n in range(701):
                archive.record(json.dumps(frame(n, n * 100_000)))
            archive.annotate("fall", 10_000_000, 12_000_000, observer_id="ANN_001", confirmed=True,
                             post_event_inactivity_start_monotonic_us=12_000_000,
                             post_event_inactivity_end_monotonic_us=25_000_000)
            archive.annotate("nonfall_activity", 30_000_000, 69_000_000,
                             observer_id="ANN_001", confirmed=True)
            archive.close(completed=True)
            independent_review(archive)
            folder = root / "corrections"
            folder.mkdir()
            (folder / "test_participants.json").write_text(json.dumps({
                "schema_version": "srasta.local.participant-correction.v1",
                "split_override": False, "raw_or_archive_modified": False,
                "sessions": [{"session_id": archive.path.name, "participant_group": "C",
                              "original_recorded_subject_id": "LOC_001", "original_split": "train",
                              "checksums_manifest_sha256": digest(archive.path / "checksums.json")}]}))
            protected = {p.name: digest(p) for p in archive.path.iterdir() if p.is_file()}
            # No QA/raw read is permitted for either held-out partition.
            for split in ("test", "validation", "pilot"):
                path = root / "sessions" / ("SES_" + split.upper())
                path.mkdir()
                (path / "capture_config.json").write_text(json.dumps({"split": split}))

            rows, report = collect_local_fall_windows(root, PreprocessConfig(max_gap_s=.15),
                                                     length=500, maximum_negative_windows=2)

            positives = [r for r in rows if r["label"] == 1]
            negatives = [r for r in rows if r["label"] == 0]
            self.assertEqual(len(positives), 1)
            self.assertEqual(len(negatives), 2)
            self.assertEqual({r["subject_id"] for r in rows}, {"LOC_C"})
            self.assertEqual(positives[0]["window"].shape, (500, 52))
            self.assertLessEqual(positives[0]["end_us"], 12_000_000)
            self.assertTrue(all(r["start_us"] >= 30_000_000 for r in negatives))
            self.assertEqual(report["skipped_partitions"], 3)
            self.assertEqual(protected, {p.name: digest(p) for p in archive.path.iterdir() if p.is_file()})


if __name__ == "__main__":
    unittest.main()
