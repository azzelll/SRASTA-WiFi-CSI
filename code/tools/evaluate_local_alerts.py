#!/usr/bin/env python3
"""Explicit evaluation only; never used automatically to tune a test capture."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from srasta_csi.capture_metrics import false_alert_report


def main():
    parser = argparse.ArgumentParser(description="Ukur false alert per jam dari sesi lokal yang sudah direview. Tidak membuktikan recall/specificity.")
    parser.add_argument("session", type=Path)
    args = parser.parse_args()
    try:
        report = false_alert_report(args.session)
        print(json.dumps(report, indent=2))
        return 0 if report["available"] else 1
    except (OSError, ValueError, KeyError) as exc:
        print(f"Evaluasi gagal: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
