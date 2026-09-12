import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
import numpy as np
from fastapi.testclient import TestClient
from srasta_csi.care_state import CareStateMachine,Observation,Policy,STATES
from srasta_csi.product import ProductRuntime
from srasta_csi.service import create_product_app
from srasta_csi.breathing import estimate_breathing,BreathingMonitor,unavailable
from srasta_csi.camera import EventCamera,summarize_pose
from srasta_csi.adapters import Notifications,LocalAlarm
from srasta_csi.contract import FrameValidator,FrameValidationError
from srasta_csi.sources import SourceRunner
from test_edge_api import frame,write_model

class ProductTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.runtimes=[]
    def tearDown(self):
        for runtime in self.runtimes: runtime.close()
        self.temp.cleanup()
    def runtime(self,**kwargs):
        r=ProductRuntime(self.root/f'events{len(self.runtimes)}.sqlite3',**kwargs)
        self.runtimes.append(r)
        return r

    def test_all_five_states_by_observed_transitions(self):
        m=CareStateMachine(Policy(inactivity_s=2,confirmation_s=2))
        states=[m.state]
        m.update(Observation(0,True,.05));states.append(m.state)
        m.update(Observation(1,True,0));m.update(Observation(2,True,0));states.append(m.state)
        m.update(Observation(3,True,.2,sudden_motion=True));states.append(m.state)
        m.update(Observation(4,True,0));m.update(Observation(5,True,0));m.update(Observation(6,True,0));states.append(m.state)
        self.assertEqual(states,list(STATES))
        self.assertTrue(m.acknowledge());self.assertEqual(m.state,'critical')
        m.update(Observation(7,True,.05));self.assertEqual(m.state,'normal')

    def test_missing_packets_and_bad_signal_never_confirm(self):
        m=CareStateMachine(Policy(confirmation_s=2))
        m.update(Observation(0,True,.2,fall_probability=.9))
        m.update(Observation(100,True,0))
        self.assertNotEqual(m.state,'critical')
        m.update(Observation(101,True,.2,fall_probability=.9))
        m.update(Observation(102,True,0,quality=False))
        m.update(Observation(103,True,0))
        self.assertNotEqual(m.state,'critical')
        with self.assertRaises(ValueError):m.update(Observation(102,True,.01))

    def test_persistent_inactivity_and_breathing_anomaly(self):
        m=CareStateMachine(Policy(inactivity_s=2,confirmation_s=2))
        for t in range(7):m.update(Observation(t,True,0))
        self.assertEqual(m.state,'critical')
        m=CareStateMachine(Policy(confirmation_s=2))
        for t in range(3):m.update(Observation(t,True,0,breathing_anomaly=True))
        self.assertEqual(m.state,'critical')

    def test_real_input_contract_and_recovery_from_gap(self):
        r=self.runtime(source='serial',sender='aa:bb:cc:dd:ee:ff')
        for i in range(300):self.assertTrue(r.ingest_json_line(json.dumps(frame(i,i*10000))))
        self.assertEqual(r.accepted,300)
        self.assertIsNotNone(r.last_inference)
        self.assertFalse(r.ingest_json_line(json.dumps({**frame(301,3010000),'sender_mac':'00:11:22:33:44:55'})))
        self.assertFalse(r.ingest_json_line(json.dumps({**frame(301,3010000),'rssi':1000})))
        for i in range(302,602):r.ingest_json_line(json.dumps(frame(i,(i+1000)*10000)))
        self.assertGreaterEqual(r.accepted,600)
        self.assertIsNone(r.input_error)
        self.assertEqual(r.status()['state'],'standby')
        self.assertIsNone(r.status()['confidence'])

    def test_window_coverage_is_separate_from_invalid_frames(self):
        r=self.runtime(source='serial')
        with patch.object(r.preprocessor,'window',side_effect=ValueError('coverage')):
            for i in range(275):r.ingest_json_line(json.dumps(frame(i,i*10000)))
        self.assertEqual(r.accepted,275)
        self.assertEqual(r.rejected,0)
        self.assertEqual(r.window_rejections,2)
        self.assertFalse(r.status()['health']['inference_ready'])
        r.ingest_json_line(json.dumps(frame(275,2750000)))
        self.assertFalse(r.status()['health']['inference_ready'])
        for i in range(276,300):r.ingest_json_line(json.dumps(frame(i,i*10000)))
        self.assertTrue(r.status()['health']['inference_ready'])
        r.reconnect()
        self.assertFalse(r.status()['health']['inference_ready'])

    def test_measured_hotspot_jitter_override_never_relabels_model_config(self):
        default=self.runtime(source='serial')
        hotspot=self.runtime(source='serial',max_packet_gap_s=.1)
        for i in range(300):
            line=json.dumps(frame(i,i*10000+(70000 if i>=100 else 0)))
            default.ingest_json_line(line);hotspot.ingest_json_line(line)
        self.assertEqual(default.packet_gap_count,1)
        self.assertFalse(default.status()['health']['inference_ready'])
        self.assertEqual(hotspot.packet_gap_count,0)
        self.assertTrue(hotspot.status()['health']['inference_ready'])
        hotspot.ingest_json_line(json.dumps(frame(300,3220000)))
        self.assertFalse(hotspot.status()['health']['inference_ready'])
        with self.assertRaisesRegex(ValueError,'saved preprocessing'):
            self.runtime(source='serial',model=self.root/'unused.tflite',max_packet_gap_s=.1)
        with self.assertRaises(ValueError):self.runtime(source='serial',max_packet_gap_s=.3)

    def test_room_motion_calibration_does_not_lower_sudden_motion_trigger(self):
        r=self.runtime(source='serial',policy=Policy(motion_threshold=.0005))
        with patch.object(r.preprocessor,'motion_energy',return_value=.003):
            for i in range(300):r.ingest_json_line(json.dumps(frame(i,i*10000)))
        self.assertEqual(r.machine.state,'normal')
        self.assertEqual(r.machine.policy.sudden_motion_threshold,.08)

    def test_calibration_requires_separation_and_matching_setup(self):
        from tools.calibrate_motion import compare_sessions
        def session(label,values,start):
            return {'label':label,'status':'passed','setup_id':'fixture','preprocess_config_hash':'fixture-hash','start_utc':start,'end_utc':start+30,'samples':[{'energy':float(v)} for v in values]}
        quiet=session('quiet',np.full(80,.001),0)
        movement=session('movement',np.full(80,.01),40)
        result=compare_sessions(quiet,movement)
        self.assertEqual(result['status'],'provisional_pass')
        self.assertTrue(.001<result['threshold']<.01)
        overlap=session('movement',np.full(80,.0005),40)
        self.assertEqual(compare_sessions(quiet,overlap)['status'],'not_separated')
        shifted=session('movement',np.r_[np.full(40,.01),np.full(40,.0001)],40)
        self.assertEqual(compare_sessions(quiet,shifted)['status'],'holdout_failed')
        movement['setup_id']='moved'
        with self.assertRaises(ValueError):compare_sessions(quiet,movement)

    def test_bounded_queue_and_payload_free_api(self):
        r=self.runtime(source='serial')
        for _ in range(64):self.assertTrue(r.submit_line('{}'))
        self.assertFalse(r.submit_line('{}'))
        self.assertFalse(r.submit_line('x'*4097))
        r.process_pending()
        encoded=json.dumps(r.status())+json.dumps(r.store.list())
        for forbidden in ['iq_bytes','sender_mac','password','token','video','aa:bb:cc']:
            self.assertNotIn(forbidden,encoded)

    def test_simulator_api_realtime_ack_and_csrf(self):
        r=self.runtime(demo=True)
        with TestClient(create_product_app(r)) as c:
            self.assertEqual(c.get('/').status_code,200)
            token=c.get('/config').json()['token']
            self.assertEqual(c.post('/dev/state',json={'state':'critical'}).status_code,403)
            headers={'x-srasta-token':token}
            self.assertEqual(c.post('/dev/state',headers={**headers,'origin':'https://attacker.example'},json={'state':'critical'}).status_code,403)
            self.assertEqual(c.get('/status',headers={'host':'attacker.example'}).status_code,400)
            self.assertEqual(c.post('/dev/state',headers=headers,json={'state':'other'}).status_code,422)
            for state in STATES:
                response=c.post('/dev/state',headers=headers,json={'state':state})
                self.assertEqual(response.status_code,200);self.assertEqual(response.json()['state'],state)
                with c.websocket_connect('/ws') as ws:
                    update=ws.receive_json()
                    self.assertEqual(update['status']['state'],state)
                    self.assertTrue(update['status']['simulated'])
                    self.assertEqual(update['status']['active_event_id'],update['events'][0]['id'])
                self.assertEqual(response.json()['events'][0]['state'],state)
            self.assertEqual(len(c.get('/events').json()['events']),5)
            event_id=r.current_event_id
            self.assertTrue(c.post(f'/events/{event_id}/acknowledge',headers=headers).json()['acknowledged'])
            self.assertFalse(c.post(f'/events/{event_id}/acknowledge',headers=headers).json()['acknowledged'])
            self.assertEqual(r.machine.state,'critical');self.assertFalse(r.alarm.active)

    def test_controller_not_present_for_live_or_replay(self):
        for source in ['replay','serial']:
            r=self.runtime(source=source)
            with TestClient(create_product_app(r)) as c:
                config=c.get('/config').json()
                self.assertFalse(config['demo'])
                self.assertEqual(c.post('/dev/state',headers={'x-srasta-token':config['token']},json={'state':'critical'}).status_code,404)
            with self.assertRaises(PermissionError):r.simulate('critical')

    def test_critical_ack_persists_across_restart(self):
        path=self.root/'persistent.sqlite3'
        r=ProductRuntime(path,demo=True);r.simulate('critical');event_id=r.current_event_id;r.close()
        r=ProductRuntime(path,demo=True)
        self.assertEqual(r.machine.state,'critical');self.assertTrue(r.alarm.active)
        self.assertTrue(r.acknowledge(event_id));r.close()
        r=ProductRuntime(path,demo=True)
        self.assertTrue(r.machine.acknowledged);self.assertFalse(r.alarm.active);r.close()

    def test_old_event_ack_does_not_silence_new_critical(self):
        r=self.runtime(demo=True)
        r.simulate('critical');old=r.current_event_id;r.simulate('normal');r.simulate('critical')
        r.acknowledge(old)
        self.assertTrue(r.alarm.active);self.assertFalse(r.machine.acknowledged)

    def test_event_only_camera_and_expired_results(self):
        camera=Mock();camera.poll.return_value=None
        r=self.runtime(source='serial',camera=camera)
        r.observe(Observation(0,True,.05));camera.request.assert_not_called()
        r.observe(Observation(1,True,.2,fall_probability=.9));camera.request.assert_called_once()
        event_id=r.current_event_id
        self.assertFalse(r.apply_camera_result(event_id-1,{'supports_anomaly':True}))
        r.last_received=time.monotonic()-4
        self.assertFalse(r.apply_camera_result(event_id,{'supports_anomaly':True}))
        r.last_received=time.monotonic()
        self.assertTrue(r.apply_camera_result(event_id,{'supports_anomaly':True,'status':'complete','keypoints':[],'active':False}))
        self.assertEqual(r.machine.state,'critical')
        self.assertNotIn('keypoints',json.dumps(r.store.list()))

    def test_camera_requests_capture_only_after_event(self):
        points=np.tile([.5,.5,.9],(17,1));points[[5,6,11,12,15,16],1]=np.linspace(.1,.9,6)
        capture=Mock(return_value=[points]*3)
        camera=EventCamera(capture=capture)
        capture.assert_not_called();self.assertTrue(camera.request(42));camera.requests.join()
        event,result=camera.poll();self.assertEqual(event,42);self.assertTrue(result['supports_anomaly']);self.assertFalse(result['active'])
        capture.assert_called_once();camera.close()
        with self.assertRaises(ValueError):summarize_pose(np.zeros((16,3)))

    def test_breathing_quality_and_known_synthetic_frequency(self):
        t=np.arange(3100)/100
        x=10+np.sin(2*np.pi*.3*t)[:,None]*np.linspace(.1,1,52)[None]
        result=estimate_breathing(x,t,quiet=True,signal_good=True)
        self.assertAlmostEqual(result['bpm'],18,delta=1)
        self.assertFalse(result['validated'])
        for values,quiet,good in [(x,False,True),(x,True,False),(np.ones_like(x),True,True),(np.random.default_rng(2).normal(size=x.shape),True,True)]:
            self.assertIsNone(estimate_breathing(values,t,quiet=quiet,signal_good=good)['bpm'])

    def test_alternative_classifier_contract_and_runtime_loading(self):
        import joblib
        from sklearn.linear_model import LogisticRegression
        from srasta_csi.feature_model import rich_features,FeatureInference,FEATURE_VERSION
        from srasta_csi.preprocess import PreprocessConfig
        from srasta_csi.contract import CaptureProfile
        x=np.random.default_rng(42).normal(size=(250,52))
        features=rich_features(x)
        with self.assertRaises(ValueError):rich_features(x[:,:51])
        model=LogisticRegression().fit(np.stack([features,features+.1]),[0,1])
        profile=CaptureProfile();config=PreprocessConfig(capture_profile_hash=profile.hash)
        artifact={'artifact_type':'srasta_feature_classifier_v1','feature_version':FEATURE_VERSION,'feature_count':len(features),'model':model,'window_length':250,'threshold':.55,'capture_profile_hash':profile.hash,'preprocess_config_hash':config.hash}
        path=self.root/'alternative.joblib';joblib.dump(artifact,path)
        (self.root/'capture_profile.json').write_text(json.dumps(profile.to_json()))
        (self.root/'preprocess_config.json').write_text(json.dumps(config.to_json()))
        r=self.runtime(source='replay',model=path)
        self.assertEqual(r.machine.policy.fall_threshold,.55)
        self.assertTrue(0<=r.model.probability(x)<=1)
        artifact['feature_version']='wrong';joblib.dump(artifact,path)
        with self.assertRaises(ValueError):FeatureInference(path)

    def test_breathing_is_withheld_without_confirmed_presence(self):
        r=self.runtime(source='serial')
        periodic={'bpm':18.,'quality':.95,'reason':'experimental_estimate','validated':False,'anomaly':False}
        with patch('srasta_csi.product.estimate_breathing',return_value=periodic):
            for i in range(300):r.ingest_json_line(json.dumps(frame(i,i*10000)))
        self.assertIsNone(r.breathing['bpm'])
        self.assertEqual(r.breathing['reason'],'no_confirmed_presence')

    def test_serial_boot_marker_resets_epoch_but_preserves_critical(self):
        r=self.runtime(source='serial')
        r.ingest_json_line(json.dumps(frame(900,9000000)))
        r.observe(Observation(10,True,.2,sudden_motion=True))
        for t in range(11,23):r.observe(Observation(float(t),True,0))
        self.assertEqual(r.machine.state,'critical')
        source=SourceRunner(r)
        source._consume_line('# SRASTA hotspot receiver awaiting association; credentials hidden')
        source._consume_line(json.dumps(frame(0,10000)))
        r.process_pending()
        self.assertEqual(r.machine.state,'critical')
        self.assertEqual(r.validator.stats()['accepted_frames'],1)
        self.assertEqual(r.reconnects,1)

    def test_silent_serial_reopens_then_accepts_real_frame_without_clearing_critical(self):
        from unittest.mock import MagicMock
        r=self.runtime(source='serial')
        r.machine.state='critical'
        source=SourceRunner(r,port='fixture',idle_timeout_s=.01)
        silent=MagicMock();silent.__enter__.return_value=silent;silent.in_waiting=0
        silent.read.side_effect=lambda *_:time.sleep(.02) or b''
        working=MagicMock();working.__enter__.return_value=working;working.in_waiting=1
        def read(*_):
            source.stop.set()
            return (json.dumps(frame(0,10000))+'\n').encode()
        working.read.side_effect=read
        with patch('serial.Serial',side_effect=[silent,working]) as factory,patch.object(source.stop,'wait',return_value=False):
            source.run()
        self.assertEqual(factory.call_count,2)
        silent.__exit__.assert_called_once()
        self.assertEqual(r.accepted,1)
        self.assertEqual(r.machine.state,'critical')
        self.assertTrue(r.status()['health']['fresh'])
        self.assertIsNone(r.input_error)

    def test_serial_diagnostics_expose_only_allowlisted_numbers(self):
        r=self.runtime(source='serial');source=SourceRunner(r)
        source._consume_line('# SRASTA connected=0 disconnect_reason=201 ssid=private password=secret sender_mac=aa:bb:cc:dd:ee:ff')
        report=r.status()['firmware_diagnostics']
        self.assertEqual(report['connected'],0)
        self.assertEqual(report['disconnect_reason'],201)
        self.assertEqual(set(report),{'connected','disconnect_reason','updated_at'})
        source._consume_line('# SRASTA ping_sent=100 ping_replies=95 ping_timeouts=4 ping_reply_ms=3 secret=ignored')
        self.assertEqual(r.status()['firmware_diagnostics']['ping_timeouts'],4)
        self.assertNotIn('secret',r.status()['firmware_diagnostics'])
        self.assertEqual(r.accepted,0)
        self.assertEqual(r.rejected,0)
        self.assertNotIn('secret',json.dumps(report))

    def test_failed_int8_conversion_cannot_enter_runtime(self):
        from srasta_csi.edge import TFLiteInference
        (self.root/'training_config.json').write_text(json.dumps({'representative_dataset':'curated ESP32-S3 train split only','manifest_sha256':'0'*64}))
        (self.root/'parity.json').write_text(json.dumps({'status':'failed'}))
        with self.assertRaisesRegex(ValueError,'parity'):TFLiteInference(self.root/'model.tflite')

    def test_external_source_test_never_enters_pretraining(self):
        from srasta_csi.pretraining import pretrain_esp_fi
        (self.root/'manifest.json').write_text(json.dumps({'license':'CC BY 4.0','source_test_downloaded':1}))
        with self.assertRaises(ValueError):pretrain_esp_fi(None,self.root,None)

    def test_hampel_rejects_spike_but_tracks_sustained_change(self):
        from srasta_csi.preprocess import CausalPreprocessor,PreprocessConfig
        p=CausalPreprocessor(PreprocessConfig())
        x=np.full((100,52),10,dtype=np.float32);x[20]=100;x[50:]=20
        filtered=p._hampel(x)
        self.assertEqual(float(filtered[20,0]),10)
        self.assertEqual(float(filtered[-1,0]),20)
        with self.assertRaises(ValueError):PreprocessConfig.from_json({'hampel_window':7})

    def test_breathing_rate_change_requires_baseline_and_consistent_quality(self):
        monitor=BreathingMonitor()
        estimate=lambda bpm: {'bpm':bpm,'quality':.9,'anomaly':False,'validated':False}
        for _ in range(6):self.assertFalse(monitor.update(estimate(18))['anomaly'])
        self.assertEqual(monitor.baseline,18)
        for _ in range(2):self.assertFalse(monitor.update(estimate(28))['anomaly'])
        self.assertTrue(monitor.update(estimate(28))['anomaly'])
        self.assertFalse(monitor.update(unavailable('source_unavailable'))['anomaly'])
        self.assertFalse(monitor.update(estimate(28))['anomaly'])
        monitor.reset()
        self.assertIsNone(monitor.baseline)

    def test_replay_generates_real_rule_transition_and_persistent_event(self):
        r=self.runtime(source='replay',policy=Policy(motion_threshold=.002))
        path=self.root/'motion.npz'
        t=np.arange(500)/100
        x=20+19*np.sin(2*np.pi*7*t[:,None]+np.linspace(0,2*np.pi,52))
        np.savez(path,amplitude=x,timestamps_s=t)
        SourceRunner(r,replay=path,realtime=False).run()
        events=r.store.list()
        self.assertGreater(len(events),0)
        self.assertEqual(events[0]['source'],'replay')
        self.assertIn(events[0]['state'],('normal','anomaly'))
        self.assertIsNone(events[0]['confidence'])
        with TestClient(create_product_app(r)) as c:
            self.assertEqual(c.get('/events').json()['events'],events)

    def test_optional_notifications_fail_closed_and_rate_limited(self):
        sent=[];adapter=Notifications(enabled=True,transport=sent.append)
        event={'id':1,'state':'critical','reason':'possible_fall','source':'simulator','occurred_at':1,'iq_bytes':[1],'password':'secret'}
        self.assertFalse(adapter.send(event,now=0));event['source']='serial'
        self.assertTrue(adapter.send(event,now=1));self.assertFalse(adapter.send(event,now=2));adapter.pending.join()
        self.assertEqual(len(sent),1);self.assertNotIn('iq_bytes',sent[0]);self.assertNotIn('password',sent[0]);adapter.close()
        adapter=Notifications(enabled=True,transport=Mock(side_effect=RuntimeError('secret')))
        self.assertTrue(adapter.send(event));adapter.pending.join();self.assertEqual(adapter.failed,1);adapter.close()

    def test_npz_and_jsonl_replay_reach_state_and_sqlite(self):
        for suffix in ['npz','jsonl']:
            r=self.runtime(source='replay',model=write_model(self.root,window_length=4))
            path=self.root/f'replay.{suffix}'
            if suffix=='npz':
                # Intentionally synthetic integration fixture, never model accuracy evidence.
                np.savez(path,amplitude=np.tile(np.linspace(1,100,300)[:,None],(1,52)),timestamps_s=np.arange(300)/100)
            else:
                path.write_text('\n'.join(json.dumps(frame(i,i*10000)) for i in range(300)))
            SourceRunner(r,replay=path,realtime=False).run()
            self.assertEqual(r.accepted,300)
            self.assertIsNotNone(r.last_inference)
            self.assertEqual(r.source_status,'replay_complete')
            self.assertFalse(r.status()['health']['fresh'])
            self.assertEqual(r.status()['source'],'replay')

if __name__=='__main__':unittest.main()
