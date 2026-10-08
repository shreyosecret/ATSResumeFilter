"""Entry point for the packaged desktop app (PyInstaller)."""
import multiprocessing
import os
import sys


def _log_to_file() -> None:
    # A windowed app has no console: send output to a log file the user can find.
    if sys.stdout is None or sys.stderr is None:
        from ats_sim.data import user_dir

        user_dir().mkdir(parents=True, exist_ok=True)
        log = open(user_dir() / "ats-sim.log", "a", buffering=1, encoding="utf-8")
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log


if __name__ == "__main__":
    multiprocessing.freeze_support()
    os.environ.setdefault("ATS_SIM_EMBEDDING_BACKEND", "onnx")  # no PyTorch inside: MiniLM runs on onnxruntime
    _log_to_file()
    from ats_sim.desktop import main

    sys.exit(main())
