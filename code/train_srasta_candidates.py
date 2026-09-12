"""Select alternative models by leave-one-subject-out training CV; U21 stays locked."""
import argparse,json,time
from pathlib import Path
import numpy as np
import joblib
from sklearn.base import clone
from sklearn.ensemble import ExtraTreesClassifier,RandomForestClassifier,HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.model_selection import LeaveOneGroupOut
from srasta_csi.data import read_manifest,read_h5_amplitude,resolve_source_path,timestamps,manifest_sha256,split_report
from srasta_csi.preprocess import CausalPreprocessor,PreprocessConfig
from srasta_csi.contract import CaptureProfile
from srasta_csi.feature_model import rich_features,classifier_scores,FEATURE_VERSION
from srasta_csi.metrics import classification_metrics,unavailable_event_metrics

def main():
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);p.add_argument('--data-root',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--window-length',type=int,choices=[250,500],default=250);a=p.parse_args()
    if a.manifest.resolve()!=(a.data_root/'curated/esp32_s3_fall_v1/manifest.csv').resolve():raise ValueError('primary manifest required')
    if a.out_dir.exists() and any(a.out_dir.iterdir()):raise FileExistsError('new output directory required')
    a.out_dir.mkdir(parents=True,exist_ok=True)
    rows=read_manifest(a.manifest);profile=CaptureProfile();config=PreprocessConfig(capture_profile_hash=profile.hash);processor=CausalPreprocessor(config)
    data={}
    for split in ['train','validation']:
        chosen=[r for r in rows if r.split==split];x=[]
        for row in chosen:
            values=read_h5_amplitude(resolve_source_path(row,a.data_root));window,_=processor.window(values,timestamps(len(values)),a.window_length,centered=True);x.append(rich_features(window))
        data[split]=(np.asarray(x),np.array([r.label_id for r in chosen]),np.array([r.subject_id for r in chosen]))
    x,y,groups=data['train'];vx,vy,_=data['validation']
    candidates={
        'extra_trees_leaf2':ExtraTreesClassifier(n_estimators=400,min_samples_leaf=2,class_weight='balanced',random_state=42,n_jobs=4),
        'extra_trees_leaf5':ExtraTreesClassifier(n_estimators=400,min_samples_leaf=5,class_weight='balanced',random_state=42,n_jobs=4),
        'random_forest_leaf2':RandomForestClassifier(n_estimators=400,min_samples_leaf=2,class_weight='balanced_subsample',random_state=42,n_jobs=4),
        'random_forest_leaf5':RandomForestClassifier(n_estimators=400,min_samples_leaf=5,class_weight='balanced_subsample',random_state=42,n_jobs=4),
        'svm_rbf_c03':make_pipeline(StandardScaler(),SVC(C=.3,class_weight='balanced',random_state=42)),
        'svm_rbf_c3':make_pipeline(StandardScaler(),SVC(C=3,class_weight='balanced',random_state=42)),
        'svm_rbf_c30':make_pipeline(StandardScaler(),SVC(C=30,class_weight='balanced',random_state=42)),
        'logistic_c03':make_pipeline(StandardScaler(),LogisticRegression(C=.3,class_weight='balanced',max_iter=2000,random_state=42)),
        'hist_gradient_boosting':HistGradientBoostingClassifier(max_iter=100,max_leaf_nodes=7,l2_regularization=5,class_weight='balanced',random_state=42),
    }
    results=[];fitted={};predictions={}
    for name,prototype in candidates.items():
        scores=np.zeros(len(y));folds=[]
        for train,holdout in LeaveOneGroupOut().split(x,y,groups):
            assert not set(groups[train])&set(groups[holdout])
            model=clone(prototype).fit(x[train],y[train]);scores[holdout]=classifier_scores(model,x[holdout]);folds.append({'held_out_subject':str(groups[holdout][0]),'train_count':len(train),'held_out_count':len(holdout)})
        threshold_results=[]
        for threshold in np.arange(.2,.801,.025):
            m=classification_metrics(y,(scores>=threshold).astype(int));rec=m['recall']
            rank=(min(rec['fall']/.88,rec['nonfall']/.8),(rec['fall']+rec['nonfall'])/2)
            threshold_results.append((rank,float(threshold),m))
        rank,threshold,cv=max(threshold_results,key=lambda z:z[0])
        model=clone(prototype).fit(x,y);fitted[name]=model
        started=time.perf_counter();vs=classifier_scores(model,vx);latency=(time.perf_counter()-started)*1000/len(vx)
        predictions[name]=vs
        # Validation is reported for every candidate; selection uses train CV only.
        result={'name':name,'threshold':threshold,'selection_score':list(rank),'train_leave_subject_out':cv,'folds':folds,'validation':classification_metrics(vy,(vs>=threshold).astype(int)),'batch_amortized_classifier_ms':latency}
        results.append(result);print(json.dumps({k:v for k,v in result.items() if k!='folds'}),flush=True)
    chosen=max(results,key=lambda r:tuple(r['selection_score']));model=fitted[chosen['name']]
    artifact={'artifact_type':'srasta_feature_classifier_v1','feature_version':FEATURE_VERSION,'feature_count':x.shape[1],'model':model,'window_length':a.window_length,'threshold':chosen['threshold'],'capture_profile_hash':profile.hash,'preprocess_config_hash':config.hash,'manifest_sha256':manifest_sha256(a.manifest),'score_kind':'uncalibrated classifier score; not confidence in safety'}
    joblib.dump(artifact,a.out_dir/'model.joblib')
    rec=chosen['validation']['recall'];gates={'fall_recall_at_least_0_88':rec['fall']>=.88,'specificity_at_least_0_80':rec['nonfall']>=.8,'event_and_local_hardware_evidence':False}
    report={'selection':'Train subjects only: leave-one-subject-out, choose classifier/threshold by minimum normalized class recall then balanced accuracy; U19 reported after fitting. Prior TCN/RF validation experiments disclosed separately.','selected':chosen,'candidates':results,'deployment_status':'not_deployment_ready','deployment_gate':gates,'locked_test':'not downloaded or evaluated','unavailable':unavailable_event_metrics(),'score_kind':artifact['score_kind']}
    for filename,payload in [('metrics.json',report),('preprocess_config.json',config.to_json()),('capture_profile.json',profile.to_json()),('split_report.json',split_report(rows))]:(a.out_dir/filename).write_text(json.dumps(payload,indent=2))
    (a.out_dir/'MODEL_CARD.md').write_text('# Alternative classifier candidate\n\nUser-authorized comparison with fixed 52-channel input. Selected on grouped train CV, with U19 validation disclosed. No U21 access. Uncalibrated scores, incomplete event and local-domain evidence: not deployment ready.\n')
    print('Selected: '+chosen['name'],flush=True)
if __name__=='__main__':main()
