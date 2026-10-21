from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from unittest.mock import Mock

from srasta_csi.capture_archive import CaptureArchive, archive_projection, canonical, digest, qa_capture, read_jsonl
from srasta_csi.capture_metrics import false_alert_report, subtract_intervals
from srasta_csi.contract import CaptureProfile, FrameValidator
from test_edge_api import frame, write_model


def configuration(session="SES_TEST_001", subject="LOC_001", split="train"):
    return {"session_id": session, "subject_id": subject, "site_id": "SITE_001", "room_id": "ROOM_001", "split": split,
            "channel": 1, "firmware_revision": "TEST_ONLY_NOT_HARDWARE", "maximum_packet_gap_s": 1.5,
            "inactivity_min_s": 60, "authority_ref": "TEST_FIXTURE", "independent_local_cohort_attested": True,
            "prediction_interval_s": .2, "model_sha256": "test-model"}


def independent_review(archive):
    events = read_jsonl(archive.path / "events.jsonl")
    with (archive.path / "reviews.jsonl").open("w") as stream:
        for event in events:
            stream.write(canonical({"event_id": event["event_id"], "reviewer_id": "ANN_002", "agrees": True, "events_sha256": digest(archive.path / "events.jsonl")}) + "\n")


class CaptureTests(unittest.TestCase):
    def test_native_profile_preserves_bytes_and_archive_qa_order(self):
        archive = CaptureArchive(self.root, {**configuration(), "subcarrier_order": "esp_idf_native"})
        row = frame(1, 100)
        row["iq_bytes"] = [0] * 128
        for position in list(range(1, 27)) + list(range(38, 64)):
            row["iq_bytes"][position * 2:position * 2 + 2] = [3, 4]
        archive.record(json.dumps(row))
        archive.close(completed=True)
        stored = read_jsonl(archive.path / "frames.jsonl")[0]
        self.assertEqual(stored["iq_bytes"], row["iq_bytes"])
        config = json.loads((archive.path / "capture_config.json").read_text())
        self.assertEqual(config["capture_profile"]["subcarrier_order"], "esp_idf_native")
        self.assertNotIn("declared capture profile mismatch", qa_capture(archive.path)["issues"])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def populated(self, label="nonfall_activity", predictions=False):
        archive = CaptureArchive(self.root, configuration())
        for n in range(101):
            archive.record(json.dumps(frame(n, n*1_000_000)))
        extra = {"stationary_since_monotonic_us": 0} if label == "inactivity_without_fall" else {}
        start = 60_000_000 if extra else 1_000_000
        archive.annotate(label, start, 100_000_000, observer_id="ANN_001", confirmed=True, **extra)
        if predictions:
            for n in range(401):
                t = 10_000_000 + n*200_000
                state = "suspected_fall" if 20_000_000 <= t < 25_000_000 else "confirmed_fall" if 25_000_000 <= t < 30_000_000 else "normal"
                archive.prediction(t, state, .9 if state != "normal" else .1, .001)
        archive.close(completed=True)
        return archive

    def test_original_signed_bytes_metadata_and_permissions_are_preserved(self):
        archive = CaptureArchive(self.root, configuration())
        row = frame(1, 100)
        row["iq_bytes"] = [-128, 127] + row["iq_bytes"][2:]
        row["first_word_invalid"] = True
        archive.record(json.dumps(row))
        archive.close(completed=True)
        saved = read_jsonl(archive.path / "frames.jsonl")[0]
        self.assertEqual(archive_projection(saved), row)
        self.assertEqual((archive.path / "frames.jsonl").stat().st_mode & 0o777, 0o600)
        self.assertEqual(archive.path.stat().st_mode & 0o777, 0o700)
        validated = FrameValidator(CaptureProfile()).validate(archive_projection(saved))
        self.assertEqual(validated.iq_bytes[0], -128)

    def test_schema_sender_duplicates_and_clock_reversal_are_quarantined(self):
        archive = CaptureArchive(self.root, configuration())
        archive.record(json.dumps(frame(1, 100)))
        archive.record("{bad json")
        wrong = frame(2, 200); wrong["len"] = 104
        archive.record(json.dumps(wrong))
        sender = frame(2, 200); sender["sender_mac"] = "00:11:22:33:44:55"
        archive.record(json.dumps(sender))
        archive.record(json.dumps(frame(1, 100)))
        archive.record(json.dumps(frame(3, 300)))
        archive.close(completed=True)
        self.assertEqual(archive.stats()["accepted_frames"], 2)
        self.assertEqual(archive.stats()["quarantined_frames"], 4)
        self.assertEqual(archive.stats()["missing_packets"], 1)
        self.assertEqual(archive.stats()["duplicate_sequences"], 1)
        self.assertEqual(archive.stats()["timestamp_reversals"], 1)
        self.assertNotIn("iq_bytes", (archive.path / "quarantine.jsonl").read_text())
        self.assertEqual(qa_capture(archive.path)["status"], "rejected")

    def test_reset_ends_session_instead_of_changing_epoch_silently(self):
        archive = CaptureArchive(self.root, configuration())
        archive.record(json.dumps(frame(99, 1_000_000)))
        archive.record(json.dumps(frame(0, 0)))
        self.assertEqual(archive.failure, "receiver_clock_reset")
        self.assertEqual(archive.record(json.dumps(frame(1, 100))), {"status": "dropped"})
        archive.close(completed=False)
        self.assertEqual(qa_capture(archive.path)["status"], "rejected")

    def test_subject_split_is_frozen_across_sessions(self):
        first = CaptureArchive(self.root, configuration())
        first.close(completed=False)
        with self.assertRaisesRegex(ValueError, "split is frozen"):
            CaptureArchive(self.root, configuration("SES_SECOND", split="test"))
        self.assertEqual(read_jsonl(self.root / "subjects.jsonl")[0]["split"], "train")

    def test_git_tree_and_source_data_tree_are_not_capture_destinations(self):
        git_root = self.root / "git"; git_root.mkdir(); (git_root / ".git").mkdir()
        for path in (git_root / "captures", self.root / "data/captures"):
            with self.assertRaises(ValueError):
                CaptureArchive(path, configuration())

    def test_human_confirmation_is_pending_until_independent_review(self):
        archive = self.populated()
        self.assertEqual(qa_capture(archive.path)["status"], "pending")
        independent_review(archive)
        self.assertEqual(qa_capture(archive.path)["status"], "accepted")
        self.assertTrue(qa_capture(archive.path)["labels_ready_for_training"])
        reviews = read_jsonl(archive.path / "reviews.jsonl")
        reviews[0]["reviewer_id"] = "ANN_001"
        (archive.path / "reviews.jsonl").write_text(canonical(reviews[0])+"\n")
        self.assertEqual(qa_capture(archive.path)["status"], "pending")

    def test_archive_mutation_is_detected_and_not_repaired(self):
        archive = self.populated()
        original = (archive.path / "frames.jsonl").read_text()
        (archive.path / "frames.jsonl").write_text(original.replace('"rssi_dbm":-42', '"rssi_dbm":-43', 1))
        self.assertIn("archive checksum mismatch", qa_capture(archive.path)["issues"])
        checks = json.loads((archive.path / "checksums.json").read_text())
        del checks["events.jsonl"]
        (archive.path / "checksums.json").write_text(json.dumps(checks))
        self.assertIn("required archive checksums missing", qa_capture(archive.path)["issues"])

    def test_inactive_requires_prior_stationary_interval(self):
        archive = CaptureArchive(self.root, configuration())
        for n in range(101):
            archive.record(json.dumps(frame(n, n*1_000_000)))
        archive.annotate("inactivity_without_fall", 1_000_000, 70_000_000, observer_id="ANN_001", confirmed=True, stationary_since_monotonic_us=0)
        archive.close(completed=True)
        self.assertIn("inactive interval lacks the minimum prior stationary period", qa_capture(archive.path)["issues"])

    def test_fall_needs_separate_event_end_and_post_event_inactivity(self):
        archive = CaptureArchive(self.root, configuration())
        for n in range(30):
            archive.record(json.dumps(frame(n, n*1_000_000)))
        archive.annotate("fall", 5_000_000, 7_000_000, observer_id="ANN_001", confirmed=True)
        archive.close(completed=True)
        self.assertIn("fall lacks verified post-event inactivity bounds", qa_capture(archive.path)["issues"])

    def test_missing_predictions_cannot_be_reported_as_zero_false_alerts(self):
        archive = self.populated()
        independent_review(archive)
        report = false_alert_report(archive.path)
        self.assertFalse(report["available"])
        self.assertIsNone(report["false_alerts_per_hour"])

    def test_one_episode_upgrade_counts_once_and_coverage_is_measured(self):
        archive = self.populated(predictions=True)
        independent_review(archive)
        report = false_alert_report(archive.path)
        self.assertTrue(report["available"])
        self.assertEqual(report["false_alert_episodes"], 1)
        self.assertEqual(report["confirmed_false_alert_episodes"], 1)
        self.assertAlmostEqual(report["eligible_nonfall_s"], 80, places=4)
        self.assertGreater(report["poisson_one_sided_95_upper_per_hour"], report["false_alerts_per_hour"])
        self.assertFalse(report["two_per_day_supported_at_95_percent"])
        self.assertFalse(report["four_class_target_proven"])
        self.assertIn("fall_anomaly", report["missing_classes"])

    def test_gaps_are_subtracted_from_exposure(self):
        self.assertEqual(subtract_intervals([(0, 100), (80, 120)], [(20, 30), (40, 70)]), [(0, 20), (30, 40), (70, 120)])

    def test_interruption_saves_partial_raw_and_aborted_annotation(self):
        path = Path(__file__).resolve().parents[1] / "tools/record_esp32_capture.py"
        spec = importlib.util.spec_from_file_location("guided_capture", path)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        args = module.argparse.Namespace(channel=1, subcarrier_order="centered", baud=115200)
        recorder = module.GuidedRecorder(args, {"observer_id": "ANN_001"}, self.root, "unused")
        recorder.archive = CaptureArchive(self.root, configuration())
        for n in range(5):
            recorder.archive.record(json.dumps(frame(n, n*1_000_000)))
        recorder.interval = (1_000_000, "nonfall_activity")
        with patch("builtins.print"):
            recorder.finish(completed=False)
        self.assertEqual(len(read_jsonl(recorder.archive.path / "frames.jsonl")), 5)
        self.assertEqual(read_jsonl(recorder.archive.path / "events.jsonl")[0]["event_type"], "aborted_event")
        self.assertEqual(json.loads((recorder.archive.path / "qa_report.json").read_text())["status"], "rejected")

    def test_model_loads_before_serial_reception_starts(self):
        path = Path(__file__).resolve().parents[1] / "tools/record_esp32_capture.py"
        spec = importlib.util.spec_from_file_location("guided_warmup", path)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        args = module.argparse.Namespace(channel=1, subcarrier_order="centered", baud=115200, model=self.root / "unused.tflite")
        recorder = module.GuidedRecorder(args, {}, self.root, "unused")
        order = []
        def runtime_factory(*a, **kw):
            order.append("model")
            return Mock()
        def start_reader():
            order.append("serial")
            raise RuntimeError("test stops before opening any hardware")
        recorder.reader.start = start_reader
        with patch.object(module, "EdgeRuntime", side_effect=runtime_factory), patch("builtins.print"):
            with self.assertRaisesRegex(RuntimeError, "test stops"):
                recorder.start()
        self.assertEqual(order, ["model", "serial"])

    def test_guidance_creates_human_confirmed_intervals_and_stationary_marker(self):
        path = Path(__file__).resolve().parents[1] / "tools/record_esp32_capture.py"
        spec = importlib.util.spec_from_file_location("guided_conditions", path)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        args = module.argparse.Namespace(channel=1, subcarrier_order="centered", baud=115200, duration=60, prepare=20)
        recorder = module.GuidedRecorder(args, {"observer_id": "ANN_001"}, self.root, "unused")
        recorder.archive = CaptureArchive(self.root, configuration())
        sequence = 0
        recorder.archive.record(json.dumps(frame(sequence, 0)))
        def advance(seconds, title):
            nonlocal sequence
            for _ in range(seconds):
                sequence += 1
                recorder.archive.record(json.dumps(frame(sequence, sequence*1_000_000)))
        recorder.timed = advance
        with patch("builtins.input", side_effect=["", "y", "", "y", "", "y"]), patch("builtins.print"):
            recorder.condition("1/3", "Keluar ruangan", "no_person")
            recorder.condition("2/3", "Aktivitas biasa", "nonfall_activity")
            recorder.condition("3/3", "Tetap diam", "inactivity_without_fall", stationary=True)
        recorder.archive.close(completed=True)
        events = read_jsonl(recorder.archive.path / "events.jsonl")
        self.assertEqual([e["activity_label"] for e in events], ["no_person", "normal", "inactive"])
        self.assertTrue(all(e["review_status"] == "pending" for e in events))
        self.assertEqual(events[2]["onset_monotonic_us"]-events[2]["stationary_since_monotonic_us"], 61_000_000)
        self.assertIsNone(recorder.interval)
        independent_review(recorder.archive)
        self.assertEqual(qa_capture(recorder.archive.path)["status"], "accepted")

    def test_inference_clock_is_receiver_clock_not_host_wall_clock(self):
        from srasta_csi.edge import EdgeRuntime
        runtime = EdgeRuntime(write_model(self.root), self.root / "test.sqlite3")
        for n in range(1, 8):
            runtime.ingest_json_line(json.dumps(frame(n, n*10_000)))
        self.assertAlmostEqual(runtime.last_inference_sample_s, .07)
        self.assertGreater(runtime.last_inference_wall_s, 1_000_000_000)
        runtime.reset_capture_session()
        self.assertIsNone(runtime.last_inference_sample_s)
        runtime.close()


if __name__ == "__main__":
    unittest.main()
