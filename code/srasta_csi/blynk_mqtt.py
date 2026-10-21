"""Persistent TLS MQTT bridge for a SRASTA Blynk IoT device.

Only derived, nonsensitive state is published. Commands are limited to the two
caregiver actions. The local edge runtime never waits for cloud delivery.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from urllib.parse import urlparse


DATASTREAMS = {
    0: "System State Code", 1: "System Status", 2: "Activity",
    3: "Breathing Estimate", 4: "Breathing Quality",
    # Blynk does not accept '/' in the MQTT datastream name. The display name
    # in the app remains "Fall/Anomaly Confidence".
    5: "Fall Anomaly Confidence", 6: "Signal Quality",
    7: "Last Event", 8: "Edge Health", 9: "Local Alarm",
    10: "Acknowledge Alert", 11: "Request Assistance", 12: "Simulation Mode",
}
STATE_CODES = {"standby": 0, "normal": 1, "inactive": 2, "anomaly": 3, "critical": 4}
STATE_LABELS = {
    "standby": "Siaga", "normal": "Normal", "inactive": "Tidak aktif",
    "anomaly": "Perlu perhatian", "critical": "Kritis",
}
EVENT_CODES = {"inactive": "srasta_warning", "anomaly": "srasta_warning", "critical": "srasta_critical"}


def values_from_status(status: dict[str, object], *, cloud_connected: bool) -> dict[int, str]:
    state = str(status.get("public_state", "standby"))
    if state not in STATE_CODES:
        state = "standby"
    transport = status.get("transport")
    stream_age = status.get("stream_age_s")
    simulation = bool(status.get("simulation_mode"))
    live = bool(isinstance(transport, dict) and transport.get("connected") and isinstance(stream_age, (int, float)) and stream_age < 10)
    inferred_at = status.get("inferred_at_s")
    inferred = bool(live and isinstance(inferred_at, (int, float)) and 0 <= time.time() - inferred_at < 10)
    latest = status.get("latest_csi")
    rssi = latest.get("rssi_dbm") if isinstance(latest, dict) else None
    quality = max(0, min(100, round((float(rssi) + 95) * 100 / 55))) if live and isinstance(rssi, (int, float)) else None
    probability = status.get("fall_probability")
    confidence = max(0, min(100, round(float(probability) * 100))) if inferred and isinstance(probability, (int, float)) and status.get("inference_latency_ms") is not None else None
    breathing = status.get("breathing_estimate_bpm")
    breathing_quality = status.get("breathing_quality")
    breath_ok = live and isinstance(breathing, (int, float)) and isinstance(breathing_quality, (int, float)) and breathing_quality >= 50
    serial = "terputus" if not isinstance(transport, dict) or not transport.get("connected") else (
        "aliran CSI terhenti" if stream_age is None or isinstance(stream_age, (int, float)) and stream_age >= 10 else "terhubung"
    )
    cloud = "online" if cloud_connected else "offline"
    motion = status.get("motion_energy")
    threshold = status.get("motion_threshold", 0.02)
    activity = "Gerakan terdeteksi" if inferred and isinstance(motion, (int, float)) and isinstance(threshold, (int, float)) and motion >= threshold else "Aktivitas belum dapat dipastikan"
    last_event = status.get("last_event")
    event_text = STATE_LABELS.get(str(last_event.get("state")), "Peristiwa terekam") if isinstance(last_event, dict) else "Belum ada peringatan"
    return {
        # V0 retains the last category; V1 and V8 explicitly mark stale data.
        0: str(STATE_CODES[state]), 1: STATE_LABELS[state] if live or simulation else f"Status terakhir: {STATE_LABELS[state]}; pemantauan terputus", 2: activity,
        3: str(round(float(breathing), 1)) if breath_ok else "",
        4: str(max(0, min(100, round(float(breathing_quality))))) if live and isinstance(breathing_quality, (int, float)) else "0",
        5: str(confidence) if confidence is not None else "", 6: str(quality) if quality is not None else "", 7: event_text,
        8: f"Serial {serial}; model kandidat; DB lokal; cloud {cloud}",
        9: "1" if status.get("local_alarm_on") else "0",
        12: "1" if status.get("simulation_mode") else "0",
    }


class BlynkMQTTAdapter:
    """One persistent device connection, reconnecting through paho's loop."""

    def __init__(self, token: str, *, host: str = "blynk.cloud", port: int = 8883,
                 on_acknowledge: Callable[[], object], on_assistance: Callable[[], object],
                 status_provider: Callable[[], dict[str, object]], min_interval_s: float = 30.0,
                 event_interval_s: float = 60.0, client: object | None = None):
        if not token or not token.strip():
            raise ValueError("Blynk token is required for an enabled adapter")
        if not host.endswith(".blynk.cloud") and host != "blynk.cloud":
            raise ValueError("Blynk MQTT host must be an official Blynk domain")
        if port != 8883 or min_interval_s <= 0 or event_interval_s <= 0:
            raise ValueError("Blynk requires TLS port 8883 and positive rate limits")
        if client is None:
            import paho.mqtt.client as mqtt
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv311, clean_session=True)
            client.tls_set()
        self.client = client
        self.client.username_pw_set("device", token)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.host, self.port = host, port
        self.on_acknowledge, self.on_assistance = on_acknowledge, on_assistance
        self.status_provider = status_provider
        self.min_interval_s, self.event_interval_s = min_interval_s, event_interval_s
        self._lock = threading.RLock()
        self.connected = False
        self.started = False
        self._started_at = time.monotonic()
        self._last_send = 0.0
        self._last_state: str | None = None
        self._last_offline = False
        self._last_events: dict[str, float] = {}
        self._latest: dict[str, object] | None = None
        self.last_error: str | None = None
        self._redirect_host: str | None = None
        self._received_commands: dict[tuple[str, int], float] = {}

    def start(self) -> None:
        if self.started:
            return
        self.started = True
        self.client.connect_async(self.host, self.port, keepalive=45)
        self.client.loop_start()

    def close(self) -> None:
        if self.started:
            self.client.disconnect()
            self.client.loop_stop()
        self.started = False
        self.connected = False

    def status(self) -> dict[str, object]:
        with self._lock:
            return {"enabled": True, "connected": self.connected, "host": self.host,
                    "last_error": self.last_error, "worker_running": self.started}

    def _on_connect(self, client, _userdata, _flags, reason_code, _properties) -> None:
        code = int(getattr(reason_code, "value", reason_code))
        with self._lock:
            self.connected = code == 0
            self.last_error = None if self.connected else f"MQTT connect code {code}"
        if self.connected:
            client.subscribe("downlink/ds/#", qos=1)
            client.subscribe("downlink/redirect", qos=1)
            self._last_offline = False
            self._publish_latest(force=True)

    def _on_disconnect(self, _client, _userdata, _flags, reason_code, _properties) -> None:
        code = int(getattr(reason_code, "value", reason_code))
        with self._lock:
            self.connected = False
            if code != 0:
                self.last_error = f"MQTT disconnected: {code}"

    def _on_message(self, client, _userdata, message) -> None:
        if message.topic == "downlink/redirect":
            try:
                target = urlparse(message.payload.decode("utf-8").strip())
                if target.scheme != "mqtts" or not target.hostname or not target.hostname.endswith(".blynk.cloud") or target.port not in {None, 8883} or target.username or target.path not in {"", "/"} or target.query or target.fragment:
                    raise ValueError("invalid redirect URI")
                self._redirect_host = target.hostname
            except (UnicodeDecodeError, ValueError, AttributeError):
                self.last_error = "invalid Blynk redirect"
            return
        if message.payload.strip() != b"1":
            return
        actions = {
            "downlink/ds/Acknowledge Alert": (self.on_acknowledge, "Acknowledge Alert"),
            "downlink/ds/Request Assistance": (self.on_assistance, "Request Assistance"),
        }
        action = actions.get(message.topic)
        if action is None:
            return
        command_key = (message.topic, getattr(message, "mid", -1))
        now = time.monotonic()
        self._received_commands = {key: timestamp for key, timestamp in self._received_commands.items() if now - timestamp < 120}
        if getattr(message, "dup", False) and command_key in self._received_commands:
            return
        callback, name = action
        try:
            callback()
            self._received_commands[command_key] = now
            client.publish(f"ds/{name}", "0", qos=1)
        except Exception as exc:
            self.last_error = f"caregiver action failed: {type(exc).__name__}"

    def update(self, status: dict[str, object], *, now_s: float | None = None) -> None:
        # Called by the publisher worker, outside paho's callback thread.
        # Stop the old loop before selecting the regional endpoint.
        if self._redirect_host:
            host, self._redirect_host = self._redirect_host, None
            self.client.disconnect()
            self.client.loop_stop()
            self.host = host
            self.client.connect_async(host, self.port, keepalive=45)
            self.client.loop_start()
        now = time.monotonic() if now_s is None else now_s
        with self._lock:
            self._latest = status
            state = str(status.get("public_state", "standby"))
            transition = state != self._last_state
            self._last_state = state
            transport = status.get("transport")
            age = status.get("stream_age_s")
            offline = isinstance(transport, dict) and (
                not transport.get("connected") or
                (isinstance(age, (int, float)) and age >= 10) or
                (age is None and now - self._started_at >= 10)
            )
            if self.connected and (transition or offline != self._last_offline or now - self._last_send >= self.min_interval_s):
                self._publish_latest(force=True, now_s=now)
            if self.connected and transition and state in EVENT_CODES:
                self._event(EVENT_CODES[state], state, now)
            if self.connected and offline and not self._last_offline:
                self._event("srasta_device_offline", "RX atau aliran CSI terputus", now)
            self._last_offline = offline

    def _publish_latest(self, *, force: bool, now_s: float | None = None) -> None:
        del force
        if not self.connected:
            return
        snapshot = self._latest or self.status_provider()
        for pin, value in values_from_status(snapshot, cloud_connected=True).items():
            topic = f"ds/{DATASTREAMS[pin]}"
            if pin in {3, 5, 6} and value == "":
                self.client.publish(f"{topic}/erase", "", qos=1)
            else:
                self.client.publish(topic, value, qos=1)
        self._last_send = time.monotonic() if now_s is None else now_s

    def _event(self, code: str, description: str, now_s: float) -> None:
        simulation = bool((self._latest or self.status_provider()).get("simulation_mode"))
        key = f"{code}:{simulation}:{description}"
        if now_s - self._last_events.get(key, float("-inf")) < self.event_interval_s:
            return
        text = f"SIMULASI: {description}" if simulation else description
        self.client.publish(f"event/{code}", text[:120], qos=1)
        self._last_events[key] = now_s
