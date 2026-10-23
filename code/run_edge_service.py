#!/usr/bin/env python3
"""Run the local SRASTA BE+AI service using an internal RF baseline artifact."""

from __future__ import annotations

import argparse
import json
import threading
import os
from datetime import datetime, timezone
from pathlib import Path

from srasta_csi.contract import CaptureProfile, FrameValidator
from srasta_csi.edge import EdgeRuntime, create_app
from srasta_csi.serial_reader import SerialJSONLReader
from srasta_csi.blynk_mqtt import BlynkMQTTAdapter
from srasta_csi.cloud_sync import CloudSync
from srasta_csi.alarm import LocalAlarm
from srasta_csi.camera import AnomalyCamera, PiMoveNetCapture


def load_local_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        result[name.strip()] = value.strip().strip('"')
    return result


def format_live_status(status: dict[str, object]) -> str:
    quality = status.get("packet_quality")
    drop = quality.get("packet_drop_rate") if isinstance(quality, dict) else None
    latency = status.get("inference_latency_ms")
    probability = status.get("fall_probability")
    motion = status.get("motion_energy")
    frames = status.get("accepted_frames")
    quarantine = status.get("quarantine_count")
    latest_csi = status.get("latest_csi")
    csi_sequence = latest_csi.get("sequence") if isinstance(latest_csi, dict) else None
    csi_mean = latest_csi.get("mean") if isinstance(latest_csi, dict) else None
    source = "MANUAL-STAGED" if status.get("demo_override") else "MODEL"
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    return (
        f"{timestamp} | state={str(status.get('state', '-')):<15}"
        f" | source={source:<18}"
        f" | fall={(float(probability) if isinstance(probability, (int, float)) else 0.0):6.2%}"
        f" | motion={(float(motion) if isinstance(motion, (int, float)) else 0.0):.6f}"
        f" | inference={'-' if not isinstance(latency, (int, float)) else f'{float(latency):.3f} ms':>9}"
        f" | frames={(int(frames) if isinstance(frames, int) else 0):>7}"
        f" | quarantine={(int(quarantine) if isinstance(quarantine, int) else 0):>4}"
        f" | drop={'-' if not isinstance(drop, (int, float)) else f'{float(drop):.2%}'}"
        f" | csi_seq={'-' if not isinstance(csi_sequence, int) else csi_sequence}"
        f" | csi_mean={'-' if not isinstance(csi_mean, (int, float)) else f'{float(csi_mean):.2f}'}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--presence-model", type=Path, help="Reviewed local empty/present classifier")
    parser.add_argument("--inactivity-s", type=float, default=60.)
    parser.add_argument("--db", type=Path, required=True)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--replay", type=Path)
    source.add_argument("--serial")
    parser.add_argument("--baud", type=int, default=1000000)
    parser.add_argument("--capture-channel", type=int, default=1)
    parser.add_argument("--subcarrier-order", choices=("centered", "esp_idf_native"), default="centered")
    parser.add_argument("--max-gap-s", type=float)
    parser.add_argument("--log-interval", type=float, default=1.0)
    parser.add_argument("--inference-interval", type=float, default=0.2)
    parser.add_argument("--demo-mode", action="store_true")
    parser.add_argument("--allow-capture-profile-override", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--alarm", choices=("audio", "gpio", "disabled"), default="audio")
    parser.add_argument("--buzzer-pin", type=int, default=18)
    parser.add_argument("--camera-model", type=Path)
    parser.add_argument("--camera-python", default=os.sys.executable, help="Python with OS Picamera2 installed")
    args = parser.parse_args()
    if args.log_interval <= 0:
        parser.error("--log-interval must be positive")
    if not 0 < args.inference_interval <= 2:
        parser.error("--inference-interval must be positive and at most two seconds")
    runtime = EdgeRuntime(
        args.model,
        args.db,
        validator=FrameValidator(CaptureProfile(channel=args.capture_channel, subcarrier_order=args.subcarrier_order)),
        max_gap_s=args.max_gap_s,
        demo_mode=args.demo_mode,
        allow_capture_profile_override=args.allow_capture_profile_override,
        auto_process_frames=not bool(args.serial),
        presence_model=args.presence_model,
        inactivity_s=args.inactivity_s,
    )
    local_env = {**load_local_env(args.env), **os.environ}
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("Local API binds to loopback only. Use the authenticated cloud app remotely or SSH forwarding locally.")
    cloud = None
    if local_env.get("SRASTA_SUPABASE_URL"):
        cloud = CloudSync(runtime, local_env["SRASTA_SUPABASE_URL"], local_env.get("SRASTA_DEVICE_ID", ""), local_env.get("SRASTA_DEVICE_TOKEN", ""))
        runtime.remote_status = cloud.status
        cloud.start()
    alarm = LocalAlarm(runtime.status, mode=args.alarm, gpio_pin=args.buzzer_pin)
    runtime.alarm_status = alarm.status
    alarm.start()
    camera = AnomalyCamera(runtime.status, PiMoveNetCapture(args.camera_model, camera_python=args.camera_python) if args.camera_model else None,
                           save_result=runtime.store.save_camera_validation, results_provider=runtime.store.camera_validations)
    runtime.camera_status = camera.status
    camera.start()
    token = local_env.get("BLYNK_AUTH_TOKEN", "")
    blynk = None
    blynk_stop = threading.Event()
    blynk_thread = None
    if token:
        blynk = BlynkMQTTAdapter(
            token,
            host=local_env.get("BLYNK_MQTT_HOST", "blynk.cloud"),
            port=int(local_env.get("BLYNK_MQTT_PORT", "8883")),
            on_acknowledge=lambda: runtime.acknowledge_alert("blynk_v10"),
            on_assistance=lambda: runtime.request_assistance("blynk_v11"),
            status_provider=runtime.status,
        )
        runtime.cloud_status = blynk.status
        blynk.start()

        def publish_blynk() -> None:
            while not blynk_stop.wait(1.0):
                try:
                    blynk.update(runtime.status())
                except Exception as exc:
                    print(f"Blynk adapter error: {type(exc).__name__}", flush=True)

        blynk_thread = threading.Thread(target=publish_blynk, name="blynk-mqtt", daemon=True)
        blynk_thread.start()
    reader = None
    log_stop = threading.Event()
    log_thread = None
    inference_stop = threading.Event()
    inference_thread = None
    if args.replay:
        print(json.dumps(runtime.replay(args.replay), indent=2))
    elif args.serial:
        def infer_live() -> None:
            while not inference_stop.wait(args.inference_interval):
                try:
                    runtime.process_queue()
                except Exception as exc:
                    print(f"Inference worker error: {type(exc).__name__}", flush=True)
        inference_thread = threading.Thread(target=infer_live, name="csi-inference", daemon=True)
        inference_thread.start()
        reader = SerialJSONLReader(args.serial, args.baud, runtime.ingest_json_line, on_reconnect=runtime.reset_capture_session)
        runtime.transport_status = reader.status
        reader.start()
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        print(f"{timestamp} | service=start | port={args.serial} | baud={args.baud}", flush=True)
        def log_live_status() -> None:
            while not log_stop.wait(args.log_interval):
                print(format_live_status(runtime.status()), flush=True)
        log_thread = threading.Thread(target=log_live_status, name="live-status-log", daemon=True)
        log_thread.start()
    import uvicorn

    try:
        # Browser SSE connections can remain open indefinitely during shutdown.
        # Bound the drain so the serial reader and adapters actually close.
        uvicorn.run(create_app(runtime), host=args.host, port=args.port, timeout_graceful_shutdown=5)
    finally:
        camera.close()
        alarm.close()
        if cloud:
            cloud.close()
        blynk_stop.set()
        if blynk_thread:
            blynk_thread.join(timeout=2)
        if blynk:
            blynk.close()
        log_stop.set()
        if log_thread:
            log_thread.join(timeout=2)
        if reader:
            reader.close()
        inference_stop.set()
        if inference_thread:
            inference_thread.join(timeout=5)
        runtime.close()


if __name__ == "__main__":
    main()
