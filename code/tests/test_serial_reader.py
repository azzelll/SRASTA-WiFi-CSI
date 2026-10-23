from __future__ import annotations

import tempfile
import json
import os
import pty
import threading
import termios
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from srasta_csi.serial_reader import SerialJSONLReader, configure_serial


class SerialConfigurationTests(unittest.TestCase):
    def test_unplug_reconnect_exact_port_resets_session_and_discards_partial_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            port = os.path.join(tmp, 'verified-rx')
            master, slave = pty.openpty()
            replacement_master, replacement_slave = pty.openpty()
            os.symlink(os.ttyname(slave), port)
            received, reset = threading.Event(), threading.Event()
            lines = []
            def ingest(line):
                lines.append(json.loads(line))
                received.set()
            reader = SerialJSONLReader(port, 115200, ingest, on_reconnect=reset.set)
            reader.start()
            try:
                # Wait until configuration has completed before sending bytes.
                deadline = threading.Event()
                for _ in range(100):
                    if reader.connected: break
                    deadline.wait(.01)
                self.assertTrue(reader.connected)
                os.write(master, b'{"sequence":40}\n{"partial":')
                self.assertTrue(received.wait(2))
                received.clear()
                os.close(master); master = -1
                os.unlink(port)
                os.symlink(os.ttyname(replacement_slave), port)
                self.assertTrue(reset.wait(3))
                os.write(replacement_master, b'{"sequence":1}\n')
                self.assertTrue(received.wait(2))
                self.assertEqual(lines, [{'sequence':40}, {'sequence':1}])
                self.assertGreaterEqual(reader.reconnects, 1)
            finally:
                reader.close()
                for fd in (master, slave, replacement_master, replacement_slave):
                    if fd >= 0: os.close(fd)

    def test_macos_reopen_normalizes_previous_custom_speed_before_raw_mode(self):
        # IOSSIOSPEED leaves 1 MHz in tcgetattr, but tcsetattr accepts only the
        # standard speed constants. Emulate the actual CH340 reopen failure.
        attrs = [0, 0, 0, 0, 1000000, 1000000, []]

        def set_attrs(fd, when, value):
            if value[4] == 1000000 or value[5] == 1000000:
                raise termios.error(22, "Invalid argument")
            attrs[:] = value

        def set_raw(fd, when=termios.TCSAFLUSH):
            set_attrs(fd, when, attrs.copy())

        # Linux exports B1000000; Darwin does not. Patching sys.platform alone
        # still reads the Linux constant and fails to exercise IOSSIOSPEED.
        darwin_termios = SimpleNamespace(
            B115200=termios.B115200,
            TCSANOW=termios.TCSANOW,
            tcgetattr=lambda fd: attrs.copy(),
            tcsetattr=set_attrs,
        )
        with patch("srasta_csi.serial_reader.sys.platform", "darwin"), patch(
            "srasta_csi.serial_reader.termios", darwin_termios
        ), patch(
            "srasta_csi.serial_reader.tty.setraw", side_effect=set_raw
        ), patch("srasta_csi.serial_reader.fcntl.ioctl") as ioctl:
            configure_serial(42, 1000000)
        self.assertEqual(attrs[4:6], [termios.B115200, termios.B115200])
        self.assertEqual(ioctl.call_args.args[2][0], 1000000)

    def test_linux_uses_native_megabaud_without_macos_ioctl(self):
        master, slave = pty.openpty()
        try:
            # PTY exercises the real Linux termios configuration, not a USB RX.
            if not hasattr(termios, "B1000000"):
                self.skipTest("Host termios has no native B1000000 constant")
            with patch("srasta_csi.serial_reader.fcntl.ioctl") as ioctl:
                configure_serial(slave, 1000000)
            attrs = termios.tcgetattr(slave)
            self.assertEqual(attrs[4:6], [termios.B1000000, termios.B1000000])
            ioctl.assert_not_called()
        finally:
            os.close(master)
            os.close(slave)

    def test_configuration_error_retries_instead_of_killing_reader(self):
        with tempfile.NamedTemporaryFile() as port:
            reader = SerialJSONLReader(port.name, 1000000, lambda line: None)
            attempts = []

            def configure(fd, baud):
                attempts.append(fd)
                if len(attempts) == 1:
                    raise termios.error(22, "Invalid argument")
                reader._stop.set()

            with patch("srasta_csi.serial_reader.configure_serial", side_effect=configure), patch.object(
                reader._stop, "wait", side_effect=lambda timeout: reader._stop.is_set()
            ):
                reader._run()
            self.assertEqual(len(attempts), 2)
            self.assertEqual(reader.read_errors, 1)
            self.assertEqual(reader.reconnects, 1)
            self.assertFalse(reader.connected)


if __name__ == "__main__":
    unittest.main()
