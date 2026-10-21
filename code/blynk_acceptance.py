#!/usr/bin/env python3
"""Blynk HTTPS command -> live TLS MQTT -> isolated simulator SQLite proof.

Stop the real edge's Blynk client before running: one device token supports
one MQTT client. V12 is checked before issuing a clearly labeled simulation.
This does not prove delivery to a phone or operation of its Blynk widgets.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
import urllib.request
from urllib.parse import urlencode

from run_edge_service import load_local_env
from srasta_csi.blynk_mqtt import BlynkMQTTAdapter
from srasta_csi.edge import EdgeRuntime


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.env.stat().st_mode & 0o077:
        parser.error("private env file must have permission 0600")
    if args.out_dir.exists():
        parser.error("output directory must be new")
    args.out_dir.mkdir(parents=True,mode=0o700)
    env = load_local_env(args.env)
    token = env["BLYNK_AUTH_TOKEN"]
    host = env.get("BLYNK_MQTT_HOST","blynk.cloud")
    if host != "blynk.cloud" and not host.endswith(".blynk.cloud"):
        parser.error("Blynk host must be official")
    opener = urllib.request.build_opener(NoRedirect())
    def http(method,pin,value=None):
        query = {"token":token, pin:str(value)} if method=="update" else {"token":token,pin:""}
        req = urllib.request.Request(f"https://{host}/external/api/{method}?"+urlencode(query))
        try:
            with opener.open(req,timeout=8) as r:
                body = r.read(65536)
                return json.loads(body) if body else None
        except Exception as error:
            raise RuntimeError(f"Blynk API request failed: {type(error).__name__}") from None
    def wait_for(predicate):
        deadline = time.monotonic()+15
        while time.monotonic()<deadline:
            if predicate(): return
            time.sleep(.25)
        raise RuntimeError("Blynk acceptance condition timed out")
    runtime = EdgeRuntime(args.model,args.out_dir/"events.sqlite3",demo_mode=True)
    runtime.set_demo_state("normal")
    adapter = BlynkMQTTAdapter(token,host=host,on_acknowledge=lambda:runtime.acknowledge_alert("blynk_v10"),on_assistance=lambda:runtime.request_assistance("blynk_v11"),status_provider=runtime.status)
    report = {"source":"simulator","mobile_push_or_widget_proof":False,"checked_at_s":time.time(),"checks":{}}
    try:
        adapter.start()
        wait_for(lambda:adapter.connected)
        adapter.update(runtime.status())
        wait_for(lambda:float(http("get","v12"))==1)
        report["checks"]["simulation_flag_v12"]="pass"
        runtime.set_demo_state("critical")
        adapter.update(runtime.status())
        wait_for(lambda:float(http("get","v0"))==4)
        assert float(http("get","v12"))==1
        http("update","v10",1)
        wait_for(lambda:runtime.store.list()[0]["acknowledged_at_s"] is not None)
        assert runtime.store.list()[0]["ack_source"]=="blynk_v10"
        wait_for(lambda:float(http("get","v10"))==0)
        report["checks"]["v10_https_to_mqtt_to_sqlite_and_reset"]="pass"
        http("update","v11",1)
        wait_for(lambda:bool(runtime.store.actions()))
        assert len(runtime.store.actions())==1 and runtime.store.actions()[0]["source"]=="blynk_v11"
        wait_for(lambda:float(http("get","v11"))==0)
        report["checks"]["v11_https_to_mqtt_to_sqlite_and_reset"]="pass"
        report["checks"]["auto_call"]=False
        report["result"]="pass"
    except Exception as error:
        report["result"]="fail"
        report["error_type"]=type(error).__name__
        raise
    finally:
        runtime.set_demo_state("normal")
        adapter.update(runtime.status())
        time.sleep(.5)
        adapter.close()
        runtime.close()
        (args.out_dir/"report.json").write_text(json.dumps(report,indent=2)+"\n")
        print(json.dumps(report,indent=2))


if __name__=="__main__":
    main()
