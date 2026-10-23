#!/usr/bin/env python3
"""Owner-authorized HTTPS/SQLite acceptance on a disposable simulation device.

Never uses the live device credential, raw CSI, browser sessions, or push
subscriptions. Private admin keys are read from a local file, never printed.
The temporary device is removed after the run, including on a failed check.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import urllib.error
import urllib.request
import uuid

from srasta_csi.cloud_sync import CloudSync
from srasta_csi.edge import EdgeRuntime


class AcceptanceHTTP:
    def __init__(self, url, public_key, admin_key):
        self.url = url.rstrip("/")
        self.public_key, self.admin_key = public_key, admin_key
        self.access_token = None
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(self, path, payload=None, *, admin=False, anonymous=False):
        headers = {"Content-Type": "application/json", "apikey": self.admin_key if admin else self.public_key}
        if admin or (self.access_token and not anonymous):
            headers["Authorization"] = "Bearer " + (self.admin_key if admin else self.access_token)
        req = urllib.request.Request(self.url + path, data=None if payload is None else json.dumps(payload).encode(), headers=headers, method="GET" if payload is None else "POST")
        with self.opener.open(req, timeout=15) as response:
            body = response.read(1_048_576)
            return json.loads(body) if body else None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def private_json(path):
    if path.stat().st_mode & 0o077:
        raise ValueError("credential files must be private (0600)")
    return json.loads(path.read_text())


def query(sql, path, project_ref):
    path.write_text(sql)
    path.chmod(0o600)
    env = {**os.environ, "npm_config_cache": "/private/tmp/srasta-npm-cache"}
    result = subprocess.run(["npx", "--yes", "supabase", "db", "query", "--linked", "--project-ref", project_ref, "--file", str(path), "--output", "json"], env=env, capture_output=True, text=True, timeout=60)
    if result.returncode:
        # CLI output could contain query contents; keep it out of public logs.
        raise RuntimeError("Supabase management SQL request failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--project-ref", required=True)
    parser.add_argument("--keys-file", type=Path, required=True)
    parser.add_argument("--owner-file", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.url != f"https://{args.project_ref}.supabase.co":
        parser.error("URL must match the official project origin")
    if args.model.is_dir():
        args.model = args.model / "model.tflite"
    if not args.model.is_file() or args.model.suffix != ".tflite":
        parser.error("model must be an existing TFLite release file or directory")
    if args.out_dir.exists():
        parser.error("output directory must be new")
    args.out_dir.mkdir(parents=True, mode=0o700)
    keys = private_json(args.keys_file)["keys"]
    public_key = next(k["api_key"] for k in keys if k["type"] == "publishable")
    admin_key = next(k["api_key"] for k in keys if k["name"] == "service_role")
    owner = private_json(args.owner_file)
    owner_id = str(uuid.UUID(owner["user_id"]))
    device_id, token = str(uuid.uuid4()), secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    http = AcceptanceHTTP(args.url, public_key, admin_key)
    report = {"source": "simulator", "hardware_proof": False, "mobile_push_proof": False, "checked_at_s": time.time(), "checks": {}}
    runtime = None
    provisioned = False
    try:
        query(f"begin; insert into public.devices(id,label) values('{device_id}','SRASTA QA — simulasi sementara'); insert into srasta_private.device_secrets(device_id,token_sha256) values('{device_id}','{token_hash}'); insert into public.device_members(device_id,user_id) values('{device_id}','{owner_id}'); commit;", args.out_dir / "provision.sql", args.project_ref)
        provisioned = True
        # generate_link does not send an email. The short-lived QA session is
        # isolated from the user's Safari/phone sessions and revoked locally.
        link = http.request("/auth/v1/admin/generate_link", {"type": "magiclink", "email": owner["email"]}, admin=True)
        hashed_token = link.get("hashed_token") or link.get("properties", {}).get("hashed_token")
        if not hashed_token:
            raise RuntimeError("Auth did not return a verification token")
        session = http.request("/auth/v1/verify", {"type": "magiclink", "token_hash": hashed_token}, anonymous=True)
        if session["user"]["id"] != owner_id:
            raise RuntimeError("Auth owner does not match the provisioned membership")
        http.access_token = session["access_token"]
        runtime = EdgeRuntime(args.model, args.out_dir / "events.sqlite3", demo_mode=True)
        sync = CloudSync(runtime, args.url, device_id, token)
        states = []
        for state in ("standby", "normal", "inactive", "anomaly", "critical"):
            runtime.set_demo_state(state)
            sync.sync_once()
            remote = http.request(f"/rest/v1/device_status?device_id=eq.{device_id}&select=snapshot")[0]["snapshot"]
            assert remote["state"] == state and remote["simulation"] is True and remote["source"] == "simulator"
            assert not any(key in json.dumps(remote) for key in ("iq_bytes", "sender_mac", "amplitude"))
            states.append(state)
        report["checks"]["https_five_states"] = states
        target = next(e for e in runtime.store.list() if e["state"] == "anomaly")
        critical = next(e for e in runtime.store.list() if e["state"] == "critical")
        command_id, assistance_id = str(uuid.uuid4()), str(uuid.uuid4())
        command = {"p_id": command_id, "p_device_id": device_id, "p_event_uid": target["event_uid"], "p_action": "acknowledge"}
        pending = http.request("/rest/v1/rpc/request_caregiver_command", command)
        assert pending["status"] == "pending"
        assert http.request("/rest/v1/rpc/request_caregiver_command", command)["id"] == command_id
        http.request("/rest/v1/rpc/request_caregiver_command", {**command, "p_id": assistance_id, "p_action": "assistance"})
        sync.sync_once()  # actual Edge Function -> local SQLite transaction
        events = {e["event_uid"]: e for e in runtime.store.list()}
        assert events[target["event_uid"]]["acknowledged_at_s"] is not None
        assert events[critical["event_uid"]]["acknowledged_at_s"] is None
        assert len(runtime.store.actions()) == 1
        assert all(r["auto_call"] is False for r in runtime.store.cloud_batch()[1])
        # Restart before uploading receipts: durable SQLite must complete both
        # commands without executing the assistance again.
        runtime.close()
        runtime = EdgeRuntime(args.model, args.out_dir / "events.sqlite3", demo_mode=True)
        sync = CloudSync(runtime, args.url, device_id, token)
        sync.sync_once()
        remote_commands = http.request(f"/rest/v1/caregiver_commands?device_id=eq.{device_id}&select=id,status,applied_at_s")
        assert len(remote_commands) == 2 and all(c["status"] == "applied" and c["applied_at_s"] for c in remote_commands)
        assert len(runtime.store.actions()) == 1
        report["checks"].update(targeted_ack_sqlite="pass", assistance_auto_call=False, receipt_after_restart="pass", command_idempotence="pass")
        runtime.set_demo_state("inactive")
        # Fail after the real server commits but before the edge receives its
        # response. This fault injection tests the ambiguous retry boundary;
        # it is not described as a real internet outage.
        real_post = sync.post
        def lost_response(payload):
            real_post(payload)
            raise ConnectionResetError("injected response loss")
        sync.post = lost_response
        try:
            sync.sync_once()
            raise AssertionError("fault injection did not fail")
        except ConnectionResetError:
            pass
        assert runtime.store.cloud_batch()[0]
        runtime.close()
        runtime = EdgeRuntime(args.model, args.out_dir / "events.sqlite3", demo_mode=True)
        sync = CloudSync(runtime, args.url, device_id, token)
        sync.sync_once()
        remote_events = http.request(f"/rest/v1/care_events?device_id=eq.{device_id}&select=event_uid")
        assert {e["event_uid"] for e in remote_events} == {e["event_uid"] for e in runtime.store.list(100)}
        assert len(remote_events) == len(runtime.store.list(100))
        assert runtime.store.cloud_batch() == ([], [])
        assert len(runtime.store.actions()) == 1
        report["checks"]["lost_response_retry_and_restart"] = "pass"
        try:
            http.request(f"/rest/v1/device_status?device_id=eq.{device_id}", anonymous=True)
            raise AssertionError("anonymous status access unexpectedly allowed")
        except urllib.error.HTTPError as error:
            assert error.code in (401, 403)
        report["checks"]["anonymous_denied"] = "pass"
        query(f"delete from public.device_members where device_id='{device_id}' and user_id='{owner_id}';", args.out_dir / "revoke.sql", args.project_ref)
        assert http.request(f"/rest/v1/device_status?device_id=eq.{device_id}") == []
        try:
            http.request("/rest/v1/rpc/request_caregiver_command", {**command, "p_id": str(uuid.uuid4())})
            raise AssertionError("revoked membership unexpectedly allowed a command")
        except urllib.error.HTTPError as error:
            assert error.code == 400
        report["checks"]["membership_revocation_live_jwt"] = "pass"
        report["result"] = "pass"
    except Exception as error:
        report["result"] = "fail"
        report["error_type"] = type(error).__name__
        raise
    finally:
        if runtime:
            runtime.close()
        try:
            if http.access_token:
                http.request("/auth/v1/logout?scope=local", {})
        finally:
            try:
                if provisioned:
                    query(f"delete from public.devices where id='{device_id}' and label='SRASTA QA — simulasi sementara';", args.out_dir / "cleanup.sql", args.project_ref)
                    report["temporary_device_removed"] = True
            finally:
                (args.out_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n")
                print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
