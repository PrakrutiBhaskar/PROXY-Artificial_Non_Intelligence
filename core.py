"""Proxy core: consent gate, capability tokens, undo registry, ledger. In-memory for the MVP."""
import functools, json, os, re, sqlite3, threading, time, uuid
import google_data, notify

RULES = {"auto_approve_under": 0,            # set e.g. 2000 to pre-approve known billers
         "known_billers": ["BESCOM", "BWSSB"], "max_money_actions_per_day": 5}
SCAM_EN = [r"urgent(ly)?", r"gift ?cards?", r"kyc", r"anydesk", r"teamviewer", r"quick ?support", r"remote (access|control)",
           r"otp", r"cvv", r"pin", r"lottery", r"prize", r"arrest", r"customs", r"refund link", r"verify (your )?account"]
SCAM_LOCAL = ["ತುರ್ತು", "ತಕ್ಷಣ", "ಒಟಿಪಿ", "ಗಿಫ್ಟ್ ಕಾರ್ಡ್", "जरूरी", "तुरंत", "ओटीपी", "लॉटरी", "गिफ्ट कार्ड", "அவசர", "உடனடியாக", "ஓடிபி"]
def is_scam(text):
    t = text.lower()
    return any(re.search(rf"\b{p}\b", t) for p in SCAM_EN) or any(w in t for w in SCAM_LOCAL)
