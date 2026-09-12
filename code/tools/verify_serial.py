"""Probe an authorized receiver, save aggregate evidence only (never raw CSI)."""
import argparse
import json
import re
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from srasta_csi.product import ProductRuntime
from srasta_csi.contract import CaptureProfile
from tools.configure_hotspot import load_hotspot

def main():
    p=argparse.ArgumentParser();p.add_argument('--port',required=True);p.add_argument('--config',type=Path,default=Path('artifacts/hotspot.local.json'));p.add_argument('--seconds',type=float,default=45);p.add_argument('--out',type=Path,default=Path('artifacts/hardware-serial.json'));a=p.parse_args()
    if not 1<=a.seconds<=600:p.error('seconds must be 1..600')
    import serial
    c=load_hotspot(a.config)
    runtime=ProductRuntime(a.out.with_suffix('.sqlite3'),source='serial',sender=c['sender_mac'],channel=c['channel'])
    started=time.monotonic();diagnostics={};first_stamp=last_stamp=None;frames=0;first_invalid=0;mcs=set();snr=[]
    try:
        connection=serial.Serial(port=None,baudrate=921600,timeout=.2)
        connection.dtr=False;connection.rts=False;connection.port=a.port;connection.open()
        with connection:
            connection.reset_input_buffer();buffer=bytearray();discard=False
            while time.monotonic()-started<a.seconds:
                chunk=connection.read(max(1,min(connection.in_waiting,8192)))
                for byte in chunk:
                    if byte==10:
                        if not discard and buffer:
                            line=buffer.decode('utf-8',errors='replace').strip()
                            if line.startswith('{'):
                                accepted=runtime.ingest_json_line(line)
                                if accepted:
                                    payload=json.loads(line)
                                    stamp=payload['local_timestamp_us']/1e6
                                    first_stamp=stamp if first_stamp is None else first_stamp;last_stamp=stamp
                                    frames+=1;first_invalid+=payload['first_word_invalid'];mcs.add(payload['mcs']);snr.append(payload['rssi']-payload['noise_floor'])
                            elif line.startswith('# SRASTA'):
                                for key,value in re.findall(r'(rejected|queue_dropped|observed|last_len|last_mode|connected|disconnect_reason|stack_low_watermark)=(\d+)',line):diagnostics[key]=int(value)
                        buffer.clear();discard=False
                    elif not discard:
                        buffer.append(byte)
                        if len(buffer)>4096:buffer.clear();discard=True;runtime.rejected+=1
                runtime.heartbeat()
        status=runtime.status()
        report={'status':'passed' if frames>0 and status['health']['inference_count']>0 and status['health']['inference_ready'] else 'failed','duration_s':round(time.monotonic()-started,2),'port':a.port,'profile':CaptureProfile(channel=c['channel']).to_json(),'frames_accepted':frames,'inference_count':status['health']['inference_count'],'inference_ready_at_end':status['health']['inference_ready'],'observed_rate_hz':round((frames-1)/(last_stamp-first_stamp),2) if frames>1 and last_stamp>first_stamp else None,'first_word_invalid_frames':first_invalid,'mcs_values':sorted(mcs),'snr_range_db':[min(snr),max(snr)] if snr else None,'firmware_diagnostics':diagnostics,'runtime':status,'events_count':len(runtime.store.list(200)),'raw_saved':False,'evidence_scope':'One laptop-connected RX receiving HT20 traffic from user-authorized phone hotspot; no controlled ESP TX, Pi, camera or physical alarm evidence.'}
        a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k not in ('runtime','profile')},indent=2))
        if report['status']!='passed':raise SystemExit(1)
    finally:runtime.close()
if __name__=='__main__':main()
