#!/bin/bash
# Masq Local — quick start
set -e

cd "$(dirname "$0")"

# Create venv if missing
if [ ! -d venv ]; then
    echo "[masq-local] Creating virtual environment..."
    python3 -m venv venv
fi

# Install deps
source venv/bin/activate
pip install -q -r requirements.txt

# Start server
echo "[masq-local] Starting server on http://localhost:8844"
echo "[masq-local] Models will cold-load on first request."
exec python masq_local_server.py
