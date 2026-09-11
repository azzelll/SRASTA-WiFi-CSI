"""Room motion calibration from user-labelled sessions; aggregate energies only."""
import argparse
import json
import math
from pathlib import Path
import time
from urllib.parse import urlsplit
from urllib.request import urlopen
import numpy as np


def compare_sessions(quiet, movement):
    for record,label in [(quiet,'quiet'),(movement,'movement')]:
        if record.get('label')!=label or record.get('status')!='passed':
            raise ValueError('Both sessions must have the requested label and sufficient continuous data')
        energies=np.asarray([sample['energy'] for sample in record['samples']],dtype=float)
        if len(energies)<60 or not np.isfinite(energies).all() or np.any(energies<0):
            raise ValueError('Each session needs at least 60 finite motion observations')
    if not quiet.get('setup_id') or quiet['setup_id']!=movement.get('setup_id'):
        raise ValueError('Sessions must describe the same unchanged physical setup')
    if not quiet.get('preprocess_config_hash') or quiet['preprocess_config_hash']!=movement.get('preprocess_config_hash'):
        raise ValueError('Session preprocessing configurations must match')
    if max(quiet['start_utc'],movement['start_utc'])<min(quiet['end_utc'],movement['end_utc']):
        raise ValueError('Opposite condition sessions cannot overlap in time')
    q=np.asarray([s['energy'] for s in quiet['samples']]);m=np.asarray([s['energy'] for s in movement['samples']])
    qfit,qcheck=np.array_split(q,2);mfit,mcheck=np.array_split(m,2)
    noise=float(np.quantile(qfit,.95));moving=float(np.quantile(mfit,.25))
    report={'status':'not_separated','setup_id':quiet['setup_id'],'preprocess_config_hash':quiet['preprocess_config_hash'],'quiet_fit_p95':noise,'movement_fit_p25':moving,'threshold':None,'scope':'Provisional room motion threshold; user session labels, not per-window ground truth, fall accuracy or independent subjects. Chronological second halves withheld from threshold selection.'}
    if moving<=max(noise,1e-12):return report
    threshold=math.sqrt(max(noise,1e-12)*moving)
    quiet_fraction=float(np.mean(qcheck>=threshold));movement_fraction=float(np.mean(mcheck>=threshold))
    report.update(candidate_threshold=threshold,quiet_holdout_exceedance=quiet_fraction,movement_holdout_exceedance=movement_fraction)
    if quiet_fraction<=.1 and movement_fraction>=.7:
        report.update(status='provisional_pass',threshold=threshold)
    else:report['status']='holdout_failed'
    return report


def capture(url, label, setup_id, seconds):
    origin=urlsplit(url)
    if origin.scheme!='http' or origin.hostname not in ('127.0.0.1','localhost') or origin.path not in ('','/') or origin.query or origin.fragment or origin.username:
        raise ValueError('Calibration reads only the local service origin')
    if not 30<=seconds<=120:raise ValueError('Capture duration must be 30..120 seconds')
    start=time.monotonic();utc=time.time();samples=[];seen=set();polls=good=0;session=None;config_hash=None
    while time.monotonic()-start<seconds:
        polls+=1
        try:
            with urlopen(url.rstrip('/')+'/status',timeout=2) as response:status=json.load(response)
            if status['source']!='serial' or status['simulated']:raise ValueError('Calibration requires actual serial input')
            active=status['session_id'];signature=status['preprocess_config_hash']
            if session is None:session,config_hash=active,signature
            if active!=session or signature!=config_hash:raise ValueError('Service or preprocessing changed during capture; repeat session')
            if status['health']['fresh'] and status['health']['inference_ready'] and status['trend']:
                good+=1;stamp=status['trend'][-1]['at'];energy=status['motion_energy']
                if stamp not in seen and stamp>=utc and energy is not None and math.isfinite(energy):
                    seen.add(stamp);samples.append({'elapsed_s':round(stamp-utc,3),'energy':energy})
        except (OSError,TimeoutError):pass
        time.sleep(.2)
    return {'status':'passed' if len(samples)>=60 and good/max(1,polls)>=.8 else 'insufficient_continuity','label':label,'setup_id':setup_id,'preprocess_config_hash':config_hash,'start_utc':utc,'end_utc':time.time(),'duration_s':round(time.monotonic()-start,2),'ready_fraction':good/max(1,polls),'samples':samples,'raw_saved':False,'label_scope':'User-reported condition of this session; does not label every frame or establish fall ground truth.'}


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    cap=sub.add_parser('capture');cap.add_argument('--url',default='http://127.0.0.1:8000');cap.add_argument('--label',choices=['quiet','movement'],required=True);cap.add_argument('--setup-id',required=True);cap.add_argument('--seconds',type=float,default=30);cap.add_argument('--out',type=Path,required=True)
    compare=sub.add_parser('compare');compare.add_argument('--quiet',type=Path,required=True);compare.add_argument('--movement',type=Path,required=True);compare.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    if args.out.exists():p.error('Output exists; preserve evidence and choose a new path')
    if args.action=='capture':result=capture(args.url,args.label,args.setup_id,args.seconds)
    else:result=compare_sessions(json.loads(args.quiet.read_text()),json.loads(args.movement.read_text()))
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    summary={k:v for k,v in result.items() if k!='samples'}
    if 'samples' in result:
        values=[s['energy'] for s in result['samples']];summary['sample_count']=len(values);summary['energy_quantiles']=np.quantile(values,[0,.1,.5,.9,1]).tolist() if values else []
    print(json.dumps(summary,indent=2))
    if result['status'] not in ('passed','provisional_pass'):raise SystemExit(1)

if __name__=='__main__':main()
