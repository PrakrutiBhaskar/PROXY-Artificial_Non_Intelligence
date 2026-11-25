"""Approver notifications: WhatsApp Cloud API with a signed approval link (falls back to a console line).
Env: WHATSAPP_TOKEN, WHATSAPP_PHONE_ID, APPROVER_WHATSAPP (e.g. 9198xxxxxxxx), PROXY_BASE_URL, PROXY_SECRET.
Note: free-form WhatsApp text only delivers inside the 24h window after the approver messages your number;
production needs an approved message template."""
import hashlib, hmac, json, os, threading, urllib.request

def _secret(): return os.environ.get("PROXY_SECRET", "dev-secret").encode()
def sign(aid): return hmac.new(_secret(), aid.encode(), hashlib.sha256).hexdigest()[:20]
def link(aid): return f"{os.environ.get('PROXY_BASE_URL', 'http://localhost:8000')}/a/{aid}?sig={sign(aid)}"

def _send(a, kind):
    text = (f"{a['requester']} asks: {a['what']}. Review and decide: {link(a['id'])}" if kind == "approve"
            else f"Blocked for {a['requester']} (looked like a scam): {a['what']}. Nothing was done.")
    e = os.environ
    if not (e.get("WHATSAPP_TOKEN") and e.get("WHATSAPP_PHONE_ID") and e.get("APPROVER_WHATSAPP")):
        print("[notify]", text, flush=True); return False
    body = {"messaging_product": "whatsapp", "to": e["APPROVER_WHATSAPP"], "type": "text",
            "text": {"body": text, "preview_url": False}}
    req = urllib.request.Request(f"https://graph.facebook.com/v20.0/{e['WHATSAPP_PHONE_ID']}/messages",
          json.dumps(body).encode(), {"Authorization": f"Bearer {e['WHATSAPP_TOKEN']}", "content-type": "application/json"})
    try: urllib.request.urlopen(req, timeout=10); return True
    except Exception as ex: print("[notify] failed:", ex, flush=True); return False

def pending(a, kind="approve"):
    threading.Thread(target=_send, args=(dict(a), kind), daemon=True).start()