TTL = 2 * 3600
ACTIONS, TOKENS, LEDGER, BOOKINGS, REVERSE, EVENTS = {}, {}, [], {}, {}, {}   # EVENTS: calendar entries Proxy added
DB = os.environ.get("PROXY_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "proxy.db"))
_tl = threading.local()

def synced(fn):
    """Load shared state from SQLite, run fn, save it back. Lets several MCP server processes share one state."""
    @functools.wraps(fn)
    def wrap(*a, **k):
        if getattr(_tl, "in_txn", False): return fn(*a, **k)       # nested call: already synced
        con = sqlite3.connect(DB, timeout=10, isolation_level=None)
        _tl.in_txn = True
        try:
            con.execute("BEGIN IMMEDIATE")
            con.execute("CREATE TABLE IF NOT EXISTS s(k TEXT PRIMARY KEY, v TEXT)")
            row = con.execute("SELECT v FROM s WHERE k='state'").fetchone()
            st = json.loads(row[0]) if row else {}
            for d, key in ((ACTIONS, "a"), (TOKENS, "t"), (BOOKINGS, "b"), (REVERSE, "r"), (EVENTS, "e")):
                d.clear(); d.update(st.get(key, {}))
            LEDGER[:] = st.get("l", [])
            try: return fn(*a, **k)
            finally:
                con.execute("INSERT OR REPLACE INTO s VALUES('state', ?)",
                            (json.dumps({"a": ACTIONS, "t": TOKENS, "b": BOOKINGS, "r": REVERSE, "e": EVENTS, "l": LEDGER}),))
                con.execute("COMMIT")
        finally:
            _tl.in_txn = False; con.close()
    return wrap

EN = {"paid": "Paid ₹{amount} to {payee}.", "booked": "Appointment booked with {payee}, {slot}.",
      "blocked": "This looks unsafe, so I did not do it. {approver} has been alerted.",
      "undone": "Cancelled: {what}.", "rejected": "{approver} said no to: {what}.",
      "expired": "No answer from {approver} in time. Nothing was done: {what}.",
      "pending": "Waiting for {approver} to approve: {what}."}
KN = {"paid": "{payee}ಗೆ ₹{amount} ಪಾವತಿಸಲಾಗಿದೆ.", "booked": "{payee} ಅವರ ಬಳಿ {slot}ಕ್ಕೆ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಬುಕ್ ಆಗಿದೆ.",
      "blocked": "ಇದು ಸುರಕ್ಷಿತವಲ್ಲ, ಹಾಗಾಗಿ ನಾನು ಮಾಡಿಲ್ಲ. {approver} ಅವರಿಗೆ ತಿಳಿಸಲಾಗಿದೆ.",
      "undone": "ರದ್ದು ಮಾಡಲಾಗಿದೆ: {what}.", "rejected": "{approver} ಒಪ್ಪಿಲ್ಲ: {what}.",
      "expired": "{approver} ಉತ್ತರಿಸಲಿಲ್ಲ. ಏನನ್ನೂ ಮಾಡಿಲ್ಲ: {what}.",
      "pending": "{approver} ಅವರ ಒಪ್ಪಿಗೆಗಾಗಿ ಕಾಯುತ್ತಿದೆ: {what}."}

def log(key, **kw):
    LEDGER.append({"t": time.strftime("%H:%M:%S"), "en": EN[key].format(**kw), "kn": KN[key].format(**kw)})

def describe(a):
    if a["type"] == "pay_bill": return f"pay ₹{a['amount']} to {a['payee']}"
    if a["type"] == "book": return f"book {a['payee']} on {a['slot']}"
    return f"send ₹{a['amount']} to {a['payee']}"

# ---- consent-mcp -------------------------------------------------------------
@synced
def request_approval(type, payee, amount=0, slot="", text="", requester="Amma", approver="Pooja"):
    a = dict(id=uuid.uuid4().hex[:6], type=type, payee=payee, amount=amount, slot=slot,
             requester=requester, approver=approver, status="pending", created=time.time())
    a["what"] = describe(a)
    ACTIONS[a["id"]] = a
    money_today = sum(1 for x in ACTIONS.values() if x["type"] != "book" and x["status"] == "done")
    if (is_scam(text) or type == "transfer"
            or money_today >= RULES["max_money_actions_per_day"]):
        a["status"] = "blocked"; log("blocked", approver=approver); notify.pending(a, "blocked")
    elif type == "pay_bill" and payee in RULES["known_billers"] and amount <= RULES["auto_approve_under"]:
        approve(a["id"], by="standing rule")
    else:
        log("pending", approver=approver, what=a["what"]); notify.pending(a)
    return a

def _open(aid):
    a = ACTIONS[aid]
    if a["status"] == "pending" and time.time() - a["created"] > TTL:
        a["status"] = "expired"; log("expired", approver=a["approver"], what=a["what"])
    return a

@synced
def approve(aid, by="Pooja", slot=None, amount=None):
    a = _open(aid)
    if a["status"] != "pending": raise ValueError(f"action is {a['status']}")
    if slot: a["slot"] = slot
    if amount is not None: a["amount"] = amount
    a["what"] = describe(a)
    tok = "cap_" + uuid.uuid4().hex[:8]
    TOKENS[tok] = dict(token=tok, action=a["type"], payee=a["payee"], max_amount_inr=a["amount"],
                       uses=1, expires=time.time() + 1800, approved_by=by,
                       undo="raise_refund" if a["type"] == "pay_bill" else "cancel_booking")
    a["token"] = tok
    _run(a, tok)
    return a

@synced
def reject(aid):
    a = _open(aid)
    if a["status"] == "pending": a["status"] = "rejected"; log("rejected", approver=a["approver"], what=a["what"])
    return a

@synced
def revoke(tok): TOKENS.pop(tok, None)

def _check(tok, action, payee, amount=0):
    t = TOKENS.get(tok)
    if not t: raise PermissionError("no valid consent token")
    if t["uses"] < 1 or t["expires"] < time.time(): raise PermissionError("token used or expired")
    if t["action"] != action or t["payee"] != payee or amount > t["max_amount_inr"]:
        raise PermissionError("token does not cover this action")
    t["uses"] -= 1

# ---- mock action servers (token-gated) -----------------------------------------
@synced
def pay_bill(token, biller, amount):
    _check(token, "pay_bill", biller, amount); return {"receipt": "RCPT-" + uuid.uuid4().hex[:6]}
def _calendar_add(provider, slot):
    """Add the appointment to the calendar (Google when live, plus our own record). Returns an event id or None."""
    day, _, hm = slot.partition(" ")
    date, hour = google_data._next(day).isoformat(), int(hm.split(":")[0])
    title, gid = f"Appointment: {provider}", None
    if google_data._live():
        try: gid = google_data.create_event(title, date, hour)
        except Exception as ex: print("[calendar] could not add event:", ex, flush=True); return None
    eid = "ev_" + uuid.uuid4().hex[:6]
    EVENTS[eid] = dict(id=eid, title=title, date=date, hour=hour, gid=gid)
    return eid

def _calendar_remove(eid):
    ev = EVENTS.pop(eid, None)
    if ev and ev.get("gid"):
        try: google_data.delete_event(ev["gid"])
        except Exception as ex: print("[calendar] could not delete event:", ex, flush=True)

@synced
def book(token, provider, slot):
    _check(token, "book", provider); bid = "BK-" + uuid.uuid4().hex[:5]
    eid = _calendar_add(provider, slot)
    BOOKINGS[bid] = dict(provider=provider, slot=slot, active=True, event_id=eid); return {"booking_id": bid, "event_id": eid}
@synced
def cancel_booking(bid):
    BOOKINGS[bid]["active"] = False; _calendar_remove(BOOKINGS[bid].get("event_id"))
@synced
def busy_hours(date_iso): return sorted(e["hour"] for e in EVENTS.values() if e["date"] == date_iso)

# ---- undo-mcp ------------------------------------------------------------------
def _run(a, tok):
    REVERSE[a["id"]] = "raise_refund" if a["type"] == "pay_bill" else "cancel_booking"  # recorded BEFORE running
    try:
        if a["type"] == "pay_bill": a["result"] = pay_bill(tok, a["payee"], a["amount"]); log("paid", **a)
        else: a["result"] = book(tok, a["payee"], a["slot"]); log("booked", **a)
        a["status"] = "done"
    except Exception as e:
        a["status"] = "failed"; a["error"] = str(e)

@synced
def undo(aid):
    a = ACTIONS[aid]
    if a["status"] != "done": raise ValueError(f"cannot undo: action is {a['status']}")
    if REVERSE[aid] == "cancel_booking": cancel_booking(a["result"]["booking_id"])
    a["status"] = "undone"; log("undone", what=a["what"])   # payments: a refund request is filed
    return a

# ---- planner (rule-based stand-in for the LLM) ------------------------------------
def parse(text):
    t, out = text.lower(), []
    if re.search(r"send|transfer|ಕಳುಹಿಸ|भेज", t):
        m = re.search(r"(\d[\d,]*)", t)
        out.append(dict(type="transfer", payee="unknown number", amount=int(m.group(1).replace(",", "")) if m else 0))
    if re.search(r"bill|ಬಿಲ್|बिल", t): out.append(dict(type="pay_bill", payee="BESCOM", amount=1240))
    if not out and re.search(r"\b(pay|give)\b", t) and re.search(r"\d", t):
        out.append(dict(type="transfer", payee="unknown number", amount=int(re.search(r"(\d[\d,]*)", t).group(1).replace(",", ""))))
    if re.search(r"book|appointment|checkup|ಅಪಾಯಿಂಟ್|अपॉइंटमेंट", t): out.append(dict(type="book", payee="", slot="Thursday 11:00"))   # empty = ask the requester
    return out

def plan(text, requester="Amma"):
    return [request_approval(text=text, requester=requester, **{**i, "payee": i.get("payee") or "Dr. Rao"}) for i in parse(text)]

@synced
def state():
    for aid in list(ACTIONS): _open(aid)
    return {"actions": sorted(ACTIONS.values(), key=lambda a: a["created"]), "ledger": LEDGER,
            "events": sorted(EVENTS.values(), key=lambda e: (e["date"], e["hour"]))}

@synced
def reset():
    for d in (ACTIONS, TOKENS, BOOKINGS, REVERSE, EVENTS): d.clear()
    LEDGER.clear()

@synced
def status(aid): return dict(_open(aid))
@synced
def ledger_text(): return "\n".join(f"{e['t']} {e['en']}" for e in LEDGER)
