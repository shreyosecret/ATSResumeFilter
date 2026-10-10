"""Check that a running desktop build has every feature, from its /api/meta
and one /api/analyze response (engines and deep skill scan on).

    python scripts/check_full_package.py meta.json analysis.json --engines openresume,pyresparser

Exits non-zero, listing what is missing, so CI fails before a release.
"""
import argparse
import json
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("meta")
    ap.add_argument("analysis")
    ap.add_argument("--engines", default="openresume,pyresparser")
    a = ap.parse_args()
    meta = json.load(open(a.meta, encoding="utf-8"))
    r = json.load(open(a.analysis, encoding="utf-8"))
    want = [e for e in a.engines.split(",") if e]
    checks = {
        "semantic scorer (MiniLM)": "MiniLM" in (meta.get("embedding_backend") or ""),
        "ranking pool with real resumes": meta["pool"]["public"] > 0,
        "visual check (OCR)": bool(meta["engines"].get("visual")) and isinstance(r.get("visual"), dict)
        and "visible_letters" in r["visual"],
        "deep skill scan (SkillNer)": bool(meta["engines"].get("skillner")) and bool(r["skills"].get("skillner")),
        "learned parser": "learned" in r["parsers"] and bool(r.get("lines")),
        "parsing risks": bool(r.get("risks")),
        "job matches": bool(r.get("matches")),
        "report download": bool(r.get("report_md")),
    }
    for e in want:
        checks[f"{e} parser"] = bool(meta["engines"].get(e)) and e in r["parsers"]
    if want:
        checks["combined vote"] = "ensemble" in r["parsers"]
    width = max(map(len, checks))
    for name, ok in checks.items():
        print(f"  {name.ljust(width)}  {'ok' if ok else 'MISSING'}")
    print(f"  pool: {meta['pool']}; parsers: {list(r['parsers'])}")
    bad = [k for k, ok in checks.items() if not ok]
    if bad:
        print("missing:", ", ".join(bad))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
