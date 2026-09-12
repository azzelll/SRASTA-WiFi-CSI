"""Actual browser acceptance: five states, actions, mobile, PWA and privacy."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:8000');parser.add_argument('--out',type=Path,default=Path('artifacts/ui'));args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    evidence=[];errors=[];external=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1100})
        page=context.new_page()
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('request',lambda r:external.append(r.url) if not r.url.startswith(args.url) else None)
        page.goto(args.url)
        expect(page.locator('#lab')).to_be_visible()
        for viewport in [{'width':1440,'height':1100},{'width':390,'height':844}]:
            page.set_viewport_size(viewport)
            for state in ['standby','normal','inactive','anomaly','critical']:
                with page.expect_response(lambda r:r.url.endswith('/dev/state') and r.request.method=='POST') as changed:
                    page.locator(f'[data-demo-state="{state}"]').click()
                assert changed.value.ok
                expect(page.locator('#state-card')).to_have_attribute('data-state',state)
                expect(page.locator('#mode')).to_contain_text('MODE SIMULATOR')
                expect(page.locator('#events .event strong').first).to_have_text(page.locator('#state-title').inner_text())
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),f'overflow {viewport} {state}'
                assert page.locator('video').count()==0
                page.locator('h1').scroll_into_view_if_needed()
                page.screenshot(path=str(args.out/f'{viewport["width"]}-{state}.png'),full_page=True)
                evidence.append({'viewport':viewport,'state':state,'overflow':False})
            page.evaluate("const old={...current,state:'standby',revision:current.revision-1};render(old,[]);")
            expect(page.locator('#state-card')).to_have_attribute('data-state','critical')
            page.locator('#ack').click()
            expect(page.locator('#ack')).to_have_text('Sudah ditangani')
            expect(page.locator('#state-card')).to_have_attribute('data-state','critical')
            page.locator('#emergency').click()
            expect(page.locator('#emergency-dialog')).to_be_visible()
            assert page.locator('#call-link').get_attribute('href') is None
            page.locator('#emergency-number').fill('12345')
            expect(page.locator('#call-link')).to_have_attribute('href','tel:12345')
            # Never launch an actual telephone call in acceptance tests.
            page.locator('#emergency-dialog .secondary').click()
        page.set_viewport_size({'width':390,'height':844})
        page.evaluate("document.documentElement.style.fontSize='200%'")
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),'200% text overflow'
        page.screenshot(path=str(args.out/'text-200-percent.png'),full_page=True)
        page.evaluate("document.documentElement.style.fontSize=''")
        page.evaluate('navigator.serviceWorker.ready')
        cached=page.evaluate('''async()=>{const keys=await caches.keys();const urls=[];for(const key of keys){const cache=await caches.open(key);for(const request of await cache.keys())urls.push(new URL(request.url).pathname);}return urls;}''')
        assert '/' in cached
        assert not set(cached)&{'/status','/events','/config','/ws'}
        context.set_offline(True)
        page.reload()
        expect(page.locator('h1')).to_have_text('Ringkasan pemantauan')
        expect(page.locator('#offline')).to_be_visible()
        page.screenshot(path=str(args.out/'offline.png'),full_page=True)
        context.set_offline(False)
        context.close();browser.close()
    assert not errors,errors
    assert not external,external
    report={'status':'passed','checks':evidence,'acknowledgement':'passed','explicit_emergency_dialog':'passed_no_call_made','text_200_percent':'passed','offline_shell':'passed','sensitive_cache':'absent','page_errors':errors,'external_requests':external}
    (args.out/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
