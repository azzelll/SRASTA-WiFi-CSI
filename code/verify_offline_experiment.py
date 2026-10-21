#!/usr/bin/env python3
"""Read back trained research models, predictions, source hashes and live gates."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from sklearn.metrics import confusion_matrix

from predict_offline_candidate import OfflineResearchInference
from srasta_csi.edge import RandomForestInference
from srasta_csi.presence import PresenceInference
from srasta_csi.public_occupancy import load_amplitude, source_rows


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(run, calibrated, source):
    if (run / 'INVALIDATED.md').exists():
        raise ValueError('Invalidated experiment')
    protocol = json.loads((run / 'protocol.json').read_text())
    assert sha256(run / 'source_snapshot/train_offline_candidates.py') == protocol['source_code_sha256']
    assert sha256(run / 'source_snapshot/research_features.py') == protocol['feature_code_sha256']
    metadata = json.loads((run / 'eligible_metadata.json').read_text())
    before = json.loads((run / 'source_integrity.json').read_text())
    assert not before['changed'] and before['cross_partition_duplicates'] == 0
    assert all(sha256(Path(p)) == h for p, h in before['sha256'].items())
    people = [{r['user'] for rows in part.values() for r in rows} for part in metadata.values()]
    assert not people[0] & people[1]
    allowed = {task: source_rows(source, task)[1] for task in ('BreathingDetection', 'HumanActivityRecognition')}
    assert all(r['id'] in allowed[r['task']] for part in metadata.values() for rows in part.values() for r in rows)
    raw = json.loads((run / 'metrics.json').read_text())
    posthoc = json.loads((calibrated / 'metrics.json').read_text())
    result = {'public_source_only': True, 'source_payload_hashes_unchanged': len(before['sha256']),
              'subject_disjoint': True, 'independent_test': False, 'local_deployment_ready': False,
              'candidate_confusion_matrices_verified': 0, 'tasks': {}}
    for task, original in raw.items():
        for candidate in original['candidates']:
            with np.load(run / task / (candidate['candidate'] + '-predictions.npz')) as a:
                matrix = confusion_matrix(a['y'], a['probabilities'].argmax(axis=1)).tolist()
            assert matrix == candidate['metrics']['confusion_matrix']
            result['candidate_confusion_matrices_verified'] += 1
        task_result = posthoc[task]
        path = calibrated / task / 'model.joblib'
        assert sha256(path) == task_result['model_sha256']
        model = OfflineResearchInference(path)
        payload = model.payload
        with np.load(calibrated / task / 'predictions.npz') as a:
            y, probabilities, predictions = a['y'], a['probabilities'], a['prediction']
        expected = ((probabilities[:, 1] >= payload['threshold']).astype(int)
                    if probabilities.shape[1] == 2 else (probabilities * model.bias).argmax(axis=1))
        np.testing.assert_array_equal(predictions, expected)
        assert confusion_matrix(y, predictions).tolist() == task_result['selected']['metrics']['confusion_matrix']
        strata = ['empty', 'sleep'] + (['awake'] if task == 'presence' else ['normal'] if task == 'breathing_three' else [])
        checked, offset = 0, 0
        for stratum in strata:
            rows = metadata['validation'][stratum]
            # The first ten records are chosen before reading their outcomes.
            for i, row in enumerate(rows[:10]):
                values, rate = load_amplitude(source, row, allowed[row['task']], payload['layout'])
                prediction = model.predict(values, rate)
                np.testing.assert_allclose(list(prediction['probabilities'].values()), probabilities[offset+i], atol=1e-10)
                assert payload['classes'].index(prediction['label']) == int(predictions[offset+i])
                checked += 1
            offset += len(rows)
        for loader in (PresenceInference, RandomForestInference):
            try:
                loader(path)
            except ValueError:
                pass
            else:
                raise AssertionError('Live loader accepted a public research model')
        result['tasks'][task] = {'reloaded_real_recordings_checked': checked,
                                'confusion_matrix_verified': True, 'live_loaders_reject': True}
    result['passed'] = True
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--calibrated', type=Path, required=True)
    parser.add_argument('--source', type=Path, default=Path('data/csi-bench'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    result = verify(args.run, args.calibrated, args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
