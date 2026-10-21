"""Outbound HTTPS sync; persistent SQLite outbox, per-device credential, no raw CSI."""
from __future__ import annotations

import json
import math
import threading
import time
import urllib.error
import urllib.request
import uuid
from urllib.parse import urlparse

from .caregiver import caregiver_snapshot


class CloudSync:
    def __init__(self, runtime, url: str, device_id: str, device_token: str, *, interval_s: float = 5.0, post=None):
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith(".supabase.co") or parsed.path not in {"", "/"} or parsed.username or parsed.query or parsed.port not in {None, 443}:
            raise ValueError("cloud sync requires an official Supabase HTTPS project URL")
        uuid.UUID(device_id)
        if len(device_token) < 32 or interval_s <= 0:
            raise ValueError("device token must have at least 32 characters and interval must be positive")
        self.runtime = runtime
        self.endpoint = url.rstrip("/") + "/functions/v1/edge-sync"
        self.device_id, self.device_token = device_id, device_token
        self.interval_s = interval_s
        self.post = post or self._post
        self.connected = False
        self.last_success_s = None
        self.last_error = None
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, name="caregiver-cloud-sync", daemon=True)

    def _post(self, payload):
        request = urllib.request.Request(self.endpoint, data=json.dumps(payload, allow_nan=False).encode(), headers={"Content-Type": "application/json", "X-SRASTA-Device-Token": self.device_token}, method="POST")
        # No redirects: never forward a device credential to another origin.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=5) as response:
            return json.loads(response.read(262144))

    def start(self):
        self.thread.start()

    def sync_once(self):
        try:
            self._sync_once()
        except Exception as exc:
            self.connected = False
            self.last_error = f"Sync failed: {type(exc).__name__}"
            raise

    def _sync_once(self):
        events, receipts = self.runtime.store.cloud_batch()
        snapshot = caregiver_snapshot(self.runtime)
        response = self.post({"device_id": self.device_id, "snapshot": snapshot, "events": events, "receipts": receipts})
        if not isinstance(response, dict) or response.get("ok") is not True or not isinstance(response.get("commands"), list):
            raise ValueError("cloud did not confirm transaction")
        commands = response["commands"]
        if len(commands) > 30:
            raise ValueError("cloud command batch exceeds limit")
        for command in commands:
            if not isinstance(command, dict) or set(command) != {"id", "event_uid", "action", "expires_at_s"}:
                raise ValueError("invalid cloud command")
            uuid.UUID(command["id"])
            uuid.UUID(command["event_uid"])
            expiry = command["expires_at_s"]
            if (command["action"] not in {"acknowledge", "assistance"} or isinstance(expiry, bool)
                    or not isinstance(expiry, (int, float)) or not math.isfinite(expiry) or expiry <= 0):
                raise ValueError("invalid cloud command")
        for command in commands:
            self.runtime.apply_caregiver_command(command_id=command["id"], event_uid=command["event_uid"], action=command["action"], source="remote_caregiver", expires_at_s=command["expires_at_s"])
        self.runtime.store.mark_cloud_batch(events, receipts)
        self.connected = True
        self.last_success_s = time.time()
        self.last_error = None

    def _run(self):
        delay = 0.0
        while not self.stop.wait(delay):
            try:
                self.sync_once()
                delay = self.interval_s
            except Exception as exc:
                self.connected = False
                self.last_error = f"Sync failed: {type(exc).__name__}"  # never include URL/token/payload.
                delay = min(max(delay * 2, self.interval_s), 60)

    def status(self):
        return {"enabled": True, "connected": self.connected and self.last_success_s is not None and time.time() - self.last_success_s < 20, "last_success_s": self.last_success_s, "last_error": self.last_error, "worker_running": self.thread.is_alive()}

    def close(self):
        self.stop.set()
        if self.thread.is_alive():
            self.thread.join(timeout=6)
