#!/usr/bin/env python3
"""
infer_blynk.py

Inference real-time SRASTA di Raspberry Pi:
- Baca CSI dari serial ESP32-S3 receiver.
- Preprocessing window.
- Inferensi TFLite.
- State machine sederhana: standby/normal/inactive/anomaly/critical.
- Estimasi breathing rate berbasis SVD + FFT.
- Kirim status ke Blynk Datastream + log event untuk alert.

Format serial yang didukung:
1) JSON: {"csi":[...]}
2) Baris ESP-CSI berisi angka dalam kurung siku: CSI_DATA,...,[1,2,3,...]
3) CSV angka: 1,2,3,...

Contoh:
python3 infer_blynk.py \
  --model runs/srasta_fall/model_int8.tflite \
  --labels runs/srasta_fall/label_map.json \
  --serial-port /dev/ttyUSB0 \
  --baud 921600 \
  --win-len 500 \
  --feature-size 232 \
  --sample-rate 50
"""

import argparse
import json
import os
import re
import time
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlencode

import numpy as np
import requests
from scipy import signal
from scipy.fft import rfft, rfftfreq

try:
    from tflite_runtime.interpreter import Interpreter
except Exception:
    from tensorflow.lite import Interpreter

try:
    import serial
except Exception:
    serial = None


def load_labels(path: str) -> Dict[int, str]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    # file training menyimpan name -> id
    return {int(v): str(k) for k, v in raw.items()}


class BlynkClient:
    def __init__(self, token: str, server: str = "blynk.cloud", event_code: str = "srasta_alert"):
        self.token = token
        self.server = server.replace("https://", "").replace("http://", "").strip("/")
        self.event_code = event_code
        self.session = requests.Session()
        self.last_event_ts = 0.0

    def batch_update(self, values: Dict[str, object]) -> None:
        if not self.token:
            return
        params = {"token": self.token}
        params.update({pin.lower(): str(value) for pin, value in values.items()})
        url = f"https://{self.server}/external/api/batch/update"
        r = self.session.get(url, params=params, timeout=3)
        if r.status_code >= 300:
            print(f"[BLYNK] batch_update failed {r.status_code}: {r.text[:200]}")

    def log_event(self, description: str, min_interval_s: int = 60) -> None:
        if not self.token or not self.event_code:
            return
        now = time.time()
        if now - self.last_event_ts < min_interval_s:
            return
        self.last_event_ts = now

        params = {
            "token": self.token,
            "code": self.event_code,
            "description": description[:280],
        }
        url = f"https://{self.server}/external/api/logEvent"
        r = self.session.get(url, params=params, timeout=3)
        if r.status_code >= 300:
            print(f"[BLYNK] log_event failed {r.status_code}: {r.text[:200]}")


def parse_csi_line(line: bytes) -> Optional[np.ndarray]:
    text = line.decode("utf-8", errors="ignore").strip()
    if not text:
        return None

    # JSON format: {"csi":[...]}
    if text.startswith("{") and text.endswith("}"):
        try:
            obj = json.loads(text)
            for key in ["csi", "CSI", "CSI_DATA", "data", "raw"]:
                if key in obj:
                    arr = np.asarray(obj[key], dtype=np.float32)
                    return np.nan_to_num(arr)
        except Exception:
            pass

    # ESP-CSI biasanya punya list dalam [...]
    m = re.search(r"\[([^\]]+)\]", text)
    if m:
        nums = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", m.group(1))
    else:
        nums = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", text)

    if len(nums) < 8:
        return None

    arr = np.asarray([float(x) for x in nums], dtype=np.float32)
    return np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)


def resize_vector(vec: np.ndarray, feature_size: int) -> np.ndarray:
    vec = vec.astype(np.float32).reshape(-1)
    n = vec.shape[0]
    if n == feature_size:
        return vec
    if n > feature_size:
        idx = np.linspace(0, n - 1, feature_size).astype(np.int64)
        return vec[idx]
    out = np.zeros(feature_size, dtype=np.float32)
    out[:n] = vec
    return out


def normalize_window(w: np.ndarray) -> np.ndarray:
    mean = w.mean(axis=0, keepdims=True)
    std = w.std(axis=0, keepdims=True) + 1e-6
    return ((w - mean) / std).astype(np.float32)


