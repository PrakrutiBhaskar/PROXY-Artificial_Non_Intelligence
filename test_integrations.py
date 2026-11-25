"""Run with the app up (uvicorn app:app --port 8000):  python test_integrations.py
Checks Gmail/Calendar via MCP (mock data), the signed approver link, and voice endpoints.
ElevenLabs calls are checked against a fake urlopen, so no key or network is needed."""
import json, sys, urllib.error, urllib.request as u
import notify, voice

def web(path, body=None, method=None):
    r = u.Request("http://localhost:8000" + path, json.dumps(body).encode() if body is not None else None,
                  {"content-type": "application/json"}, method=method)
    try: return json.load(u.urlopen(r))
    except urllib.error.HTTPError as e: return {"http": e.code}

web("/api/reset", {})
acts = web("/api/ask", {"text": "pay the bill and book my eye checkup Thursday"})
print("planner via MCP:", [(a["type"], a["amount"] or a["slot"]) for a in acts])

bill = next(a for a in acts if a["type"] == "pay_bill")
link = notify.link(bill["id"]); path = link.replace("http://localhost:8000", "")
print("card page       :", u.urlopen(link).status)
print("bad signature   :", web(path.split("?")[0] + "?sig=wrong").get("http"))
print("approve by link :", web(path.split("?")[0] + "/decide?" + path.split("?")[1] + "&d=approve", {}, "POST")["status"])
print("link again      :", web(path.split("?")[0] + "/decide?" + path.split("?")[1] + "&d=approve", {}, "POST").get("http"), "(409 = already decided)")
print("voice config    :", web("/api/config"), "| tts without key:", web("/api/tts?text=hi").get("http"))

# ElevenLabs request shapes against a fake urlopen
seen = {}
class R:
    def __init__(s, b): s.b = b
    def read(s): return s.b
    def __enter__(s): return s
    def __exit__(s, *a): pass
def fake(req, timeout=0):
    seen.update(url=req.full_url, key=req.headers.get("Xi-api-key"), body=req.data)
    return R(b'{"text": "\\u0cb5\\u0cc0\\u0cb8\\u0cb2\\u0ccd"}' if "speech-to-text" in req.full_url else b"MP3")
u.urlopen = fake
import os; os.environ["ELEVENLABS_API_KEY"] = "k"
print("tts request     :", voice.tts("ನಮಸ್ಕಾರ") == b"MP3", seen["url"].rsplit("/", 2)[-2:], json.loads(seen["body"])["model_id"])
print("stt request     :", voice.stt(b"audio", "kn-IN"), b'name="language_code"\r\n\r\nkn' in seen["body"], b"scribe_v2" in seen["body"])
