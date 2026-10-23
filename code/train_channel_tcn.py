#!/usr/bin/env python3
"""One preregistered TCN ablation: per-window channel normalization, train folds."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from srasta_csi.development import load_development, grouped_folds, select_threshold
from srasta_csi.model import export_full_int8, TFLiteModel, parity_report
from srasta_csi.research_features import channel_normalize
from train_fall_grouped import fit_tcn, TCN_SPEC
from train_offline_candidates import save, report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root',type=Path,default=Path('data'))
    parser.add_argument('--out-dir',type=Path,required=True)
    args=parser.parse_args(); args.out_dir.mkdir(parents=True,exist_ok=False)
    code=Path(__file__)
    save(args.out_dir/'protocol.json',{'architecture':TCN_SPEC,'seed':42,'epochs_max':30,
        'normalization':'current-window per-channel relative/std clipped +/-5; not frame-prefix causal',
        'selection':'six train-only outer subjects, separate cyclic calibration subject; no U19 tuning',
        'final_epochs':'median best calibration epoch','final_threshold':'seed42 train OOF',
        'representative_partition':'primary train only','test_payload_opened':False,
        'independent_test':False,'local_deployment_ready':False,'research_only':True,
        'source_code_sha256':hashlib.sha256(code.read_bytes()).hexdigest()})
    snapshot=args.out_dir/'source_snapshot'; snapshot.mkdir()
    for p in (code,code.with_name('train_fall_grouped.py'),code.with_name('train_srasta_release.py'),
              code.parent/'srasta_csi/research_features.py'):
        (snapshot/p.name).write_bytes(p.read_bytes())
    rows,raw=load_development(args.data_root,'train'); x=channel_normalize(raw)
    y=np.array([r.label_id for r in rows]); groups=np.array([r.subject_id for r in rows])
    probability=np.zeros(len(y)); prediction=np.zeros(len(y),dtype=int); folds=[]
    for f in grouped_folds(groups):
        fit,cal,ev=(f[k] for k in ('fit','calibrate','evaluate'))
        model,history,epoch=fit_tcn(x[fit],y[fit],42,30,(x[cal],y[cal]))
        cut=select_threshold(y[cal],model.predict(x[cal],verbose=0)[:,1])['threshold']
        probability[ev]=model.predict(x[ev],verbose=0)[:,1]; prediction[ev]=probability[ev]>=cut
        folds.append({'held_out_subject':f['held_out_subject'],'calibration_subject':f['calibration_subject'],
            'fit_subjects':f['fit_subjects'],'threshold':cut,'best_epoch':epoch,'history':history})
        save(args.out_dir/'folds.json',folds)
        print('TCN',f['held_out_subject'],'best_epoch',epoch,report(y[ev],prediction[ev],['nonfall','fall'])['per_class_recall'],flush=True)
    cutoff=select_threshold(y,probability)['threshold']; epochs=max(1,int(np.median([f['best_epoch'] for f in folds])))
    np.savez_compressed(args.out_dir/'oof_predictions.npz',y=y,probability=probability,prediction=prediction)
    model,history,_=fit_tcn(x,y,42,epochs); model.save(args.out_dir/'model.keras')
    representative=np.random.default_rng(42).choice(len(x),256,replace=False)
    export_full_int8(model,x[representative],args.out_dir/'model.tflite')
    config={'research_only':True,'classes':['nonfall','fall'],'threshold':cutoff,'epochs':epochs,
        'window_length':500,'model_sha256':hashlib.sha256((args.out_dir/'model.tflite').read_bytes()).hexdigest(),
        'normalization':'research channel_normalize, not deployed causal preprocessing','deployment_ready':False}
    save(args.out_dir/'training_config.json',config)
    save(args.out_dir/'selection_before_validation.json',dict(config,train_outer=report(y,prediction,['nonfall','fall'])))
    save(args.out_dir/'representative_provenance.json',{'source':'primary train','ids':[rows[i].sample_id for i in representative]})
    # Read the historical development validation only after freezing the fit.
    vr,vraw=load_development(args.data_root,'validation'); vx=channel_normalize(vraw); vy=np.array([r.label_id for r in vr])
    runtime=TFLiteModel(args.out_dir/'model.tflite'); p=np.array([runtime.probability(v) for v in vx])
    metrics=report(vy,(p>=cutoff).astype(int),['nonfall','fall'])
    np.savez_compressed(args.out_dir/'validation_predictions.npz',y=vy,probability=p)
    save(args.out_dir/'metrics.json',{'development_validation':metrics,'parity':parity_report(model,runtime,vx),
        'threshold':cutoff,'epochs':epochs,'model_size_bytes':(args.out_dir/'model.tflite').stat().st_size,
        'independent_test':False,'test_payload_opened':False,'local_deployment_ready':False,
        'joint_80_pass':metrics['minimum_class_recall']>=.8})
    print('TCN validation',metrics['per_class_recall'],flush=True)


if __name__=='__main__':main()
