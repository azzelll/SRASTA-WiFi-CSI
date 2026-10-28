import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from srasta_csi.capture_archive import CaptureArchive, digest, qa_capture, read_jsonl
from test_capture import configuration
from test_edge_api import frame
from test_fall_workflow import tool


class QAReviewInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.archive = CaptureArchive(Path(self.temp.name), configuration())
        for n in range(101):
            self.archive.record(json.dumps(frame(n, n * 1_000_000)))
        self.archive.annotate("nonfall_activity", 1_000_000, 100_000_000,
                              observer_id="ANN_001", confirmed=True)
        self.archive.close(completed=True)
        self.module = tool("qa_capture")

    def invoke(self, answers):
        args = ["qa_capture.py", str(self.archive.path), "--reviewer", "ANN_002"]
        with patch("sys.argv", args), patch("builtins.input", side_effect=answers) as prompt, \
                patch("builtins.print"):
            result = self.module.main()
        return result, prompt.call_count

    def test_blank_or_invalid_answers_wait_for_an_explicit_review(self):
        before = {name: digest(self.archive.path / name)
                  for name in ("frames.jsonl", "events.jsonl", "capture_config.json", "checksums.json")}
        result, prompts = self.invoke(["", "?", "y", "", "?", "y"])
        self.assertEqual(result, 0)
        self.assertEqual(prompts, 6)
        reviews = read_jsonl(self.archive.path / "reviews.jsonl")
        self.assertEqual(len(reviews), 1)
        self.assertIs(reviews[0]["agrees"], True)
        self.assertEqual(qa_capture(self.archive.path)["status"], "accepted")
        self.assertEqual(before, {name: digest(self.archive.path / name) for name in before})

    def test_explicit_observer_decline_writes_no_review(self):
        result, prompts = self.invoke(["", "n"])
        self.assertEqual((result, prompts), (1, 2))
        self.assertFalse((self.archive.path / "reviews.jsonl").exists())
        self.assertEqual(qa_capture(self.archive.path)["status"], "pending")

    def test_explicit_skip_after_blank_keeps_label_pending(self):
        result, prompts = self.invoke(["y", "", "s"])
        self.assertEqual((result, prompts), (0, 3))
        self.assertEqual(read_jsonl(self.archive.path / "reviews.jsonl"), [])
        self.assertEqual(qa_capture(self.archive.path)["status"], "pending")

    def test_explicit_disagreement_after_blank_still_rejects_label(self):
        result, prompts = self.invoke(["y", "", "n"])
        self.assertEqual((result, prompts), (1, 3))
        self.assertIs(read_jsonl(self.archive.path / "reviews.jsonl")[0]["agrees"], False)
        self.assertEqual(qa_capture(self.archive.path)["status"], "rejected")


if __name__ == "__main__":
    unittest.main()
