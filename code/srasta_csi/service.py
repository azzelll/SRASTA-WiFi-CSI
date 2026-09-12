"""Loopback API and same-origin realtime dashboard."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import secrets
from urllib.parse import urlsplit
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, ConfigDict
from .care_state import STATES

class StateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    state: str

def create_product_app(runtime,runner=None):
    token = secrets.token_urlsafe(32)
    web = Path(__file__).parent/'web'
    async def pulse():
        while True:
            runtime.heartbeat()
            await asyncio.sleep(.5)
    @asynccontextmanager
    async def lifespan(app):
        if runner:
            runner.start()
        task = asyncio.create_task(pulse())
        yield
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        if runner:
            runner.close()
    app = FastAPI(title='SRASTA Local',lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','testserver','[::1]'])

    @app.middleware('http')
    async def protect(request,call_next):
        origin=request.headers.get('origin')
        expected=f'{request.url.scheme}://{request.url.netloc}'
        if origin and origin != expected:
            return JSONResponse({'detail':'cross-origin request refused'},status_code=403)
        if request.method not in ('GET','HEAD') and not secrets.compare_digest(request.headers.get('x-srasta-token',''),token):
            return JSONResponse({'detail':'local session token required'},status_code=403)
        try:
            length = int(request.headers.get('content-length','0') or '0')
            if length < 0:
                raise ValueError()
        except ValueError:
            return JSONResponse({'detail':'invalid request length'},status_code=400)
        if length > 4096:
            return JSONResponse({'detail':'request too large'},status_code=413)
        response=await call_next(request)
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
        return response

    def snapshot():
        with runtime.lock:
            return {'status':runtime.status(),'events':runtime.store.list(50)}

    @app.get('/')
    def index():
        return FileResponse(web/'index.html')
    @app.get('/health')
    def health():
        return {'ok':True,'service':'srasta-local','monitoring':runtime.status()['health']}
    @app.get('/status')
    def status():
        return runtime.status()
    @app.get('/events')
    def events(limit:int=50):
        return {'events':runtime.store.list(limit)}
    @app.get('/config')
    def config():
        return {'token':token,'demo':runtime.demo,'states':STATES}
    @app.post('/events/{event_id}/acknowledge')
    def acknowledge(event_id:int):
        if not runtime.acknowledge(event_id):
            # Idempotence is visible; an unknown/non-alert ID does not acknowledge anything.
            return {'acknowledged':False,**snapshot()}
        return {'acknowledged':True,**snapshot()}
    @app.post('/dev/state')
    def dev_state(payload:StateRequest):
        if not runtime.demo:
            raise HTTPException(404,'development controller disabled')
        if payload.state not in STATES:
            raise HTTPException(422,'invalid caregiver state')
        with runtime.lock:
            status=runtime.simulate(payload.state)
            return {**status,'events':runtime.store.list(50)}
    @app.websocket('/ws')
    async def realtime(ws:WebSocket):
        origin=ws.headers.get('origin')
        if origin and urlsplit(origin).netloc != ws.headers.get('host'):
            await ws.close(code=1008)
            return
        await ws.accept()
        try:
            while True:
                await ws.send_json(snapshot())
                await asyncio.sleep(.5)
        except (WebSocketDisconnect,RuntimeError):
            pass
    app.mount('/static',StaticFiles(directory=web),name='static')
    @app.get('/sw.js')
    def sw():
        return FileResponse(web/'sw.js',media_type='application/javascript',headers={'Service-Worker-Allowed':'/'})
    return app
