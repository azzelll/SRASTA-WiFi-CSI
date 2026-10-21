from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import h5py
import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier

from srasta_csi.presence import PresenceInference
from srasta_csi.public_occupancy import (ARTIFACT_TYPE, INVARIANT_NAMES, PublicOccupancyInference,
                                       invariant_features, load_amplitude, select_protocol, source_rows)
from calibrate_public_occupancy import choose_threshold


class PublicOccupancyTests(unittest.TestCase):
    def test_calibration_uses_real_boundaries_and_keeps_ties_together(self):
        result = choose_threshold([0, 0, 1, 1], [.80, .82, .91, .93])
        self.assertEqual(result["threshold"], .91)
        self.assertEqual(result["positive_recall"], 1.)
        self.assertEqual(result["empty_recall_specificity"], 1.)
        result = choose_threshold([0, 1], [.7, .7])
        self.assertEqual(min(result["positive_recall"], result["empty_recall_specificity"]), 0.)
        with self.assertRaises(ValueError):
            choose_threshold([0, 1], [.5, float("nan")])

    def test_storage_ablation_recovers_native_values_without_carrier_resize(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            folder = root / "BreathingDetection"
            folder.mkdir()
            measured = np.arange(300 * 8, dtype=np.float32).reshape(300, 8)
            measured[:, 0] = 0
            with h5py.File(folder / "recording.h5", "w") as f:
                f["CSI_amps"] = measured.reshape(8, 300, 1)
            row = {"task": "BreathingDetection", "id": "native", "file_path": "recording.h5", "num_sub": "8"}
            reconstructed, rate = load_amplitude(root, row, {"native"}, "flat_time_major_ablation")
            np.testing.assert_array_equal(reconstructed, measured)
            self.assertEqual(rate, 30.)
            declared, _ = load_amplitude(root, row, {"native"}, "declared_axes")
            self.assertEqual(declared.shape, (300, 8))
            self.assertFalse(np.array_equal(declared, measured))
            row["num_sub"] = "52"
            with self.assertRaisesRegex(ValueError, "unexpected native shape"):
                load_amplitude(root, row, {"native"}, "flat_time_major_ablation")

    def test_forbidden_source_id_rejected_before_file_open(self):
        row = {"task": "BreathingDetection", "id": "official_test", "file_path": "not-opened.h5"}
        with patch("srasta_csi.public_occupancy.h5py.File") as opened:
            with self.assertRaisesRegex(ValueError, "forbidden"):
                load_amplitude(Path("/tmp"), row, {"train"}, "declared_axes")
            opened.assert_not_called()

    def test_features_do_not_learn_gain_or_channel_order_and_detect_periodicity(self):
        t = np.arange(300) / 30.
        x = (10 + .5 * np.sin(2 * np.pi * .3 * t))[:, None] * np.linspace(1., 3., 12)[None]
        a = invariant_features(x, 30.)
        np.testing.assert_allclose(a, invariant_features(x[:, ::-1] * 100., 30.), atol=1e-6)
        self.assertEqual(len(a), len(INVARIANT_NAMES))
        noise = 10 + np.random.default_rng(42).normal(0., .5, (300, 12))
        self.assertGreater(a[-3], invariant_features(noise, 30.)[-3] + .5)
        with self.assertRaises(ValueError):
            invariant_features(np.zeros((300, 8)), 30.)

    def test_subject_and_official_payload_boundaries_with_awake_presence(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for task in ("BreathingDetection", "HumanActivityRecognition"):
                folder = root / task
                (folder / "metadata").mkdir(parents=True)
                (folder / "splits").mkdir()
                users = ["U06", "U23"] if task == "BreathingDetection" else ["U01", "U05", "U06"]
                labels = ["empty", "sleep"] if task == "BreathingDetection" else ["walking", "seated-breathing"]
                rows = [{"id": f"{task}_{u}_{label}_{s}", "user": u, "label": label, "device": "real", "num_sub": "112", "deplyoment": "room"}
                        for u in users for label in labels for s in ["train", "test"]]
                with (folder / "metadata/sample_metadata.csv").open("w") as f:
                    w = csv.DictWriter(f, fieldnames=list(rows[0]))
                    w.writeheader()
                    w.writerows(rows)
                allowed = [r["id"] for r in rows if r["id"].endswith("train")]
                (folder / "splits/train_id.json").write_text(json.dumps(allowed))
                self.assertTrue(all(r["id"] in allowed for r in source_rows(root, task)[0]))
            selected = select_protocol(root, 20)
            users = [{r["user"] for rs in part.values() for r in rs} for part in selected.values()]
            self.assertFalse(users[0] & users[1])
            self.assertEqual({r["user"] for r in selected["validation"]["awake"]}, {"U05"})
            self.assertTrue(all(r["id"].endswith("train") for part in selected.values() for rs in part.values() for r in rs))

    def test_public_predictor_emits_labels_but_local_presence_rejects_it(self):
        with tempfile.TemporaryDirectory() as d:
            t = np.arange(300) / 30.
            empty = np.ones((300, 8)) * 10
            sleep = np.tile((10 + np.sin(2 * np.pi * .3 * t))[:, None], (1, 8))
            x = np.stack([invariant_features(empty, 30.), invariant_features(sleep, 30.)])
            model = RandomForestClassifier(n_estimators=10, random_state=42, bootstrap=False).fit(x, [0, 1])
            path = Path(d) / "model.joblib"
            payload = {"artifact_type": ARTIFACT_TYPE, "research_only": True, "task": "breathing", "model": model,
                       "classes": ["empty", "sleep"], "features": "invariant", "feature_names": INVARIANT_NAMES,
                       "layout": "flat_time_major_ablation"}
            joblib.dump(payload, path)
            inference = PublicOccupancyInference(path)
            self.assertEqual(inference.predict(empty, 30.)["label"], "empty")
            self.assertEqual(inference.predict(sleep, 30.)["label"], "sleep")
            self.assertFalse(inference.predict(sleep, 30.)["normal_class_available"])
            with self.assertRaises(ValueError):
                PresenceInference(path)
            payload["threshold"] = float("nan")
            joblib.dump(payload, path)
            with self.assertRaisesRegex(ValueError, "decision threshold"):
                PublicOccupancyInference(path)


if __name__ == "__main__":
    unittest.main()
