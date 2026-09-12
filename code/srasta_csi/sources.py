"""Serial/replay sources. No raw capture is saved by the local product."""
import json
import re
import threading
import time
from pathlib import Path
from .data import read_replay

class SourceRunner:
    def __init__(self,runtime,*,port=None,baud=921600,replay=None,realtime=True,idle_timeout_s=5):
        self.runtime,self.port,self.baud,self.replay = runtime,port,baud,replay
        if not 0 < idle_timeout_s <= 60:
            raise ValueError('serial idle timeout must be in (0,60] seconds')
        self.idle_timeout_s = idle_timeout_s
        self.realtime = realtime
        self.stop = threading.Event()
        self.thread = None
        self.connection = None

    def start(self):
        if self.port or self.replay:
            self.thread = threading.Thread(target=self.run,daemon=True)
            self.thread.start()

    def run(self):
        try:
            if self.replay:
                self._replay()
            else:
                self._serial()
        except Exception:
            self.runtime.source_status = 'error'
            self.runtime.input_error = 'source_failed'

    def _wait_until(self, target):
        while not self.stop.is_set():
            remaining=target-time.monotonic()
            if remaining <= 0:
                return True
            self.stop.wait(min(.5,remaining))
        return False

    def _replay(self):
        path = Path(self.replay)
        started = time.monotonic()
        first = None
        if path.suffix.lower()=='.jsonl':
            from .contract import FrameValidator
            pacing=FrameValidator(self.runtime.profile,expected_sender=self.runtime.sender)
            with path.open(encoding='utf-8') as handle:
                while not self.stop.is_set():
                    line=handle.readline(4097)
                    if not line:
                        break
                    if len(line)>4096:
                        self.runtime.rejected += 1
                        while line and not line.endswith('\n'):
                            line=handle.readline(4097)
                        continue
                    try:
                        frame=pacing.parse_json_line(line)
                    except ValueError:
                        self.runtime.ingest_json_line(line)
                        continue
                    stamp=frame.local_timestamp_us/1e6
                    if first is None:
                        first=stamp
                    if self.realtime and not self._wait_until(started+stamp-first):
                        break
                    self.runtime.ingest_json_line(line)
        else:
            values,times = read_replay(path)
            for value,stamp in zip(values,times):
                if self.stop.is_set():
                    break
                if self.realtime and not self._wait_until(started+float(stamp-times[0])):
                    break
                self.runtime.ingest_amplitude(value,float(stamp))
        self.runtime.source_status = 'replay_complete' if not self.stop.is_set() else 'stopped'

    def _serial(self):
        import serial
        idle_attempts = 0
        while not self.stop.is_set():
            try:
                connection=serial.Serial(port=None,baudrate=self.baud,timeout=.3)
                connection.dtr=False; connection.rts=False
                connection.port=self.port; connection.open()
                # Explicitly propagate the idle control-line state to Windows USB.
                connection.rts=False; connection.dtr=False
                with connection:
                    self.connection = connection
                    self.runtime.reconnect()
                    buffer = bytearray()
                    discard = False
                    last_byte = time.monotonic()
                    while not self.stop.is_set():
                        chunk = connection.read(max(1,min(connection.in_waiting,8192)))
                        if chunk:
                            last_byte = time.monotonic()
                            idle_attempts = 0
                        elif time.monotonic()-last_byte >= self.idle_timeout_s:
                            with self.runtime.lock:
                                self.runtime.source_status = 'disconnected'
                                self.runtime.input_error = 'serial_no_data'
                            idle_attempts += 1
                            break
                        for byte in chunk:
                            if byte==10:
                                if not discard and buffer:
                                    try:
                                        line = buffer.decode('utf-8')
                                        self._consume_line(line)
                                    except UnicodeDecodeError:
                                        self.runtime.rejected += 1
                                buffer.clear(); discard=False
                            elif not discard:
                                buffer.append(byte)
                                if len(buffer)>4096:
                                    buffer.clear(); discard=True
                                    self.runtime.rejected += 1
                        self.runtime.process_pending()
                if not self.stop.is_set():
                    self.stop.wait(min(8,2**min(3,max(0,idle_attempts-1))))
            except (serial.SerialException,OSError):
                self.runtime.source_status = 'disconnected'
                self.runtime.input_error = 'serial_unavailable'
                self.stop.wait(1)
            finally:
                self.connection = None

    def _consume_line(self,line):
        if line.startswith('# SRASTA boot revision=') or line.startswith('# SRASTA hotspot receiver awaiting association;'):
            # USB can stay open through an ESP reboot. Do not compare a new boot's
            # uptime/sequence to the old boot, or count its outage as inactivity.
            self.runtime.process_pending()
            self.runtime.reconnect()
        if line.startswith('# SRASTA'):
            values={key:int(value) for key,value in re.findall(r'\b(connected|disconnect_reason|rejected|queue_dropped|observed|last_len|last_mode|stack_low_watermark|ping_sent|ping_replies|ping_timeouts|ping_reply_ms)=(\d{1,15})(?!\d)',line)}
            if values:
                with self.runtime.lock:
                    self.runtime.firmware_diagnostics.update(values)
                    self.runtime.firmware_diagnostics['updated_at']=time.time()
        elif line.startswith('{'):
            self.runtime.submit_line(line)

    def close(self):
        self.stop.set()
        connection = self.connection
        if connection is not None and hasattr(connection,'cancel_read'):
            try:
                connection.cancel_read()
            except OSError:
                pass
        if self.thread:
            self.thread.join(timeout=3)
