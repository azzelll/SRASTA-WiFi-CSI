#!/usr/bin/env python3
"""Check archives and append independent observer reviews without editing raw CSI."""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from srasta_csi.capture_archive import digest, private_write, qa_capture, read_jsonl, utc_now


def ask_choice(prompt, choices):
    while True:
        answer = input(prompt).strip().lower()
        if answer in choices:
            return answer
        print("Jawab " + "/".join(choices) + "; Enter kosong belum menyimpan jawaban.")


def main():
    parser = argparse.ArgumentParser(description="Periksa capture lokal; review hanya oleh pengamat yang menyaksikan kondisi.")
    parser.add_argument("session", type=Path)
    parser.add_argument("--reviewer", help="ANN_002: pengamat kedua yang independen dan menyaksikan interval tersebut")
    args = parser.parse_args()
    path = args.session.resolve()
    os.umask(0o077)
    try:
        initial = qa_capture(path)
        if initial["issues"]:
            print(json.dumps(initial, indent=2))
            print("Archive ditolak; review tidak dapat memperbaiki raw CSI.")
            return 1
        if args.reviewer:
            if not re.fullmatch(r"ANN_[A-Z0-9_]{1,32}", args.reviewer):
                parser.error("reviewer harus berupa kode ANN_")
            print("Hanya beri review bila Anda pengamat kedua yang menyaksikan kondisi dan waktunya. Prediksi model tidak boleh dipakai untuk memilih label.")
            if ask_choice("Apakah Anda pengamat independen yang menyaksikannya? [y/n]: ", ("y", "n")) != "y":
                return 1
            event_hash = digest(path / "events.jsonl")
            import fcntl
            with os.fdopen(os.open(path / "reviews.jsonl", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600), "a") as stream:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
                for event in read_jsonl(path / "events.jsonl"):
                    if args.reviewer in event["annotator_ids"]:
                        raise ValueError("Pengamat pertama tidak dapat mengesahkan review independen sendiri.")
                    start, end = event["onset_monotonic_us"], event["event_end_monotonic_us"]
                    print(f"\n{event['event_id']} | {event['activity_label']} | clock RX {start}..{end}us | {(end-start)/1e6:.1f}s")
                    if event["event_type"] == "fall":
                        print(f"Diam pascakejadian: {event.get('post_event_inactivity_start_monotonic_us')}..{event.get('post_event_inactivity_end_monotonic_us')}us; periksa keempat batas, termasuk ketidakpastian reaksi pengamat.")
                    answer = ask_choice("Sesuai dengan kondisi yang Anda saksikan? [y=sesuai/n=tidak/s=lewati]: ", ("y", "n", "s"))
                    if answer == "s":
                        continue
                    record = {"event_id": event["event_id"], "reviewer_id": args.reviewer, "agrees": answer == "y", "events_sha256": event_hash, "reviewed_at_utc": utc_now()}
                    stream.write(json.dumps(record, separators=(",", ":")) + "\n")
                    stream.flush(); os.fsync(stream.fileno())
        report = qa_capture(path)
        reports = path / "qa_reports"
        reports.mkdir(mode=0o700, exist_ok=True)
        destination = reports / (uuid.uuid4().hex + ".json")
        private_write(destination, report)
        print(json.dumps(report, indent=2))
        print(f"Report: {destination}")
        return 1 if report["status"] == "rejected" else 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"QA gagal: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
