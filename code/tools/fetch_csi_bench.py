"""Fetch only public CSI-Bench ESP32 train/validation files; preserve U21 lock."""
import concurrent.futures
import csv
import hashlib
import io
import json
from pathlib import Path
from urllib.parse import quote
import requests

ROOT=Path(__file__).resolve().parents[2]
TRAIN={'U08','U09','U11','U12','U17','U18'}
BASE='https://www.kaggle.com/api/v1/datasets/download/guozhenjennzhu/csi-bench/'

def main():
    # Never overwrite source recordings or an already frozen local manifest.
    manifest=ROOT/'data/curated/esp32_s3_fall_v1/manifest.csv'
    if manifest.exists():
        raise SystemExit('manifest already exists; use the recorded source version to resume manually')
    raw=requests.get(BASE+quote('FallDetection/metadata/sample_metadata.csv',safe=''),timeout=30)
    raw.raise_for_status()
    rows=[r for r in csv.DictReader(io.StringIO(raw.content.decode('utf-8-sig'))) if r['device']=='ESP32']
    output=[]
    for row in rows:
        relative='csi-bench/FallDetection/'+row['file_path'].removeprefix('./')
        target=(ROOT/'data'/relative).resolve()
        if (ROOT/'data/csi-bench/FallDetection').resolve() not in target.parents:
            raise ValueError('source path escapes corpus')
        split='train' if row['user'] in TRAIN else ('validation' if row['user']=='U19' else ('test' if row['user']=='U21' else 'excluded'))
        output.append({'sample_id':row['id'],'source_path':relative,'label':row['label'].lower(),'label_id':int(row['label']=='Fall'),'subject_id':row['user'],'session_id':row['session'],'device':'ESP32','feature_count':52,'split':split})
    if len({r['source_path'] for r in output})!=len(output):
        raise ValueError('duplicate source paths')
    def download(row):
        target=ROOT/'data'/row['source_path']
        if target.exists():
            return 'existing'
        url=BASE+quote(row['source_path'].removeprefix('csi-bench/'),safe='')
        response=requests.get(url,timeout=60);response.raise_for_status()
        if not response.content.startswith(b'\x89HDF'):
            raise ValueError('expected HDF5 source file')
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as handle:
            handle.write(response.content)
        return 'downloaded'
    selected=[r for r in output if r['split'] in ('train','validation')]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        done=0
        for result in pool.map(download,selected):
            done+=1
            if done%50==0: print(f'Fetched {done}/{len(selected)} train/validation recordings',flush=True)
    manifest.parent.mkdir(parents=True,exist_ok=True)
    with manifest.open('x',newline='') as h:
        writer=csv.DictWriter(h,fieldnames=list(output[0]));writer.writeheader();writer.writerows(output)
    info={'source':'https://www.kaggle.com/datasets/guozhenjennzhu/csi-bench','license':'CC BY-NC-ND 4.0','metadata_sha256':hashlib.sha256(raw.content).hexdigest(),'indexed':len(output),'downloaded_train_validation':len(selected),'locked_test_downloaded':0,'subject_split':{'train':sorted(TRAIN),'validation':['U19'],'test':['U21'],'excluded':['U22']},'version_note':'2026-09-11 public metadata includes 22 additional U22 nonfall entries; U22 remains excluded.'}
    (manifest.parent/'dataset_info.json').write_text(json.dumps(info,indent=2))
    print(json.dumps(info,indent=2))

if __name__=='__main__':main()
