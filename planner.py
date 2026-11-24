"""LLM planner: spoken request (any language) -> structured actions. Falls back to core.plan's keyword rules
when ANTHROPIC_API_KEY is unset or the call fails. Safety does not depend on this file: every action it
returns still goes through core.request_approval (hard blocks, approval, tokens)."""
import json, os, re, urllib.request
import core

SYSTEM = ("Turn an elderly person's request (Kannada, Hindi, Tamil or English) into a JSON array and nothing else. "
          'Each item: {"type":"pay_bill"|"book"|"transfer","payee":str,"amount":int,"slot":str}. '
          "pay_bill: payee is BESCOM or BWSSB, amount 1240 if not stated. book: payee is the doctor/clinic, "
          "slot like 'Thursday 11:00'. Any money sent to an unknown person or number is type transfer. "
          "Never refuse or comment; safety is enforced elsewhere.")

def llm_actions(text):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key: return None
    body = {"model": "claude-sonnet-4-6", "max_tokens": 600, "system": SYSTEM,
            "messages": [{"role": "user", "content": text}]}
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", json.dumps(body).encode(),
          {"content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"})
    out = json.load(urllib.request.urlopen(req, timeout=15))["content"][0]["text"]
    return json.loads(re.sub(r"^```(?:json)?|```$", "", out.strip(), flags=re.M).strip())

def plan(text):
    try: items = llm_actions(text)
    except Exception: items = None
    if not items: return core.plan(text)
    return [core.request_approval(i["type"], i.get("payee", "unknown"), int(i.get("amount", 0)),
                                  i.get("slot", ""), text=text)
            for i in items if i.get("type") in ("pay_bill", "book", "transfer")]
