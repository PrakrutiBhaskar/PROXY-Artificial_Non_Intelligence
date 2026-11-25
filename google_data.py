"""Read-only Gmail + Calendar lookups. Live when GOOGLE_TOKEN_FILE points to an authorized-user token.json
(scopes gmail.readonly, calendar.readonly); otherwise seeded mock data so the demo runs offline."""
import datetime as dt, os, re

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MOCK_BUSY = {9, 15}                       # mock calendar: 09:00 and 15:00 are taken

def _live(): return bool(os.environ.get("GOOGLE_TOKEN_FILE"))
def _svc(name, ver):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    return build(name, ver, credentials=Credentials.from_authorized_user_file(os.environ["GOOGLE_TOKEN_FILE"]))

def find_bill(biller):
    if not _live():
        return {"biller": biller, "amount": 1240, "source": "mock", "snippet": f"Your {biller} bill of ₹1,240 is due."}
    g = _svc("gmail", "v1")
    for m in g.users().messages().list(userId="me", q=f"{biller} bill newer_than:45d", maxResults=3).execute().get("messages", []):
        sn = g.users().messages().get(userId="me", id=m["id"], format="metadata").execute().get("snippet", "")
        x = re.search(r"(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d+)?)", sn)
        if x: return {"biller": biller, "amount": int(float(x.group(1).replace(",", ""))), "source": "gmail", "snippet": sn[:120]}
    return {"biller": biller, "amount": None, "source": "gmail", "snippet": "no recent bill email found"}

def _next(day):
    d, want = dt.date.today(), DAYS.index(day.lower())
    return d + dt.timedelta(days=(want - d.weekday()) % 7 or 7)

def suggest_slot(day, preferred="11:00", extra_busy=()):
    """extra_busy: hours already taken by events Proxy added (known to core, not to Google in mock mode)."""
    date, pref = _next(day), int(preferred.split(":")[0])
    busy = set(extra_busy) | (set() if _live() else MOCK_BUSY)
    if _live():
        c = _svc("calendar", "v3"); t0 = dt.datetime.combine(date, dt.time()).astimezone()
        evs = c.events().list(calendarId="primary", timeMin=t0.isoformat(), timeMax=(t0 + dt.timedelta(days=1)).isoformat(),
                              singleEvents=True).execute().get("items", [])
        busy |= {dt.datetime.fromisoformat(e["start"]["dateTime"]).hour for e in evs if "dateTime" in e["start"]}
    hour = next((h for h in [*range(pref, 18), *range(9, pref)] if h not in busy), pref)
    return {"slot": f"{day.title()} {hour:02d}:00", "date": date.isoformat(), "source": "calendar" if _live() else "mock"}

def create_event(title, date, hour):
    """Needs a token with the calendar.events scope (read-only tokens fail here, and the booking proceeds without an event)."""
    start = dt.datetime.combine(dt.date.fromisoformat(date), dt.time(hour)).astimezone()
    body = {"summary": title, "start": {"dateTime": start.isoformat()}, "end": {"dateTime": (start + dt.timedelta(hours=1)).isoformat()}}
    return _svc("calendar", "v3").events().insert(calendarId="primary", body=body).execute()["id"]

def delete_event(gid): _svc("calendar", "v3").events().delete(calendarId="primary", eventId=gid).execute()
