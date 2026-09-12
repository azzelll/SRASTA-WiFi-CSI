from __future__ import annotations

import unittest

import numpy as np

from srasta_csi.baseline import FEATURE_NAMES, motion_features


class BaselineTests(unittest.TestCase):
    def test_motion_feature_vector_is_fixed_and_finite(self):
        values = np.tile(np.linspace(0, 1, 250, dtype=np.float32)[:, None], (1, 52))
        values[100:105] += 0.5
        features = motion_features(values)
        self.assertEqual(features.shape, (len(FEATURE_NAMES),))
        self.assertTrue(np.isfinite(features).all())


if __name__ == "__main__":
    unittest.main()
