"""Fixed-window temporal/spectral descriptors for group-tested alternatives."""
import numpy as np
FEATURE_VERSION='temporal-spectral-v1'

def rich_features(values):
    x=np.asarray(values,dtype=np.float64)
    if x.ndim!=2 or x.shape[1]!=52 or len(x)<32 or not np.isfinite(x).all():
        raise ValueError('features require finite [time,52]')
    centered=x-x.mean(axis=0);d=np.diff(x,axis=0)
    scale=np.maximum(centered.std(axis=0),1e-6)
    z=centered/scale
    arrays=[x.mean(axis=0),x.std(axis=0),np.ptp(x,axis=0),np.mean(abs(x),axis=0),np.mean(d*d,axis=0),np.max(abs(d),axis=0),np.mean(z**3,axis=0),np.mean(z**4,axis=0)]
    features=[]
    for a in arrays:features.extend(np.quantile(a,[0,.1,.25,.5,.75,.9,1]))
    # Aggregate amplitude descriptors and temporal shape, not subject identifiers.
    energy=np.mean(d*d,axis=1);envelope=np.mean(abs(centered),axis=1)
    for a in [energy,envelope,np.mean(z,axis=1)]:
        features.extend(np.quantile(a,[0,.1,.25,.5,.75,.9,1]))
        normalizer=max(np.mean(abs(a)),1e-9)
        features.extend([np.mean(part)/normalizer for part in np.array_split(a,10)])
        features.extend([np.std(a)/normalizer,float(np.argmax(abs(a)))/len(a)])
    power=abs(np.fft.rfft(centered*np.hanning(len(x))[:,None],axis=0))**2
    frequencies=np.fft.rfftfreq(len(x),.01)
    total=np.maximum(power[1:].sum(axis=0),1e-12)
    for low,high in [(0,.8),(.8,1.6),(1.6,3.2),(3.2,6.4),(6.4,12.8),(12.8,50.1)]:
        ratio=power[(frequencies>low)&(frequencies<=high)].sum(axis=0)/total
        features.extend(np.quantile(ratio,[.1,.5,.9]))
    channel_power=np.maximum(power[1:],1e-12)/total
    entropy=-np.sum(channel_power*np.log(channel_power),axis=0)/np.log(len(power)-1)
    features.extend(np.quantile(entropy,[0,.25,.5,.75,1]))
    correlation=np.mean(z[:,:-1]*z[:,1:],axis=0)
    features.extend(np.quantile(correlation,[0,.25,.5,.75,1]))
    # Keep per-subcarrier positional variance available; all 52 positions fixed.
    features.extend(scale)
    result=np.asarray(features,dtype=np.float32)
    return np.sign(result)*np.log1p(abs(result))

def classifier_scores(model,features):
    if hasattr(model,'predict_proba'):
        return np.asarray(model.predict_proba(features))[:,1]
    margin=np.asarray(model.decision_function(features))
    return 1/(1+np.exp(-np.clip(margin,-30,30)))

class FeatureInference:
    def __init__(self,path):
        import joblib
        artifact=joblib.load(path)
        if artifact.get('artifact_type')!='srasta_feature_classifier_v1' or artifact.get('feature_version')!=FEATURE_VERSION:
            raise ValueError('alternative model feature contract mismatch')
        self.model=artifact['model']
        if list(self.model.classes_)!=[0,1]:raise ValueError('classifier must contain nonfall/fall in order')
        self.window_length=int(artifact['window_length'])
        expected=len(rich_features(np.zeros((self.window_length,52))))
        if artifact['feature_count']!=expected:raise ValueError('classifier feature count mismatch')
        self.capture_profile_hash=artifact['capture_profile_hash'];self.preprocess_config_hash=artifact['preprocess_config_hash']
        self.threshold=float(artifact['threshold'])
        if not 0<self.threshold<1:raise ValueError('invalid classifier threshold')
    def probability(self,window):
        score=float(classifier_scores(self.model,rich_features(window)[None])[0])
        if not np.isfinite(score) or not 0<=score<=1:raise ValueError('invalid classifier score')
        return score
