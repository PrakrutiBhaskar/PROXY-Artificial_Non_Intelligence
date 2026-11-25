"""Demo backend + UI.  Run: uvicorn app:app --port 8000   (6 MCP servers start on :8765-8770/mcp, localhost only)
Auth: see auth.py. On first start without keys set, sign-in links are printed to the console."""
import atexit, hmac, html, os, subprocess, sys
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
import auth
auth.setup()                                   # before the subprocesses below, so they share the same secret
import core, notify, planner, servers, voice

BASE = os.environ.get("PROXY_BASE_URL", "http://localhost:8000")
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
PROCS = [subprocess.Popen([sys.executable, "servers.py", n]) for n in servers.PORTS]
atexit.register(lambda: [p.terminate() for p in PROCS])
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
       "media-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")

@app.middleware("http")
async def security_headers(request: Request, call_next):
    r = await call_next(request)
    r.headers.update({"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
                      "Referrer-Policy": "no-referrer", "Content-Security-Policy": CSP})
    if request.url.path.startswith(("/api", "/login")): r.headers["Cache-Control"] = "no-store"
    if BASE.startswith("https"): r.headers["Strict-Transport-Security"] = "max-age=31536000"
    return r

class Ask(BaseModel): text: str
class Answer(BaseModel): id: str; choice: str
class Edit(BaseModel): slot: str | None = None; amount: int | None = None
class Login(BaseModel): role: str; key: str

REQ, APR, ANY = Depends(auth.need("requester")), Depends(auth.need("approver")), Depends(auth.need("requester", "approver"))
def _ip(r: Request): return r.client.host if r.client else "?"
def _found(fn, *a, **k):
    try: return fn(*a, **k)
    except KeyError: raise HTTPException(404, "no such action")
    except ValueError as e: raise HTTPException(409, str(e))

@app.get("/healthz")
def healthz(): return {"ok": True}

LOGIN = """<meta name=viewport content="width=device-width,initial-scale=1"><title>Proxy sign-in</title>
<body style="font:18px system-ui;max-width:380px;margin:40px auto;padding:0 16px"><h2>Proxy sign-in</h2>
<select id=r style="font:inherit;width:100%;padding:10px;margin:6px 0"><option value=approver>Approver</option><option value=requester>Requester</option></select>
<input id=k type=password placeholder="Access key" style="font:inherit;width:100%;padding:10px;margin:6px 0">
<button onclick="go()" style="font:inherit;padding:10px 16px">Sign in</button><p id=m></p>
<script>function go(role,key){fetch('/login',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({role:role||r.value,key:key||k.value})})
.then(x=>x.ok?location.replace('/'):(m.textContent=x.status==429?'Too many tries, wait a minute.':'Wrong key.'))}
const h=location.hash.slice(1);if(h.includes(':')){history.replaceState(null,'','/login');const i=h.indexOf(':');go(h.slice(0,i),h.slice(i+1))}</script>"""

@app.get("/login", response_class=HTMLResponse)
def login_page(): return LOGIN
@app.post("/login")
def login(b: Login, request: Request):
    auth.limit("login:" + _ip(request), 10)
    if not auth.key_ok(b.role, b.key): raise HTTPException(401, "wrong key")
    r = JSONResponse({"role": b.role})
    r.set_cookie("proxy_session", auth.make_session(b.role), max_age=auth.SESSION_TTL, httponly=True,
                 samesite="strict", secure=BASE.startswith("https"))
    return r

@app.get("/")
def home(request: Request):
    if auth.role_of(request) is None: return RedirectResponse("/login")
    return FileResponse("static/index.html")
@app.get("/api/me")
def me(role=ANY): return {"role": role, "reset": (not auth.ENABLED) or os.environ.get("PROXY_ALLOW_RESET") == "1"}
@app.get("/api/state")
def state(role=ANY): return {**core.state(), "question": planner.pending_question()}
@app.get("/api/config")
def config(role=ANY): return voice.config()

@app.post("/api/ask")
def ask(b: Ask, request: Request, role=REQ):
    auth.limit("ask:" + _ip(request), 30)
    return planner.plan(b.text[:500])
@app.post("/api/answer")
def answer(b: Answer, role=REQ): return {"ok": planner.answer(b.id, b.choice)}
@app.get("/api/tts")
def tts(text: str, request: Request, role=REQ):
    auth.limit("voice:" + _ip(request), 60)
    if not voice.config()["tts"]: raise HTTPException(503, "ELEVENLABS_API_KEY not set")
    return Response(voice.tts(text[:600]), media_type="audio/mpeg")
@app.post("/api/stt")
async def stt(request: Request, lang: str = "kn", role=REQ):
    auth.limit("voice:" + _ip(request), 60)
    if not voice.config()["stt"]: raise HTTPException(503, "ELEVENLABS_API_KEY not set")
    audio = await request.body()
    if len(audio) > 5_000_000: raise HTTPException(413, "recording too long")
    return {"text": await run_in_threadpool(voice.stt, audio, lang)}

@app.post("/api/approve/{aid}")
def approve(aid: str, e: Edit = Edit(), role=APR): return _found(core.approve, aid, slot=e.slot, amount=e.amount)
@app.post("/api/reject/{aid}")
def reject(aid: str, role=APR): return _found(core.reject, aid)
@app.post("/api/undo/{aid}")
def undo(aid: str, role=ANY): return _found(core.undo, aid)
@app.post("/api/reset")
def reset(role=APR):
    if auth.ENABLED and os.environ.get("PROXY_ALLOW_RESET") != "1": raise HTTPException(403, "reset is disabled (set PROXY_ALLOW_RESET=1)")
    core.reset(); return {}

# Approver link sent by WhatsApp: signed per action. GET only shows the card; deciding needs a POST (link previews can't approve).
def _sig(aid, sig):
    if not hmac.compare_digest(sig.encode(), notify.sign(aid).encode()): raise HTTPException(403, "bad link")
@app.get("/a/{aid}", response_class=HTMLResponse)
def card(aid: str, sig: str):
    _sig(aid, sig); x = _found(core.status, aid)
    btn = ("<button onclick=\"d('approve')\">Approve</button> <button onclick=\"d('reject')\">Reject</button>"
           if x["status"] == "pending" else f"<p>Status: <b>{html.escape(x['status'])}</b></p>")
    return f"""<meta name=viewport content="width=device-width,initial-scale=1"><body style="font:18px system-ui;max-width:420px;margin:24px auto;padding:0 16px">
<h3>{html.escape(x['requester'])} asks:</h3><p style="font-size:22px"><b>{html.escape(x['what'])}</b></p>{btn}<p id=r></p>
<script>const d=k=>fetch(location.pathname+'/decide?sig={html.escape(sig)}&d='+k,{{method:'POST'}}).then(r=>r.json()).then(j=>document.getElementById('r').textContent=j.status||j.detail)</script>"""
@app.post("/a/{aid}/decide")
def decide(aid: str, sig: str, d: str):
    _sig(aid, sig)
    return _found(core.approve, aid) if d == "approve" else _found(core.reject, aid)
