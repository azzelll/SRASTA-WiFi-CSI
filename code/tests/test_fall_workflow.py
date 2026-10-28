import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from srasta_csi.capture_archive import CaptureArchive, qa_capture, read_jsonl
from srasta_csi.capture_metrics import fall_event_report
from srasta_csi.presence import collect_presence_windows
from test_capture import configuration, independent_review
from test_edge_api import frame
from train_fall_ablation import select_candidate


def tool(name):
    path = Path(__file__).resolve().parents[1] / "tools" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


class FallWorkflowTests(unittest.TestCase):
    def test_fall_capture_cannot_start_without_procedure_reference(self):
        module = tool("record_esp32_capture")
        args = module.argparse.Namespace(channel=1, subcarrier_order="centered", baud=115200,
                                         pilot_only=False, protocol="fall-observer")
        recorder = module.GuidedRecorder(args, {"authority_ref": ""}, Path("unused"), "unused")
        with patch.object(recorder, "start") as start:
            with self.assertRaisesRegex(ValueError, "referensi prosedur"):
                recorder.run()
            start.assert_not_called()

    def test_single_condition_and_motion_modes_preserve_nonfall_labels(self):
        module = tool("record_esp32_capture")
        for protocol, expected in (("empty", ["no_person"]), ("presence", ["nonfall_activity"]),
                                   ("adl", ["nonfall_activity"]),
                                   ("motion", ["nonfall_activity", "inactivity_without_fall", "nonfall_activity"])):
            args = module.argparse.Namespace(channel=1, subcarrier_order="centered", baud=115200,
                                             pilot_only=False, protocol=protocol)
            recorder = module.GuidedRecorder(args, {}, Path("unused"), "unused")
            with patch.object(recorder, "start"), patch.object(recorder, "condition") as condition:
                recorder.run()
            self.assertEqual([call.args[2] for call in condition.call_args_list], expected)

    def test_empty_only_keeps_one_full_30_minute_interval_pending_review(self):
        module = tool("record_esp32_capture")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = module.argparse.Namespace(channel=1, subcarrier_order="centered", baud=115200,
                                             pilot_only=False, protocol="empty", duration=1800, prepare=20)
            recorder = module.GuidedRecorder(args, {"observer_id": "ANN_001"}, root, "unused")
            recorder.archive = CaptureArchive(root, {**configuration(), "guided_protocol": "empty",
                                                     "planned_conditions": ["no_person"]})
            recorder.archive.record(json.dumps(frame(0, 0)))

            def receive_during_interval(seconds, _title):
                first = recorder.archive.last_frame.sequence + 1
                for n in range(first, first + seconds):
                    recorder.archive.record(json.dumps(frame(n, n * 1_000_000)))

            with patch.object(recorder, "start"), patch.object(recorder, "timed", side_effect=receive_during_interval), \
                    patch("builtins.input", side_effect=["", "y"]), patch("builtins.print"):
                recorder.run()
            recorder.archive.close(completed=True)
            events = read_jsonl(recorder.archive.path / "events.jsonl")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event_type"], "no_person")
            self.assertEqual(events[0]["onset_monotonic_us"], 20_000_000)
            self.assertEqual(events[0]["event_end_monotonic_us"], 1_820_000_000)
            self.assertEqual(events[0]["review_status"], "pending")
            self.assertFalse(qa_capture(recorder.archive.path)["labels_ready_for_training"])
            independent_review(recorder.archive)
            self.assertEqual(qa_capture(recorder.archive.path)["status"], "accepted")

    def test_presence_only_produces_present_windows_after_independent_review(self):
        module = tool("record_esp32_capture")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = module.argparse.Namespace(channel=1, subcarrier_order="centered", baud=115200,
                                             pilot_only=False, protocol="presence", duration=600, prepare=20)
            recorder = module.GuidedRecorder(args, {"observer_id": "ANN_001"}, root, "unused")
            recorder.archive = CaptureArchive(root, {**configuration(), "guided_protocol": "presence",
                                                     "planned_conditions": ["normal"]})
            recorder.archive.record(json.dumps(frame(0, 0)))

            def receive_during_interval(seconds, _title):
                first = recorder.archive.last_frame.sequence + 1
                for n in range(first, first + seconds * 10):
                    recorder.archive.record(json.dumps(frame(n, n * 100_000)))

            with patch.object(recorder, "start"), patch.object(recorder, "timed", side_effect=receive_during_interval), \
                    patch("builtins.input", side_effect=["", "y"]), patch("builtins.print"):
                recorder.run()
            recorder.archive.close(completed=True)
            events = read_jsonl(recorder.archive.path / "events.jsonl")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event_type"], "nonfall_activity")
            self.assertNotIn("stationary_since_monotonic_us", events[0])
            self.assertEqual(events[0]["event_end_monotonic_us"] - events[0]["onset_monotonic_us"], 600_000_000)
            rows, rejected = collect_presence_windows(root)
            self.assertEqual(rows, [])
            self.assertEqual(len(rejected), 1)
            independent_review(recorder.archive)
            rows, rejected = collect_presence_windows(root)
            self.assertEqual(rejected, [])
            self.assertGreater(len(rows), 0)
            self.assertTrue(all(row["label"] == 1 for row in rows))
            self.assertTrue(all(row["subject_id"] == "LOC_001" and row["split"] == "train" for row in rows))

    def test_model_selection_rejects_recall_specificity_tradeoff(self):
        def result(recall, specificity):
            return {"summary": {"recall_mean": recall, "specificity_mean": specificity,
                                "macro_f1_mean": .6, "all_seeds_targets_pass": False}}
        self.assertIsNone(select_candidate({"filtered": result(.6, .6), "raw": result(.8, .59)})["chosen"])
        self.assertEqual(select_candidate({"filtered": result(.6, .6), "raw": result(.65, .7)})["chosen"], "raw")

    def test_readiness_never_qa_opens_test_or_pilot_payloads(self):
        module = tool("local_capture_readiness")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for i, split in enumerate(("test", "pilot")):
                path = root / "sessions" / f"SES_{i}"; path.mkdir(parents=True)
                (path / "capture_config.json").write_text(json.dumps({"split": split}))
            with patch.object(module, "qa_capture", side_effect=AssertionError("forbidden raw read")):
                report = module.readiness(root)
            self.assertEqual(report["test_or_pilot_sessions_skipped_before_QA"], 2)
            self.assertFalse(report["presence_ready_to_train"])

    def archive(self, root, *, outage=False, missed=False, premature=False):
        archive = CaptureArchive(root, configuration())
        for n in range(41):
            archive.record(json.dumps(frame(n, n * 1_000_000)))
        archive.annotate("fall", 5_000_000, 7_000_000, observer_id="ANN_001", confirmed=True,
                         post_event_inactivity_start_monotonic_us=7_000_000,
                         post_event_inactivity_end_monotonic_us=25_000_000)
        for n in range(201):
            t = n * 200_000
            if outage and 8_000_000 <= t <= 10_000_000:
                continue
            state = "normal"
            if not missed and 6_000_000 <= t < 30_000_000:
                state = "confirmed_fall" if t >= (10_000_000 if premature else 18_000_000) else "suspected_fall"
            archive.prediction(t, state, .9 if state != "normal" else .1, .001)
        return archive

    def test_recall_matches_episode_once_and_confirmation_latency_is_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = self.archive(Path(directory))
            archive.close(completed=True); independent_review(archive)
            report = fall_event_report(archive.path)
            self.assertEqual(report["detected_falls"], 1)
            self.assertEqual(report["event_recall"], 1.)
            self.assertEqual(report["events"][0]["suspected_latency_s"], 1.)
            self.assertEqual(report["events"][0]["confirmed_latency_s"], 13.)
            self.assertTrue(report["events"][0]["confirmed"])
            self.assertLess(report["binomial_exact_95_interval"][0], .1)
            self.assertFalse(report["final_model_target_proven"])

    def test_inference_outage_is_unavailable_but_covered_miss_counts_as_miss(self):
        for outage in (False, True):
            with self.subTest(outage=outage), tempfile.TemporaryDirectory() as directory:
                archive = self.archive(Path(directory), outage=outage, missed=True)
                archive.close(completed=True); independent_review(archive)
                report = fall_event_report(archive.path)
                self.assertEqual(report["available"], not outage)
                self.assertEqual(report["event_recall"], None if outage else 0.)

    def test_early_confirmation_does_not_satisfy_post_event_stillness(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = self.archive(Path(directory), premature=True)
            archive.close(completed=True); independent_review(archive)
            record = fall_event_report(archive.path)["events"][0]
            self.assertTrue(record["premature_confirmation"])
            self.assertFalse(record["confirmed"])

    def test_postfall_stillness_cannot_be_counted_as_nonfall(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = self.archive(Path(directory))
            archive.annotate("nonfall_activity", 20_000_000, 40_000_000, observer_id="ANN_001", confirmed=True)
            archive.close(completed=True); independent_review(archive)
            self.assertIn("overlapping observer intervals", qa_capture(archive.path)["issues"])

    def test_observer_mode_saves_four_actual_marks_without_model_labels(self):
        module = tool("record_esp32_capture")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = module.argparse.Namespace(channel=1, subcarrier_order="centered", baud=115200, prepare=20)
            recorder = module.GuidedRecorder(args, {"observer_id": "ANN_001"}, root, "unused")
            recorder.archive = CaptureArchive(root, configuration())
            for n in range(41):
                recorder.archive.record(json.dumps(frame(n, n * 1_000_000)))
            recorder.timed = lambda *_: None
            with patch.object(recorder.archive, "clock", side_effect=[5_000_000, 7_000_000, 7_000_000, 25_000_000]), patch("builtins.input", side_effect=["", "", "", "", "y"]), patch("builtins.print"):
                recorder.observed_fall()
            recorder.archive.close(completed=True)
            event = read_jsonl(recorder.archive.path / "events.jsonl")[0]
            self.assertEqual(event["post_event_inactivity_end_monotonic_us"], 25_000_000)
            self.assertEqual(event["review_status"], "pending")
            self.assertEqual(event["annotation_method"], "observer_keyboard_receiver_clock")
            self.assertFalse(fall_event_report(recorder.archive.path)["available"])


if __name__ == "__main__":
    unittest.main()
