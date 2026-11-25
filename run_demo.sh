#!/usr/bin/env bash
# Start Proxy for a LOCAL demo. Auth is on: the console prints a sign-in link for each role (open the approver link on
# Pooja's phone/browser, the requester link for Amma). To keep the same keys between runs, export
# PROXY_APPROVER_KEY / PROXY_REQUESTER_KEY / PROXY_SECRET first. Then:  python demo_check.py  (same env vars)
# For the approver's phone: `ngrok http 8000`, export PROXY_BASE_URL=https://<id>.ngrok-free.app before running this.
set -e
cd "$(dirname "$0")"
[ -d .venv ] || { python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt; }
rm -f proxy.db
export PROXY_ALLOW_RESET=1          # demo only: lets the approver wipe state. Never set this on a public deployment.
exec .venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
