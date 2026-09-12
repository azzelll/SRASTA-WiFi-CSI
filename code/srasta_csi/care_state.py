"""Five caregiver states; missing packets are never evidence of inactivity."""
from dataclasses import dataclass
import math

STATES = ('standby', 'normal', 'inactive', 'anomaly', 'critical')

@dataclass
class Policy:
    inactivity_s: float = 120.0
    confirmation_s: float = 10.0
    stale_s: float = 3.0
    motion_threshold: float = 0.02
    fall_threshold: float = 0.7
    sudden_motion_threshold: float = 0.08

    def __post_init__(self):
        if not all(math.isfinite(x) and x > 0 for x in (self.inactivity_s, self.confirmation_s, self.stale_s, self.motion_threshold, self.sudden_motion_threshold)):
            raise ValueError('policy durations and motion threshold must be positive and finite')
        if not 0 < self.fall_threshold <= 1:
            raise ValueError('fall threshold must be in (0,1]')

@dataclass
class Observation:
    time_s: float
    presence: bool | None
    motion: float
    quality: bool = True
    fall_probability: float | None = None
    breathing_anomaly: bool = False
    uncertain: bool = False
    sudden_motion: bool = False

    def __post_init__(self):
        if not math.isfinite(self.time_s) or not math.isfinite(self.motion) or self.motion < 0:
            raise ValueError('invalid observation')
        if self.presence is not None and type(self.presence) is not bool:
            raise ValueError('presence must be boolean or unknown')
        if self.fall_probability is not None and (not math.isfinite(self.fall_probability) or not 0 <= self.fall_probability <= 1):
            raise ValueError('invalid probability')

class CareStateMachine:
    def __init__(self, policy=None):
        self.policy = policy or Policy()
        self.state = 'standby'
        self.reason = 'no_confirmed_presence'
        self.last_time = None
        self.last_motion = None
        self.anomaly_since = None
        self.still_since = None
        self.acknowledged = False
        self.last_observation = None

    def update(self, obs):
        previous = self.state
        if self.last_time is not None:
            if obs.time_s <= self.last_time:
                raise ValueError('observation timestamps must increase')
            if obs.time_s - self.last_time > self.policy.stale_s:
                self.still_since = self.anomaly_since = self.last_motion = None
        self.last_time = obs.time_s
        self.last_observation = obs
        if not obs.quality:
            self.still_since = self.anomaly_since = self.last_motion = None
            if self.state != 'critical':
                self.state, self.reason = 'anomaly', 'insufficient_signal'
            return self.state != previous
        moving = obs.motion >= self.policy.motion_threshold
        if moving:
            self.last_motion = obs.time_s
            self.still_since = None
        elif self.still_since is None:
            self.still_since = obs.time_s
        fall = obs.sudden_motion or (obs.fall_probability is not None and obs.fall_probability >= self.policy.fall_threshold and moving)
        abnormal = fall or obs.breathing_anomaly or obs.uncertain
        if self.state == 'critical':
            if self.acknowledged and not abnormal and moving:
                self.state, self.reason = 'normal', 'activity_recovered'
                self.anomaly_since = None
            return self.state != previous
        if abnormal:
            if self.anomaly_since is None:
                self.anomaly_since = obs.time_s
            self.state = 'anomaly'
            self.reason = 'possible_fall' if fall else ('breathing_pattern' if obs.breathing_anomaly else 'uncertain_result')
            if not obs.uncertain and obs.breathing_anomaly and obs.time_s - self.anomaly_since >= self.policy.confirmation_s:
                self.state, self.reason = 'critical', 'persistent_anomaly'
        elif self.anomaly_since is not None and self.state == 'anomaly':
            if not moving and obs.presence is True and self.still_since is not None and obs.time_s - self.still_since >= self.policy.confirmation_s:
                self.state, self.reason = 'critical', 'post_anomaly_inactivity'
            elif moving:
                self.state, self.reason = 'normal', 'activity_recovered'
                self.anomaly_since = None
        elif obs.presence is not True:
            self.state, self.reason = 'standby', 'no_confirmed_presence'
            self.last_motion = None
        else:
            if self.last_motion is None:
                self.last_motion = obs.time_s
            inactive = obs.time_s - self.last_motion >= self.policy.inactivity_s
            self.state = 'inactive' if inactive else 'normal'
            self.reason = 'prolonged_inactivity' if inactive else 'ordinary_activity'
            if inactive and obs.time_s-self.last_motion >= 2*self.policy.inactivity_s:
                self.state = 'anomaly'
                self.anomaly_since = obs.time_s
                self.still_since = obs.time_s
        if self.state == 'critical' and previous != 'critical':
            self.acknowledged = False
        return self.state != previous

    def confirm_pose(self, supports_anomaly):
        # A pose can support an existing good-quality anomaly, never create one.
        if self.state == 'anomaly' and self.anomaly_since is not None and self.last_observation.quality and supports_anomaly:
            self.state, self.reason = 'critical', 'anomaly_supported_by_pose'
            self.acknowledged = False
            return True
        return False

    def acknowledge(self):
        if self.state != 'critical' or self.acknowledged:
            return False
        self.acknowledged = True
        return True
