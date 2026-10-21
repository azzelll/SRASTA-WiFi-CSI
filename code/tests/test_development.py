from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from srasta_csi.development import (load_development, prepare_windows, grouped_folds,
                                   select_threshold, development_features, DEVELOPMENT_FEATURE_NAMES)


class DevelopmentTests(unittest.TestCase):
    def test_test_and_excluded_payloads_cannot_be_loaded(self):
        with patch("srasta_csi.development.read_manifest") as manifest:
            for split in ("test", "excluded", "all"):
                with self.assertRaises(ValueError):
                    load_development(Path("unused"), split)
            manifest.assert_not_called()

    def test_three_subject_roles_disjoint_and_outer_coverage_once(self):
        groups = np.repeat(["A", "B", "C", "D", "E", "F"], 4)
        coverage = np.zeros(len(groups), dtype=int)
        for fold in grouped_folds(groups):
            roles = [set(groups[fold[k]]) for k in ("fit", "calibrate", "evaluate")]
            self.assertFalse(roles[0] & roles[1] or roles[0] & roles[2] or roles[1] & roles[2])
            self.assertEqual(len(roles[0]), 4)
            coverage[fold["evaluate"]] += 1
        np.testing.assert_array_equal(coverage, np.ones(len(groups)))

    def test_window_normalization_uses_only_current_recording(self):
        rng = np.random.default_rng(42)
        x = rng.uniform(0, 20, (2, 500, 52)).astype(np.float32)
        first = prepare_windows(x, "paper_window_zscore")
        changed = x.copy()
        changed[1] *= 100
        np.testing.assert_array_equal(first[0], prepare_windows(changed, "paper_window_zscore")[0])
        self.assertAlmostEqual(float(first[0].mean()), 0., places=6)
        self.assertAlmostEqual(float(first[0].std()), 1., places=5)
        self.assertEqual(first.shape, x.shape)
        constant = prepare_windows(np.ones((1, 500, 52), dtype=np.float32), "paper_window_zscore")
        self.assertTrue(np.isfinite(constant).all())
        self.assertFalse(constant.any())

    def test_threshold_requires_joint_gates_and_uses_exact_boundaries(self):
        labels = np.array([0]*10 + [1]*10)
        probabilities = np.r_[np.arange(10)/100 + .4, np.arange(10)/100 + .44]
        report = select_threshold(labels, probabilities)
        # Moving the cut changes sensitivity and specificity together. An
        # impossible target must remain failed rather than reporting accuracy.
        self.assertFalse(report["proxy_gates_pass"])
        self.assertEqual(report["targets"], {"recall": .8, "specificity": .8})
        separable = select_threshold(np.array([0, 0, 1, 1]), np.array([.401, .402, .403, .404]))
        self.assertTrue(separable["proxy_gates_pass"])
        self.assertAlmostEqual(separable["threshold"], .4025)
        with self.assertRaises(ValueError):
            select_threshold(np.array([1, 1]), np.array([.2, .3]))

    def test_temporal_features_are_finite_and_keep_bin_order(self):
        x = np.zeros((500, 52), dtype=np.float32)
        x[100:120] = np.arange(20)[:, None]
        features = development_features(x)
        self.assertEqual(features.shape, (len(DEVELOPMENT_FEATURE_NAMES),))
        self.assertTrue(np.isfinite(features).all())
        reversed_features = development_features(x[::-1])
        self.assertNotEqual(float(features[-4]), float(reversed_features[-4]))


if __name__ == "__main__":
    unittest.main()
