"""Fault injection only: no hardware, production database or network."""
import json
import sqlite3
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import numpy as np

from srasta_csi.camera import AnomalyCamera, PiMoveNetCapture, assess_capture, posture_from_keypoints
from srasta_csi.cloud_sync import CloudSync
from srasta_csi.edge import EdgeRuntime, EventStore
from test_edge_api import write_model


def upright():
    points = np.tile([.3, .4, .9], (17, 1))
    points[[11, 12], :2] = [.65, .4]
    points[[13, 14], :2] = [.8, .4]
    return points


def horizontal():
    points = upright()
    points[[11, 12], :2] = [.3, .75]
    return points


def status():
    return {"public_state": "anomaly", "simulation_mode": False, "state_source": "model",
            "transport": {"connected": True}, "stream_age_s": 0, "inferred_at_s": time.time(),
            "last_event": {"event_uid": str(uuid.uuid4()), "state": "suspected_fall", "timestamp_s": time.time(), "evidence": "model"}}


class CameraResilienceTests(unittest.TestCase):
    def test_burst_requires_consistency_and_preserves_one_measured_frame(self):
        a, b = horizontal(), horizontal()
        b[:, 2] = .95
        weak = upright(); weak[:, 2] = .1
        result, outcome, pose = assess_capture(np.stack([a, b, weak]))
        self.assertEqual(outcome, "horizontal")
        self.assertIn("2/3", result)
        np.testing.assert_allclose(pose['keypoints'], b, atol=1e-4)
        self.assertEqual(assess_capture(np.stack([a, b, upright()]))[1], 'uncertain')
        self.assertEqual(assess_capture(np.stack([a, weak, weak]))[1], 'uncertain')
        self.assertEqual(assess_capture(np.stack([upright()] * 3))[1], 'not_horizontal')

    def test_occluded_cropped_diagonal_and_missing_body_stay_uncertain(self):
        cropped = upright(); cropped[[5, 6], 0] = .99
        occluded = upright(); occluded[[13, 14], 2] = .1
        missing = upright(); missing[:, 2] = .1
        diagonal = upright(); diagonal[[11, 12], :2] = [.6, .7]
        for points in [cropped, occluded, missing, diagonal]:
            with self.subTest(points=points):
                result, outcome, _ = assess_capture(np.stack([points] * 3))
                self.assertEqual(outcome, 'uncertain')
                self.assertNotIn('ruangan kosong', result.lower())
        self.assertIn('belum terbaca', posture_from_keypoints(missing))
        for shape in [np.zeros((4, 17, 3)), np.zeros((3, 16, 3)), np.full((3,17,3), np.nan)]:
            self.assertEqual(assess_capture(shape)[1:], ('uncertain', None))

    def test_real_adapter_runs_bounded_burst_and_rejects_partial_output(self):
        model = Path('artifacts/models/movenet-lightning/model.tflite')
        capture = PiMoveNetCapture(model)
        from types import SimpleNamespace
        pixels = bytes(3 * 192 * 192 * 3)
        with patch('srasta_csi.camera.subprocess.run', return_value=SimpleNamespace(stdout=pixels)) as run:
            points = capture()
        self.assertEqual(points.shape, (3, 17, 3))
        self.assertTrue(np.isfinite(points).all())
        self.assertEqual(run.call_args.args[0][-2:], ['--frames', '3'])
        self.assertEqual(run.call_args.kwargs['timeout'], 10)
        with patch('srasta_csi.camera.subprocess.run', return_value=SimpleNamespace(stdout=pixels[:-1])):
            with self.assertRaisesRegex(ValueError, 'exactly three'):
                capture()

    def test_persistence_failure_retries_without_recapture_and_restart_deduplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'camera.sqlite3'
            store = EventStore(path)
            current = status(); calls = []
            def capture():
                calls.append(True)
                return np.stack([horizontal()] * 3)
            attempts = []
            def save(row):
                attempts.append(True)
                if len(attempts) < 3:
                    raise sqlite3.OperationalError('disk busy')
                store.save_camera_validation(row)
            camera = AnomalyCamera(lambda: current, capture, save_result=save, results_provider=store.camera_validations)
            camera.check_once()
            self.assertIn('menunggu penyimpanan', camera.status()['result'])
            self.assertEqual(len(camera.status()['validations']), 1)
            camera.check_once(); camera.check_once(); camera.check_once()
            self.assertEqual(len(calls), 1)
            self.assertEqual(len(store.camera_validations()), 1)
            store.close()
            reopened = EventStore(path)
            restarted = AnomalyCamera(lambda: current, capture, save_result=reopened.save_camera_validation, results_provider=reopened.camera_validations)
            restarted.check_once()
            self.assertEqual(len(calls), 1)
            reopened.close()

    def test_failed_sensor_can_recover_for_next_event_and_history_read_failure_does_not_recapture(self):
        current = status(); calls = []
        def capture():
            calls.append(True)
            if len(calls) == 1:
                raise TimeoutError('sensor timeout')
            return np.stack([upright()] * 3)
        camera = AnomalyCamera(lambda: current, capture)
        camera.check_once(); camera.check_once()
        self.assertFalse(camera.active)
        self.assertEqual(camera.status()['validations'][0]['outcome'], 'error')
        current['last_event']['event_uid'] = str(uuid.uuid4())
        camera.check_once()
        self.assertEqual(camera.status()['validations'][0]['outcome'], 'not_horizontal')
        camera.results_provider = lambda: (_ for _ in ()).throw(sqlite3.OperationalError('busy'))
        current['last_event']['event_uid'] = str(uuid.uuid4())
        camera.check_once()
        self.assertEqual(len(calls), 2)

    def test_worker_survives_provider_failure(self):
        current = status()
        camera = AnomalyCamera(lambda: current, lambda: np.stack([upright()] * 3))
        with patch.object(camera.stop, 'wait', side_effect=[False, False, True]), patch.object(camera, 'provider', side_effect=[RuntimeError('unavailable'), current]):
            camera._run()
        self.assertEqual(camera.status()['validations'][0]['outcome'], 'not_horizontal')


class CloudResilienceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.model = write_model(self.root)
        self.path = self.root / 'events.sqlite3'
        self.runtime = EdgeRuntime(self.model, self.path, demo_mode=True)
        self.runtime.set_demo_state('critical')
        self.event = self.runtime.store.list()[0]

    def tearDown(self):
        self.runtime.close()
        self.tmp.cleanup()

    def adapter(self, post):
        return CloudSync(self.runtime, 'https://example.supabase.co', str(uuid.uuid4()), 'x'*40, post=post)

    def test_timeout_after_remote_commit_retries_same_event_and_survives_restart(self):
        accepted = set(); requests = []
        def lost_response(body):
            requests.append(body)
            accepted.update(row['event_uid'] for row in body['events'])
            raise TimeoutError('response lost')
        adapter = self.adapter(lost_response)
        with self.assertRaises(TimeoutError): adapter.sync_once()
        self.assertFalse(adapter.status()['connected'])
        self.assertNotIn('response lost', adapter.status()['last_error'])
        self.runtime.close()
        self.runtime = EdgeRuntime(self.model, self.path, demo_mode=True)
        def recovered(body):
            requests.append(body)
            accepted.update(row['event_uid'] for row in body['events'])
            return {'ok': True, 'commands': []}
        adapter = self.adapter(recovered)
        adapter.sync_once()
        self.assertTrue(adapter.status()['connected'])
        self.assertEqual(len(accepted), 1)
        self.assertEqual(requests[0]['events'], requests[1]['events'])
        self.assertEqual(self.runtime.store.cloud_batch()[0], [])

    def test_malformed_batch_is_not_acknowledged_or_partially_applied(self):
        command = {'id': str(uuid.uuid4()), 'event_uid': self.event['event_uid'], 'action': 'assistance', 'expires_at_s': time.time()+120}
        for invalid in [None, {'ok': True, 'commands': [command, {**command, 'id': 'invalid'}]}, {'ok': True, 'commands': [{**command, 'expires_at_s': float('nan')}]}, {'ok': True, 'commands': [{**command, 'expires_at_s': True}]}, {'ok': True, 'commands': [command]*31}]:
            adapter = self.adapter(lambda body: invalid)
            with self.subTest(invalid=invalid), self.assertRaises((ValueError, TypeError, AttributeError)):
                adapter.sync_once()
            self.assertFalse(adapter.connected)
            self.assertEqual(len(self.runtime.store.cloud_batch()[0]), 1)
            self.assertEqual(self.runtime.store.actions(), [])

    def test_failed_receipt_upload_after_restart_does_not_repeat_assistance(self):
        command = {'id': str(uuid.uuid4()), 'event_uid': self.event['event_uid'], 'action': 'assistance', 'expires_at_s': time.time()+120}
        adapter = self.adapter(lambda body: {'ok': True, 'commands': [command]})
        adapter.sync_once()
        self.assertEqual(len(self.runtime.store.actions()), 1)
        self.runtime.close()
        self.runtime = EdgeRuntime(self.model, self.path, demo_mode=True)
        adapter = self.adapter(lambda body: {'ok': True, 'commands': [command]})
        adapter.sync_once(); adapter.sync_once()
        self.assertEqual(len(self.runtime.store.actions()), 1)
        with patch.object(adapter, 'post', side_effect=OSError('offline')):
            with self.assertRaises(OSError): adapter.sync_once()
        self.assertFalse(adapter.status()['connected'])

    def test_concurrent_ack_during_upload_stays_in_outbox(self):
        event = self.event
        def post(body):
            self.runtime.apply_caregiver_command(command_id=str(uuid.uuid4()), event_uid=event['event_uid'], action='acknowledge', source='test', expires_at_s=time.time()+120)
            return {'ok': True, 'commands': []}
        self.adapter(post).sync_once()
        pending = self.runtime.store.cloud_batch()[0]
        self.assertEqual(len(pending), 1)
        self.assertIsNotNone(pending[0]['acknowledged_at_s'])

    def test_worker_backs_off_then_returns_to_normal_interval(self):
        adapter = self.adapter(lambda body: {'ok': True, 'commands': []})
        with patch.object(adapter, 'post', side_effect=[TimeoutError('offline'), OSError('offline'), {'ok': True, 'commands': []}]), patch.object(adapter.stop, 'wait', side_effect=[False, False, False, True]) as wait:
            adapter._run()
        self.assertEqual([call.args[0] for call in wait.call_args_list], [0, 5, 10, 5])
        self.assertTrue(adapter.connected)
        self.assertIsNone(adapter.last_error)
