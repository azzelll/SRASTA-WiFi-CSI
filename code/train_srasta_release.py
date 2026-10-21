#!/usr/bin/env python3
"""Bounded, reproducible TCN selection; test data is opened only after freeze.

These are recording-label proxies, not fall-onset/event/clinical metrics.
No external corpus, locked-test fitting, fake presence label, or source edits.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
import platform
import shutil
import sys
import time
from dataclasses import replace
from pathlib import Path
import numpy as np
from srasta_csi.contract import CaptureProfile
from srasta_csi.data import read_manifest, read_h5_amplitude, resolve_source_path, timestamps, manifest_sha256, split_report
from srasta_csi.metrics import classification_metrics, unavailable_event_metrics
from srasta_csi.model import TFLiteModel, export_full_int8, parity_report
from srasta_csi.preprocess import CausalPreprocessor, PreprocessConfig
from srasta_csi.development import select_threshold

PROTOCOL = [
    {"name":"tcn_250", "length":250, "channels":32, "dilations":[1,2,4,8]},
    {"name":"tcn_500", "length":500, "channels":32, "dilations":[1,2,4,8,16]},
]
WIDE_PROTOCOL = [
    {"name":"tcn_500_wide32", "length":500, "channels":32, "kernel":5, "dilations":[1,2,4,8,16,32], "batch_norm":True},
    {"name":"tcn_500_wide48", "length":500, "channels":48, "kernel":5, "dilations":[1,2,4,8,16,32], "batch_norm":True},
]
SEGMENTED_PROTOCOL = [
    {"name":"tcn_250_segments", "length":250, "channels":24, "kernel":5, "dilations":[1,2,4,8], "segments":10, "l2":1e-5, "dropout":.05, "learning_rate":1e-3},
    {"name":"tcn_500_segments", "length":500, "channels":24, "kernel":5, "dilations":[1,2,4,8,16], "segments":10, "l2":1e-5, "dropout":.05, "learning_rate":1e-3},
]
DIFFERENCE_PROTOCOL = [
    {"name":"tcn_500_difference", "length":500, "channels":24, "kernel":5,
     "dilations":[1,2,4,8,16], "difference_input":True, "l2":1e-4,
     "dropout":.15, "learning_rate":3e-4},
]
MOMENT_PROTOCOL = [
    {"name":"tcn_500_moments", "length":500, "channels":24, "kernel":5,
     "dilations":[1,2,4,8,16], "moment_head":True, "l2":1e-4,
     "dropout":.15, "learning_rate":3e-4},
]
COMPACT_PROTOCOL = [
    {"name":"tcn_500_compact", "length":500, "channels":24, "kernel":5,
     "dilations":[1,2,4,8,16], "l2":1e-4, "dropout":.1},
]

def save(path, value):
    Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+"\n")

def read_processed(rows, split, data_root, processor):
    selected=[row for row in rows if row.split==split]
    values=[processor.transform(read_h5_amplitude(resolve_source_path(row,data_root)),timestamps(500)) for row in selected]
    if any(value.shape!=(500,52) for value in values):
        raise ValueError("release protocol requires actual 500-frame, 52-feature recordings")
    return np.stack(values).astype(np.float32),np.asarray([row.label_id for row in selected]),[row.sample_id for row in selected]

def crop(values,length):
    start=(values.shape[1]-length)//2
    if start<0: raise ValueError("no padding is permitted")
    return values[:,start:start+length].copy()

def threshold_report(y,p,recall_target=.8,specificity_target=.8):
    return select_threshold(y,p,recall_target,specificity_target)

def build(spec,x_train,seed,classes=2):
    import tensorflow as tf
    tf.keras.utils.set_random_seed(seed)
    inputs=tf.keras.Input((spec['length'],52),name='amplitude_52')
    # Shared causal preprocessing already normalizes gain drift and bounds
    # pathological near-zero baselines; avoid a high-gain quantized affine step.
    x=inputs
    if spec.get('difference_input'):
        # Measured adjacent samples only; no padding or change to the 52
        # physical input positions. Keep both level and temporal derivative.
        current=inputs[:,1:,:]
        difference=tf.keras.layers.Subtract(name='adjacent_difference')([current,inputs[:,:-1,:]])
        x=tf.keras.layers.Concatenate(name='level_and_difference')([current,difference])
    if spec.get('train_standardization'):
        # Adapt only primary train rows. This affine transform is serialized in
        # the model, so exported edge inference applies the identical transform.
        normalization=tf.keras.layers.Normalization(axis=-1,name='train_standardization')
        normalization.adapt(x_train)
        x=normalization(x)
    x=tf.keras.layers.Conv1D(spec['channels'],1,padding='causal',activation='relu',name='projection')(x)
    for d in spec['dilations']:
        skip=x
        for suffix in ('a','b'):
            x=tf.keras.layers.Conv1D(spec['channels'],spec.get('kernel',3),padding='causal',dilation_rate=d,activation=None if spec.get('batch_norm') else 'relu',kernel_regularizer=tf.keras.regularizers.l2(spec.get('l2',1e-4)),name=f'd{d}_{suffix}')(x)
            if spec.get('batch_norm'):
                x=tf.keras.layers.BatchNormalization(name=f'd{d}_{suffix}_bn')(x)
                x=tf.keras.layers.Activation('relu')(x)
        x=tf.keras.layers.Add()([skip,x]);x=tf.keras.layers.Activation('relu')(x)
        x=tf.keras.layers.SpatialDropout1D(spec.get('dropout',.10))(x)
    pooled=tf.keras.layers.Concatenate()([tf.keras.layers.GlobalAveragePooling1D()(x),tf.keras.layers.GlobalMaxPooling1D()(x)])
    if spec.get('moment_head'):
        # Preserve temporal intensity and extrema next to the learned encoder.
        # Every statistic is measured on the same fixed 52 input positions.
        squares=tf.keras.layers.Multiply(name='squared_amplitude')([inputs,inputs])
        moments=tf.keras.layers.Concatenate(name='temporal_moments')([
            tf.keras.layers.GlobalAveragePooling1D()(inputs),
            tf.keras.layers.GlobalAveragePooling1D()(squares),
            tf.keras.layers.GlobalMaxPooling1D()(inputs),
            tf.keras.layers.GlobalMaxPooling1D()(tf.keras.layers.Rescaling(-1.)(inputs)),
        ])
        moments=tf.keras.layers.Dense(16,activation='relu',kernel_regularizer=tf.keras.regularizers.l2(1e-3),name='moment_projection')(moments)
        pooled=tf.keras.layers.Concatenate()([pooled,moments])
    if spec.get('segments'):
        temporal=tf.keras.layers.AveragePooling1D(spec['length']//spec['segments'])(x)
        temporal=tf.keras.layers.Flatten()(temporal)
        pooled=tf.keras.layers.Concatenate()([pooled,temporal])
        pooled=tf.keras.layers.Dense(24,activation='relu')(pooled)
        pooled=tf.keras.layers.Dropout(.15)(pooled)
    outputs=tf.keras.layers.Dense(classes,activation='softmax',name='fall_probability' if classes==2 else 'source_activity')(pooled)
    return tf.keras.Model(inputs,outputs,name=spec['name'])

def load_pretraining(data_root,processor):
    """Source-train representation learning; source test is never opened."""
    from scipy.io import loadmat
    manifest=data_root/'external/esp_fi_har/manifest.csv'
    with manifest.open(newline='') as stream:
        rows=[row for row in csv.DictReader(stream) if row['source_partition']=='train' and row['pretraining_train_eligible']=='yes' and row['main_test_eligible']=='no']
    if not rows: raise ValueError('no eligible ESP-Fi source-train rows')
    actions=sorted({row['action'] for row in rows});values=[]
    for row in rows:
        source=(data_root.parent/row['source_path']).resolve()
        if not source.is_relative_to((data_root/'external/esp_fi_har').resolve()):
            raise ValueError('external manifest source escaped its corpus')
        amplitude=np.asarray(loadmat(source)['CSIamp'],dtype=np.float32)
        if amplitude.shape!=(950,52): raise ValueError('ESP-Fi shape must be actual [950,52]')
        values.append(processor.transform(amplitude,timestamps(len(amplitude))))
    provenance={'source':'ESP-Fi HAR; Wen et al. (2026), CC BY 4.0','hardware':'ESP32-C3; different capture domain','manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest(),'source_partition':'train only','recordings':len(rows),'actions':actions,'timestamps':'synthetic nominal 100 Hz, not live packet timing','crop':'one centered window per source recording','use':'encoder pretraining only; source test not opened; no SRASTA metric/threshold/INT8 representative rows'}
    return np.stack(values),np.asarray([actions.index(row['action']) for row in rows]),provenance

def evaluate_frozen(root,rows,data_root,processor):
    target=root/'selected';report=target/'locked_test_report.json'
    if report.exists(): raise FileExistsError('locked test has already been reported; do not tune on it')
    frozen=json.loads((target/'frozen.json').read_text())
    digest=hashlib.sha256((target/'model.tflite').read_bytes()).hexdigest()
    if digest!=frozen['model_sha256']:raise ValueError('model changed after freeze')
    processor=CausalPreprocessor(PreprocessConfig.from_json(json.loads((target/'preprocess_config.json').read_text())))
    values,y,ids=read_processed(rows,'test',data_root,processor)
    windows=crop(values,frozen['window_length']);runtime=TFLiteModel(target/'model.tflite')
    p=np.asarray([runtime.probability(window) for window in windows])
    metrics=classification_metrics(y,(p>=frozen['threshold']).astype(np.int64))
    save(report,{"model_sha256":digest,"threshold":frozen['threshold'],"evaluation":"one frozen-model recording-level proxy; not final local/event validation","classification":metrics,"recordings":len(ids),"manifest_sha256":manifest_sha256(data_root/'curated/esp32_s3_fall_v1/manifest.csv'),"test_used_for_fitting":False,"unavailable":unavailable_event_metrics()})
    print(json.dumps({"locked_test_proxy":metrics,"report":str(report)},indent=2),flush=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root',type=Path,default=Path('data'))
    parser.add_argument('--out-dir',type=Path,required=True)
    parser.add_argument('--epochs',type=int,default=60)
    parser.add_argument('--seed',type=int,default=42)
    parser.add_argument('--recall-target',type=float,default=.8)
    parser.add_argument('--specificity-target',type=float,default=.8)
    parser.add_argument('--evaluate-frozen',action='store_true')
    parser.add_argument('--pretrain-esp-fi',action='store_true')
    parser.add_argument('--pretrained-motion',type=Path,help='Grouped ESP-Fi research encoder directory')
    parser.add_argument('--hampel-history',choices=('filtered','raw'),default='filtered')
    parser.add_argument('--normalization-mode',choices=('relative','log_difference'),default='relative')
    parser.add_argument('--architecture',choices=('standard','wide','segmented','difference','moments','compact'),default='standard')
    parser.add_argument('--train-standardization',action='store_true')
    args=parser.parse_args()
    if not 0 < args.recall_target <= 1 or not 0 < args.specificity_target <= 1:
        parser.error('recall/specificity targets must lie in (0,1]')
    if args.architecture == 'difference' and args.train_standardization:
        parser.error('difference input and train standardization are separate experiment protocols')
    if args.pretrained_motion and (args.pretrain_esp_fi or args.architecture != 'compact'):
        parser.error('grouped pretrained motion requires compact architecture and a separate external-pretraining mode')
    os.environ.setdefault('TF_DETERMINISTIC_OPS','1')
    os.environ.setdefault('TF_NUM_INTRAOP_THREADS','4');os.environ.setdefault('TF_NUM_INTEROP_THREADS','2')
    import tensorflow as tf
    rows=read_manifest(args.data_root/'curated/esp32_s3_fall_v1/manifest.csv')
    profile=CaptureProfile();config=PreprocessConfig(capture_profile_hash=profile.hash,normalized_clip=2.0,hampel_history=args.hampel_history,normalization_mode=args.normalization_mode);processor=CausalPreprocessor(config)
    if args.evaluate_frozen:
        evaluate_frozen(args.out_dir,rows,args.data_root,processor);return
    if args.epochs<1:raise ValueError('epochs must be positive')
    if args.out_dir.exists():raise FileExistsError('refusing to overwrite release artifacts')
    args.out_dir.mkdir(parents=True)
    protocol=[{**spec,**({'train_standardization':True} if args.train_standardization else {})} for spec in {'standard':PROTOCOL,'wide':WIDE_PROTOCOL,'segmented':SEGMENTED_PROTOCOL,'difference':DIFFERENCE_PROTOCOL,'moments':MOMENT_PROTOCOL,'compact':COMPACT_PROTOCOL}[args.architecture]]
    save(args.out_dir/'selection_protocol.json',{"candidates":protocol,"seed":args.seed,"epochs_max":args.epochs,"threshold_grid":"all distinct probability boundaries","targets":{"recall":args.recall_target,"specificity":args.specificity_target},"selection":"both recall/specificity gates, then minimum normalized gate, then macro F1","test_status":"locked; not loaded","classes":["nonfall","fall"],"product_missing_labels":["no_person","inactive"],"window_labels":"recording-label proxy; no released onset annotation","external_data":"ESP-Fi source-train encoder pretraining" if args.pretrain_esp_fi or args.pretrained_motion else "not used","pretraining_epochs":30 if args.pretrain_esp_fi else 0,"pretrained_motion":str(args.pretrained_motion) if args.pretrained_motion else None,"preprocess":config.to_json(),"source_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),"command":sys.argv,"versions":{"python":platform.python_version(),"tensorflow":tf.__version__,"numpy":np.__version__}})
    print('Loading train and validation only; locked test is not opened.',flush=True)
    train,y_train,_=read_processed(rows,'train',args.data_root,processor)
    validation,y_validation,_=read_processed(rows,'validation',args.data_root,processor)
    external=None
    if args.pretrain_esp_fi:
        external=load_pretraining(args.data_root,processor)
        save(args.out_dir/'pretraining_provenance.json',external[2])
    grouped_encoder=None
    grouped_provenance=None
    if args.pretrained_motion:
        grouped_provenance=json.loads((args.pretrained_motion/'protocol.json').read_text())
        source_config=PreprocessConfig.from_json(json.loads((args.pretrained_motion/'preprocess_config.json').read_text()))
        numerical_source_config=replace(source_config,capture_profile_hash=config.capture_profile_hash)
        if grouped_provenance.get('source_test_opened') is not False or grouped_provenance.get('hardware') != 'ESP32-C3; different capture domain' or numerical_source_config.hash != config.hash:
            raise ValueError('pretrained encoder provenance/configuration mismatch')
        if len(grouped_provenance.get('classes',[])) != 7 or set(grouped_provenance['train_subjects']) & set(grouped_provenance['validation_subjects']):
            raise ValueError('pretrained activity labels/subject split invalid')
        grouped_encoder=tf.keras.models.load_model(args.pretrained_motion/'model.keras')
        grouped_provenance={**grouped_provenance,'model_sha256':hashlib.sha256((args.pretrained_motion/'model.keras').read_bytes()).hexdigest(),'use':'encoder transfer only; source head discarded; primary-only fitting/representative quantization'}
        save(args.out_dir/'pretraining_provenance.json',grouped_provenance)
    results=[]
    for spec in protocol:
        tf.keras.backend.clear_session();path=args.out_dir/spec['name'];path.mkdir()
        x_train=crop(train,spec['length']);x_validation=crop(validation,spec['length'])
        encoder=None
        if grouped_encoder is not None:
            encoder=grouped_encoder
        if external is not None:
            source_values,source_labels,provenance=external
            encoder=build(spec,x_train,args.seed,classes=len(provenance['actions']))
            encoder.compile(optimizer=tf.keras.optimizers.Adam(3e-4,clipnorm=1),loss='sparse_categorical_crossentropy',metrics=['accuracy'])
            print('Pretraining '+spec['name']+' on eligible ESP-Fi source-train rows only.',flush=True)
            source_history=encoder.fit(crop(source_values,spec['length']),source_labels,epochs=30,batch_size=16,verbose=2)
            save(path/'pretraining_history.json',source_history.history)
        model=build(spec,x_train,args.seed)
        if encoder is not None:
            copied=[]
            for layer in model.layers:
                if layer.weights and layer.name!='fall_probability':
                    layer.set_weights(encoder.get_layer(layer.name).get_weights());copied.append(layer.name)
            save(path/'pretraining_transfer.json',{'copied_encoder_layers':copied,'source_head_discarded':True,'provenance':external[2] if external is not None else grouped_provenance})
        counts=np.bincount(y_train,minlength=2)
        if np.any(counts==0):raise ValueError('both classes required')
        weights={i:float(len(y_train)/(2*counts[i])) for i in range(2)}
        model.compile(optimizer=tf.keras.optimizers.Adam(spec.get('learning_rate',3e-4),clipnorm=1),loss='sparse_categorical_crossentropy',metrics=['accuracy'])
        print('Training '+spec['name'],flush=True)
        history=model.fit(x_train,y_train,validation_data=(x_validation,y_validation),epochs=args.epochs,batch_size=16,class_weight=weights,callbacks=[tf.keras.callbacks.EarlyStopping(monitor='val_loss',patience=12,restore_best_weights=True),tf.keras.callbacks.ReduceLROnPlateau(monitor='val_loss',patience=5,factor=.5,min_lr=1e-5)],verbose=2)
        save(path/'history.json',history.history);model.save(path/'model.keras')
        rng=np.random.default_rng(args.seed);indices=rng.choice(len(x_train),min(256,len(x_train)),replace=False)
        export_full_int8(model,x_train[indices],path/'model.tflite')
        runtime=TFLiteModel(path/'model.tflite');parity=parity_report(model,runtime,x_validation)
        p=np.asarray([runtime.probability(window) for window in x_validation])
        selected=threshold_report(y_validation,p,args.recall_target,args.specificity_target)
        metrics={**selected,"parity":parity,"model_size_bytes":(path/'model.tflite').stat().st_size,"evaluation":"subject-disjoint validation; recording-label centered-window proxy","event_local_four_class_status":"unavailable; deployment gate incomplete","unavailable":unavailable_event_metrics()}
        save(path/'metrics.json',metrics)
        save(path/'training_config.json',{"window_length":spec['length'],"seed":args.seed,"epochs_completed":len(history.history['loss']),"architecture":spec,"representative_dataset":"curated ESP32-S3 train split only","representative_window_count":len(indices),"manifest_sha256":manifest_sha256(args.data_root/'curated/esp32_s3_fall_v1/manifest.csv'),"classes":["nonfall","fall"],"threshold":selected['threshold']})
        save(path/'preprocess_config.json',config.to_json());save(path/'capture_profile.json',profile.to_json());save(path/'split_report.json',split_report(rows))
        results.append({"name":spec['name'],**metrics})
        print(json.dumps(results[-1],indent=2),flush=True)
    def score(row):
        recalls=row['classification']['recall'];parity=row['parity']['status']=='passed'
        return (parity,row['proxy_gates_pass'],min(recalls['fall']/args.recall_target,recalls['nonfall']/args.specificity_target),row['classification']['macro_f1'])
    eligible=[row for row in results if row['parity']['status']=='passed']
    if not eligible:
        save(args.out_dir/'selection_report.json',{'candidates':results,'selected':None,'reason':'no candidate passed INT8 parity'})
        raise RuntimeError('no candidate passed INT8 parity; release not frozen')
    chosen=max(eligible,key=score);destination=args.out_dir/'selected';shutil.copytree(args.out_dir/chosen['name'],destination)
    training=json.loads((destination/'training_config.json').read_text())
    frozen={"model_sha256":hashlib.sha256((destination/'model.tflite').read_bytes()).hexdigest(),"threshold":chosen['threshold'],"window_length":training['window_length'],"selected_candidate":chosen['name'],"frozen_at_s":time.time(),"test_status":"not_opened","software_ready":chosen['parity']['status']=='passed' and chosen['model_size_bytes']<=1_000_000 and chosen['parity']['mean_tflite_inference_ms']<=100,"deployment_ready":False,"remaining_gates":["independent local ESP32-S3 event/FAR evidence","Pi latency and live capture profile","presence/inactive four-class labels","breathing/camera validation"]}
    save(destination/'frozen.json',frozen);save(args.out_dir/'selection_report.json',{"candidates":results,"selected":chosen['name']})
    (destination/'MODEL_CARD.md').write_text('# SRASTA TCN-Lite INT8\n\nA reproducible two-class fall-path engineering model selected on subject-disjoint validation.\n\nSoftware readiness is recorded in frozen.json; the validation proxy targets are separately recorded in metrics.json. Full product deployment readiness remains false until the stated accuracy, independent local/event/FAR, four-class presence/inactivity, and Pi gates are met.\n\nShared causal preprocessing bounds pathological baseline values without changing the fixed 52 input positions. Primary train data fitted binary weights and representative quantization. Optional external source-train encoder pretraining is disclosed in pretraining_transfer.json; its activity head is discarded and is not evidence of SRASTA four-class readiness. Validation selected the threshold/candidate. Locked test is opened only by the separate --evaluate-frozen command. Existing recordings lack verified onset and continuous negative exposure, so classification here is a recording-label proxy.\n')
    print(json.dumps({"selected":str(destination),**frozen},indent=2),flush=True)

if __name__=='__main__':main()
