"""Proxy MCP server (consent + undo + ledger + mock action tools), streamable HTTP on :8765.
Any MCP client can connect. In the MVP the three servers share one process; split them later."""
from mcp.server.fastmcp import FastMCP
import core

mcp = FastMCP("proxy", host="127.0.0.1", port=8765)

@mcp.tool()
def consent_request_approval(action: str, payee: str, amount: int = 0, slot: str = "") -> dict:
    """Ask the family approver. action: pay_bill | book | transfer. Returns the pending action (poll consent_status)."""
    return core.request_approval(action, payee, amount, slot)
@mcp.tool()
def consent_status(action_id: str) -> dict:
    """Status of an action and, once approved, its single-use capability token."""
    return core._open(action_id)
@mcp.tool()
def consent_revoke(token: str) -> str:
    core.revoke(token); return "revoked"
@mcp.tool()
def payments_pay_bill(token: str, biller: str, amount: int) -> dict:
    """Mock payment. Fails without a valid consent token."""
    return core.pay_bill(token, biller, amount)
@mcp.tool()
def bookings_book(token: str, provider: str, slot: str) -> dict:
    """Mock booking. Fails without a valid consent token."""
    return core.book(token, provider, slot)
@mcp.tool()
def undo_undo(action_id: str) -> dict:
    return core.undo(action_id)
@mcp.resource("ledger://{requester}/today")
def ledger(requester: str) -> str:
    return "\n".join(f"{e['t']} {e['en']}" for e in core.LEDGER)

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
