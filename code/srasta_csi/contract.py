"""Strict versioned JSONL contract for ESP32-S3 CSI frames."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from .decoder import RAW_IQ_BYTE_COUNT


class FrameValidationError(ValueError):
    pass


@dataclass(frozen=True)
class CaptureProfile:
    version: int = 1
    ltf: str = "LLTF"
    bandwidth: str = "HT20"
    sig_mode: str = "HT"
    channel: int = 1
    iq_order: str = "imaginary_real"
    raw_len: int = RAW_IQ_BYTE_COUNT

    @property
    def hash(self) -> str:
        body = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(body.encode("utf-8")).hexdigest()

    def to_json(self) -> dict[str, object]:
        return {**asdict(self), "hash": self.hash}


@dataclass(frozen=True)
class CSIFrame:
    version: int
    sequence: int
    local_timestamp_us: int
    sender_mac: str
    rssi: int
    noise_floor: int
    channel: int
    bandwidth: str
    sig_mode: str
    mcs: int
    rx_state: int
    length: int
    first_word_invalid: bool
    iq_bytes: tuple[int, ...]


_FIELD_MAP = {
    "version", "sequence", "local_timestamp_us", "sender_mac", "rssi", "noise_floor",
    "channel", "bandwidth", "sig_mode", "mcs", "rx_state", "len", "first_word_invalid", "iq_bytes",
}
_MAC = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$", re.IGNORECASE)


class FrameValidator:
    """Validate the active capture profile and retain payload-free quality counters."""

    def __init__(self, profile: CaptureProfile | None = None):
        self.profile = profile or CaptureProfile()
        self._last_sequence: int | None = None
        self._last_timestamp_us: int | None = None
        self.accepted_frames = 0
        self.quarantined_frames = 0
        self.sequence_gap_events = 0
        self.missing_packets = 0

    def parse_json_line(self, line: str) -> CSIFrame:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            self.quarantined_frames += 1
            raise FrameValidationError("frame is not valid JSON") from exc
        if not isinstance(payload, dict):
            self.quarantined_frames += 1
            raise FrameValidationError("frame must be a JSON object")
        return self._validate(payload, count_quarantine=True)

    def validate(self, payload: dict[str, Any]) -> CSIFrame:
        return self._validate(payload, count_quarantine=True)

    def _validate(self, payload: dict[str, Any], *, count_quarantine: bool) -> CSIFrame:
        try:
            return self._validate_fields(payload)
        except FrameValidationError:
            if count_quarantine:
                self.quarantined_frames += 1
            raise

    def _validate_fields(self, payload: dict[str, Any]) -> CSIFrame:
        if set(payload) != _FIELD_MAP:
            missing = sorted(_FIELD_MAP - set(payload))
            unknown = sorted(set(payload) - _FIELD_MAP)
            raise FrameValidationError(f"frame schema mismatch; missing={missing}, unknown={unknown}")
        version = _integer(payload["version"], "version")
        sequence = _integer(payload["sequence"], "sequence")
        timestamp = _integer(payload["local_timestamp_us"], "local_timestamp_us")
        length = _integer(payload["len"], "len")
        channel = _integer(payload["channel"], "channel")
        mcs = _integer(payload["mcs"], "mcs")
        rx_state = _integer(payload["rx_state"], "rx_state")
        rssi = _integer(payload["rssi"], "rssi")
        noise_floor = _integer(payload["noise_floor"], "noise_floor")
        if version != self.profile.version or length != self.profile.raw_len:
            raise FrameValidationError("frame version or CSI length differs from active capture profile")
        if payload["bandwidth"] != self.profile.bandwidth or payload["sig_mode"] != self.profile.sig_mode:
            raise FrameValidationError("frame radio profile differs from active capture profile")
        if rx_state != 0 or channel != self.profile.channel or mcs < 0 or sequence < 0 or timestamp < 0:
            raise FrameValidationError("frame channel/metadata is invalid or receiver reported an error")
        sender_mac = payload["sender_mac"]
        if not isinstance(sender_mac, str) or not _MAC.fullmatch(sender_mac):
            raise FrameValidationError("sender_mac must be a colon-delimited MAC address")
        if not isinstance(payload["first_word_invalid"], bool):
            raise FrameValidationError("first_word_invalid must be boolean")
        iq_bytes = payload["iq_bytes"]
        if not isinstance(iq_bytes, list) or len(iq_bytes) != RAW_IQ_BYTE_COUNT:
            raise FrameValidationError("iq_bytes must contain exactly 128 signed values")
        if any(not isinstance(value, int) or isinstance(value, bool) or value < -128 or value > 127 for value in iq_bytes):
            raise FrameValidationError("iq_bytes contains a value outside signed int8 range")
        if self._last_sequence is not None and sequence <= self._last_sequence:
            raise FrameValidationError("sequence must be strictly increasing")
        if self._last_timestamp_us is not None and timestamp <= self._last_timestamp_us:
            raise FrameValidationError("local timestamp must be strictly increasing")
        if self._last_sequence is not None and sequence > self._last_sequence + 1:
            self.sequence_gap_events += 1
            self.missing_packets += sequence - self._last_sequence - 1
        self._last_sequence = sequence
        self._last_timestamp_us = timestamp
        self.accepted_frames += 1
        return CSIFrame(
            version=version, sequence=sequence, local_timestamp_us=timestamp, sender_mac=sender_mac.lower(),
            rssi=rssi, noise_floor=noise_floor, channel=channel, bandwidth=payload["bandwidth"],
            sig_mode=payload["sig_mode"], mcs=mcs, rx_state=rx_state, length=length,
            first_word_invalid=payload["first_word_invalid"], iq_bytes=tuple(iq_bytes),
        )

    def stats(self) -> dict[str, int | None]:
        return {
            "accepted_frames": self.accepted_frames,
            "quarantined_frames": self.quarantined_frames,
            "sequence_gap_events": self.sequence_gap_events,
            "missing_packets": self.missing_packets,
            "last_sequence": self._last_sequence,
            "last_timestamp_us": self._last_timestamp_us,
        }

    @staticmethod
    def quarantine(reason: Exception | str, payload: object | None = None) -> dict[str, str]:
        """Return bounded diagnostics only. Never retain raw I/Q in quarantine data."""
        del payload
        return {"status": "quarantined", "reason": str(reason)[:240]}


def _integer(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise FrameValidationError(f"{name} must be an integer")
    return value
