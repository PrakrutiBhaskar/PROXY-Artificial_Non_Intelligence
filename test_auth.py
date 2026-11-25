"""Access control against the running app (auth ON, keys in PROXY_APPROVER_KEY / PROXY_REQUESTER_KEY, PROXY_ALLOW_RESET unset).
    python test_auth.py"""
import asyncio, json, os, urllib.error, urllib.request as u
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from _http import web, BASE
import notify

class NoRedirect(u.HTTPRedirectHandler):
    def redirect_request(self, *a, **k): return None
op = u.build_opener(NoRedirect)
def raw(path, data=None, headers=None, method=None):
    try:
        r = op.open(u.Request(BASE + path, data, headers or {}, method=method)); return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read().decode()
    except urllib.error.HTTPError as e: return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read().decode()
fails = []
def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name, detail); ok or fails.append(name)
A, R = os.environ["PROXY_APPROVER_KEY"], os.environ["PROXY_REQUESTER_KEY"]
J = {"content-type": "application/json"}

check("healthz is open", raw("/healthz")[0] == 200)
check("no session: state 401", raw("/api/state")[0] == 401)
check("no session: / redirects to /login", raw("/")[0] in (302, 303, 307))
check("security headers", {"x-frame-options", "content-security-policy"} <= {k.lower() for k in raw("/login")[1]})
check("wrong key rejected", raw("/login", json.dumps({"role": "approver", "key": "nope"}).encode(), J, "POST")[0] == 401)
st, hd, _ = raw("/login", json.dumps({"role": "approver", "key": A}).encode(), J, "POST")
cookie = hd.get("set-cookie", "").split(";")[0]
check("login sets HttpOnly strict cookie", st == 200 and "HttpOnly" in hd["set-cookie"] and "SameSite=strict" in hd["set-cookie"], cookie[:30])
check("cookie works", raw("/api/state", headers={"Cookie": cookie})[0] == 200)
role, exp, sig = cookie.split("=", 1)[1].split(".")
check("tampered cookie rejected", raw("/api/state", headers={"Cookie": f"proxy_session=requester.{exp}.{sig}"})[0] == 401)
check("requester key cannot approve", web("approve/zzz", {}, role="requester").get("http") == 403)
check("approver key cannot ask", web("ask", {"text": "pay the bill"}, role="approver").get("http") == 403)
check("reset is off by default", web("reset", {}).get("http") == 403)
check("unknown action is 404, not a crash", web("approve/zzzzzz", {}).get("http") == 404)

# markup from the model must never reach a screen: create an action with a hostile payee through the consent MCP server
async def hostile():
    async with streamablehttp_client("http://127.0.0.1:8765/mcp") as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.call_tool("request_approval", {"action": "book", "payee": '<img src=x onerror=alert(1)>"Dr', "slot": "Thursday 11:00"})
            return json.loads(res.content[0].text)
a = asyncio.run(hostile())
check("markup stripped from payee", "<" not in a["payee"] and '"' not in a["payee"], a["payee"])
link = notify.link(a["id"]).replace("http://localhost:8000", BASE)
body = raw(link.replace(BASE, ""))[2]
check("approver card page is escaped", "<img" not in body and a["payee"][:3] in body)
check("bad link signature 403", raw(f"/a/{a['id']}?sig=wrong")[0] == 403)

codes = [(r.get("http") if isinstance(r, dict) else 200) for r in (web("ask", {"text": "hello"}) for _ in range(35))]
check("ask is rate limited", 429 in codes, f"{codes.count(429)} of 35 refused")
raise SystemExit(1 if fails else 0)
