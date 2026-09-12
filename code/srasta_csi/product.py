"""Product runtime: bounded CSI ingestion and five-state caregiver summaries."""
from collections import deque
from dataclasses import replace
from pathlib import Path
import math
import queue
import threading
import time
import uuid
import numpy as np
from .contract import CaptureProfile, FrameValidator
from .decoder import decode_iq_to_amplitude
from .preprocess import CausalPreprocessor, PreprocessConfig
from .care_state import CareStateMachine, Observation, Policy, STATES
from .care_store import CareEventStore
from .breathing import estimate_breathing, unavailable, BreathingMonitor
from .adapters import LocalAlarm, Notifications

class ProductRuntime:
    def __init__(self, db_path, *, source='simulator', demo=False, policy=None, sender=None, channel=1, model=None, alarm=None, notifications=None, camera=None, max_packet_gap_s=None):
        if source not in ('simulator','replay','serial') or (source=='simulator' and not demo):
            raise ValueError('simulator requires explicit demo mode')
        if demo and source != 'simulator':
            raise ValueError('development controller only belongs to simulator mode')
        self.lock = threading.RLock()
        self.session_id = uuid.uuid4().hex
        self.source, self.demo = source, demo
        self.machine = CareStateMachine(policy)
        self.sender = sender
        self.profile = CaptureProfile(channel=channel)
        self.validator = FrameValidator(self.profile, expected_sender=sender)
        self.preprocessor = CausalPreprocessor(PreprocessConfig(capture_profile_hash=self.profile.hash))
        if max_packet_gap_s is not None:
            if model is not None:
                raise ValueError('trained models require their saved preprocessing configuration')
            if not math.isfinite(max_packet_gap_s) or not 0 < max_packet_gap_s <= .2:
                raise ValueError('experimental packet gap must be finite in (0,0.2] seconds')
            self.preprocessor = CausalPreprocessor(replace(self.preprocessor.config,max_gap_s=max_packet_gap_s))
        self.model = None
        self.window_length = 250
        if model:
            from .edge import RandomForestInference,TFLiteInference,_load_config
            model = Path(model)
            if model.suffix=='.tflite':
                self.model=TFLiteInference(model)
            else:
                import joblib
                from .feature_model import FeatureInference
                kind=joblib.load(model).get('artifact_type')
                self.model=FeatureInference(model) if kind=='srasta_feature_classifier_v1' else RandomForestInference(model)
            if hasattr(self.model,'threshold'):
                self.machine.policy.fall_threshold=self.model.threshold
            self.preprocessor = CausalPreprocessor(_load_config(model,self.model))
            if self.preprocessor.config.capture_profile_hash != self.profile.hash:
                raise ValueError('model capture profile does not match configured channel')
            self.window_length = self.model.window_length
        self.frames = deque(maxlen=max(4000,self.window_length))
        self.times = deque(maxlen=max(4000,self.window_length))
        self.pending = queue.Queue(maxsize=64)
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True,exist_ok=True)
        self.store = CareEventStore(db_path)
        self.alarm = alarm or LocalAlarm()
        self.notifications = notifications or Notifications()
        self.camera = camera
        self.camera_result = {'status':'idle','keypoints':[],'evidence':'unavailable','active':False}
        self.last_received = self.last_inference = None
        self.last_utc = None
        self.last_source_time = None
        self.source_status = 'waiting'
        self.firmware_diagnostics = {}
        self.input_error = None
        self.window_error = None
        self.window_rejections = 0
        self.inference_count = 0
        self.packet_gap_count = 0
        self.max_packet_gap_s = 0.0
        self.accepted = self.rejected = self.dropped = self.reconnects = 0
        self.motion = None
        self.probability = None
        self.presence = None
        self.breathing = unavailable('insufficient_window')
        self.breathing_monitor = BreathingMonitor()
        self.trend = deque(maxlen=120)
        self.last_breathing_time = -math.inf
        self.current_event_id = None
        self.revision = 0
        self._since_infer = 0
        latest = self.store.latest(source)
        if latest and latest['state']=='critical':
            self.machine.state, self.machine.reason = 'critical', latest['reason']
            self.machine.acknowledged = latest['acknowledged_at'] is not None
            self.current_event_id = latest['id']
            self.alarm.set('critical',self.machine.acknowledged)

    def submit_line(self, line):
        if len(line)>4096:
            self.rejected += 1
            self.input_error = 'oversize_frame'
            return False
        try:
            self.pending.put_nowait(line)
            return True
        except queue.Full:
            self.dropped += 1
            return False

    def process_pending(self):
        while True:
            try:
                line = self.pending.get_nowait()
            except queue.Empty:
                break
            try:
                self.ingest_json_line(line)
            finally:
                self.pending.task_done()

    def ingest_json_line(self,line):
        with self.lock:
            try:
                frame = self.validator.parse_json_line(line)
                values = decode_iq_to_amplitude(frame.iq_bytes,first_word_invalid=frame.first_word_invalid)
            except (ValueError,TypeError):
                self.rejected += 1
                self.input_error = 'invalid_csi_frame'
                return False
            self.ingest_amplitude(values,frame.local_timestamp_us/1e6,signal_good=frame.rssi-frame.noise_floor >= 10)
            return True

    def ingest_amplitude(self,values,timestamp_s,*,signal_good=True):
        with self.lock:
            values = np.asarray(values,dtype=np.float32)
            if values.shape != (52,) or not np.isfinite(values).all() or not math.isfinite(timestamp_s):
                raise ValueError('amplitude must be finite [52] with finite time')
            if self.times and timestamp_s <= self.times[-1]:
                self.rejected += 1
                return False
            if self.times:
                self.max_packet_gap_s = max(self.max_packet_gap_s,timestamp_s-self.times[-1])
            if self.times and timestamp_s-self.times[-1] > self.preprocessor.config.max_gap_s:
                self.packet_gap_count += 1
                self.frames.clear()
                self.times.clear()
                self._since_infer = 0
                self.last_inference = None
                self.window_error = None
                self.breathing = unavailable('insufficient_coverage')
                self.breathing_monitor.reset()
                self.last_breathing_time = -math.inf
                self.machine.still_since = self.machine.anomaly_since = self.machine.last_motion = None
            self.frames.append(values.copy())
            self.times.append(timestamp_s)
            self.accepted += 1
            self.last_received,self.last_utc = time.monotonic(),time.time()
            self.last_source_time = timestamp_s
            self.source_status = 'receiving'
            self.input_error = None
            self._since_infer += 1
            if len(self.frames)<self.window_length or self._since_infer<25:
                return True
            self._since_infer = 0
            # Same shared preprocessing as offline training; fixed feature positions.
            count = min(len(self.frames), max(512,self.window_length+32))
            raw,times = np.asarray(self.frames)[-count:],np.asarray(self.times)[-count:]
            try:
                window,_ = self.preprocessor.window(raw,times,self.window_length,centered=False)
            except ValueError:
                self.window_rejections += 1
                self.window_error = 'insufficient_window_coverage'
                return False
            self.window_error = None
            started = time.perf_counter()
            self.motion = self.preprocessor.motion_energy(window[-25:])
            self.probability = self.model.probability(window) if self.model else None
            self.last_inference = (time.perf_counter()-started)*1000
            self.inference_count += 1
            # Experimental motion evidence; static occupancy is not guessed as absent.
            if self.motion>=self.machine.policy.motion_threshold:
                self.presence = True
            if self.motion>=self.machine.policy.motion_threshold or not signal_good:
                self.breathing_monitor.reset()
                self.breathing = unavailable('motion_or_signal_quality')
            if timestamp_s-self.last_breathing_time>=5:
                self.breathing = estimate_breathing(np.asarray(self.frames),np.asarray(self.times),quiet=self.motion<self.machine.policy.motion_threshold,signal_good=signal_good)
                if self.presence is not True:
                    self.breathing = unavailable('no_confirmed_presence')
                self.breathing = self.breathing_monitor.update(self.breathing)
                self.last_breathing_time = timestamp_s
            obs = Observation(timestamp_s,self.presence,self.motion,quality=signal_good,fall_probability=self.probability,breathing_anomaly=self.breathing['anomaly'],sudden_motion=self.model is None and self.motion>=self.machine.policy.sudden_motion_threshold)
            self.observe(obs)
            return True

    def observe(self,obs):
        with self.lock:
            changed = self.machine.update(obs)
            self.motion,self.probability,self.presence = obs.motion,obs.fall_probability,obs.presence
            self.last_source_time = obs.time_s
            self.last_received,self.last_utc = time.monotonic(),time.time()
            self.source_status = 'receiving'
            self.trend.append({'at':self.last_utc,'motion':round(obs.motion,6)})
            if changed:
                self._transition()
            self.revision += 1

    def _transition(self):
        self.current_event_id = self.store.append(self.machine.state,self.machine.reason,self.source,self.last_source_time,self.probability)
        self.alarm.set(self.machine.state,self.machine.acknowledged)
        self.notifications.send(self.store.list(1)[0])
        if self.machine.state == 'anomaly':
            self.camera_result = {'status':'pending' if self.camera else 'unavailable','keypoints':[],'evidence':'unavailable','active':False}
            if self.camera:
                self.camera.request(self.current_event_id)
        elif self.machine.state not in ('critical',):
            self.camera_result = {'status':'idle','keypoints':[],'evidence':'unavailable','active':False}

    def apply_camera_result(self,event_id,result):
        with self.lock:
            if event_id != self.current_event_id or self.machine.state != 'anomaly':
                return False
            if self.last_received is None or time.monotonic()-self.last_received>self.machine.policy.stale_s:
                return False
            self.camera_result = result
            if self.machine.confirm_pose(result.get('supports_anomaly',False)):
                self._transition()
            self.revision += 1
            return True

    def simulate(self,state):
        with self.lock:
            if not self.demo or self.source!='simulator':
                raise PermissionError('development controller disabled')
            if state not in STATES:
                raise ValueError('invalid state')
            self.machine.state,self.machine.reason = state,'simulated_state'
            self.machine.acknowledged = False
            self.last_source_time = time.monotonic()
            self.last_received,self.last_utc = time.monotonic(),time.time()
            self.source_status = 'receiving'
            self.presence = state!='standby'
            self.motion = .05 if state=='normal' else .0001
            self.probability = None
            self.breathing = unavailable('simulator_not_physiology')
            self._transition()
            self.revision += 1
            return self.status()

    def acknowledge(self,event_id):
        with self.lock:
            if not self.store.acknowledge(event_id):
                return False
            if event_id == self.current_event_id:
                self.machine.acknowledge()
                self.alarm.set(self.machine.state,self.machine.acknowledged)
            self.revision += 1
            return True

    def reconnect(self):
        with self.lock:
            self.reconnects += 1
            self.validator = FrameValidator(self.profile,expected_sender=self.sender)
            self.frames.clear(); self.times.clear()
            self.machine.last_time = None
            self.machine.last_motion = self.machine.anomaly_since = self.machine.still_since = None
            self.breathing = unavailable('insufficient_window')
            self.breathing_monitor.reset()
            self.last_breathing_time = -math.inf
            self.last_received = self.last_inference = None
            self.window_error = None
            self._since_infer = 0
            self.source_status = 'reconnecting'

    def heartbeat(self):
        with self.lock:
            if self.demo and self.source_status=='receiving':
                self.last_received,self.last_utc = time.monotonic(),time.time()
                self.trend.append({'at':self.last_utc,'motion':self.motion})
            if self.camera:
                item = self.camera.poll()
                if item:
                    self.apply_camera_result(*item)
            self.revision += 1

    def status(self):
        with self.lock:
            age = time.monotonic()-self.last_received if self.last_received is not None else None
            fresh = age is not None and age <= self.machine.policy.stale_s and self.source_status=='receiving'
            breathing = self.breathing if fresh else unavailable('source_unavailable')
            return {'state':self.machine.state,'reason':self.machine.reason,'source':self.source,'simulated':self.demo,
                'preprocess_config_hash':self.preprocessor.config.hash,
                'model_status':'unverified_candidate' if self.model else 'experimental_motion_rules',
                'confidence':self.probability,'presence':self.presence,'motion_energy':self.motion,
                'breathing':breathing,'updated_at':self.last_utc,'source_time_s':self.last_source_time,
                'health':{'fresh':fresh,'age_s':round(age,2) if age is not None else None,'source_status':self.source_status,'accepted_frames':self.accepted,'rejected_frames':self.rejected,'dropped_frames':self.dropped,'reconnects':self.reconnects,'error':self.input_error or self.window_error,'window_rejections':self.window_rejections,'inference_count':self.inference_count,'packet_gap_count':self.packet_gap_count,'max_packet_gap_s':round(self.max_packet_gap_s,6),'allowed_packet_gap_s':self.preprocessor.config.max_gap_s,'inference_ready':fresh and self.last_inference is not None and self.input_error is None and self.window_error is None,'queue_depth':self.pending.qsize(),'inference_ms':self.last_inference},
                'packet_quality':self.validator.stats() if self.source=='serial' else None,
                'firmware_diagnostics':dict(self.firmware_diagnostics) if self.source=='serial' else None,
                'alarm':self.alarm.status(),'notifications':self.notifications.status(),'camera':self.camera_result,
                'acknowledged':self.machine.acknowledged,'active_event_id':self.current_event_id,'trend':list(self.trend),
                'policy':{'inactivity_s':self.machine.policy.inactivity_s,'confirmation_s':self.machine.policy.confirmation_s,'motion_threshold':self.machine.policy.motion_threshold,'sudden_motion_threshold':self.machine.policy.sudden_motion_threshold},'revision':self.revision,'session_id':self.session_id}

    def close(self):
        if self.camera:
            self.camera.close()
        self.notifications.close()
        self.alarm.close()
        self.store.close()
