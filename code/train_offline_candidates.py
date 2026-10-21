#!/usr/bin/env python3
"""Bounded offline experiments; never read official test/local capture payloads."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

import joblib
import numpy as np
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.linear_model import LogisticRegression

from srasta_csi.development import load_development, grouped_folds, select_threshold
from srasta_csi.public_occupancy import (LAYOUTS, balanced_sample, source_rows,
                                       select_protocol, load_amplitude, invariant_features, INVARIANT_NAMES)
from srasta_csi.research_features import temporal_features, FEATURE_NAMES

ARTIFACT = "srasta_offline_native_research_v1"
FAMILIES = ("rf", "extra_trees", "hist_gradient")


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def classifier(family, seed=42):
    if family == "rf":
        return RandomForestClassifier(n_estimators=300, min_samples_leaf=5,
            class_weight="balanced", random_state=seed, n_jobs=2)
    if family == "extra_trees":
        return ExtraTreesClassifier(n_estimators=400, min_samples_leaf=3,
            class_weight="balanced", random_state=seed, n_jobs=2)
    if family == "hist_gradient":
        return HistGradientBoostingClassifier(max_iter=150, max_leaf_nodes=15,
            l2_regularization=5., class_weight="balanced", early_stopping=False, random_state=seed)
    raise ValueError("unknown preregistered family")


def report(y, predicted, classes):
    cm = confusion_matrix(y, predicted, labels=range(len(classes)))
    recalls = np.divide(cm.diagonal(), cm.sum(axis=1), out=np.zeros(len(classes)), where=cm.sum(axis=1)>0)
    return {"classification": classification_report(y, predicted, labels=range(len(classes)),
                target_names=classes, output_dict=True, zero_division=0),
            "confusion_matrix": cm.tolist(), "minimum_class_recall": float(min(recalls)),
            "balanced_accuracy": float(recalls.mean()),
            "per_class_recall": dict(zip(classes, map(float, recalls)))}


def rank(item):
    m = item["metrics"]
    return m["minimum_class_recall"], m["balanced_accuracy"], m["classification"]["macro avg"]["f1-score"]


def export_model(path, model, classes, feature, **metadata):
    payload = {"artifact_type": ARTIFACT, "model": model, "classes": classes,
        "feature": feature, "feature_names": FEATURE_NAMES if feature == "temporal" else INVARIANT_NAMES,
        "research_only": True, "local_deployment_ready": False, **metadata}
    joblib.dump(payload, path, compress=3)


def audit(root, out):
    rows = {task: source_rows(root, task)[0] for task in ("BreathingDetection", "HumanActivityRecognition")}
    counts = {}
    for task, rr in rows.items():
        counts[task] = {label: {"recordings": len(rs), "subjects": sorted({r["user"] for r in rs}),
             "environments": sorted({r["environment"] for r in rs}),
             "devices": sorted({r["device"] for r in rs}), "native_channels": sorted({int(r["num_sub"]) for r in rs})}
             for label in sorted({r["label"] for r in rr})
             for rs in [[r for r in rr if r["label"] == label]]}
    normal = counts["HumanActivityRecognition"]["seated-breathing"]
    sleep = counts["BreathingDetection"]["sleep"]
    findings = {"source_train_only": True, "metadata_only": True, "counts": counts,
        "normal_proxy": {"source_label": "seated-breathing", "product_label": "normal",
            "meaning": "performed seated breathing activity; proxy for awake, not reference-confirmed normal respiration",
            "physiological_normality_verified": False},
        "normal_sleep_environment_overlap": sorted(set(normal["environments"]) & set(sleep["environments"])),
        "normal_sleep_device_overlap": sorted(set(normal["devices"]) & set(sleep["devices"])),
        "normal_sleep_device_overlap_casefold": sorted({d.casefold() for d in normal["devices"]} &
                                                       {d.casefold() for d in sleep["devices"]}),
        "device_overlap_note": "Raw names are case-sensitive; device-name overlap alone does not establish a shared capture domain",
        "three_classes_in_same_capture_domain": False,
        "normal_class_confounded_with_source_task": True,
        "local_deployment_ready": False, "independent_test": False,
        "source_metadata_hashes": {task: digest(root/task/"metadata/sample_metadata.csv") for task in rows},
        "references": ["https://arxiv.org/html/2505.21866v2#A6", "https://arxiv.org/html/2505.21866v2#A9"]}
    save(out/"label_audit.json", findings)
    return findings


def occupancy(args):
    selected = select_protocol(args.source, args.cap)
    har, _ = source_rows(args.source, "HumanActivityRecognition")
    for split, part in selected.items():
        users = {"U05"} if split == "validation" else {"U01", "U03", "U04", "U06"}
        part["normal"] = balanced_sample([r for r in har if r["label"] == "seated-breathing" and r["user"] in users], args.cap, "normal-proxy-v1:")
    people = [{r["user"] for rs in part.values() for r in rs} for part in selected.values()]
    if people[0] & people[1]:
        raise ValueError("cross-task subject leakage")
    protocol = {"stage": "public_occupancy", "seed": 42, "cap": args.cap, "layouts": LAYOUTS,
        "features": ["invariant", "temporal"], "families": FAMILIES,
        "binary_threshold": .5, "three_class_decision": "argmax; no fitted cutoff",
        "selection": "development validation minimum class recall, balanced accuracy, macro F1",
        "subject_split": dict(zip(selected, map(sorted, people))),
        "source_validation_test_payload_opened": False, "local_capture_payload_opened": False,
        "independent_test": False, "validation_historically_inspected": True,
        "normal_proxy_only": True, "local_deployment_ready": False,
        "source_code_sha256": digest(Path(__file__)),
        "feature_code_sha256": digest(Path(__file__).parent/"srasta_csi/research_features.py")}
    save(args.out_dir/"protocol.json", protocol)
    snapshot=args.out_dir/'source_snapshot'; snapshot.mkdir()
    for p in (Path(__file__),Path(__file__).parent/'srasta_csi/research_features.py'):
        (snapshot/p.name).write_bytes(p.read_bytes())
    audit(args.source, args.out_dir)
    allowed = {t: source_rows(args.source, t)[1] for t in ("BreathingDetection", "HumanActivityRecognition")}
    arrays, before, excluded, used = {}, {}, [], {}
    cache = {}
    for split, part in selected.items():
        arrays[split], used[split] = {}, {}
        for stratum, rows in part.items():
            result = {(layout, kind): [] for layout in LAYOUTS for kind in ("invariant", "temporal")}
            eligible = []
            for i, r in enumerate(rows):
                key = (r["task"], r["id"])
                if key not in cache:
                    path = args.source/r["task"]/r["file_path"]
                    before[str(path)] = digest(path)
                    x, rate = load_amplitude(args.source, r, allowed[r["task"]], "declared_axes")
                    if not np.any(x):
                        excluded.append({"id": r["id"], "task": r["task"], "reason": "all_zero", "split": split, "stratum": stratum})
                        continue
                    cache[key] = {}
                    for layout in LAYOUTS:
                        native = x if layout == "declared_axes" else x.T.reshape(x.shape)
                        cache[key][layout,"invariant"] = invariant_features(native, rate)
                        cache[key][layout,"temporal"] = temporal_features(native, rate)
                for k in result:
                    result[k].append(cache[key][k])
                eligible.append(r)
                if (i+1) % 500 == 0:
                    print(f"features {split}/{stratum} {i+1}/{len(rows)}", flush=True)
            arrays[split][stratum] = {k: np.stack(v) for k,v in result.items()}
            used[split][stratum] = eligible
    save(args.out_dir/"eligible_metadata.json", used)
    save(args.out_dir/"excluded.json", excluded)
    hashes = [{before[str(args.source/r["task"]/r["file_path"])] for rs in part.values() for r in rs} for part in used.values()]
    if hashes[0] & hashes[1]:
        raise ValueError("identical source payload across partitions")
    output = {}
    specs = {"breathing": (["empty","sleep"], ["empty","sleep"], [0,1]),
             "presence": (["empty","present"], ["empty","sleep","awake"], [0,1,1]),
             "breathing_three": (["empty","sleep","normal"], ["empty","sleep","normal"], [0,1,2])}
    for task,(classes,strata,labels) in specs.items():
        folder=args.out_dir/task; folder.mkdir()
        trials=[]
        for layout in LAYOUTS:
            for kind in ("invariant", "temporal"):
                xy={s:(np.concatenate([arrays[s][v][layout,kind] for v in strata]),
                       np.concatenate([np.full(len(used[s][v]),label) for v,label in zip(strata,labels)])) for s in selected}
                for family in FAMILIES:
                    name=f"{layout}-{kind}-{family}"
                    started=time.perf_counter(); model=classifier(family).fit(*xy["train"])
                    x,y=xy["validation"]; probabilities=model.predict_proba(x); prediction=probabilities.argmax(axis=1)
                    m=report(y,prediction,classes)
                    np.savez_compressed(folder/(name+"-predictions.npz"),y=y,probabilities=probabilities)
                    export_model(folder/(name+".joblib"),model,classes,kind,layout=layout,task=task,
                        normal_proxy_only=task=="breathing_three",threshold=.5)
                    trial={"candidate":name,"metrics":m,"seconds":time.perf_counter()-started,
                        "strata_recall":{v:float((prediction[sum(len(used['validation'][a]) for a in strata[:j]):sum(len(used['validation'][a]) for a in strata[:j+1])]==labels[j]).mean()) for j,v in enumerate(strata)}}
                    trials.append(trial); print(task,name,m["per_class_recall"],flush=True)
        # Confound diagnostic: metadata only, never used by the CSI model.
        metadata={s:([[r['task'],r['device'],r['num_sub']] for v in strata for r in used[s][v]],
                       np.concatenate([np.full(len(used[s][v]),label) for v,label in zip(strata,labels)])) for s in selected}
        nuisance=make_pipeline(OneHotEncoder(handle_unknown="ignore"),LogisticRegression(max_iter=500,class_weight="balanced"))
        nuisance.fit(*metadata['train'])
        diagnostic=report(metadata['validation'][1],nuisance.predict(metadata['validation'][0]),classes)
        chosen=max(trials,key=rank)
        chosen_path=folder/(chosen["candidate"]+".joblib")
        (folder/"model.joblib").write_bytes(chosen_path.read_bytes())
        output[task]={"selected":chosen,"candidates":trials,"metadata_only_diagnostic":diagnostic,
            "counts":{s:{v:len(used[s][v]) for v in strata} for s in selected},
            "model_sha256":digest(folder/"model.joblib"),"independent_test":False,"local_deployment_ready":False}
        save(args.out_dir/"metrics.json",output)
    changed=[p for p,h in before.items() if digest(Path(p))!=h]
    save(args.out_dir/"source_integrity.json",{"sha256":before,"changed":changed,"cross_partition_duplicates":0})
    if changed: raise ValueError("source changed")


def fall(args):
    protocol={"stage":"fall", "families":FAMILIES,"features":"native relative multiscale temporal",
        "seeds":[42,43,44],"folds":"fit four train subjects; calibrate next subject; evaluate held-out subject",
        "candidate_selection":"mean outer minimum recall and balanced accuracy across seeds; no U19 tuning",
        "final_threshold":"train OOF seed42", "test_payload_opened":False,"local_capture_opened":False,
        "source_validation_status":"historically inspected development only",
        "source_code_sha256":digest(Path(__file__)),"features_sha256":digest(Path(__file__).parent/"srasta_csi/research_features.py")}
    save(args.out_dir/"protocol.json",protocol)
    snapshot=args.out_dir/'source_snapshot'; snapshot.mkdir()
    for p in (Path(__file__),Path(__file__).parent/'srasta_csi/research_features.py'):
        (snapshot/p.name).write_bytes(p.read_bytes())
    rows,raw=load_development(args.data_root,"train")
    y=np.array([r.label_id for r in rows]); groups=np.array([r.subject_id for r in rows])
    x=np.stack([temporal_features(v,100.) for v in raw]); candidates=[]
    for family in FAMILIES:
        runs=[]
        for seed in protocol['seeds']:
            p=np.zeros(len(y)); predicted=np.zeros(len(y),dtype=int); folds=[]
            for f in grouped_folds(groups):
                fit,cal,ev=(f[k] for k in ('fit','calibrate','evaluate'))
                model=classifier(family,seed).fit(x[fit],y[fit]); cutoff=select_threshold(y[cal],model.predict_proba(x[cal])[:,1])['threshold']
                p[ev]=model.predict_proba(x[ev])[:,1]; predicted[ev]=p[ev]>=cutoff
                folds.append({'evaluation_subject':f['held_out_subject'],'calibration_subject':f['calibration_subject'],
                    'fit_subjects':f['fit_subjects'],'threshold':cutoff})
            runs.append({'seed':seed,'metrics':report(y,predicted,['nonfall','fall']),'folds':folds})
            np.savez_compressed(args.out_dir/f'{family}-{seed}-oof.npz',y=y,probabilities=p,prediction=predicted)
            print('fall',family,seed,runs[-1]['metrics']['per_class_recall'],flush=True)
        score={'minimum_class_recall':float(np.mean([r['metrics']['minimum_class_recall'] for r in runs])),
               'balanced_accuracy':float(np.mean([r['metrics']['balanced_accuracy'] for r in runs])),
               'classification':{'macro avg':{'f1-score':float(np.mean([r['metrics']['classification']['macro avg']['f1-score'] for r in runs]))}}}
        candidates.append({'candidate':family,'metrics':score,'runs':runs})
    chosen=max(candidates,key=rank); family=chosen['candidate']
    with np.load(args.out_dir/f'{family}-42-oof.npz') as a: cutoff=select_threshold(y,a['probabilities'])['threshold']
    model=classifier(family).fit(x,y)
    export_model(args.out_dir/'model.joblib',model,['nonfall','fall'],'temporal',task='fall',threshold=cutoff,rate_hz=100.)
    save(args.out_dir/'selection_before_validation.json',{'selected':chosen,'candidates':candidates,'threshold':cutoff})
    # All baseline choices/weights/thresholds above are frozen before U19 load.
    vr,values=load_development(args.data_root,'validation'); vy=np.array([r.label_id for r in vr])
    probabilities=model.predict_proba(np.stack([temporal_features(v,100.) for v in values]))[:,1]
    m=report(vy,(probabilities>=cutoff).astype(int),['nonfall','fall'])
    np.savez_compressed(args.out_dir/'validation_predictions.npz',y=vy,probabilities=probabilities)
    save(args.out_dir/'metrics.json',{'selected':family,'threshold':cutoff,'development_validation':m,
        'candidates':candidates,'test_payload_opened':False,'independent_test':False,'local_deployment_ready':False,
        'joint_80_pass':m['minimum_class_recall']>=.8,'model_sha256':digest(args.out_dir/'model.joblib')})
    print('fall validation',m['per_class_recall'],flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--task',choices=['audit','occupancy','fall'],required=True)
    p.add_argument('--source',type=Path,default=Path('data/csi-bench'))
    p.add_argument('--data-root',type=Path,default=Path('data'))
    p.add_argument('--out-dir',type=Path,required=True)
    p.add_argument('--cap',type=int,default=2000)
    args=p.parse_args()
    if args.cap<1:p.error('positive cap required')
    args.out_dir.mkdir(parents=True,exist_ok=False)
    {'audit':lambda a:audit(a.source,a.out_dir),'occupancy':occupancy,'fall':fall}[args.task](args)


if __name__=='__main__':main()
