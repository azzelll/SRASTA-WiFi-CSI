from pathlib import Path
import tempfile
import unittest

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier

from srasta_csi.research_features import temporal_features, FEATURE_NAMES, channel_normalize
from srasta_csi.presence import PresenceInference
from srasta_csi.edge import RandomForestInference
from predict_offline_candidate import OfflineResearchInference
from calibrate_offline_candidates import choose_bias


class ResearchCandidateTests(unittest.TestCase):
    def test_multiclass_bias_keeps_probability_ties_and_rejects_invalid_payload(self):
        y=[0,1,2]; p=np.array([[.8,.1,.1],[.3,.6,.1],[.1,.1,.8]])
        weights,metrics=choose_bias(y,p)
        self.assertEqual(metrics['minimum_class_recall'],1.)
        self.assertEqual(weights,[1.,1.,1.])
        with self.assertRaises(ValueError):choose_bias(y,p*2)
    def test_native_features_preserve_gain_and_channel_permutation_invariance(self):
        t=np.arange(300)/30.
        values=(10+np.sin(2*np.pi*.3*t))[:,None]*np.arange(1,9)[None,:]
        a=temporal_features(values,30.)
        np.testing.assert_allclose(a,temporal_features(values[:,::-1]*100,30.),atol=1e-6)
        self.assertEqual(a.shape,(len(FEATURE_NAMES),))
        self.assertTrue(np.isfinite(temporal_features(np.ones((500,52)),100.)).all())
        for bad in (np.zeros((300,8)),np.ones((300,8))*-1,np.ones((300,8))*np.nan):
            with self.assertRaises(ValueError):temporal_features(bad,30.)

    def test_tcn_rejects_shape_resize_and_normalizes_only_each_current_window(self):
        rng=np.random.default_rng(42); values=rng.uniform(1,20,(2,500,52)).astype('float32')
        a=channel_normalize(values)
        np.testing.assert_allclose(a[:1],channel_normalize(values[:1]))
        np.testing.assert_allclose(a,channel_normalize(values*50),atol=1e-5)
        for wrong in (values[:,:,:51],values[:,:250],values.reshape(2,52,500)):
            with self.assertRaises(ValueError):channel_normalize(wrong)

    def test_three_class_inference_and_live_loader_rejection(self):
        rng=np.random.default_rng(2)
        windows=[rng.uniform(1,10,(300,8)) for _ in range(3)]
        x=np.stack([temporal_features(v,30.) for v in windows])
        classifier=RandomForestClassifier(n_estimators=10,bootstrap=False,random_state=42).fit(x,[0,1,2])
        payload={'artifact_type':'srasta_offline_native_research_v1','research_only':True,
            'local_deployment_ready':False,'model':classifier,'task':'breathing_three',
            'classes':['empty','sleep','normal'],'feature':'temporal','feature_names':FEATURE_NAMES,
            'layout':'declared_axes','normal_proxy_only':True,'threshold':.5}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'model.joblib';joblib.dump(payload,path)
            model=OfflineResearchInference(path)
            self.assertEqual(model.predict(windows[2],30.)['label'],'normal')
            self.assertTrue(model.predict(windows[2],30.)['normal_proxy_only'])
            for loader in (PresenceInference,RandomForestInference):
                with self.assertRaises(ValueError):loader(path)
            payload['normal_proxy_only']=False;joblib.dump(payload,path)
            with self.assertRaisesRegex(ValueError,'proxy provenance'):OfflineResearchInference(path)


if __name__=='__main__':unittest.main()
