"""An optional check for a newer release, off until the person turns it on.

The app otherwise never goes online. When the check is on, it asks GitHub for
the latest release's version number (one HTTPS request, no resume data) at
most every few hours, and the app shows a link if a newer one exists.
"""
from __future__ import annotations

import json
import re
import time
import urllib.request

from . import __version__
from .data import user_dir

RELEASES = "https://github.com/shreyosecret/ATSResumeFilter/releases"
LATEST_API = "https://api.github.com/repos/shreyosecret/ATSResumeFilter/releases/latest"
CACHE_SECONDS = 6 * 3600
_cache: dict = {}


def _settings_path():
    return user_dir() / "settings.json"


def settings() -> dict:
    try:
        d = json.loads(_settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    return {"check_updates": bool(d.get("check_updates", False))}


def save_settings(**changes) -> dict:
    d = settings()
    d.update({k: bool(v) for k, v in changes.items() if k in d})
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(d, indent=2), encoding="utf-8")
    return d


def _version(tag: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", tag)[:3])


def _fetch_latest() -> str:
    req = urllib.request.Request(LATEST_API, headers={"Accept": "application/vnd.github+json",
                                                      "User-Agent": f"ats-simulator/{__version__}"})
    with urllib.request.urlopen(req, timeout=6) as r:
        return json.loads(r.read().decode("utf-8"))["tag_name"]


def check(fetch=_fetch_latest) -> dict:
    """{"enabled", "current", "latest", "newer", "url"}; does nothing online when off."""
    out = {"enabled": settings()["check_updates"], "current": __version__, "latest": None, "newer": False,
           "url": RELEASES + "/latest"}
    if not out["enabled"]:
        return out
    if _cache.get("at", 0) > time.time() - CACHE_SECONDS:
        latest = _cache["latest"]
    else:
        try:
            latest = fetch()
        except Exception as e:  # offline, rate-limited: say so, never fail the app
            return {**out, "error": f"Could not reach GitHub ({type(e).__name__})."}
        _cache.update(at=time.time(), latest=latest)
    return {**out, "latest": latest.lstrip("v"), "newer": _version(latest) > _version(__version__)}
