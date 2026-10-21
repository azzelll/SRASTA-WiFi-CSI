import unittest

import numpy as np

from calibrate_motion_gate import train_motion_floor, trigger_predictions


class MotionCalibrationTests(unittest.TestCase):
    def test_calibrated_trigger_does_not_block_every_positive_but_rejects_flat_input(self):
        threshold = train_motion_floor(np.array([.0003, .0005, .0007, .0009]), np.array([0, 1, 1, 1]))
        self.assertGreater(threshold, 0)
        np.testing.assert_array_equal(trigger_predictions([.9, .9, .1], [.0008, 0, .0008], .45, threshold), [1, 0, 0])
        np.testing.assert_array_equal(trigger_predictions([.9], [.0008], .45, .02), [0])

    def test_calibration_rejects_missing_classes_nonfinite_or_flat_falls(self):
        for energy, labels in (([0, 0], [0, 1]), ([.001, float('nan')], [0, 1]), ([.001, .002], [1, 1])):
            with self.assertRaises(ValueError):
                train_motion_floor(np.array(energy), np.array(labels))
