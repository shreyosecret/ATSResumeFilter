@echo off
rem Windows: double-click to open the ATS Simulator (first run sets everything up).
cd /d "%~dp0\.."
if not exist ".venv\Scripts\ats-sim.exe" (
  echo First run: setting up (a few minutes, once)...
  py -3 -m venv .venv || python -m venv .venv
  .venv\Scripts\python -m pip install --upgrade pip
  .venv\Scripts\python -m pip install -e ".[embeddings,desktop]"
  .venv\Scripts\python -m spacy download en_core_web_sm
)
.venv\Scripts\ats-sim.exe %*
