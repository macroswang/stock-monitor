#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npm ci
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/package_core.py
npm run tauri -- build
