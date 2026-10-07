#!/bin/bash
# macOS: double-click to open the ATS Simulator (first run sets everything up).
cd "$(dirname "$0")/.." || exit 1
exec bash launchers/run.sh
