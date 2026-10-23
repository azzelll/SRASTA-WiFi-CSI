"""Versioned summary-only contract shared by local UI and outbound cloud sync."""
from __future__ import annotations

import time

PUBLIC_STATES = {"standby", "normal", "inactive", "anomaly", "critical"}


def caregiver_snapshot(runtime) -> dict[str, object]:
    status = runtime.status()
    age = status["stream_age_s"]
    transport = status.get("transport") or {}
    is_live = bool(transport.get("connected") and age is not None and age < 10 and not status["simulation_mode"])
    source = "simulator" if runtime.demo_mode else "replay" if runtime.last_replay_source else "live" if is_live else "unavailable"
    infer_age = None if runtime.last_inference_wall_s is None else max(0.0, time.time() - runtime.last_inference_wall_s)
    confidence = status["fall_probability"] if infer_age is not None and infer_age < 10 and source == "live" else None
    state = str(status["public_state"])
    latest = status.get("latest_csi") or {}
    rssi = latest.get("rssi_dbm")
    signal_quality = round(max(0, min(100, (rssi + 95) * 100 / 55))) if is_live and isinstance(rssi, (int, float)) else None
    return {
        "schema_version": 1,
        "updated_at_s": time.time(),
        "observed_at_s": status["observed_at_s"],
        "source": source,
        "simulation": status["simulation_mode"],
        "state": state if state in PUBLIC_STATES else "standby",
        "state_verified": source == "simulator" or (is_live and infer_age is not None and infer_age < 10),
        "monitoring_online": is_live,
        "stream_age_s": age,
        "activity": "Gerakan terdeteksi" if is_live and status["motion_energy"] >= runtime.machine.motion_threshold else "Tubuh relatif diam" if is_live and infer_age is not None else "Belum tersedia",
        "motion_energy": status["motion_energy"] if is_live or source == "replay" else None,
        "presence": status["features"]["presence"] if is_live or source == "replay" else "unknown",
        "inactivity": status["features"]["inactive"] if is_live or source == "replay" else None,
        "stationary_duration_s": status["features"]["stationary_duration_s"] if is_live or source == "replay" else None,
        "breathing_condition": status["features"]["breathing_condition"] if is_live or source == "replay" else None,
        "fall_confidence": confidence,
        "breathing_bpm": status["breathing_estimate_bpm"] if is_live else None,
        "breathing_quality": status["breathing_quality"] if is_live else 0,
        "breathing_reason": runtime.breathing.reason,
        "signal_quality": signal_quality,
        "capture_rate_hz": status["capture_rate_hz"],
        "accepted_frames": status["accepted_frames"],
        "quarantined_frames": status["quarantine_count"],
        "packet_loss_rate": status["packet_quality"]["packet_drop_rate"],
        "inference_ms": status["inference_latency_ms"],
        "serial_connected": bool(transport.get("connected")),
        "serial_reconnects": transport.get("reconnects", 0),
        "alarm": runtime.alarm_status() if runtime.alarm_status else {"requested": status["local_alarm_on"], "available": False, "active": False},
        "camera": runtime.camera_status() if runtime.camera_status else {"available": False, "active": False, "result": "Kamera belum tersambung"},
        "blynk_connected": bool(status["blynk"].get("connected")),
        "remote": runtime.remote_status() if runtime.remote_status else {"enabled": False, "connected": False},
        "model": {"label": "TCN-Lite INT8" if runtime.inference.__class__.__name__ == "TFLiteInference" else "RF baseline", "validation": "Kandidat engineering; validasi ruangan belum selesai", "presence_available": runtime.presence_inference is not None, "activity_classes_available": False},
        "events": runtime.store.list(100),
    }
