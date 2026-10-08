"""Launch the ATS Simulator app.

    ats-sim                  # opens a native window (pip install "ats-sim[desktop]"), else your browser
    ats-sim --browser        # always use the browser
    ats-sim --no-open        # just serve, for example on a remote machine with port forwarding
    python -m ats_sim        # same as ats-sim

The server listens on 127.0.0.1 only, so nothing on the network can reach it.
"""
from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
import urllib.request
import webbrowser


def free_port(preferred: int) -> int:
    for port in (preferred, 0):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("no free port")


def wait_until_up(url: str, timeout: float = 30) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url + "api/status", timeout=1)
            return True
        except Exception:
            time.sleep(0.2)
    return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ats-sim", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--browser", action="store_true", help="open in the default browser instead of a native window")
    ap.add_argument("--no-open", action="store_true", help="do not open anything; just serve")
    ap.add_argument("--no-public-pool", action="store_true", help="rank only against the 16 synthetic resumes")
    ap.add_argument("--no-learning", action="store_true", help="turn off the learned parser and the Teach tab")
    ap.add_argument("--quit-when-idle", type=float, default=None, metavar="MINUTES",
                    help="in browser mode, quit after the page has been closed this long "
                         "(default: 3 in the packaged app, never otherwise)")
    args = ap.parse_args(argv)

    print("loading", flush=True)
    import uvicorn

    from .webapp.server import create_app

    kwargs = {"public_pool": False} if args.no_public_pool else {}
    app = create_app(kwargs, model_store=not args.no_learning)
    port = free_port(args.port)
    url = f"http://127.0.0.1:{port}/"
    print(f"serving on {url}", flush=True)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    if not wait_until_up(url):
        print("The app server did not start.", file=sys.stderr)
        return 1
    print(f"ATS Simulator is running at {url}  (Ctrl+C to quit)")

    if not args.no_open and not args.browser:
        try:
            import webview  # pywebview

            webview.create_window("ATS Simulator", url, width=1320, height=880, min_size=(900, 640))
            webview.start()  # blocks until the window closes
            server.should_exit = True
            return 0
        except ImportError:
            print('Tip: pip install "ats-sim[desktop]" to open in its own window.')
        except Exception as e:  # no GUI toolkit available, for example
            print(f"Could not open a native window ({e}); using the browser.")
    if not args.no_open:
        webbrowser.open(url)
    idle = args.quit_when_idle
    if idle is None and getattr(sys, "frozen", False) and not args.no_open:
        idle = 3.0  # a packaged app has no terminal to stop it from, so it stops itself
    try:
        while thread.is_alive():
            thread.join(0.5)
            if idle and time.time() - app.state.last_request > idle * 60:
                server.should_exit = True
    except KeyboardInterrupt:
        server.should_exit = True
    return 0


if __name__ == "__main__":
    sys.exit(main())
