"""Role-based access: 'requester' (Amma) and 'approver' (Pooja). Cookie session after signing in with a role key,
or an X-Proxy-Key header for scripts. PROXY_AUTH=off disables everything (local development only)."""
import hashlib, hmac, os, secrets, time
from collections import defaultdict, deque
from fastapi import HTTPException, Request

ENABLED = os.environ.get("PROXY_AUTH", "on") != "off"
SESSION_TTL = 12 * 3600
ROLES = ("approver", "requester")

def setup():
    """Run once at startup, BEFORE the MCP subprocesses are spawned (they inherit these env vars)."""
    if not ENABLED:
        print("[auth] DISABLED (PROXY_AUTH=off): local development only", flush=True); return
    made = []
    for k in ("PROXY_SECRET", "PROXY_APPROVER_KEY", "PROXY_REQUESTER_KEY"):
        if not os.environ.get(k): os.environ[k] = secrets.token_urlsafe(24); made.append(k)
    base = os.environ.get("PROXY_BASE_URL", "http://localhost:8000")
    for role in ROLES:
        if f"PROXY_{role.upper()}_KEY" in made:
            print(f"[auth] {role} sign-in link (generated this run): {base}/login#{role}:{os.environ[f'PROXY_{role.upper()}_KEY']}", flush=True)

def _sig(msg): return hmac.new(os.environ["PROXY_SECRET"].encode(), msg.encode(), hashlib.sha256).hexdigest()[:32]
def _eq(a, b): return hmac.compare_digest(str(a).encode(), str(b).encode())

def key_ok(role, key): return role in ROLES and bool(key) and _eq(key, os.environ.get(f"PROXY_{role.upper()}_KEY", ""))
def make_session(role):
    exp = int(time.time()) + SESSION_TTL
    return f"{role}.{exp}.{_sig(f'{role}.{exp}')}"

def role_of(request: Request):
    if not ENABLED: return "both"
    k = request.headers.get("x-proxy-key")
    if k: return next((r for r in ROLES if key_ok(r, k)), None)
    try:
        role, exp, sig = request.cookies.get("proxy_session", "").split(".")
        if role in ROLES and int(exp) > time.time() and _eq(sig, _sig(f"{role}.{exp}")): return role
    except ValueError: pass
    return None

def need(*roles):
    """FastAPI dependency: 401 if not signed in, 403 if the role may not do this."""
    def dep(request: Request):
        r = role_of(request)
        if r is None: raise HTTPException(401, "sign in")
        if r != "both" and r not in roles: raise HTTPException(403, "your role cannot do this")
        return r
    return dep

_hits = defaultdict(deque)
def limit(name, n=30, per=60):
    now = time.time(); q = _hits[name]
    while q and q[0] < now - per: q.popleft()
    if len(q) >= n: raise HTTPException(429, "too many requests, slow down")
    q.append(now)
