"""Fetch a pinned public ESP-Fi HAR source-train subset; never its test partition."""
import concurrent.futures,csv,hashlib,io,json
from pathlib import Path
from urllib.parse import quote
import requests
import time

def get_source(url,**kwargs):
    for attempt in range(3):
        try:
            return requests.get(url,**kwargs)
        except (requests.Timeout,requests.ConnectionError):
            if attempt==2:raise
            time.sleep(2**attempt)
REPO='AutoSmartGroup/ESP-Fi-HAR'
COMMIT='c8bf6aa0d680fa02695c85a82b05e79b3ebb10c4'
BASE=f'https://raw.githubusercontent.com/{REPO}/{COMMIT}/'

def main():
    root=Path('data/external/esp_fi_har');root.mkdir(parents=True,exist_ok=True)
    if (root/'manifest.json').exists():raise FileExistsError('frozen external manifest already exists')
    source=get_source(f'https://api.github.com/repos/{REPO}/git/trees/{COMMIT}',params={'recursive':'1'},timeout=30);source.raise_for_status();tree=source.json()
    if tree.get('truncated'):raise ValueError('incomplete source listing')
    files=[f for f in tree['tree'] if f['type']=='blob' and f['path'].endswith('.mat') and '/train_amp/' in f['path']]
    readme=get_source(BASE+'README.md',timeout=30);readme.raise_for_status()
    (root/'SOURCE_README.md').write_bytes(readme.content)
    def download(item):
        path=item['path'];relative=path.split('/train_amp/',1)[1];target=(root/'train_amp'/relative).resolve()
        if (root/'train_amp').resolve() not in target.parents:raise ValueError('unsafe source path')
        if target.exists():payload=target.read_bytes()
        else:
            response=get_source(BASE+quote(path,safe='/'),timeout=60);response.raise_for_status();payload=response.content
            if len(payload)!=item['size']:raise ValueError('source size mismatch')
            target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as h:h.write(payload)
        digest=hashlib.sha1(f'blob {len(payload)}\0'.encode()+payload).hexdigest()
        if digest!=item['sha']:raise ValueError('Git source hash mismatch')
        pieces=target.stem.split('-')
        return {'source_path':'train_amp/'+relative,'source_split':'train','label':relative.split('/')[0],'subject':pieces[1],'scenario':pieces[0],'trial':pieces[-1],'sha256':hashlib.sha256(payload).hexdigest()}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:rows=list(pool.map(download,files))
    report={'source':f'https://github.com/{REPO}','commit':COMMIT,'license':'CC BY 4.0','attribution':'Wen, Ruan, Wang, Zhou, Gao, Li (2026), ESP-Fi HAR, Ad Hoc Networks 186:104192, doi:10.1016/j.adhoc.2026.104192','hardware':'ESP32-C3; different capture domain from SRASTA ESP32-S3','allowed_use':'source-train supervised representation pretraining or separately disclosed ablation; never primary validation/test','source_test_downloaded':0,'label_rule':'activity directory is authoritative; do not infer activity ID mapping from README filenames','records':rows}
    (root/'manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='records'},indent=2));print('Source-train recordings: '+str(len(rows)))
if __name__=='__main__':main()
