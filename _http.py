"""Shared test helper. Sends the role key from PROXY_REQUESTER_KEY / PROXY_APPROVER_KEY (set both when auth is on).
web("ask", {...}) and web("/api/ask", {...}) hit /api/...; paths starting with /a/ are raw. HTTP errors come back as {"http": code}."""
import json, os, urllib.error, urllib.request as u
BASE = os.environ.get("PROXY_URL", "http://localhost:8000")
def web(path, body=None, method=None, role=None):
    p = path.lstrip("/")
    raw = p.startswith("a/")
    if p.startswith("api/"): p = p[4:]
    role = role or ("requester" if p.split("/")[0].split("?")[0] in ("ask", "answer", "tts", "stt") else "approver")
    h = {"content-type": "application/json"}
    if os.environ.get(f"PROXY_{role.upper()}_KEY"): h["x-proxy-key"] = os.environ[f"PROXY_{role.upper()}_KEY"]
    url = f"{BASE}/{p}" if raw else f"{BASE}/api/{p}"
    data = json.dumps(body).encode() if (body is not None or method == "POST") else None
    try: return json.load(u.urlopen(u.Request(url, data, h, method=method), timeout=150))
    except urllib.error.HTTPError as e: return {"http": e.code}