class TFLiteModel:
    def __init__(self, path: str):
        self.interpreter = Interpreter(model_path=path, num_threads=2)
        self.interpreter.allocate_tensors()
        self.input_details = self.interpreter.get_input_details()[0]
        self.output_details = self.interpreter.get_output_details()[0]

    def predict(self, x: np.ndarray) -> np.ndarray:
        x = x.astype(np.float32)
        # x shape [1, T, F]
        in_dtype = self.input_details["dtype"]
        if in_dtype in (np.int8, np.uint8):
            scale, zero = self.input_details["quantization"]
            if scale == 0:
                scale = 1.0
            xq = np.round(x / scale + zero).astype(in_dtype)
            self.interpreter.set_tensor(self.input_details["index"], xq)
        else:
            self.interpreter.set_tensor(self.input_details["index"], x.astype(in_dtype))

        self.interpreter.invoke()
        y = self.interpreter.get_tensor(self.output_details["index"])[0]

        out_dtype = self.output_details["dtype"]
        if out_dtype in (np.int8, np.uint8):
            scale, zero = self.output_details["quantization"]
            if scale == 0:
                scale = 1.0
            y = (y.astype(np.float32) - zero) * scale

        # Pastikan probabilitas valid
        y = np.maximum(y.astype(np.float32), 0)
        if y.sum() > 0:
            y = y / y.sum()
        return y


def estimate_breathing_bpm(window: np.ndarray, sample_rate: float) -> Tuple[float, float]:
    """
    Estimasi pernapasan berbasis SVD-FFT.
    Mengambil komponen dominan dari CSI window, lalu mencari puncak frekuensi 0.1-0.6 Hz.
    Return: bpm, confidence.
    """
    x = normalize_window(window)
    try:
        u, s, vh = np.linalg.svd(x, full_matrices=False)
        component = u[:, 0] * s[0]
    except Exception:
        component = x.mean(axis=1)

    component = signal.detrend(component)
    component = signal.savgol_filter(component, 21 if len(component) >= 21 else 5, 2, mode="interp")

    yf = np.abs(rfft(component))
    xf = rfftfreq(len(component), d=1.0 / sample_rate)

    mask = (xf >= 0.10) & (xf <= 0.60)  # 6-36 bpm
    if not np.any(mask):
        return 0.0, 0.0

    band_f = xf[mask]
    band_y = yf[mask]
    if band_y.sum() <= 1e-8:
        return 0.0, 0.0

    peak_idx = int(np.argmax(band_y))
    freq = float(band_f[peak_idx])
    bpm = freq * 60.0
    confidence = float(band_y[peak_idx] / (band_y.sum() + 1e-8))
    return bpm, confidence


def energy_score(window: np.ndarray) -> float:
    # Energy sederhana untuk membedakan diam vs banyak gerak.
    x = normalize_window(window)
    return float(np.mean(np.std(x, axis=0)))


def state_machine(
    label: str,
    prob: np.ndarray,
    labels: Dict[int, str],
    confidence: float,
    movement_energy: float,
    inactive_since: Optional[float],
    inactive_seconds: int,
    fall_threshold: float,
) -> Tuple[str, int, Optional[float], str]:
    now = time.time()
    label_lower = label.lower()

    fall_prob = 0.0
    for idx, name in labels.items():
        if any(k in name.lower() for k in ["fall", "anomaly"]):
            fall_prob = max(fall_prob, float(prob[idx]))

    if fall_prob >= fall_threshold or ("fall" in label_lower and confidence >= fall_threshold):
        return "critical", 3, inactive_since, f"CRITICAL: indikasi jatuh terdeteksi, p={fall_prob:.2f}"

    if "no_person" in label_lower or "empty" in label_lower:
        return "standby", 0, None, "Ruangan kosong / belum ada pengguna"

    is_low_motion = movement_energy < 0.35 or "inactive" in label_lower or "still" in label_lower
    if is_low_motion:
        if inactive_since is None:
            inactive_since = now
        dur = now - inactive_since
        if dur >= inactive_seconds:
            return "inactive", 1, inactive_since, f"Pengguna diam {dur:.0f}s"
        return "normal", 0, inactive_since, "Diam sebentar, masih dalam batas aman"

    return "normal", 0, None, "Aktivitas normal"


