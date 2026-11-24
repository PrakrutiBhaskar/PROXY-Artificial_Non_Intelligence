"""Demo backend + UI.  Run: uvicorn app:app --port 8000   (MCP server starts on :8765/mcp)"""
import threading
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel
import core, mcp_server, planner

app = FastAPI()
threading.Thread(target=mcp_server.mcp.run, kwargs={"transport": "streamable-http"}, daemon=True).start()

class Ask(BaseModel): text: str
class Edit(BaseModel): slot: str | None = None; amount: int | None = None

@app.get("/")
def home(): return FileResponse("static/index.html")
@app.get("/api/state")
def state(): return core.state()
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
