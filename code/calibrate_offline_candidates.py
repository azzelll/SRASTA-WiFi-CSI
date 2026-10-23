#!/usr/bin/env python3
"""Disclosed post-hoc PUBLIC development calibration; never tunes fall/U19."""
import argparse
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np

from calibrate_public_occupancy import choose_threshold
from train_offline_candidates import report, save, rank


def choose_bias(y,probabilities):
    """Fixed finite bias grid, selected on development validation only."""
    y=np.asarray(y); p=np.asarray(probabilities,dtype=float)
    if (p.shape!=(len(y),3) or set(y.tolist())!={0,1,2} or not np.isfinite(p).all()
            or np.any(p<0) or not np.allclose(p.sum(axis=1),1.)):
        raise ValueError('three-class normalized probabilities and observed labels required')
    best=None
    for sleep in (.125,.25,.5,1.,2.,4.,8.):
        for normal in (.125,.25,.5,1.,2.,4.,8.):
            weights=[1.,sleep,normal]; prediction=np.argmax(p*weights,axis=1)
            metrics=report(y,prediction,['empty','sleep','normal'])
            score=rank({'metrics':metrics})+(-abs(np.log2(sleep))-abs(np.log2(normal)),)
            if best is None or score>best[0]:best=(score,weights,metrics)
    return best[1:]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--out-dir',type=Path,required=True)
    args=parser.parse_args()
    protocol=json.loads((args.run/'protocol.json').read_text())
    if protocol.get('stage')!='public_occupancy' or (args.run/'INVALIDATED.md').exists():
        raise ValueError('completed non-invalidated public occupancy experiment required; fall tuning forbidden')
    reports=json.loads((args.run/'metrics.json').read_text())
    args.out_dir.mkdir(parents=True,exist_ok=False)
    calibrated_protocol={'stage':'public_occupancy_calibration','source':str(args.run),
        'source_code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'candidate_and_cutoff_selected_on_same_development_validation':True,
        'independent_test':False,'local_deployment_ready':False,'weights_refitted':False,
        'three_class_bias_grid':[.125,.25,.5,1.,2.,4.,8.],
        'normal_proxy_only':True,'fall_or_locked_test_opened':False}
    save(args.out_dir/'protocol.json',calibrated_protocol)
    output={}
    for task,r in reports.items():
        if task not in {'breathing','presence','breathing_three'}:raise ValueError('public tasks only')
        trials=[]
        for candidate in r['candidates']:
            name=candidate['candidate']
            if Path(name).name!=name:raise ValueError('invalid candidate name')
            with np.load(args.run/task/(name+'-predictions.npz')) as a:y,p=a['y'],a['probabilities']
            if task=='breathing_three':
                bias,metrics=choose_bias(y,p); cutoff=None
            else:
                cutoff=choose_threshold(y,p[:,1])['threshold'];bias=None
                metrics=report(y,(p[:,1]>=cutoff).astype(int),['empty','sleep' if task=='breathing' else 'present'])
            trials.append({'candidate':name,'threshold':cutoff,'probability_bias':bias,'metrics':metrics})
        chosen=max(trials,key=rank); folder=args.out_dir/task;folder.mkdir()
        payload=joblib.load(args.run/task/(chosen['candidate']+'.joblib'))
        payload['calibration']=calibrated_protocol
        if chosen['threshold'] is not None:payload['threshold']=chosen['threshold']
        if chosen['probability_bias'] is not None:payload['probability_bias']=chosen['probability_bias']
        joblib.dump(payload,folder/'model.joblib',compress=3)
        with np.load(args.run/task/(chosen['candidate']+'-predictions.npz')) as a:y,p=a['y'],a['probabilities']
        prediction=np.argmax(p*chosen['probability_bias'],axis=1) if task=='breathing_three' else (p[:,1]>=chosen['threshold']).astype(int)
        np.savez_compressed(folder/'predictions.npz',y=y,probabilities=p,prediction=prediction)
        # Recompute strata by the recorded validation order, including sleep.
        strata=list(r['counts']['validation']); offset=0; per_stratum={}
        for s in strata:
            count=r['counts']['validation'][s]
            expected=0 if s=='empty' else 2 if s=='normal' else 1
            per_stratum[s]=float((prediction[offset:offset+count]==expected).mean());offset+=count
        output[task]={'selected':chosen,'candidates':trials,'strata_recall':per_stratum,
            'model_sha256':hashlib.sha256((folder/'model.joblib').read_bytes()).hexdigest(),
            'independent_test':False,'local_deployment_ready':False,'optimistic_development_score':True}
        print(task,chosen['candidate'],chosen['metrics']['per_class_recall'],flush=True)
    save(args.out_dir/'metrics.json',output)


if __name__=='__main__':main()
