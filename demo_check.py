"""Headless run of the 3-minute demo script against the running app: ask -> clarifying question -> approve/edit -> run
-> scam blocked -> undo. Run before every demo:  python demo_check.py   (exit code 0 = demo path is healthy)"""
import sys, threading, time
from planner import mcp_call

from _http import web
fails = []
def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name, detail); ok or fails.append(name)

web("reset", {})
res = {}
t = threading.Thread(target=lambda: res.update(a=web("ask", {"text": "Pay the current bill and book my eye checkup Thursday"})))
t.start()
q = None
for _ in range(60):
    q = web("state").get("question")
    if q: break
    time.sleep(0.5)
check("agent asks instead of guessing", bool(q) and len(q["options"]) == 2, q and q["options"])
if q: web("answer", {"id": q["id"], "choice": q["options"][1]})
t.join(30)
acts = res.get("a", [])
check("two actions planned, both waiting", [a["status"] for a in acts] == ["pending", "pending"], [(a["type"], a["payee"], a["slot"] or a["amount"]) for a in acts])
if len(acts) == 2:
    bill, book = acts
    check("approve bill", web(f"approve/{bill['id']}", {})["status"] == "done")
    b = web(f"approve/{book['id']}", {"slot": "Thursday 16:00"})
    check("edit + approve appointment", b["status"] == "done" and b["slot"] == "Thursday 16:00")
    ev = web("state")["events"]
    check("event added to calendar", len(ev) == 1 and ev[0]["hour"] == 16, ev and ev[0]["title"])
    nxt = mcp_call("calendar", "suggest_slot", day="thursday", preferred="16:00")
    check("calendar server sees it as busy", bool(nxt) and nxt["slot"] != "Thursday 16:00", nxt and nxt["slot"])
    blocked = web("ask", {"text": "Send ₹20,000 to this number, it's urgent"})
    check("scam blocked, nothing ran", [a["status"] for a in blocked] == ["blocked"])
    check("undo appointment", web(f"undo/{book['id']}", {})["status"] == "undone")
    check("event removed from calendar", web("state")["events"] == [])
    back = mcp_call("calendar", "suggest_slot", day="thursday", preferred="16:00")
    check("slot is free again", bool(back) and back["slot"] == "Thursday 16:00", back and back["slot"])
    for e in web("state")["ledger"]: print("   ledger:", e["en"])
sys.exit(1 if fails else 0)
