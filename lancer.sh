#!/usr/bin/env bash
# Lance pax en local, sans YunoHost : ./lancer.sh puis http://127.0.0.1:8800
set -euo pipefail
cd "$(dirname "$0")"
[ -d venv ] || python3 -m venv venv
venv/bin/pip install -q -r requirements.txt
export PAX_DEV_UTILISATEUR="${PAX_DEV_UTILISATEUR:-dev}"
exec venv/bin/python -m uvicorn --factory app.main:creer_app --host 127.0.0.1 --port "${PORT:-8800}"
