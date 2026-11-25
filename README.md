# Proxy MVP (wHACKiest 2026, Track 1)
Delegated AI with family approval and undo. Demo path: ask -> approve/edit -> run -> hard-block scam -> undo.

    python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
    uvicorn app:app --port 8000        # UI at http://localhost:8000, MCP servers at http://127.0.0.1:8765-8768/mcp

Voice: Chrome (SpeechRecognition + speechSynthesis; kn-IN needs a Kannada voice installed). Swap in ElevenLabs/Transcribe later.

| File | Role |
|---|---|
| core.py | consent gate, single-use capability tokens, undo registry, ledger, mock payments/bookings, keyword planner; state shared via SQLite (proxy.db) |
| servers.py | four separate MCP servers, one process each: consent :8765, undo :8766, ledger :8767 (`ledger://{requester}/today`), mock payments+bookings :8768 |
| test_mcp.py | cross-process check using real MCP clients (run while the app is up) |
| planner.py | optional LLM planner with keyword fallback |
| app.py, static/index.html | side-by-side Amma / Pooja demo UI |

Set ANTHROPIC_API_KEY to use the LLM planner (planner.py); otherwise keyword rules run.

Not built yet: URL-mode elicitation, push/WhatsApp to the approver, Gmail/Calendar servers.
