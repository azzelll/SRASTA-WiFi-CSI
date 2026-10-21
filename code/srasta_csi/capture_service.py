"""Pause only this checkout's edge process, then restore it after capture."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import time
import urllib.request


def local_status():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/status", timeout=1) as response:
            return json.load(response)
    except (OSError, ValueError):
        return {}


def process_cwd(pid):
    if sys.platform == "darwin":
        result = subprocess.run(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"], capture_output=True, text=True, timeout=5)
        paths = [line[1:] for line in result.stdout.splitlines() if line.startswith("n")]
        return Path(paths[0]).resolve() if len(paths) == 1 else None
    try:
        return Path(f"/proc/{pid}/cwd").resolve(strict=True)
    except OSError:
        return None


def matching_service(repo, port):
    result = subprocess.run(["ps", "-ax", "-o", "pid=,command="], capture_output=True, text=True, check=True, timeout=5)
    matches = []
    for line in result.stdout.splitlines():
        if "run_edge_service.py" not in line:
            continue
        pid_text, command = line.strip().split(None, 1)
        argv = shlex.split(command)
        if "--serial" not in argv or argv.index("--serial") + 1 >= len(argv):
            continue
        script = next((a for a in argv if a.endswith("/run_edge_service.py")), None)
        if script is None or argv[argv.index("--serial") + 1] != port:
            continue
        pid = int(pid_text)
        if process_cwd(pid) == repo and (repo / script).resolve() == repo / "code/run_edge_service.py":
            # ps on macOS reports the base interpreter even for a venv process.
            # Restore using this checkout's interpreter so dependencies persist.
            argv[0] = str(repo / ".venv/bin/python")
            matches.append((pid, argv))
    if len(matches) > 1:
        raise RuntimeError("Lebih dari satu layanan SRASTA memakai RX. Hentikan duplikatnya dahulu.")
    return matches[0] if matches else None


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


class PausedEdgeService:
    def __init__(self, repo, port, root, emit=print):
        self.repo, self.port, self.root, self.emit = Path(repo).resolve(), port, Path(root), emit
        self.process = None
        self.resume_pid = None

    def __enter__(self):
        self.process = matching_service(self.repo, self.port)
        try:
            if self.process:
                pid, argv = self.process
                if not Path(argv[0]).is_file():
                    raise RuntimeError("Interpreter layanan tidak tersedia untuk menjalankannya kembali.")
                self.emit("Layanan dashboard CSI dijeda selama rekaman; akan dijalankan kembali setelah selesai.")
                os.kill(pid, signal.SIGTERM)
                deadline = time.monotonic() + 25
                while alive(pid) and time.monotonic() < deadline:
                    time.sleep(.2)
                if alive(pid):
                    raise RuntimeError("Layanan belum berhenti. Recorder tidak membuka port yang masih dipakai.")
            holders = subprocess.run(["lsof", "-t", self.port], capture_output=True, text=True, timeout=5)
            if holders.stdout.strip():
                raise RuntimeError("Port RX masih dibuka aplikasi lain. Tutup serial monitor lalu ulangi.")
            return self
        except BaseException:
            self.restore()
            raise

    def restore(self):
        if not self.process:
            return
        pid, argv = self.process
        if alive(pid):
            return
        self.process = None
        log_path = self.root / "edge_resume.log"
        fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as stream:
            child = subprocess.Popen(argv, cwd=self.repo, stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        self.resume_pid = child.pid
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            if child.poll() is not None:
                self.emit(f"Layanan gagal dimulai kembali. Periksa {log_path}")
                return
            status = local_status()
            if status.get("transport", {}).get("port") == self.port:
                self.emit("Layanan dashboard CSI sudah dijalankan kembali.")
                return
            time.sleep(.3)
        self.emit(f"Layanan dimulai (PID {child.pid}); status belum tersedia. Log: {log_path}")

    def __exit__(self, *_):
        self.restore()
