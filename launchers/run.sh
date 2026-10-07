#!/bin/bash
# Linux/macOS launcher. Creates a private virtual environment on first run,
# installs the app into it, then opens the app.
set -e
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/ats-sim ]; then
  echo "First run: setting up (a few minutes, once)..."
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip >/dev/null
  .venv/bin/python -m pip install -e ".[embeddings,desktop]"
  .venv/bin/python -m spacy download en_core_web_sm
fi
exec .venv/bin/ats-sim "$@"
