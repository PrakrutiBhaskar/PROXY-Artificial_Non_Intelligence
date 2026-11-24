"""Proxy core: consent gate, capability tokens, undo registry, ledger. In-memory for the MVP."""
import re, time, uuid

RULES = {"auto_approve_under": 0,            # set e.g. 2000 to pre-approve known billers
         "known_billers": ["BESCOM", "BWSSB"], "max_money_actions_per_day": 5}
HARD_BLOCK = ["urgent", "gift card", "kyc", "anydesk", "teamviewer", "ತುರ್ತು", "जरूरी"]
TTL = 2 * 3600
ACTIONS, TOKENS, LEDGER, BOOKINGS, REVERSE = {}, {}, [], {}, {}

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
def request_approval(type, payee, amount=0, slot="", text="", requester="Amma", approver="Pooja"):
    a = dict(id=uuid.uuid4().hex[:6], type=type, payee=payee, amount=amount, slot=slot,
             requester=requester, approver=approver, status="pending", created=time.time())
    a["what"] = describe(a)
    ACTIONS[a["id"]] = a
    money_today = sum(1 for x in ACTIONS.values() if x["type"] != "book" and x["status"] == "done")
    if (any(w in text.lower() for w in HARD_BLOCK) or type == "transfer"
            or money_today >= RULES["max_money_actions_per_day"]):
        a["status"] = "blocked"; log("blocked", approver=approver)
    elif type == "pay_bill" and payee in RULES["known_billers"] and amount <= RULES["auto_approve_under"]:
        approve(a["id"], by="standing rule")
    else:
        log("pending", approver=approver, what=a["what"])
    return a

def _open(aid):
    a = ACTIONS[aid]
    if a["status"] == "pending" and time.time() - a["created"] > TTL:
        a["status"] = "expired"; log("expired", approver=a["approver"], what=a["what"])
    return a

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

def reject(aid):
    a = _open(aid)
    if a["status"] == "pending": a["status"] = "rejected"; log("rejected", approver=a["approver"], what=a["what"])
    return a

def revoke(tok): TOKENS.pop(tok, None)

def _check(tok, action, payee, amount=0):
    t = TOKENS.get(tok)
    if not t: raise PermissionError("no valid consent token")
    if t["uses"] < 1 or t["expires"] < time.time(): raise PermissionError("token used or expired")
    if t["action"] != action or t["payee"] != payee or amount > t["max_amount_inr"]:
        raise PermissionError("token does not cover this action")
    t["uses"] -= 1

# ---- mock action servers (token-gated) -----------------------------------------
def pay_bill(token, biller, amount):
    _check(token, "pay_bill", biller, amount); return {"receipt": "RCPT-" + uuid.uuid4().hex[:6]}
def book(token, provider, slot):
    _check(token, "book", provider); bid = "BK-" + uuid.uuid4().hex[:5]
    BOOKINGS[bid] = dict(provider=provider, slot=slot, active=True); return {"booking_id": bid}
def cancel_booking(bid): BOOKINGS[bid]["active"] = False

# ---- undo-mcp ------------------------------------------------------------------
def _run(a, tok):
    REVERSE[a["id"]] = "raise_refund" if a["type"] == "pay_bill" else "cancel_booking"  # recorded BEFORE running
    try:
        if a["type"] == "pay_bill": a["result"] = pay_bill(tok, a["payee"], a["amount"]); log("paid", **a)
        else: a["result"] = book(tok, a["payee"], a["slot"]); log("booked", **a)
        a["status"] = "done"
    except Exception as e:
        a["status"] = "failed"; a["error"] = str(e)

def undo(aid):
    a = ACTIONS[aid]
    if a["status"] != "done": raise ValueError(f"cannot undo: action is {a['status']}")
    if REVERSE[aid] == "cancel_booking": cancel_booking(a["result"]["booking_id"])
    a["status"] = "undone"; log("undone", what=a["what"])   # payments: a refund request is filed
    return a

# ---- planner (rule-based stand-in for the LLM) ------------------------------------
def plan(text, requester="Amma"):
    t, out = text.lower(), []
    if re.search(r"send|transfer|ಕಳುಹಿಸ|भेज", t):
        m = re.search(r"(\d[\d,]*)", t); amt = int(m.group(1).replace(",", "")) if m else 0
        out.append(request_approval("transfer", "unknown number", amt, text=text))
    if re.search(r"bill|ಬಿಲ್|बिल", t):
        out.append(request_approval("pay_bill", "BESCOM", 1240, text=text))  # amount would come from Gmail
    if re.search(r"book|appointment|checkup|ಅಪಾಯಿಂಟ್|अपॉइंटमेंट", t):
        out.append(request_approval("book", "Dr. Rao", slot="Thursday 11:00", text=text))
    return out

def state():
    for aid in list(ACTIONS): _open(aid)
    return {"actions": sorted(ACTIONS.values(), key=lambda a: a["created"]), "ledger": LEDGER}

def reset():
    for d in (ACTIONS, TOKENS, BOOKINGS, REVERSE): d.clear()
    LEDGER.clear()
