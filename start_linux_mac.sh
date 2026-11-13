#!/usr/bin/env bash
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is not installed. Install it first (e.g. sudo apt install python3 python3-venv python3-pip)"; exit 1
fi
[ -d .venv ] || python3 -m venv .venv || { echo "Install venv: sudo apt install python3-venv"; exit 1; }
.venv/bin/python -m pip install -r requirements.txt -q
exec .venv/bin/python run.py "$@"
