"""Four separate MCP servers (streamable HTTP), one process each, sharing state via SQLite.
    python servers.py consent|undo|ledger|actions      (app.py starts all four)"""
import sys
from mcp.server.fastmcp import FastMCP
import core

PORTS = {"consent": 8765, "undo": 8766, "ledger": 8767, "actions": 8768}

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
