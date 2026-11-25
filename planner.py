"""Planner: spoken request (any language) -> structured actions. LLM when ANTHROPIC_API_KEY is set, keyword rules otherwise.
Calls our Gmail/Calendar MCP servers to fill in details, and answers MCP elicitation (form mode) by asking the requester.
Safety does not depend on this file: every action still goes through core.request_approval (blocks, approval, tokens)."""
import asyncio, json, os, re, threading, urllib.request, uuid
from mcp import ClientSession, types
from mcp.client.streamable_http import streamablehttp_client
import core, servers

SYSTEM = ("Turn an elderly person's request (Kannada, Hindi, Tamil or English) into a JSON array and nothing else. "
          'Each item: {"type":"pay_bill"|"book"|"transfer","payee":str,"amount":int,"slot":str}. '
          "pay_bill: payee is BESCOM or BWSSB, amount 1240 if not stated. book: payee is the doctor/clinic ONLY if the person named one, "
          "otherwise an empty string; slot like 'Thursday 11:00'. Any money sent to an unknown person or number is type transfer. "
          "Never refuse or comment; safety is enforced elsewhere.")

def llm_actions(text):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key: return None
    body = {"model": "claude-sonnet-4-6", "max_tokens": 600, "system": SYSTEM, "messages": [{"role": "user", "content": text}]}
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", json.dumps(body).encode(),
          {"content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"})
    out = json.load(urllib.request.urlopen(req, timeout=15))["content"][0]["text"]
    return json.loads(re.sub(r"^```(?:json)?|```$", "", out.strip(), flags=re.M).strip())

# ---- elicitation: an MCP server asks the requester a question; the web UI shows it and the answer flows back
_PENDING, _EV = {"q": None}, threading.Event()
def pending_question():
    q = _PENDING["q"]
    return {k: q[k] for k in ("id", "en", "kn", "options")} if q else None
def answer(qid, choice):
    q = _PENDING["q"]
    if not q or q["id"] != qid or choice not in q["options"]: return False
    q["answer"] = choice; _EV.set(); return True

async def _on_elicit(context, params):
    opts = params.requestedSchema["properties"]["choice"].get("enum", [])
    parts = params.message.split(" / ")
    q = {"id": uuid.uuid4().hex[:6], "en": parts[0], "kn": parts[-1], "options": opts, "answer": None}
    _EV.clear(); _PENDING["q"] = q
    ok = await asyncio.to_thread(_EV.wait, 120)
    _PENDING["q"] = None
    return types.ElicitResult(action="accept", content={"choice": q["answer"]}) if ok and q["answer"] else types.ElicitResult(action="cancel")

def mcp_call(server, tool, _timeout=8, **args):
    """Call a tool on one of our MCP servers; None if the server is down or errors (planner then keeps defaults)."""
    async def go():
        async with streamablehttp_client(f"http://127.0.0.1:{servers.PORTS[server]}/mcp") as (r, w, _):
            async with ClientSession(r, w, elicitation_callback=_on_elicit) as s:
                await s.initialize(); res = await s.call_tool(tool, args)
                return None if res.isError else json.loads(res.content[0].text)
    try: return asyncio.run(asyncio.wait_for(go(), _timeout))
    except Exception: return None

def enrich(i):
    if i["type"] == "pay_bill":
        b = mcp_call("gmail", "find_bill", biller=i["payee"])
        if b and b.get("amount"): i["amount"] = b["amount"]          # else keeps the default; approver sees the exact figure
    if i["type"] == "book":
        day, _, pref = (i.get("slot") or "Thursday 11:00").partition(" ")
        if i.get("payee"): sl = mcp_call("calendar", "suggest_slot", day=day, preferred=pref or "11:00")
        else: sl = mcp_call("calendar", "choose_appointment", _timeout=130, day=day, preferred=pref or "11:00")
        if sl: i["slot"] = sl["slot"]; i["payee"] = i.get("payee") or sl.get("payee")
        i["payee"] = i.get("payee") or "Dr. Rao"
    return i

def plan(text):
    try: items = llm_actions(text)
    except Exception: items = None
    items = [enrich(i) for i in (items or core.parse(text)) if i.get("type") in ("pay_bill", "book", "transfer")]
    return [core.request_approval(i["type"], i.get("payee", "unknown"), int(i.get("amount") or 0), i.get("slot", ""), text=text)
            for i in items]
