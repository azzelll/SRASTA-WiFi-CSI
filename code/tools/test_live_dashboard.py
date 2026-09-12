"""Read-only browser acceptance against an already running physical serial source."""
import argparse,json,time,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
URL='http://127.0.0.1:8000'
def read():
    with urllib.request.urlopen(URL+'/status',timeout=5) as r:return json.load(r)
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=Path('artifacts/live-ui'));args=parser.parse_args()
    out=args.out;out.mkdir(parents=True,exist_ok=True)
    first=read();assert first['source']=='serial' and not first['simulated']
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1440,'height':1100});errors=[];messages=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('websocket',lambda ws:ws.on('framereceived',lambda payload:messages.append(json.loads(payload))))
        page.goto(URL+'/?view=live')
        expect(page.locator('#mode')).to_contain_text('CSI PERANGKAT')
        expect(page.locator('#lab')).to_be_hidden()
        expect(page.locator('#source')).to_have_text('CSI SERIAL')
        page.wait_for_function("document.querySelector('#connection').textContent==='Terhubung lokal'")
        for width,height in [(1440,1100),(390,844)]:
            page.set_viewport_size({'width':width,'height':height})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path=str(out/f'live-{width}.png'),full_page=True)
        end=read();assert end['health']['accepted_frames']>first['health']['accepted_frames']
        assert end['health']['fresh'] and end['health']['inference_ready']
        assert messages and all(m['status']['source']=='serial' and not m['status']['simulated'] for m in messages)
        assert not errors,errors
        payload=json.dumps(end)
        for key in ['iq_bytes','sender_mac','password']:assert key not in payload
        report={'status':'passed','source':'physical_serial','api_frame_count_before':first['health']['accepted_frames'],'api_frame_count_after':end['health']['accepted_frames'],'realtime_messages':len(messages),'simulator_controller':'hidden','viewports':[1440,390],'horizontal_overflow':False,'page_errors':errors,'snapshot':end,'scope':'CSI pipeline and UI proof; no labeled fall/presence accuracy claim'}
        (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in report.items() if k!='snapshot'},indent=2));browser.close()
if __name__=='__main__':main()
