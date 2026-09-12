#!/usr/bin/env python3
"""Run and record mechanically verified SRASTA BE+AI milestone evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


EXPECTED_RF = {"model.joblib", "metrics.json", "preprocess_config.json", "capture_profile.json", "split_report.json", "MODEL_CARD.md"}
EXPECTED_TCN = {"model.keras", "model.tflite", "checkpoint.weights.h5", "metrics.json", "parity.json", "preprocess_config.json", "capture_profile.json", "split_report.json", "training_config.json", "MODEL_CARD.md"}


def revision(root: Path) -> str | None:
    try:
        return subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def run(command: list[str], root: Path) -> dict[str, object]:
    environment = {**os.environ, "PYTHONPATH": "code"}
    completed = subprocess.run(command, cwd=root, env=environment, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return {
        "command": subprocess.list2cmdline(command),
        "return_code": completed.returncode,
        "output_tail": completed.stdout[-12000:],
    }


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("artifacts/milestone_50_be_ai.json"))
    parser.add_argument("--epochs", type=int, default=25)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    # Keep the virtual-environment executable path. Resolving its symlink would
    # launch the base Homebrew interpreter without the venv's site-packages.
    python = Path(sys.executable)
    manifest = (root / args.manifest).resolve() if not args.manifest.is_absolute() else args.manifest.resolve()
    data_root = (root / args.data_root).resolve() if not args.data_root.is_absolute() else args.data_root.resolve()
    replay = (root / args.replay).resolve() if not args.replay.is_absolute() else args.replay.resolve()
    out = (root / args.out).resolve() if not args.out.is_absolute() else args.out.resolve()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = root / "artifacts" / f"milestone_50_{stamp}"
    suffix = 1
    while run_dir.exists():
        run_dir = root / "artifacts" / f"milestone_50_{stamp}_{suffix}"
        suffix += 1
    rf_dir, tcn_dir = run_dir / "rf", run_dir / "tcn"
    smoke_path, db_path = run_dir / "api_smoke.json", run_dir / "edge.sqlite3"
    commands = [
        [str(python), "-m", "unittest", "discover", "-s", "code/tests", "-v"],
        [str(python), "code/train_srasta_rf_baseline.py", "--manifest", str(manifest), "--data-root", str(data_root), "--out-dir", str(rf_dir)],
        [str(python), "code/train_srasta_tcn_lite.py", "--manifest", str(manifest), "--data-root", str(data_root), "--out-dir", str(tcn_dir), "--window-length", "250", "--epochs", str(args.epochs)],
    ]
    results: list[dict[str, object]] = []
    report: dict[str, object] = {
        "milestone": "50% backend + AI",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_revision": revision(root),
        "status": "failed",
        "commands_executed": results,
        "criteria": {},
        "artifacts": {"run_dir": str(run_dir), "rf": str(rf_dir), "tcn": str(tcn_dir), "api_smoke": str(smoke_path)},
        "limitations": [
            "No ESP32-S3 hardware or continuous annotated local capture is available.",
            "Event recall/precision/F1, false alerts per hour, H5 packet-drop rate, and empirical suspected/confirmed latency remain not_available.",
            "A generated TFLite file is an engineering candidate and remains not_deployment_ready until every release gate has evidence.",
            "Frontend/dashboard, firmware/hardware, camera, mobile, breathing pipeline, four-output product model, and real external notifications remain proposal requirements beyond this BE+AI work order.",
        ],
    }
    try:
        if args.epochs < 1:
            raise ValueError("epochs must be positive")
        expected_manifest = (root / "data/curated/esp32_s3_fall_v1/manifest.csv").resolve()
        expected_data_root = (root / "data").resolve()
        if out != (root / "artifacts/milestone_50_be_ai.json").resolve():
            raise ValueError("milestone evidence must be written to artifacts/milestone_50_be_ai.json")
        if manifest != expected_manifest or data_root != expected_data_root:
            raise ValueError("milestone verification only accepts the curated primary manifest and repository data root")
        if not manifest.is_file() or not replay.is_file():
            raise FileNotFoundError("manifest and replay inputs must exist")
        if replay.suffix.lower() in {".h5", ".hdf5"} and (data_root / "csi-bench").resolve() not in replay.parents:
            raise ValueError("H5 replay must come from the unmodified csi-bench root")
        for command in commands:
            result = run(command, root)
            results.append(result)
            if result["return_code"] != 0:
                raise RuntimeError(f"command failed: {result['command']}")
        smoke_command = [str(python), "code/api_smoke.py", "--model", str(tcn_dir / "model.tflite"), "--replay", str(replay), "--db", str(db_path), "--out", str(smoke_path)]
        smoke_result = run(smoke_command, root)
        results.append(smoke_result)
        if smoke_result["return_code"] != 0:
            raise RuntimeError(f"command failed: {smoke_result['command']}")

        missing_rf = sorted(EXPECTED_RF - {path.name for path in rf_dir.iterdir()})
        missing_tcn = sorted(EXPECTED_TCN - {path.name for path in tcn_dir.iterdir()})
        rf_metrics = read_json(rf_dir / "metrics.json")
        tcn_metrics = read_json(tcn_dir / "metrics.json")
        parity = read_json(tcn_dir / "parity.json")
        splits = read_json(tcn_dir / "split_report.json")
        smoke = read_json(smoke_path)
        route_codes = [value["status_code"] for value in smoke["routes"].values()]
        test_output = str(results[0]["output_tail"]).lower()
        tests_passed = results[0]["return_code"] == 0 and "skipped" not in test_output and "ok" in test_output
        expected_counts = {"train": 288, "validation": 77, "test": 80, "excluded": 27}
        split_counts_match = all(splits.get(split, {}).get("sample_count") == count for split, count in expected_counts.items())
        manifest_hash = hashlib.sha256(manifest.read_bytes()).hexdigest()
        manifest_hashes_match = manifest_hash == splits.get("manifest_sha256") == read_json(rf_dir / "split_report.json").get("manifest_sha256")
        criteria = {
            "manifest_only_subject_session_disjoint_before_windowing": tests_passed and split_counts_match and manifest_hashes_match and splits.get("validated_before_windowing") is True and all(value == "passed" for value in splits.get("overlap_checks", {}).values()),
            "decoder_h5_preprocessing_contract": tests_passed,
            "random_forest_train_validation_artifact": not missing_rf and rf_metrics.get("locked_test", {}).get("status") == "not_evaluated",
            "tcn_training_full_int8_replay_parity": not missing_tcn and parity.get("status") == "passed" and tcn_metrics.get("locked_test", {}).get("status") == "not_evaluated",
            "strict_jsonl_quarantine_without_raw_sqlite": tests_passed,
            "bounded_queue_ring_state_sqlite_fastapi": all(code == 200 for code in route_codes) and smoke.get("persisted_transition_count", 0) >= 2,
            "external_adapters_fail_closed": tests_passed,
            "all_be_ai_tests_no_dependency_skip": tests_passed,
        }
        report.update({
            "criteria": {name: "passed" if passed else "failed" for name, passed in criteria.items()},
            "manifest_evidence": {"path": str(manifest), "sha256": manifest_hash, "split_counts": expected_counts, "overlap_checks": splits.get("overlap_checks")},
            "validation_metrics": {"random_forest": rf_metrics["validation_classification"], "tcn_lite_int8": tcn_metrics["validation_classification"]},
            "tcn_parity": parity,
            "tcn_deployment_status": tcn_metrics.get("deployment_status"),
            "tcn_deployment_gate": tcn_metrics.get("deployment_gate"),
            "api_smoke": smoke,
            "unavailable_metrics": tcn_metrics.get("unavailable"),
        })
        if all(criteria.values()):
            report["status"] = "passed"
    except Exception as exc:
        report["failure"] = str(exc)
    finally:
        out.parent.mkdir(parents=True, exist_ok=True)
        report["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
        out.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
