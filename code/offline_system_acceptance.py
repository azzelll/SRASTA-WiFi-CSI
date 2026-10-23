#!/usr/bin/env python3
"""Isolated software proof: real model replay plus synthetic event/camera/ack flow.

No sensor is opened; no network notification, live DB, image or raw CSI is
written. Injected decisions/keypoints prove wiring, never model accuracy.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import time

from fastapi.testclient import TestClient
import numpy as np

from srasta_csi.blynk import DisabledBlynkAdapter
from srasta_csi.camera import AnomalyCamera
from srasta_csi.data import read_manifest, resolve_source_path
from srasta_csi.edge import EdgeRuntime, create_app


def run(model_path, data_root):
    result={"purpose":"offline software integration only", "hardware_accuracy_proven":False,
        "live_camera_tested":False,"network_notifications_sent":False,"images_saved":False,
        "test_payload_opened":False,"model_sha256":hashlib.sha256(model_path.read_bytes()).hexdigest()}
    with tempfile.TemporaryDirectory(prefix='srasta-offline-integration-') as directory:
        root=Path(directory)
        runtime=EdgeRuntime(model_path,root/'replay.sqlite3')
        try:
            sample=next(r for r in read_manifest(data_root/'curated/esp32_s3_fall_v1/manifest.csv') if r.split=='train')
            runtime.replay(resolve_source_path(sample,data_root))
            client=TestClient(create_app(runtime))
            snapshot=client.get('/api/caregiver').json()
            assert snapshot['source']=='replay' and snapshot['simulation'] and not snapshot['monitoring_online']
            assert snapshot['presence']=='unknown' and snapshot['breathing_condition'] is None
            result['actual_model_replay']={'sample_id':sample.sample_id,'probability':runtime.last_probability,
                'routes':{route:client.get(route).status_code for route in ('/health','/status','/events','/api/caregiver')}}
            assert all(code==200 for code in result['actual_model_replay']['routes'].values())
        finally:
            runtime.close()
        runtime=EdgeRuntime(model_path,root/'fixture.sqlite3')
        camera=None
        try:
            # A synthetic transport and explicit decision injection stay wholly
            # inside this process/database. They never represent a live feed.
            runtime.transport_status=lambda:{'connected':True,'test_fixture':True}
            runtime.last_ingest_monotonic=time.monotonic()
            runtime.last_ingest_wall_s=time.time()
            runtime.last_inference_wall_s=time.time()
            calls=[]
            def capture():
                calls.append(True)
                points=np.tile([.4,.4,.9],(17,1)); points[[11,12],:2]=[.4,.8]
                return np.stack([points, points.copy(), points.copy()])
            camera=AnomalyCamera(runtime.status,capture,save_result=runtime.store.save_camera_validation,
                                 results_provider=runtime.store.camera_validations)
            runtime.camera_status=camera.status
            client=TestClient(create_app(runtime))
            camera.check_once(); assert calls==[]
            runtime.observe(.99,runtime.machine.motion_threshold*2,100.)
            suspected=runtime.store.list(1)[0]
            camera.check_once(); camera.check_once()
            assert len(calls)==1
            snapshot=client.get('/api/caregiver').json()
            assert snapshot['state']=='anomaly'
            assert snapshot['camera']['validations'][0]['event_uid']==suspected['event_uid']
            assert snapshot['camera']['validations'][0]['outcome']=='horizontal'
            assert 'konsisten 3/3 cuplikan' in snapshot['camera']['validations'][0]['result']
            runtime.tick(110.)
            critical=runtime.store.list(1)[0]
            assert critical['state']=='confirmed_fall' and critical['event_uid']!=suspected['event_uid']
            camera.check_once(); camera.check_once()
            assert len(calls)==2
            final=client.get('/api/caregiver').json()
            assert final['state']=='critical' and final['alarm']['requested'] is True
            assert {v['event_uid'] for v in final['camera']['validations']}=={suspected['event_uid'],critical['event_uid']}
            assert client.post('/acknowledge').status_code==200
            assert runtime.store.list(1)[0]['acknowledged_at_s'] is not None
            notification=DisabledBlynkAdapter()
            assert notification.send(final,now_s=0.) is False
            assert notification.send(final,now_s=1.) is False
            assert notification.status()['rate_limited_attempts']==1
            for forbidden in ('iq_bytes','sender_mac','image_data'):
                assert forbidden not in json.dumps(final)
            for validation in final['camera']['validations']:
                assert set(validation['pose']) == {'format', 'keypoints'}
                assert validation['pose']['format'] == 'movenet-coco17'
                assert np.asarray(validation['pose']['keypoints']).shape == (17,3)
            # Replaying the fixture or losing freshness blocks further capture.
            runtime.last_replay_source='isolated-fixture'
            runtime.store.append(time.time(),'suspected_fall',.99,1.)
            camera.check_once(); assert len(calls)==2
            runtime.last_replay_source=None
            runtime.last_ingest_monotonic=time.monotonic()-20
            camera.check_once(); assert len(calls)==2
            result['synthetic_event_flow']={'decision_injected':True,'keypoints_injected':True,
                'normal_no_capture':True,'one_burst_per_event_uid':True,'frames_per_burst':3,'event_uid_binding':True,
                'post_inactivity_critical':True,'caregiver_acknowledged':True,'replay_and_stale_blocked':True,
                'privacy_summary_only':True,'bounded_pose_summary':True,'external_notification_disabled':True}
            result['passed']=True
        finally:
            if camera:camera.close()
            runtime.close()
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--data-root',type=Path,default=Path('data'))
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise FileExistsError(args.output)
    result=run(args.model,args.data_root)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
