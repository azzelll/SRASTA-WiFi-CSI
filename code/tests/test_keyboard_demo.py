"""Exercise actual terminal input, latched state, and terminal cleanup."""
import json
import os
from pathlib import Path
import pty
import select
import signal
import subprocess
import sys
import tempfile
import termios
import time
import unittest
from unittest.mock import Mock, patch

from srasta_csi import keyboard_demo


CODE = Path(__file__).resolve().parents[1]


class KeyboardDemoTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.status_file = Path(self.directory.name) / "demo.json"
        self.master, self.slave = pty.openpty()
        self.original = termios.tcgetattr(self.slave)
        self.process = None
        self.output = b""

    def tearDown(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=5)
        os.close(self.master)
        os.close(self.slave)
        self.directory.cleanup()

    def start(self):
        self.process = subprocess.Popen(
            [sys.executable, "-u", "-m", "srasta_csi.keyboard_demo",
             "--terminal-only", "--status-file", str(self.status_file)],
            stdin=self.slave, stdout=self.slave, stderr=self.slave,
            env={**os.environ, "PYTHONPATH": str(CODE)},
        )
        return self.wait_level("green")

    def wait_level(self, level):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if select.select([self.master], [], [], .01)[0]:
                self.output += os.read(self.master, 65536)
            if self.status_file.exists():
                snapshot = json.loads(self.status_file.read_text())
                if snapshot["level"] == level:
                    return snapshot
            if self.process.poll() is not None:
                self.fail(f"Process exited {self.process.returncode}: {self.output!r}")
        self.fail(f"No {level} status: {self.output!r}")

    def assert_terminal_restored(self):
        actual = termios.tcgetattr(self.slave)
        expected = self.original.copy()
        if sys.platform == "darwin":
            # macOS itself sets PENDIN when canonical input is restored, even
            # for a bare setcbreak/tcsetattr pair without running the demo.
            actual[3] &= ~termios.PENDIN
            expected[3] &= ~termios.PENDIN
        self.assertEqual(actual, expected)

    def test_space_latches_fall_reset_quit_and_new_session_starts_idle(self):
        self.status_file.write_text('{"level":"red"}')
        snapshot = self.start()
        self.assertEqual(snapshot["label"], "IDLE")
        self.assertTrue(snapshot["simulation"])
        self.assertIsNone(snapshot["score"])
        os.write(self.master, b" ")  # no Enter
        snapshot = self.wait_level("red")
        self.assertEqual(snapshot["label"], "JATUH TERDETEKSI")
        # Remains fallen across a heartbeat and unrelated/repeated keys.
        before = snapshot["updated_at_s"]
        os.write(self.master, b" x ")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            snapshot = self.wait_level("red")
            if snapshot["updated_at_s"] > before:
                break
        self.assertGreater(snapshot["updated_at_s"], before)
        self.assertTrue(snapshot["simulation"])
        self.assertIsNone(snapshot["score"])
        os.write(self.master, b"R")
        self.assertEqual(self.wait_level("green")["label"], "IDLE")
        os.write(self.master, b"q")
        self.assertEqual(self.process.wait(timeout=5), 0)
        self.assertEqual(json.loads(self.status_file.read_text())["level"], "stopped")
        self.assert_terminal_restored()

    def test_sigterm_restores_terminal_and_stops_fall(self):
        self.start()
        os.write(self.master, b" ")
        self.wait_level("red")
        self.process.send_signal(signal.SIGTERM)
        self.assertEqual(self.process.wait(timeout=5), 0)
        self.assertEqual(json.loads(self.status_file.read_text())["level"], "stopped")
        self.assert_terminal_restored()

    def test_display_failure_still_releases_hardware_and_terminal(self):
        hardware = Mock()
        with os.fdopen(os.dup(self.slave)) as terminal:
            with patch.object(sys, "stdin", terminal), \
                    patch.object(keyboard_demo, "open_hardware", return_value=hardware), \
                    patch.object(keyboard_demo, "draw_demo", side_effect=OSError("OLED lost")):
                with self.assertRaisesRegex(OSError, "OLED lost"):
                    keyboard_demo.run_demo(buzzer="passive", status_file=self.status_file,
                                           terminal_only=False)
        hardware.close.assert_called_once()
        self.assertEqual(json.loads(self.status_file.read_text())["level"], "stopped")
        self.assert_terminal_restored()

    def test_noninteractive_invocation_fails_before_touching_status(self):
        result = subprocess.run(
            [sys.executable, "-m", "srasta_csi.keyboard_demo", "--terminal-only",
             "--status-file", str(self.status_file)],
            input=b" ", stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, "PYTHONPATH": str(CODE)}, timeout=5,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"ssh -t", result.stderr)
        self.assertFalse(self.status_file.exists())


if __name__ == "__main__":
    unittest.main()
