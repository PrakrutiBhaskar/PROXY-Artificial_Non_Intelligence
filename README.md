# Proxy MVP (wHACKiest 2026, Track 1)
Delegated AI with family approval and undo. Demo path: ask -> approve/edit -> run -> hard-block scam -> undo.

    python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
    uvicorn app:app --port 8000        # UI at http://localhost:8000, MCP servers at http://127.0.0.1:8765-8768/mcp

Config: copy the variables you need from `.env.example`. With nothing set, everything runs offline.

Voice: with ELEVENLABS_API_KEY the mic records and sends audio to Scribe, and read-back plays ElevenLabs TTS. Without it the app uses Chrome's built-in speech.
Approver: each pending action sends a WhatsApp message (or a console line) with a signed link; the link opens a card with Approve / Reject.

| File | Role |
|---|---|
| core.py | consent gate, single-use capability tokens, undo registry, ledger, mock payments/bookings, keyword planner; state shared via SQLite (proxy.db) |
| servers.py | six MCP servers, one process each: consent :8765, undo :8766, ledger :8767 (`ledger://{requester}/today`), mock payments+bookings :8768, gmail :8769, calendar :8770 (both read-only) |
| voice.py, notify.py, google_data.py | ElevenLabs voice, WhatsApp + signed approval links, Gmail/Calendar lookups (mock data unless GOOGLE_TOKEN_FILE is set) |
| check_live.py | pre-flight with real keys (voice round trip in kn/hi/ta/en, planner, WhatsApp, Google); `--audio clip.webm` transcribes a real recording |
| demo_check.py, test_scams.py | headless run of the whole 3-minute demo path; offline scam-phrase suite (en/kn/hi/ta) |
| run_demo.sh | clean start on 0.0.0.0 for a phone or ngrok tunnel |
| test_integrations.py | planner via Gmail/Calendar MCP, approver link, voice request shapes |
| test_mcp.py | cross-process check using real MCP clients (run while the app is up) |
| planner.py | optional LLM planner with keyword fallback |
| app.py, static/index.html | side-by-side Amma / Pooja demo UI |

Set ANTHROPIC_API_KEY to use the LLM planner (planner.py); otherwise keyword rules run.

Untested against live services (no credentials in the build sandbox): ElevenLabs, WhatsApp, Google, Anthropic. Their request shapes are checked against fakes only.

Clarifying question: when the person names no provider, the Calendar MCP server asks via form-mode elicitation ("Dr. Rao 11:00 or clinic near home 16:00?"). The UI shows and speaks it; the answer is tapped, not yet spoken. No answer in 2 minutes = default provider, and the approver still reviews.

Before each demo: `./run_demo.sh`, then `python demo_check.py` (must exit 0). Backup video: record it from a passing run.

Calendar loop: an approved booking adds a calendar event (shown in Amma's panel) and undo removes it. Writes happen only inside the token-checked booking call, so the Calendar MCP server stays read-only; the booked hour then shows as busy to later slot suggestions. For real Google Calendar the token needs the `calendar.events` scope; with a read-only token the booking still succeeds but no event is created (the server console says so).

Known gaps: URL-mode elicitation for the payment step (it needs actions to run after the approval commits, not inside it; today payments are mocked in-process), answering the question by voice, Web Push (WhatsApp only), WhatsApp templates for production, URL-mode elicitation, second approver, OAuth between servers. If Gmail finds no bill email, the planner keeps the ₹1,240 demo default; the approver still sees the exact amount.
