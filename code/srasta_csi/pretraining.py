"""Explicit cross-device representation pretraining using source-train ESP-Fi HAR."""
import hashlib,json
from pathlib import Path
import numpy as np
from scipy.io import loadmat
from .preprocess import CausalPreprocessor
from .data import timestamps

def pretrain_esp_fi(target_model,root,processor,*,epochs=20):
    import tensorflow as tf
    root=Path(root);manifest_path=root/'manifest.json';manifest=json.loads(manifest_path.read_text())
    if manifest.get('license')!='CC BY 4.0' or manifest.get('source_test_downloaded')!=0:
        raise ValueError('external source provenance not accepted')
    rows=manifest['records']
    if not rows or any(r['source_split']!='train' or not r['source_path'].startswith('train_amp/') for r in rows):
        raise ValueError('pretraining only accepts source-train records')
    labels=sorted({r['label'] for r in rows});subjects=sorted({r['subject'] for r in rows})
    if len(labels)!=7 or len(subjects)<3:raise ValueError('seven source classes and grouped holdout required')
    x=[];y=[];groups=[]
    for row in rows:
        path=(root/row['source_path']).resolve()
        if root.resolve() not in path.parents:raise ValueError('source path escape')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('source recording changed')
        payload=loadmat(path);values=np.asarray(payload.get('CSIamp'),dtype=np.float32)
        if values.shape!=(950,52) or not np.isfinite(values).all():raise ValueError('external shape must be exactly [950,52]')
        # Source is amplitude-only. This is a disclosed temporal representation
        # adapter, not raw SRASTA packet validation or evidence of capture parity.
        window,_=processor.window(values,timestamps(len(values)),target_model.input_shape[1],centered=True)
        x.append(window);y.append(labels.index(row['label']));groups.append(row['subject'])
    x=np.asarray(x);y=np.asarray(y);groups=np.asarray(groups);holdout=subjects[-1];train=groups!=holdout;validation=~train
    head=tf.keras.layers.Dense(7,activation='softmax',name='external_har_head')(target_model.get_layer('temporal_average').output)
    source_model=tf.keras.Model(target_model.input,head)
    source_model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=.001),loss='sparse_categorical_crossentropy',metrics=['accuracy'])
    history=source_model.fit(x[train],y[train],validation_data=(x[validation],y[validation]),epochs=epochs,batch_size=16,callbacks=[tf.keras.callbacks.EarlyStopping(monitor='val_loss',patience=4,restore_best_weights=True)],verbose=2)
    return {'source':manifest['source'],'commit':manifest['commit'],'manifest_sha256':hashlib.sha256(manifest_path.read_bytes()).hexdigest(),'license':manifest['license'],'attribution':manifest['attribution'],'hardware_domain':'ESP32-C3 amplitude-only, not equivalent to SRASTA S3 raw capture','source_partition':'train_amp only','source_test_used':False,'source_subject_holdout':holdout,'source_fit_count':int(train.sum()),'source_holdout_count':int(validation.sum()),'epochs_completed':len(history.history['loss']),'classes':labels,'window_length':target_model.input_shape[1],'timestamp_basis':'nominal temporal grid only; measured packet timestamps unavailable','transfer':'Shared Conv1D encoder weights only; seven-class head discarded, binary SRASTA head trained on primary train','primary_test_used':False,'use':'representation pretraining; not final performance evidence'}
