"""Entry point for the packaged desktop app (PyInstaller)."""
import multiprocessing
import os
import sys
import traceback
from pathlib import Path


def _user_dir() -> Path:
    # Same rule as ats_sim.data.user_dir, repeated here so the log opens before
    # anything that could fail is imported.
    base = os.environ.get("APPDATA") if os.name == "nt" else os.environ.get("XDG_DATA_HOME")
    return Path(base) / "ats_sim" if base else Path.home() / ".ats_sim"


def _open_log():
    try:
        _user_dir().mkdir(parents=True, exist_ok=True)
        return open(_user_dir() / "ats-sim.log", "a", buffering=1, encoding="utf-8")
    except OSError:
        return None


if __name__ == "__main__":
    multiprocessing.freeze_support()
    log = _open_log()
    # A windowed app has no console: its output goes to the log the user can find.
    if log is not None:
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log
        import faulthandler

        faulthandler.enable(log)
        if os.environ.get("ATS_SIM_DUMP_AFTER"):  # CI: show where a hung start-up is stuck
            faulthandler.dump_traceback_later(int(os.environ["ATS_SIM_DUMP_AFTER"]), repeat=True, file=log)
        print("starting ATS Simulator", sys.version.split()[0], sys.platform, flush=True)
    os.environ.setdefault("ATS_SIM_EMBEDDING_BACKEND", "onnx")  # no PyTorch inside: MiniLM runs on onnxruntime
    try:
        from ats_sim.desktop import main

        code = main()
    except SystemExit as e:
        code = e.code
    except BaseException:
        traceback.print_exc(file=log or sys.stderr)
        code = 1
    sys.exit(code)
