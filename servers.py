"""Four separate MCP servers (streamable HTTP), one process each, sharing state via SQLite.
    python servers.py consent|undo|ledger|actions|gmail|calendar      (app.py starts all four)"""
import sys
from pydantic import Field, create_model
from mcp.server.fastmcp import Context, FastMCP
import core, google_data

PORTS = {"consent": 8765, "undo": 8766, "ledger": 8767, "actions": 8768, "gmail": 8769, "calendar": 8770}

def _slot(day, pref):
    return google_data.suggest_slot(day, pref, core.busy_hours(google_data._next(day).isoformat()))

def build(name):
    m = FastMCP(f"proxy-{name}", host="127.0.0.1", port=PORTS[name])
    if name == "consent":
        @m.tool()
        def request_approval(action: str, payee: str, amount: int = 0, slot: str = "") -> dict:
            """Ask the family approver. action: pay_bill | book | transfer. Returns the pending action; poll status."""
            return core.request_approval(action, payee, amount, slot)
        @m.tool()
        def status(action_id: str) -> dict:
            """Status of an action; once approved it carries the single-use capability token."""
            return core.status(action_id)
        @m.tool()
        def revoke(token: str) -> str:
            core.revoke(token); return "revoked"
    elif name == "undo":
        @m.tool()
        def undo(action_id: str) -> dict:
            """Run the recorded reverse step for a completed action."""
            return core.undo(action_id)
    elif name == "ledger":
        @m.resource("ledger://{requester}/today")
        def ledger(requester: str) -> str:
            return core.ledger_text()
    elif name == "gmail":
        @m.tool()
        def find_bill(biller: str) -> dict:
            """Read-only: latest bill amount for a biller from the requester's Gmail."""
            return google_data.find_bill(biller)
    elif name == "calendar":
        @m.tool()
        def suggest_slot(day: str, preferred: str = "11:00") -> dict:
            """Read-only: first free hour on a weekday, starting at the preferred time."""
            return _slot(day, preferred)
        @m.tool()
        async def choose_appointment(day: str, preferred: str, ctx: Context) -> dict:
            """Ask the requester which appointment they want (MCP form-mode elicitation) instead of guessing."""
            a, b = _slot(day, preferred), _slot(day, "16:00")
            opts = {f"Dr. Rao, {a['slot']}": ("Dr. Rao", a["slot"]), f"Clinic near home, {b['slot']}": ("Clinic near home", b["slot"])}
            Pick = create_model("Pick", choice=(str, Field(description="Which appointment?", json_schema_extra={"enum": list(opts)})))
            r = await ctx.elicit(message="Which appointment do you want? / ಯಾವ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಬೇಕು?", schema=Pick)
            if r.action == "accept" and r.data.choice in opts:       # never trust the reply: must be one of our options
                p, sl = opts[r.data.choice]; return {"payee": p, "slot": sl, "asked": True}
            return {"payee": "Dr. Rao", "slot": a["slot"], "asked": False}      # declined or timed out: default, approver still reviews
    else:
        @m.tool()
        def pay_bill(token: str, biller: str, amount: int) -> dict:
            """Mock payment. Refuses without a valid consent token."""
            return core.pay_bill(token, biller, amount)
        @m.tool()
        def book(token: str, provider: str, slot: str) -> dict:
            """Mock booking. Refuses without a valid consent token."""
            return core.book(token, provider, slot)
    return m

if __name__ == "__main__":
    build(sys.argv[1]).run(transport="streamable-http")
