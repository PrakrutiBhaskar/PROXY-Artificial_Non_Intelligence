#!/usr/bin/env bash
# Start Proxy for the demo. Binds 0.0.0.0 so a phone on the same Wi-Fi (or an ngrok tunnel) can open the approver link.
#   ./run_demo.sh            then in another terminal:  python demo_check.py
# For the approver's phone: `ngrok http 8000`, then export PROXY_BASE_URL=https://<id>.ngrok-free.app BEFORE running this.
set -e
cd "$(dirname "$0")"
[ -d .venv ] || { python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt; }
rm -f proxy.db
exec .venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
