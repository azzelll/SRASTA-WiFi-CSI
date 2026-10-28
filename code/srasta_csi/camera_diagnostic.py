"""Manual Pi-camera test and a private, local report of measured COCO17 points."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html import escape
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
from zoneinfo import ZoneInfo

from .pose import validate_pose


MIN_SCORE = .3
# Same links and visibility rules as web/src/camera-pose.tsx.
BONES = ((0, 1), (0, 2), (1, 3), (2, 4), (0, 5), (0, 6),
         (5, 6), (5, 7), (7, 9), (6, 8), (8, 10), (5, 11), (6, 12),
         (11, 12), (11, 13), (13, 15), (12, 14), (14, 16))
JOINTS = ("Hidung", "Mata kiri", "Mata kanan", "Telinga kiri", "Telinga kanan",
          "Bahu kiri", "Bahu kanan", "Siku kiri", "Siku kanan", "Pergelangan kiri",
          "Pergelangan kanan", "Pinggul kiri", "Pinggul kanan", "Lutut kiri",
          "Lutut kanan", "Pergelangan kaki kiri", "Pergelangan kaki kanan")


REMOTE_CAPTURE = r'''
import fcntl, json, os, pathlib, signal, subprocess, sys, time, urllib.request

def interrupted(signum, frame):
    raise SystemExit(128 + signum)

for signum in (signal.SIGTERM, signal.SIGHUP):
    signal.signal(signum, interrupted)

def service():
    result = subprocess.run(["systemctl", "--user", "show", "srasta-edge.service",
                             "--property=WorkingDirectory,ActiveState,SubState"],
                            check=True, text=True, capture_output=True, timeout=10)
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)

def switch(action):
    subprocess.run(["systemctl", "--user", action, "srasta-edge.service"],
                   check=True, timeout=25)

lock_dir = pathlib.Path(os.environ.get("XDG_RUNTIME_DIR", "/run/user/" + str(os.getuid())))
lock = (lock_dir / "srasta-camera-test.lock").open("a")
fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
before = service()
runtime = pathlib.Path(before["WorkingDirectory"]).resolve()
if not runtime.is_relative_to((pathlib.Path.home() / "srasta-edge/releases").resolve()):
    raise SystemExit("Folder runtime Pi tidak sesuai; tes dibatalkan.")
model = runtime / "artifacts/models/movenet-lightning/model.tflite"
cli = runtime / "code/camera_acceptance.py"
if not model.is_file() or not cli.is_file():
    raise SystemExit("Model atau program tes kamera tidak ditemukan.")
active = before["ActiveState"] == "active"
try:
    if active:
        switch("stop")
    result = subprocess.run([str(runtime / ".venv/bin/python"), str(cli),
                             "--model", str(model), "--camera-python", "/usr/bin/python3"],
                            cwd=runtime, text=True, capture_output=True, timeout=40,
                            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1",
                                     PYTHONPATH=str(runtime / "code")))
    if result.returncode:
        detail = result.stderr.strip().splitlines()
        raise RuntimeError("Tes kamera gagal: " + (detail[-1] if detail else "periksa kamera/model"))
    if len(result.stdout) > 65536:
        raise RuntimeError("Output kamera melebihi batas ringkasan.")
    payload = json.loads(result.stdout.strip().splitlines()[-1])
finally:
    if active:
        switch("start")

after = service()
restored = after["ActiveState"] == before["ActiveState"]
if active:
    restored = False
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/api/caregiver", timeout=2) as response:
                snapshot = json.load(response)
            restored = (service()["ActiveState"] == "active"
                        and (snapshot.get("camera") or {}).get("available") is True)
            if restored:
                break
        except Exception:
            pass
        time.sleep(.5)
if not restored:
    raise RuntimeError("Tes selesai, tetapi pemulihan service perlu diperiksa di Pi.")
payload["edge_service_restored"] = True
payload["diagnostic_only"] = True
print(json.dumps(payload), flush=True)
'''


def report_data(payload):
    """Accept bounded diagnostics; never turn failed capture into a skeleton."""
    if (payload.get("software_passed") is not True
            or payload.get("frames_per_burst") != 3
            or payload.get("images_saved") is not False
            or payload.get("cloud_events_sent") is not False
            or payload.get("edge_service_restored") is not True):
        raise ValueError("Tes belum selesai dengan service pulih dan tanpa ekspor gambar/alert.")
    validation = payload.get("validation")
    if not isinstance(validation, dict):
        raise ValueError("Ringkasan kamera tidak tersedia.")
    pose = validate_pose(validation.get("pose"))
    points = pose["keypoints"] if pose else []
    visible = {i for i, point in enumerate(points) if point[2] >= MIN_SCORE}
    bones = [(a, b) for a, b in BONES if a in visible and b in visible]
    spread = 0
    if visible:
        width = max(points[i][1] for i in visible) - min(points[i][1] for i in visible)
        height = max(points[i][0] for i in visible) - min(points[i][0] for i in visible)
        spread = math.hypot(width, height)
    drawable = (validation.get("outcome") != "error" and len(visible) >= 4
                and len(bones) >= 2 and spread >= .03)
    return validation, points, visible, bones, drawable


def render_report(payload):
    validation, points, visible, bones, drawable = report_data(payload)
    outcome = validation.get("outcome")
    title = {"horizontal": "Postur mendatar", "not_horizontal": "Postur tegak",
             "error": "Kamera terhambat"}.get(outcome, "Postur belum jelas")
    if drawable:
        lines = [f'<line data-bone="{a}-{b}" x1="{points[a][1]*192:.2f}" '
                 f'y1="{points[a][0]*192:.2f}" x2="{points[b][1]*192:.2f}" '
                 f'y2="{points[b][0]*192:.2f}" />' for a, b in bones]
        circles = [f'<circle data-joint="{i}" cx="{points[i][1]*192:.2f}" '
                   f'cy="{points[i][0]*192:.2f}" r="2.5"><title>{JOINTS[i]}</title></circle>'
                   for i in sorted(visible)]
        drawing = ('<svg viewBox="0 0 192 192" role="img" aria-label="Skeleton hasil kamera">'
                   '<desc>Hanya koordinat terukur dengan skor setidaknya 0,30.</desc>'
                   '<rect width="192" height="192" rx="8" fill="#102a32"/>'
                   '<g stroke="#65e0bc" stroke-width="1.8">' + ''.join(lines)
                   + '</g><g fill="#fff2a8">' + ''.join(circles) + '</g></svg>')
    else:
        drawing = '<div class="empty">Titik tubuh belum jelas</div>'
    rows = ''.join(f'<tr><td>{JOINTS[i]}</td><td>{point[2]:.3f}</td>'
                   f'<td>{"Terlihat" if i in visible else "Disembunyikan"}</td></tr>'
                   for i, point in enumerate(points))
    checked = validation.get("checked_at_s")
    when = (datetime.fromtimestamp(checked, ZoneInfo("Asia/Jakarta")).strftime("%d-%m-%Y %H:%M:%S WIB")
            if type(checked) in (float, int) and math.isfinite(checked) else "Waktu tidak tersedia")
    result = escape(str(validation.get("result", "Hasil belum tersedia")))
    return f'''<!doctype html>
<html lang="id"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SRASTA · Tes skeleton kamera</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#edf5f2;color:#153b3c;font:16px system-ui,sans-serif}}
main{{max-width:940px;margin:32px auto;padding:24px}}.eyebrow{{color:#567b70;font-size:13px;letter-spacing:.12em}}
h1{{font-size:32px;margin:8px 0}}.sub{{color:#56716d}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-top:24px}}
.card{{background:white;border:1px solid #d9e7e0;border-radius:20px;padding:24px}}svg{{display:block;width:100%;max-width:400px;margin:auto}}
.empty{{min-height:320px;display:grid;place-items:center;background:#102a32;color:#bad1cc;border-radius:12px;text-align:center}}
.count{{font-size:36px;font-weight:700;margin:0}}.hint{{line-height:1.6;color:#56716d}}table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{text-align:left;padding:8px 4px;border-bottom:1px solid #e8efea}}summary{{cursor:pointer;margin:20px 0}}
footer{{margin-top:20px;font-size:13px;color:#56716d}}@media(max-width:650px){{main{{padding:16px;margin:0}}.grid{{grid-template-columns:1fr}}}}
</style><main><div class="eyebrow">SRASTA / TES KAMERA MANUAL</div>
<h1>{escape(title)}</h1><div class="sub">{when} · MoveNet Lightning INT8 · 3 cuplikan</div>
<div class="grid"><section class="card">{drawing}</section><section class="card">
<p class="count">{len(visible)} / 17</p><p>Titik dengan skor ≥ 0,30</p><p>{result}</p>
<p class="hint">Arahkan kamera agar kepala sampai kaki terlihat, dengan cahaya cukup.
Jika titik masih lemah, sesuaikan posisi lalu ulangi tes.</p>
<details><summary>Skor setiap titik tubuh</summary><table><tr><th>Titik</th><th>Skor model</th><th>Tampilan</th></tr>{rows}</table></details>
</section></div><footer>Skeleton berasal dari satu cuplikan yang dipilih dari burst.
Skor titik bukan persentase akurasi. Foto dan alert produksi tidak dikirim; service edge sudah dipulihkan.</footer></main></html>'''


def main(argv=None):
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="srasta@srasta-edge.local")
    parser.add_argument("--key", type=Path, default=root / "artifacts/private/pi-ssh-20261022")
    parser.add_argument("--prepare", type=int, default=10, help="Seconds to stand in the camera view (0–120)")
    parser.add_argument("--output", type=Path, help="New private output folder; existing folders are not overwritten")
    parser.add_argument("--no-open", action="store_true", help="Save report without opening the browser")
    args = parser.parse_args(argv)
    if not 0 <= args.prepare <= 120:
        parser.error("--prepare harus antara 0 dan 120 detik")
    if args.host.startswith("-") or any(c.isspace() for c in args.host):
        parser.error("Host SSH tidak valid")
    if not args.key.is_file():
        parser.error("Key Pi tidak ditemukan; gunakan --key dengan file key yang sudah terdaftar")
    os.umask(0o077)
    print("Berdiri normal: pastikan kepala sampai kaki terlihat kamera. Tidak perlu jatuh.", flush=True)
    for remaining in range(args.prepare, 0, -1):
        print(f"Capture dalam {remaining} detik...", flush=True)
        time.sleep(1)
    print("Mengambil tiga cuplikan; service edge dijeda sementara dan dipulihkan otomatis...", flush=True)
    command = ["ssh", "-T", "-i", str(args.key), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
               "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=8", "-o", "ServerAliveInterval=5",
               "-o", "ServerAliveCountMax=3", args.host, "PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -u -"]
    try:
        completed = subprocess.run(command, input=REMOTE_CAPTURE, text=True, capture_output=True, timeout=110)
        if completed.returncode:
            raise RuntimeError("\n".join(completed.stderr.strip().splitlines()[-8:]) or "SSH/tes kamera gagal")
        if len(completed.stdout) > 65536:
            raise ValueError("Output diagnostik terlalu besar")
        payload = json.loads(completed.stdout)
        html = render_report(payload)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output = (args.output or root / "artifacts/private/camera-skeleton" / f"CAM_{stamp}_{uuid.uuid4().hex[:8]}").resolve()
        output.mkdir(parents=True, exist_ok=False, mode=0o700)
        (output / "result.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        report = output / "skeleton.html"
        report.write_text(html)
        validation, _, visible, _, drawable = report_data(payload)
        print(f"Selesai. Titik terbaca: {len(visible)}/17; postur: {validation.get('outcome')}; skeleton: {'tersedia' if drawable else 'belum cukup jelas'}.")
        print(f"Laporan: {report}")
        print("Service edge dipulihkan. Tidak ada foto/alert yang dikirim ke cloud.")
        if not args.no_open:
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            try:
                subprocess.run([opener, str(report)], check=True)
            except (OSError, subprocess.CalledProcessError):
                print(f"Buka file laporan secara manual: {report}", file=sys.stderr)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"Tes gagal: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
