from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import h5py
import numpy as np

from srasta_csi.data import read_h5_amplitude, timestamps
from srasta_csi.model import TFLiteModel, build_tcn_lite, export_full_int8, parity_report
from srasta_csi.preprocess import CausalPreprocessor, PreprocessConfig


class TFLiteTests(unittest.TestCase):
    def test_tcn_architecture_and_full_int8_parity(self):
        model = build_tcn_lite(250)
        self.assertEqual(model.input_shape, (None, 250, 52))
        self.assertEqual(model.output_shape, (None, 2))
        dilations = [layer.dilation_rate[0] for layer in model.layers if layer.name.endswith("_a")]
        self.assertEqual(dilations, [1, 2, 4])
        windows = np.random.default_rng(1).normal(scale=0.1, size=(4, 250, 52)).astype(np.float32)
        with tempfile.TemporaryDirectory() as directory:
            path = export_full_int8(model, windows, Path(directory) / "model.tflite")
            runtime = TFLiteModel(path)
            self.assertEqual(runtime.input_detail["dtype"], np.int8)
            self.assertEqual(runtime.output_detail["dtype"], np.int8)
            report = parity_report(model, runtime, windows)
        self.assertEqual(report["windows_compared"], 4)
        self.assertIn(report["status"], {"passed", "failed"})
        self.assertEqual(report["status"] == "passed", report["mean_absolute_error"] <= 0.02 and report["max_absolute_error"] <= 0.10 and report["argmax_agreement"] >= 0.95)

    def test_h5_replay_preprocesses_to_tflite_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.h5"
            raw = np.random.default_rng(2).uniform(1, 20, size=(64, 300, 1)).astype(np.float32)
            with h5py.File(path, "w") as handle:
                handle["CSI_amps"] = raw
            values = read_h5_amplitude(path)
            window, _ = CausalPreprocessor(PreprocessConfig()).window(values, timestamps(len(values)), 250, centered=True)
            self.assertEqual(window.shape, (250, 52))
            model = build_tcn_lite(250)
            tflite = TFLiteModel(export_full_int8(model, window[None, ...], Path(directory) / "model.tflite"))
            output = tflite.predict(window)
        self.assertEqual(output.shape, (2,))
        self.assertTrue(np.isfinite(output).all())

    def test_export_rejects_empty_or_nonfinite_representative_data(self):
        model = build_tcn_lite(8)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                export_full_int8(model, np.empty((0, 8, 52), dtype=np.float32), Path(directory) / "empty.tflite")
            invalid = np.zeros((1, 8, 52), dtype=np.float32)
            invalid[0, 0, 0] = np.nan
            with self.assertRaises(ValueError):
                export_full_int8(model, invalid, Path(directory) / "nan.tflite")


if __name__ == "__main__":
    unittest.main()
