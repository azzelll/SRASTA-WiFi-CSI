from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

import h5py
import numpy as np

from srasta_csi.data import ManifestRow, assert_split_disjoint, read_h5_amplitude, read_manifest, split_report, timestamps
from srasta_csi.preprocess import CausalPreprocessor, PreprocessConfig


class DataPreprocessTests(unittest.TestCase):
    def test_h5_axis_conversion(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.h5"
            raw = np.zeros((64, 4, 1), dtype=np.float32)
            for carrier in range(64):
                raw[carrier, :, 0] = carrier * 10 + np.arange(4)
            with h5py.File(path, "w") as handle:
                handle["CSI_amps"] = raw
            values = read_h5_amplitude(path)
        self.assertEqual(values.shape, (4, 52))
        np.testing.assert_array_equal(values[:, 0], [60, 61, 62, 63])
        np.testing.assert_array_equal(values[:, 26], [330, 331, 332, 333])

    def test_curated_split_report_proves_subject_session_disjointness(self):
        root = Path(__file__).parents[2]
        rows = read_manifest(root / "data/curated/esp32_s3_fall_v1/manifest.csv")
        report = split_report(rows)
        self.assertEqual(report["overlap_checks"], {"subject": "passed", "session": "passed", "source_path": "passed"})
        self.assertTrue(report["validated_before_windowing"])
        self.assertEqual(report["train"]["sample_count"], 288)
        self.assertEqual(report["validation"]["sample_count"], 77)
        self.assertEqual(report["test"]["sample_count"], 80)

    def test_split_rejects_subject_session_and_source_leakage(self):
        base = ManifestRow("a", "csi-bench/a.h5", "fall", 1, "U1", "S1", "train")
        variants = (
            ManifestRow("b", "csi-bench/b.h5", "nonfall", 0, "U1", "S2", "validation"),
            ManifestRow("b", "csi-bench/b.h5", "nonfall", 0, "U1", "S1", "validation"),
            ManifestRow("b", "csi-bench/a.h5", "nonfall", 0, "U2", "S2", "validation"),
        )
        for other in variants:
            with self.subTest(other=other):
                with self.assertRaises(ValueError):
                    assert_split_disjoint([base, other])
        with self.assertRaises(ValueError):
            assert_split_disjoint([base, ManifestRow("b", "csi-bench/b.h5", "fall", 1, "U2", "S2", "random")])

    def test_manifest_rejects_invalid_split_and_duplicate_source(self):
        fields = ("sample_id", "source_path", "label", "label_id", "subject_id", "session_id", "device", "feature_count", "split")
        rows = [
            {"sample_id": "a", "source_path": "csi-bench/a.h5", "label": "fall", "label_id": "1", "subject_id": "U1", "session_id": "S1", "device": "ESP32", "feature_count": "52", "split": "train"},
            {"sample_id": "b", "source_path": "csi-bench/a.h5", "label": "nonfall", "label_id": "0", "subject_id": "U2", "session_id": "S2", "device": "ESP32", "feature_count": "52", "split": "validation"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.csv"
            with path.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaises(ValueError):
                read_manifest(path)
            rows[1]["source_path"], rows[1]["split"] = "csi-bench/b.h5", "random"
            with path.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaises(ValueError):
                read_manifest(path)

    def test_causal_resampling_outlier_baseline_and_window(self):
        processor = CausalPreprocessor(PreprocessConfig(hampel_window=3, baseline_warmup_frames=3))
        times_s = np.asarray([0.0, 0.009, 0.019, 0.029, 0.039, 0.05])
        values = np.full((6, 52), 10.0, dtype=np.float32)
        values[3, 0] = 1000.0
        processed, grid = processor.transform_with_times(values, times_s)
        self.assertEqual(processed.shape, (6, 52))
        np.testing.assert_allclose(grid, np.arange(6) / 100, atol=1e-12)
        self.assertLess(abs(float(processed[-1, 0])), 1.0)
        longer = np.full((300, 52), 10.0, dtype=np.float32)
        window, window_times = processor.window(longer, timestamps(300), 250, centered=True)
        self.assertEqual(window.shape, (250, 52))
        self.assertEqual(window_times.shape, (250,))

    def test_preprocess_rejects_bad_timestamps_and_is_deterministic(self):
        processor = CausalPreprocessor(PreprocessConfig())
        values = np.ones((10, 52), dtype=np.float32)
        with self.assertRaises(ValueError):
            processor.transform(values, np.asarray([0, .01, .02, .03, .04, .03, .06, .07, .08, .09]))
        with self.assertRaises(ValueError):
            processor.transform(values, np.asarray([0, .01, .02, .03, .04, .10, .11, .12, .13, .14]))
        first = processor.window(np.tile(np.arange(300, dtype=np.float32)[:, None], (1, 52)), timestamps(300), 250, centered=False)[0]
        second = processor.window(np.tile(np.arange(300, dtype=np.float32)[:, None], (1, 52)), timestamps(300), 250, centered=False)[0]
        np.testing.assert_array_equal(first, second)

    def test_preprocess_config_round_trip_and_hash(self):
        config = PreprocessConfig(capture_profile_hash="abc")
        self.assertEqual(PreprocessConfig.from_json(config.to_json()), config)
        with self.assertRaises(ValueError):
            PreprocessConfig.from_json({**config.to_json(), "hash": "wrong"})


if __name__ == "__main__":
    unittest.main()
