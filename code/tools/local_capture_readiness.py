#!/usr/bin/env python3
"""Inventory train/validation capture blockers without opening local test payloads."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from srasta_csi.capture_archive import ARCHIVE_FILES, CLASS_LABELS, qa_capture
from srasta_csi.capture_governance import participant_identity


def readiness(root):
    sessions = []
    partitions = {s: {"subjects": set(), "class_subjects": {c: set() for c in CLASS_LABELS},
                       "reviewed_nonfall_s": 0., "capture_profiles": set()} for s in ("train", "validation")}
    skipped = 0
    for path in sorted((root / "sessions").glob("SES_*")):
        config = json.loads((path / "capture_config.json").read_text())
        # Check metadata before QA: QA opens raw/prediction payloads.
        if config["split"] not in partitions:
            skipped += 1
            continue
        missing = sorted(name for name in ARCHIVE_FILES | {"checksums.json"}
                         if not (path / name).is_file())
        if missing:
            # An interrupted/unclosed archive must stay excluded, but must not
            # prevent inspection of the other completed sessions.
            sessions.append({"session_id": config["session_id"], "split": config["split"],
                             "status": "rejected", "class_counts": {c: 0 for c in CLASS_LABELS},
                             "issues": ["incomplete archive; missing: " + ", ".join(missing)],
                             "pending_reasons": []})
            continue
        qa = qa_capture(path)
        sessions.append({k: qa[k] for k in ("session_id", "split", "status", "class_counts", "issues", "pending_reasons")})
        if qa["labels_ready_for_training"]:
            identity = participant_identity(path, config)
            subject = identity["subject_id"]
            p = partitions[config["split"]]
            if not subject.startswith("EMPTY_"):
                p["subjects"].add(subject)
            p["capture_profiles"].add(config["capture_profile"]["hash"])
            p["reviewed_nonfall_s"] += qa["reviewed_nonfall_duration_s"]
            for label, count in qa["class_counts"].items():
                if count:
                    p["class_subjects"][label].add(subject)
    if partitions["train"]["subjects"] & partitions["validation"]["subjects"]:
        raise ValueError("local subject leakage across train/validation")
    profiles = set.union(*(p["capture_profiles"] for p in partitions.values()))
    presence_ready = len(profiles) == 1 and all(p["class_subjects"]["no_person"] and
        (p["class_subjects"]["normal"] or p["class_subjects"]["inactive"]) for p in partitions.values())
    fall_ready = len(profiles) == 1 and all(p["class_subjects"]["fall_anomaly"] and
        (p["class_subjects"]["normal"] or p["class_subjects"]["inactive"]) for p in partitions.values())
    # A local grouped fit/calibration/evaluation needs three training people.
    train = partitions["train"]["class_subjects"]
    paired_fall_subjects = train["fall_anomaly"] & (train["normal"] | train["inactive"])
    fall_ready = bool(fall_ready and len(paired_fall_subjects) >= 3)
    serializable = {s: {"subjects": sorted(p["subjects"]), "class_subjects": {c: sorted(v) for c, v in p["class_subjects"].items()},
                          "reviewed_nonfall_s": p["reviewed_nonfall_s"], "capture_profiles": sorted(p["capture_profiles"])} for s, p in partitions.items()}
    return {"presence_ready_to_train": bool(presence_ready), "fall_ready_for_grouped_development": fall_ready,
            "train_subjects_with_both_fall_and_nonfall": sorted(paired_fall_subjects),
            "partitions": serializable, "sessions": sessions, "test_or_pilot_sessions_skipped_before_QA": skipped,
            "local_test_payload_opened": False, "performance_proven": False,
            "next_action": "Collect/review missing classes on frozen subject splits; never infer labels or provenance from model predictions."}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path("../SRASTA_LOCAL_CAPTURE"))
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    report = readiness(args.root)
    if args.out:
        # Preserve reports and prevent accidental replacement of an archive.
        with args.out.open("x") as stream:
            json.dump(report, stream, indent=2); stream.write("\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
