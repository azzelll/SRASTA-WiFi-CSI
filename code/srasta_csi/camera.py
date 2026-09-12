"""Anomaly-triggered local MoveNet capture. Images live in memory for one request."""
import queue
import threading
from pathlib import Path
import numpy as np

def summarize_pose(points):
    p=np.asarray(points,dtype=float)
    if p.shape!=(17,3) or not np.isfinite(p).all() or np.any(p<0) or np.any(p>1):
        raise ValueError('expected 17 bounded y/x/score keypoints')
    body=p[[5,6,11,12,15,16]]
    reliable=bool(np.all(body[:,2]>=.3))
    width=float(np.ptp(body[:,1]))
    height=float(np.ptp(body[:,0]))
    horizontal=reliable and width>1.2*max(height,.01) and width>.15
    return {'keypoints':p.round(4).tolist(),'horizontal':bool(horizontal),'quality':float(body[:,2].mean())}

class EventCamera:
    def __init__(self,model_path=None,index=0,*,capture=None):
        if capture is None and (model_path is None or not Path(model_path).is_file()):
            raise ValueError('a local MoveNet Lightning model is required')
        self.model_path,self.index,self.capture=model_path,index,capture
        self.requests=queue.Queue(maxsize=1)
        self.results=queue.Queue(maxsize=1)
        self.stop=threading.Event()
        self.thread=threading.Thread(target=self._work,daemon=True)
        self.thread.start()

    def request(self,event_id):
        try:
            self.requests.put_nowait(event_id)
            return True
        except queue.Full:
            return False

    def _capture(self):
        if self.capture:
            return self.capture()
        import cv2
        try:
            from tflite_runtime.interpreter import Interpreter
        except ImportError:
            try:
                from ai_edge_litert.interpreter import Interpreter
            except ImportError:
                from tensorflow.lite.python.interpreter import Interpreter
        model=Interpreter(model_path=str(self.model_path),num_threads=2)
        model.allocate_tensors()
        inp=model.get_input_details()[0]; out=model.get_output_details()[0]
        if tuple(inp['shape'])!=(1,192,192,3) or tuple(out['shape'])!=(1,1,17,3):
            raise ValueError('model must be MoveNet Lightning singlepose 192')
        camera=cv2.VideoCapture(self.index)
        poses=[]
        try:
            if not camera.isOpened():
                raise RuntimeError('camera unavailable')
            for _ in range(3):
                ok,frame=camera.read()
                if not ok:
                    raise RuntimeError('capture failed')
                height,width=frame.shape[:2]; size=max(height,width)
                image=cv2.copyMakeBorder(frame,(size-height)//2,(size-height+1)//2,(size-width)//2,(size-width+1)//2,cv2.BORDER_CONSTANT,value=0)
                rgb=cv2.cvtColor(cv2.resize(image,(192,192)),cv2.COLOR_BGR2RGB)
                model.set_tensor(inp['index'],rgb[None].astype(inp['dtype']))
                model.invoke()
                poses.append(model.get_tensor(out['index'])[0,0].copy())
                del frame,image,rgb
                self.stop.wait(.15)
        finally:
            camera.release()
        return poses

    def _work(self):
        while not self.stop.is_set():
            try:
                event_id=self.requests.get(timeout=.2)
            except queue.Empty:
                continue
            try:
                poses=[summarize_pose(p) for p in self._capture()]
                if len(poses)!=3:
                    raise ValueError('three pose observations required')
                result={'status':'complete','keypoints':poses[-1]['keypoints'],'evidence':'local_pose_rule_unverified','active':False,'supports_anomaly':sum(p['horizontal'] for p in poses)>=2}
            except Exception:
                result={'status':'error','keypoints':[],'evidence':'camera_unavailable','active':False,'supports_anomaly':False}
            try:
                self.results.put_nowait((event_id,result))
            except queue.Full:
                pass
            self.requests.task_done()

    def poll(self):
        try:
            return self.results.get_nowait()
        except queue.Empty:
            return None

    def close(self):
        self.stop.set()
        self.thread.join(timeout=2)
