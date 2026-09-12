"""Local alarms and optional summary-only notifications; no implicit cloud delivery."""
import os
import queue
import threading
import time

class LocalAlarm:
    def __init__(self, pins=None):
        self.active = False
        self.led = 'off'
        self.available = False
        self.error = None
        self.devices = None
        if pins:
            try:
                from gpiozero import OutputDevice
                self.devices = [OutputDevice(pin, initial_value=False) for pin in pins]
                self.available = True
            except Exception:
                self.error = 'gpio_unavailable'

    def set(self, state, acknowledged=False):
        self.active = state == 'critical' and not acknowledged
        self.led = 'red' if state == 'critical' else ('orange' if state in ('anomaly','inactive') else 'green')
        if self.devices:
            try:
                for index, device in enumerate(self.devices):
                    device.value = (self.active if index == 0 else self.led == ('green','orange','red')[index-1])
            except Exception:
                self.available, self.error = False, 'gpio_write_failed'

    def status(self):
        return {'requested':self.active,'hardware_available':self.available,'led':self.led,'error':self.error}

    def close(self):
        for device in self.devices or []:
            device.close()

class Notifications:
    def __init__(self, *, enabled=False, min_interval_s=30, transport=None):
        self.enabled = enabled
        self.minimum = min_interval_s
        self.transport = transport
        self.last = {}
        self.delivered = self.failed = self.limited = 0
        self.configured = bool(transport) or bool(os.getenv('SRASTA_BLYNK_TOKEN')) or bool(os.getenv('SRASTA_MQTT_HOST') and os.getenv('SRASTA_MQTT_USER') and os.getenv('SRASTA_MQTT_PASSWORD'))
        self.pending = queue.Queue(maxsize=8)
        self.stop = threading.Event()
        self.worker = threading.Thread(target=self._work,daemon=True)
        self.worker.start()

    def send(self, event, now=None):
        if not self.enabled or not self.configured or event['source'] != 'serial':
            return False
        if event['state'] not in ('inactive','anomaly','critical'):
            return False
        now = time.monotonic() if now is None else now
        if now-self.last.get(event['state'],-float('inf')) < self.minimum:
            self.limited += 1
            return False
        self.last[event['state']] = now
        # Fixed allowlist. Never serialize an arbitrary runtime/payload object.
        message = {key:event[key] for key in ('id','state','reason','occurred_at','source')}
        try:
            self.pending.put_nowait(message)
            return True
        except queue.Full:
            self.failed += 1
            return False

    def _deliver(self, message):
        if self.transport:
            self.transport(message)
            return
        import json
        if os.getenv('SRASTA_BLYNK_TOKEN'):
            import httpx
            # Disable redirects; credentials never follow a redirect or enter logs.
            with httpx.Client(timeout=4, follow_redirects=False) as client:
                response = client.get('https://blynk.cloud/external/api/logEvent',params={'token':os.environ['SRASTA_BLYNK_TOKEN'],'code':'srasta_'+message['state'],'description':json.dumps(message)})
                response.raise_for_status()
        elif os.getenv('SRASTA_MQTT_HOST'):
            import ssl
            from paho.mqtt.publish import single
            single('srasta/events', json.dumps(message),qos=1,hostname=os.environ['SRASTA_MQTT_HOST'],port=8883,auth={'username':os.environ['SRASTA_MQTT_USER'],'password':os.environ['SRASTA_MQTT_PASSWORD']},tls={'cert_reqs':ssl.CERT_REQUIRED})
        else:
            raise RuntimeError('not configured')

    def _work(self):
        while not self.stop.is_set():
            try:
                message = self.pending.get(timeout=.2)
            except queue.Empty:
                continue
            try:
                self._deliver(message)
                self.delivered += 1
            except Exception:
                self.failed += 1
            finally:
                self.pending.task_done()

    def status(self):
        return {'enabled':self.enabled,'configured':self.configured,'delivered':self.delivered,'failed':self.failed,'rate_limited':self.limited,'pending':self.pending.qsize()}

    def close(self):
        self.stop.set()
        self.worker.join(timeout=1)
