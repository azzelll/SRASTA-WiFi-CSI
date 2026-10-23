#!/usr/bin/env python3
"""Infer a public-source research recording, with source-train access enforced."""
import argparse
import json
from pathlib import Path

import joblib
import numpy as np

from srasta_csi.public_occupancy import source_rows, load_amplitude, invariant_features, LAYOUTS, INVARIANT_NAMES
from srasta_csi.research_features import temporal_features, FEATURE_NAMES
from srasta_csi.data import read_manifest, read_h5_amplitude, resolve_source_path


class OfflineResearchInference:
    def __init__(self,path):
        self.payload=p=joblib.load(path)
        tasks={'fall':['nonfall','fall'],'breathing':['empty','sleep'],
            'presence':['empty','present'],'breathing_three':['empty','sleep','normal']}
        if (p.get('artifact_type')!='srasta_offline_native_research_v1' or p.get('research_only') is not True
                or p.get('local_deployment_ready') is not False or p.get('task') not in tasks):
            raise ValueError('explicit offline research artifact required')
        if p.get('classes')!=tasks[p['task']] or list(p['model'].classes_)!=list(range(len(p['classes']))):
            raise ValueError('invalid task/classes')
        expected={'temporal':FEATURE_NAMES,'invariant':INVARIANT_NAMES}
        if p.get('feature') not in expected or p.get('feature_names')!=expected[p['feature']]:
            raise ValueError('feature schema mismatch')
        if p['task']!='fall' and p.get('layout') not in LAYOUTS:
            raise ValueError('native layout missing')
        threshold=p.get('threshold',.5)
        if not np.isfinite(threshold) or not 0<=threshold<=1:
            raise ValueError('invalid research threshold')
        if p['task']=='breathing_three' and p.get('normal_proxy_only') is not True:
            raise ValueError('normal class proxy provenance required')
        bias=np.asarray(p.get('probability_bias',[1.]*len(p['classes'])),dtype=float)
        if bias.shape!=(len(p['classes']),) or not np.isfinite(bias).all() or np.any(bias<=0):
            raise ValueError('invalid probability bias')
        self.bias=bias

    def predict(self,values,rate_hz):
        p=self.payload; x=np.asarray(values)
        if p['task']=='fall' and (x.shape!=(500,52) or rate_hz!=100.):
            raise ValueError('fall research requires measured 500x52 at nominal 100 Hz')
        features=(temporal_features if p['feature']=='temporal' else invariant_features)(x,rate_hz)
        probability=p['model'].predict_proba(features[None])[0]
        label=int(probability[1]>=p.get('threshold',.5)) if len(probability)==2 else int((probability*self.bias).argmax())
        return {'label':p['classes'][label],'probabilities':dict(zip(p['classes'],map(float,probability))),
            'probabilities_calibrated':False,
            'decision_threshold':p.get('threshold',.5) if len(probability)==2 else None,
            'probability_bias':self.bias.tolist() if len(probability)>2 else None,
            'task':p['task'],'research_only':True,'local_deployment_ready':False,
            'normal_proxy_only':p.get('normal_proxy_only',False),'source':'public_recording'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--recording-id',required=True)
    parser.add_argument('--source',type=Path,default=Path('data/csi-bench'))
    parser.add_argument('--source-task',choices=['BreathingDetection','HumanActivityRecognition','FallDetection'],required=True)
    args=parser.parse_args(); model=OfflineResearchInference(args.model)
    if args.source_task=='FallDetection':
        rows=read_manifest(args.source.parent/'curated/esp32_s3_fall_v1/manifest.csv')
        row=next((r for r in rows if r.sample_id==args.recording_id and r.split in {'train','validation'}),None)
        if row is None:parser.error('recording must belong to permitted development partition')
        if model.payload['task']!='fall':parser.error('source task does not match model')
        x=read_h5_amplitude(resolve_source_path(row,args.source.parent)); rate=100.; label=row.label
    else:
        if model.payload['task']=='fall':parser.error('fall model requires primary ESP32 source')
        rows,allowed=source_rows(args.source,args.source_task)
        row=next((r for r in rows if r['id']==args.recording_id),None)
        if row is None:parser.error('recording must belong to official source-train')
        x,rate=load_amplitude(args.source,row,allowed,model.payload['layout']); label=row['label']
    print(json.dumps(dict(model.predict(x,rate),recording_id=args.recording_id,source_label=label),indent=2))


if __name__=='__main__':main()