def demo_vector(feature_size: int, t: int) -> np.ndarray:
    # Demo sinyal pseudo CSI untuk uji pipeline tanpa ESP32.
    rng = np.random.default_rng(t)
    base = rng.normal(0, 0.05, feature_size)
    breathing = 0.2 * np.sin(2 * np.pi * 0.25 * (t / 50.0))
    return (base + breathing).astype(np.float32)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--serial-port", default="/dev/ttyUSB0")
    ap.add_argument("--baud", type=int, default=921600)
    ap.add_argument("--win-len", type=int, default=500)
    ap.add_argument("--feature-size", type=int, default=232)
    ap.add_argument("--sample-rate", type=float, default=50.0)
    ap.add_argument("--inactive-seconds", type=int, default=60)
    ap.add_argument("--fall-threshold", type=float, default=0.70)
    ap.add_argument("--send-interval", type=float, default=1.0)
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()

    token = os.getenv("BLYNK_TOKEN", "")
    server = os.getenv("BLYNK_SERVER", "blynk.cloud")
    event_code = os.getenv("BLYNK_EVENT_CODE", "srasta_alert")

    labels = load_labels(args.labels)
    model = TFLiteModel(args.model)
    blynk = BlynkClient(token=token, server=server, event_code=event_code)

    buf = deque(maxlen=args.win_len)
    inactive_since = None
    last_send = 0.0
    frame_count = 0

    ser = None
    if not args.demo:
        if serial is None:
            raise RuntimeError("pyserial belum terinstall. Jalankan: pip3 install pyserial")
        ser = serial.Serial(args.serial_port, args.baud, timeout=1)
        print(f"[INFO] membaca CSI dari {args.serial_port} @ {args.baud}")
    else:
        print("[INFO] demo mode tanpa serial")

    while True:
        if args.demo:
            vec = demo_vector(args.feature_size, frame_count)
            time.sleep(1.0 / args.sample_rate)
        else:
            line = ser.readline()
            parsed = parse_csi_line(line)
            if parsed is None:
                continue
            vec = resize_vector(parsed, args.feature_size)

        frame_count += 1
        buf.append(vec)

        if len(buf) < args.win_len:
            continue

        now = time.time()
        if now - last_send < args.send_interval:
            continue
        last_send = now

        window = np.stack(buf).astype(np.float32)
        x = normalize_window(window)[None, :, :]

        t0 = time.perf_counter()
        prob = model.predict(x)
        latency_ms = (time.perf_counter() - t0) * 1000.0

        pred_id = int(np.argmax(prob))
        label = labels.get(pred_id, str(pred_id))
        confidence = float(prob[pred_id])

        bpm, bpm_conf = estimate_breathing_bpm(window, args.sample_rate)
        move_energy = energy_score(window)

        state, alert_level, inactive_since, msg = state_machine(
            label=label,
            prob=prob,
            labels=labels,
            confidence=confidence,
            movement_energy=move_energy,
            inactive_since=inactive_since,
            inactive_seconds=args.inactive_seconds,
            fall_threshold=args.fall_threshold,
        )

        fall_prob = 0.0
        for idx, name in labels.items():
            if any(k in name.lower() for k in ["fall", "anomaly"]):
                fall_prob = max(fall_prob, float(prob[idx]))

        print(
            f"[{time.strftime('%H:%M:%S')}] state={state:<8} label={label:<12} "
            f"conf={confidence:.2f} fall={fall_prob:.2f} bpm={bpm:.1f}/{bpm_conf:.2f} "
            f"lat={latency_ms:.1f}ms | {msg}"
        )

        blynk.batch_update(
            {
                "V0": state,
                "V1": label,
                "V2": round(confidence, 3),
                "V3": round(bpm, 1),
                "V4": alert_level,
                "V5": round(fall_prob, 3),
                "V6": round(latency_ms, 1),
                "V7": msg,
            }
        )

        if alert_level >= 2 or state == "critical":
            blynk.log_event(msg)


if __name__ == "__main__":
    main()
