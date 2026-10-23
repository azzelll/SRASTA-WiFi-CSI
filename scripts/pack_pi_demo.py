#!/usr/bin/env python3
"""Pack explicitly allowed runtime/model files, without credentials or raw data."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wheelhouse", type=Path, help="Include official downloaded ARM64 wheels for offline installation")
    parser.add_argument("--camera-model", type=Path, help="Reviewed MoveNet TFLite file within the repo")
    parser.add_argument("--research-run", type=Path, action="append", default=[],
                        help="Include selected offline research models and reports; never enables live inference")
    args = parser.parse_args()
    import numpy as np
    from srasta_csi.model import TFLiteModel
    fall = Path("artifacts/releases/20261001-tcn-v8-motion-calibrated/selected")
    public = Path("artifacts/research/20261003-public-occupancy-calibrated")
    if args.output.exists():
        raise FileExistsError("Refusing to overwrite an existing Pi package")
    files = [Path("code") / name for name in ("run_edge_service.py", "dashboard.html", "predict_public_occupancy.py", "predict_offline_candidate.py", "pi_acceptance.py", "camera_acceptance.py", "requirements-pi-demo.txt")]
    files += [p.relative_to(ROOT) for p in sorted((ROOT / "code/srasta_csi").glob("*.py"))]
    files += [Path("code/srasta_csi/alarm.wav")]
    files += [Path("scripts") / name for name in ("install_pi_demo.sh", "run_pi_demo.sh", "install_pi_user_service.py")]
    files += [fall / name for name in ("model.tflite", "training_config.json", "preprocess_config.json", "capture_profile.json", "frozen.json", "motion_calibration.json", "metrics.json", "MODEL_CARD.md")]
    files += [public / task / "model.joblib" for task in ("breathing", "presence")]
    files += [public / "metrics.json", Path("docs/evidence/20261003-public-occupancy.md")]
    files += [Path("docs/evidence/20261019-offline-model-development.md"),
              Path("docs/evidence/20261019-camera-skeleton.md"),
              Path("docs/evidence/20261019-caregiver-hardening.md"),
              Path("docs/pi-offline-package.md")]
    files += [p.relative_to(ROOT) for p in sorted((ROOT / "web/dist").rglob("*")) if p.is_file()]
    camera_relative = None
    if args.camera_model:
        camera_relative = args.camera_model.resolve().relative_to(ROOT)
        files += [camera_relative, camera_relative.with_name("MODEL_CARD.md"),
                  camera_relative.with_name("LICENSE")]
    research_models = []
    from predict_offline_candidate import OfflineResearchInference
    for run in args.research_run:
        relative = run.resolve().relative_to(ROOT)
        if relative.parts[:2] != ("artifacts", "research") or (ROOT / relative / "INVALIDATED.md").exists():
            raise ValueError("Only non-invalidated local research runs may be bundled")
        candidates = sorted((ROOT / relative).glob("*/model.joblib"))
        if not candidates:
            raise ValueError("No selected research models in run")
        for model_path in candidates:
            OfflineResearchInference(model_path)
            model_relative = model_path.relative_to(ROOT)
            files.append(model_relative)
            research_models.append(str(model_relative))
        files += [relative / "metrics.json", relative / "protocol.json"]
    if not (ROOT / "web/dist/index.html").is_file():
        raise ValueError("Build web/dist before packaging")
    with tempfile.TemporaryDirectory(prefix="srasta-pi-pack-") as tmp:
        stage = Path(tmp)
        for relative in files:
            source = ROOT / relative
            if not source.is_file() or source.is_symlink():
                raise ValueError(f"Missing file or symlink forbidden: {relative}")
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        if args.wheelhouse:
            wheels = sorted(args.wheelhouse.glob("*.whl"))
            if not wheels:
                raise ValueError("Wheelhouse has no wheels")
            (stage / "wheelhouse").mkdir()
            for wheel in wheels:
                if wheel.is_symlink():
                    raise ValueError("Wheel symlinks forbidden")
                shutil.copy2(wheel, stage / "wheelhouse" / wheel.name)
        model = TFLiteModel(stage / fall / "model.tflite")
        rng = np.random.default_rng(482)
        windows = rng.normal(0, .1, (3, model.window_length, 52)).astype(np.float32)
        windows[0] = 0
        probabilities = np.stack([model.predict(w) for w in windows])
        np.savez_compressed(stage / "synthetic_acceptance.npz", windows=windows, mac_probabilities=probabilities)
        hashes = {str(p.relative_to(stage)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted(stage.rglob("*")) if p.is_file()}
        manifest = {"schema": 1, "purpose": "Pi demo software deployment, not accuracy validation",
                    "fall_model": str(fall / "model.tflite"),
                    "public_models": {task: str(public / task / "model.joblib") for task in ("breathing", "presence")},
                    "public_models_live_enabled": False, "sha256": hashes}
        manifest["research_models"] = research_models
        manifest["research_models_live_enabled"] = False
        if camera_relative:
            manifest["camera_model"] = str(camera_relative)
        (stage / "deployment_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(args.output, "w:gz", format=tarfile.PAX_FORMAT) as archive:
            for path in sorted(stage.rglob("*")):
                if path.is_file():
                    archive.add(path, arcname=str(path.relative_to(stage)), recursive=False)
    print(json.dumps({"archive": str(args.output.resolve()), "bytes": args.output.stat().st_size,
                      "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(), "files": len(hashes)+1}))


if __name__ == "__main__":
    main()
