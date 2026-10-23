#!/usr/bin/env python3
"""Calibrate the motion trigger from primary train only; never open test clips.

The frozen classifier is unchanged. Validation reports a recording-level
trigger proxy, not event recall, FAR, room performance or final readiness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

from srasta_csi.data import read_manifest, manifest_sha256
from srasta_csi.edge import StateMachine
from srasta_csi.metrics import classification_metrics
from srasta_csi.model import TFLiteModel
from srasta_csi.preprocess import CausalPreprocessor, PreprocessConfig
from train_srasta_release import crop, read_processed, save


def train_motion_floor(energies: np.ndarray, labels: np.ndarray) -> float:
    energies, labels = np.asarray(energies), np.asarray(labels)
    if energies.shape != labels.shape or energies.ndim != 1 or not np.isfinite(energies).all() or np.any(energies < 0):
        raise ValueError('finite per-recording train energy and labels required')
    fall = energies[labels == 1]
    if not len(fall) or not np.any(labels == 0):
        raise ValueError('both train classes required')
    threshold = float(np.quantile(fall, .01))
    if threshold <= 0:
        raise ValueError('cannot calibrate a motion floor from flat fall recordings')
    return threshold


def trigger_predictions(probabilities, energies, probability_threshold, motion_threshold):
    # A fresh state per recording is a classification proxy. A continuous
    # stream must be evaluated separately with onset/inactivity annotations.
    return np.asarray([
        int(StateMachine(fall_threshold=probability_threshold, motion_threshold=motion_threshold)
            .update(float(probability), float(energy), 0.0)[0] == 'suspected_fall')
        for probability, energy in zip(probabilities, energies, strict=True)
    ])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--data-root', type=Path, default=Path('data'))
    args = parser.parse_args()
    if args.out_dir.exists():
        raise FileExistsError('refusing to overwrite a release')
    source = args.source
    frozen = json.loads((source/'frozen.json').read_text())
    digest = hashlib.sha256((source/'model.tflite').read_bytes()).hexdigest()
    if digest != frozen['model_sha256'] or not frozen['software_ready']:
        raise ValueError('source classifier must be frozen and software-ready')
    config = PreprocessConfig.from_json(json.loads((source/'preprocess_config.json').read_text()))
    processor = CausalPreprocessor(config)
    manifest = args.data_root/'curated/esp32_s3_fall_v1/manifest.csv'
    rows = read_manifest(manifest)
    train, y_train, _ = read_processed(rows, 'train', args.data_root, processor)
    train = crop(train, frozen['window_length'])
    energies = np.asarray([processor.motion_energy(window) for window in train])
    threshold = train_motion_floor(energies, y_train)
    validation, y_validation, _ = read_processed(rows, 'validation', args.data_root, processor)
    validation = crop(validation, frozen['window_length'])
    runtime = TFLiteModel(source/'model.tflite')
    probabilities = np.asarray([runtime.probability(window) for window in validation])
    validation_energy = np.asarray([processor.motion_energy(window) for window in validation])
    report = {
        'method': '1st percentile of primary train fall-window motion; no validation selection',
        'source_model_sha256': digest, 'classifier_weights_unchanged': True,
        'manifest_sha256': manifest_sha256(manifest), 'train_recordings': len(train),
        'before_motion_threshold': config.motion_energy_threshold, 'motion_threshold': threshold,
        'train_fall_motion_gate_coverage': float(np.mean(energies[y_train == 1] >= threshold)),
        'evaluation': 'subject-disjoint validation recording-level trigger proxy; not event recall or local accuracy',
        'before': classification_metrics(y_validation, trigger_predictions(probabilities, validation_energy, frozen['threshold'], config.motion_energy_threshold)),
        'after': classification_metrics(y_validation, trigger_predictions(probabilities, validation_energy, frozen['threshold'], threshold)),
        'test': 'U21 was already reported for v2; not reopened or used here',
        'deployment_ready': False,
        'remaining': ['local safe negative exposure and fall event protocol', 'independent four-class data', 'Pi measurements'],
    }
    destination = args.out_dir/'selected'
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns('locked_test_report.json'))
    calibrated = replace(config, motion_energy_threshold=threshold)
    save(destination/'preprocess_config.json', calibrated.to_json())
    save(destination/'motion_calibration.json', report)
    frozen.update({'preprocess_config_hash': calibrated.hash, 'capture_profile_hash': calibrated.capture_profile_hash,
                   'motion_energy_threshold': threshold, 'frozen_at_s': time.time(),
                   'test_status': 'not_reopened; source v2 U21 result does not validate this trigger',
                   'selected_candidate': 'v2_classifier_train_calibrated_motion', 'deployment_ready': False})
    save(destination/'frozen.json', frozen)
    (destination/'MODEL_CARD.md').write_text('# SRASTA TCN-Lite with calibrated motion trigger\n\n'
        'The v2 classifier weights/probability threshold are unchanged. Primary train only calibrates '
        'the motion floor. The former 0.02 gate rejected every primary train/validation window. '
        'motion_calibration.json reports validation recording-level trigger proxies. '
        'U21 is not reopened. Local event/FAR, four-class labels, and Pi validation remain required.\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
