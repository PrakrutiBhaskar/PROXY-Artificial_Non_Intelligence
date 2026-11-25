"""Demo backend + UI.  Run: uvicorn app:app --port 8000   (4 MCP servers start on :8765-8768/mcp)"""
import atexit, subprocess, sys
import hmac
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel
import core, notify, planner, servers, voice

app = FastAPI()
PROCS = [subprocess.Popen([sys.executable, "servers.py", n]) for n in servers.PORTS]
atexit.register(lambda: [p.terminate() for p in PROCS])

class Ask(BaseModel): text: str
class Answer(BaseModel): id: str; choice: str
class Edit(BaseModel): slot: str | None = None; amount: int | None = None

@app.get("/")
def home(): return FileResponse("static/index.html")
@app.get("/api/state")
def state(): return {**core.state(), "question": planner.pending_question()}
@app.post("/api/answer")
def answer(b: Answer): return {"ok": planner.answer(b.id, b.choice)}
@app.post("/api/ask")
def ask(b: Ask): return planner.plan(b.text)
@app.post("/api/approve/{aid}")
def approve(aid: str, e: Edit = Edit()): return core.approve(aid, slot=e.slot, amount=e.amount)
@app.post("/api/reject/{aid}")
def reject(aid: str): return core.reject(aid)
@app.post("/api/undo/{aid}")
def undo(aid: str): return core.undo(aid)
@app.post("/api/reset")
def reset(): core.reset(); return {}

@app.get("/api/config")
def config(): return voice.config()
@app.get("/api/tts")
def tts(text: str):
    if not voice.config()["tts"]: raise HTTPException(503, "ELEVENLABS_API_KEY not set")
    return Response(voice.tts(text), media_type="audio/mpeg")
@app.post("/api/stt")
async def stt(request: Request, lang: str = "kn"):
    if not voice.config()["stt"]: raise HTTPException(503, "ELEVENLABS_API_KEY not set")
    return {"text": await run_in_threadpool(voice.stt, await request.body(), lang)}

# Approver link sent by WhatsApp: a GET only shows the card; deciding needs a POST (link previews can't approve).
def _sig(aid, sig):
    if not hmac.compare_digest(sig, notify.sign(aid)): raise HTTPException(403, "bad link")
@app.get("/a/{aid}", response_class=HTMLResponse)
def card(aid: str, sig: str):
    _sig(aid, sig); x = core.status(aid)
    btn = ("<button onclick=\"d('approve')\">Approve</button> <button onclick=\"d('reject')\">Reject</button>"
           if x["status"] == "pending" else f"<p>Status: <b>{x['status']}</b></p>")
    return f"""<meta name=viewport content="width=device-width,initial-scale=1"><body style="font:18px system-ui;max-width:420px;margin:24px auto;padding:0 16px">
<h3>{x['requester']} asks:</h3><p style="font-size:22px"><b>{x['what']}</b></p>{btn}<p id=r></p>
<script>const d=k=>fetch(location.pathname+'/decide?sig={sig}&d='+k,{{method:'POST'}}).then(r=>r.json()).then(j=>document.getElementById('r').textContent=j.status||j.detail)</script>"""
@app.post("/a/{aid}/decide")
def decide(aid: str, sig: str, d: str):
    _sig(aid, sig)
    try: return core.approve(aid) if d == "approve" else core.reject(aid)
    except ValueError as e: raise HTTPException(409, str(e))
