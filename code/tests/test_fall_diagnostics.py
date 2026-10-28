import unittest
import numpy as np

from srasta_csi.data import timestamps
from srasta_csi.fall_diagnostics import preprocess_trace, recording_decision, quantization_saturation
from srasta_csi.preprocess import CausalPreprocessor, PreprocessConfig


class FallDiagnosticTests(unittest.TestCase):
    def test_trace_is_identical_to_shared_inference_and_counts_clipping(self):
        rng = np.random.default_rng(42)
        raw = rng.uniform(1, 30, (100, 52)).astype(np.float32)
        config = PreprocessConfig(normalized_clip=.01)
        trace = preprocess_trace(raw, timestamps(len(raw)), config)
        np.testing.assert_array_equal(trace["processed"], CausalPreprocessor(config).transform(raw, timestamps(len(raw))))
        self.assertGreater(trace["stats"]["clipped_fraction"], 0)

    def test_missed_fall_attribution_does_not_blame_gate_for_classifier_error(self):
        for p, energy, expected in ((.4, .1, "classifier"), (.9, .001, "motion_gate"), (.4, .001, "classifier_and_motion_gate")):
            decision = recording_decision(1, p, energy, .5, .01)
            self.assertEqual(decision["outcome"], "FN")
            self.assertEqual(decision["missed_by"], expected)
        self.assertEqual(recording_decision(0, .9, .1, .5, .01)["outcome"], "FP")
        self.assertEqual(recording_decision(1, .5, .01, .5, .01)["outcome"], "TP")

    def test_saturation_uses_rounded_int8_range(self):
        self.assertEqual(quantization_saturation(np.array([-128, 127, 128, -129]), (1., 0)), .5)
        with self.assertRaises(ValueError):
            quantization_saturation(np.zeros(1), (0., 0))


if __name__ == "__main__":
    unittest.main()
