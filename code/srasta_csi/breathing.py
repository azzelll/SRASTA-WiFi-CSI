"""Experimental SVD/FFT indication, with explicit rejection of inadequate windows."""
import numpy as np

def unavailable(reason):
    return {'bpm': None, 'quality': 0.0, 'reason': reason, 'validated': False, 'anomaly': False}

def estimate_breathing(values, times, *, quiet, signal_good, minimum_s=30.0):
    x, t = np.asarray(values,dtype=np.float64), np.asarray(times,dtype=np.float64)
    if not quiet or not signal_good:
        return unavailable('motion_or_signal_quality')
    if x.ndim != 2 or x.shape[1] != 52 or t.shape != (len(x),) or len(x) < 32:
        return unavailable('insufficient_window')
    if not np.isfinite(x).all() or not np.isfinite(t).all() or np.any(np.diff(t) <= 0):
        return unavailable('invalid_window')
    if t[-1]-t[0] < minimum_s or np.max(np.diff(t)) > 0.2:
        return unavailable('insufficient_coverage')
    grid = np.arange(t[0],t[-1],0.1)
    # Time resampling, never feature resizing. Anti-alias by bin averaging.
    bins = np.searchsorted(t, np.r_[grid,grid[-1]+.1])
    sampled = np.array([x[a:b].mean(axis=0) for a,b in zip(bins[:-1],bins[1:]) if b>a])
    if len(sampled) != len(grid):
        return unavailable('insufficient_coverage')
    sampled -= sampled.mean(axis=0)
    if np.std(sampled) < 1e-5:
        return unavailable('no_periodic_evidence')
    u,s,_ = np.linalg.svd(sampled,full_matrices=False)
    component = u[:,0]*s[0]
    power = abs(np.fft.rfft(component*np.hanning(len(component))))**2
    frequencies = np.fft.rfftfreq(len(component),.1)
    band = (frequencies >= .1)&(frequencies <= .6)
    peak = np.flatnonzero(band)[np.argmax(power[band])]
    concentration = float(power[max(1,peak-1):peak+2].sum()/max(power[1:].sum(),1e-12))
    coherence = float(s[0]**2/max(np.sum(s*s),1e-12))
    quality = min(concentration,coherence)
    if quality < .65:
        result = unavailable('low_periodicity')
        result['quality'] = round(quality,3)
        return result
    return {'bpm': round(float(frequencies[peak]*60),1), 'quality': round(quality,3), 'reason':'experimental_estimate', 'validated':False, 'anomaly':False}


class BreathingMonitor:
    """Experimental within-session rate-change indication; no clinical thresholds.

    Calibrate six quality-gated estimates, then require three estimates with a
    >=40% and >=4 bpm shift. Missing estimates never imply breathing cessation.
    Motion and source discontinuities discard the baseline.
    """
    def __init__(self):
        self.reset()

    def reset(self):
        self.reference = []
        self.baseline = None
        self.changed = 0

    def update(self, estimate):
        result = dict(estimate)
        result['anomaly'] = False
        result['baseline_bpm'] = self.baseline
        bpm = result.get('bpm')
        if bpm is None or not np.isfinite(bpm) or result.get('quality', 0) < .65:
            self.changed = 0
            return result
        if self.baseline is None:
            self.reference.append(float(bpm))
            if len(self.reference) >= 6:
                candidate = float(np.median(self.reference[-6:]))
                if np.ptp(self.reference[-6:]) <= max(3., candidate * .2):
                    self.baseline = round(candidate, 1)
                self.reference = self.reference[-6:]
        else:
            shift = abs(float(bpm) - self.baseline)
            self.changed = self.changed + 1 if shift >= max(4., .4 * self.baseline) else 0
            result['anomaly'] = self.changed >= 3
            if result['anomaly']:
                result['reason'] = 'experimental_rate_change'
        result['baseline_bpm'] = self.baseline
        return result
