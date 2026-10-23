#!/usr/bin/env python3
"""Check deployment integrity and synthetic Mac/Pi inference compatibility.

This is a software benchmark, never a CSI accuracy or physiological test.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import platform
import time

import numpy as np

from srasta_csi.contract import CaptureProfile, FrameValidator
from srasta_csi.edge import EdgeRuntime, create_app
from srasta_csi.public_occupancy import PublicOccupancyInference


def installed_version(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.output.exists() or args.output.with_suffix(".sqlite3").exists():
        raise FileExistsError("Choose a new acceptance output path")
    manifest = json.loads((root / "deployment_manifest.json").read_text())
    for name, digest in manifest["sha256"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f"Missing/invalid deployment file: {name}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Deployment checksum mismatch: {name}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    runtime = EdgeRuntime(
        root / manifest["fall_model"], args.output.with_suffix(".sqlite3"),
        validator=FrameValidator(CaptureProfile(channel=6)), max_gap_s=.15,
        allow_capture_profile_override=True,
    )
    app = create_app(runtime)
    required_routes = {"/", "/health", "/api/caregiver", "/assets"}
    if not required_routes.issubset({route.path for route in app.routes}):
        raise ValueError("Deployment is missing required API/dashboard routes")
    with np.load(root / "synthetic_acceptance.npz", allow_pickle=False) as fixture:
        windows = fixture["windows"]
        reference = fixture["mac_probabilities"]
        probabilities = np.stack([runtime.inference.model.predict(w) for w in windows])
    tolerance = float(runtime.inference.model.output_detail["quantization"][0]) + 1e-7
    if not np.allclose(probabilities, reference, rtol=0, atol=tolerance):
        raise ValueError("Mac/Pi inference difference exceeds one INT8 output step")
    if not np.array_equal(probabilities.argmax(1), reference.argmax(1)):
        raise ValueError("Mac/Pi synthetic class decisions differ")
    for _ in range(20):
        runtime.inference.model.predict(windows[1])
    elapsed = []
    for _ in range(200):
        start = time.perf_counter()
        runtime.inference.model.predict(windows[1])
        elapsed.append((time.perf_counter() - start) * 1000)
    probes = {}
    rng = np.random.default_rng(481)
    for task, channels, frames, rate in (("breathing", 256, 300, 30.), ("presence", 56, 500, 100.)):
        model = PublicOccupancyInference(root / manifest["public_models"][task])
        # Generated amplitudes test loading/feature execution only, no labels.
        prediction = model.predict(rng.uniform(1, 20, (frames, channels)), rate)
        probes[task] = {"loaded": True, "synthetic_execution": True,
                       "research_only": prediction["research_only"],
                       "ESP32_validated": prediction["ESP32_validated"]}
    research_probes = {}
    if manifest.get("research_models_live_enabled", False):
        raise ValueError("Offline research models must not be enabled for live inference")
    if manifest.get("research_models"):
        from predict_offline_candidate import OfflineResearchInference
        for name in manifest["research_models"]:
            path = (root / name).resolve()
            if not path.is_relative_to(root) or name not in manifest["sha256"]:
                raise ValueError("Research model is outside the verified manifest")
            model = OfflineResearchInference(path)
            rate, frames = (100., 500) if model.payload["task"] == "presence" else (30., 300)
            prediction = model.predict(rng.uniform(1, 20, (frames, 56)), rate)
            research_probes[name] = {
                "loaded": True, "synthetic_execution": True,
                "research_only": prediction["research_only"],
                "local_deployment_ready": prediction["local_deployment_ready"],
                "normal_proxy_only": prediction["normal_proxy_only"],
                "accuracy_test": False,
            }
    camera_probe = None
    if manifest.get("camera_model"):
        from srasta_csi.camera import PiMoveNetCapture, assess_capture
        camera_path = (root / manifest["camera_model"]).resolve()
        if not camera_path.is_relative_to(root) or manifest["camera_model"] not in manifest["sha256"]:
            raise ValueError("Camera model is outside the verified manifest")
        # Load/infer synthetic pixels without constructing Picamera2 or opening
        # the sensor. Real-camera quality and timing remain a separate check.
        camera = PiMoveNetCapture(camera_path)
        camera.interpreter.set_tensor(camera.input["index"], np.zeros((1, 192, 192, 3), dtype=camera.input["dtype"]))
        camera.interpreter.invoke()
        points = camera.interpreter.get_tensor(camera.output["index"]).reshape(17, 3).astype(np.float32)
        if camera.output["dtype"] in {np.int8, np.uint8}:
            scale, zero = camera.output["quantization"]
            points = (points - zero) * scale
        _, _, pose = assess_capture(np.stack([points, points, points]))
        if pose is None:
            raise ValueError("Camera model did not produce bounded COCO17 coordinates")
        camera_probe = {"loaded": True, "synthetic_execution": True, "frames_in_consistency_check": 3,
                        "pose_shape": [17, 3], "camera_sensor_opened": False, "accuracy_test": False}
    result = {
        "software_check": "passed", "accuracy_test": False, "live_CSI_test": False,
        "app_startup": "passed", "required_routes": sorted(required_routes),
        "platform": platform.platform(), "machine": platform.machine(),
        "python": platform.python_version(), "checked_files": len(manifest["sha256"]),
        "versions": {k: installed_version(k) for k in ("numpy", "h5py", "scikit-learn", "joblib", "ai-edge-litert", "tflite-runtime", "tensorflow")},
        "interpreter": type(runtime.inference.model.interpreter).__module__,
        "input_shape": runtime.inference.model.input_detail["shape"].tolist(),
        "input_dtype": str(runtime.inference.model.input_detail["dtype"]),
        "output_dtype": str(runtime.inference.model.output_detail["dtype"]),
        "reference_windows": len(windows), "max_probability_difference": float(np.abs(probabilities-reference).max()),
        "synthetic_inference_ms": {"runs": len(elapsed), "median": float(np.median(elapsed)),
                                   "p95": float(np.percentile(elapsed, 95)), "max": max(elapsed)},
        "public_models": probes, "offline_research_models": research_probes, "camera_model": camera_probe,
        "fall_threshold": runtime.inference.fall_threshold,
        "motion_threshold": runtime.machine.motion_threshold,
    }
    runtime.close()
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
