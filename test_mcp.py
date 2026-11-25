"""Cross-process check: the web app creates an action; MCP clients on separate servers see and use it.
Run with the app already up:  python test_mcp.py"""
import asyncio, json, urllib.request as u
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from _http import web

async def call(port, tool, **args):
    async with streamablehttp_client(f"http://127.0.0.1:{port}/mcp") as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.call_tool(tool, args)
            return ("ERROR " if res.isError else "ok ") + res.content[0].text[:80]

async def main():
    web("reset")
    a = web("ask", {"text": "pay the bill"})[0]
    print("pay without token   :", await call(8768, "pay_bill", token="cap_fake", biller="BESCOM", amount=1240))
    print("consent sees pending:", (await call(8765, "status", action_id=a["id"]))[:70])
    tok = web(f"approve/{a['id']}", {})["token"]
    print("after approval      :", tok, "| consent status ->", (await call(8765, "status", action_id=a["id"]))[:60])
    print("reuse spent token   :", await call(8768, "pay_bill", token=tok, biller="BESCOM", amount=1240))
    print("undo server         :", (await call(8766, "undo", action_id=a["id"]))[:60])

asyncio.run(main())
