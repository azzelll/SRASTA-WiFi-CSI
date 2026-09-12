"""Run fresh unit/API/replay + real-browser checks; return every failure."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[2]
def main():
    p=argparse.ArgumentParser();p.add_argument('--firmware',action='store_true');a=p.parse_args()
    out=ROOT/'artifacts/verification';out.mkdir(parents=True,exist_ok=True)
    env={**os.environ,'PYTHONPATH':str(ROOT/'code')}
    if os.name=='nt':
        user_temp=str(Path(os.environ['LOCALAPPDATA'])/'Temp')
        env.update(TEMP=user_temp,TMP=user_temp)
        env.setdefault('PLATFORMIO_CORE_DIR',str(Path(os.environ['LOCALAPPDATA'])/'srasta-pio'))
    commands=[]
    def run(args,name):
        with (out/f'{name}.log').open('w',encoding='utf-8') as log:
            result=subprocess.run(args,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        commands.append({'name':name,'exit_code':result.returncode,'command':args})
        print(f'{name}: '+('PASSED' if result.returncode==0 else 'FAILED'),flush=True)
        return result.returncode
    run([sys.executable,'-m','unittest','discover','-s','code/tests','-v'],'unit-api-replay')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    stamp=str(time.time_ns());db=out/f'demo-{stamp}.sqlite3';url=f'http://127.0.0.1:{port}'
    with (out/'demo-service.log').open('w',encoding='utf-8') as log:
        server=subprocess.Popen([sys.executable,'code/run_edge_service.py','--demo','--db',str(db),'--port',str(port)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        try:
            ready=False
            for _ in range(60):
                if server.poll() is not None:break
                try:
                    with urllib.request.urlopen(url+'/health',timeout=1) as response:ready=response.status==200
                    if ready:break
                except OSError:time.sleep(.25)
            if ready:run([sys.executable,'code/tools/test_dashboard.py','--url',url,'--out',str(out/'ui')],'dashboard')
            else:commands.append({'name':'demo-start','exit_code':1})
        finally:
            server.terminate()
            try:server.wait(timeout=8)
            except subprocess.TimeoutExpired:server.kill();server.wait()
    if a.firmware:
        run([sys.executable,'-m','platformio','run','-d','firmware','-e','tx','-e','rx'],'firmware')
    report={'status':'passed' if all(c['exit_code']==0 for c in commands) else 'failed','checks':commands,'firmware_requested':a.firmware,'hardware_test':'separate verify_serial.py command; no automatic flash'}
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    raise SystemExit(0 if report['status']=='passed' else 1)
if __name__=='__main__':main()
