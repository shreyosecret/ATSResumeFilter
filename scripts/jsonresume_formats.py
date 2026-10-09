"""JSON Resume themes: real third-party designs, rendered from the personas.

    python scripts/jsonresume_formats.py --list       # MIT themes on npm -> data/jsonresume_themes.json
    python scripts/jsonresume_formats.py --render     # npm install, render, print to PDF (data/resumes/jsonresume/)
    python scripts/jsonresume_formats.py --evaluate   # -> results/jsonresume/

Each theme is installed from npm into build/jsonresume (install scripts off)
and run with Node to turn a persona's JSON Resume into HTML, which Chromium
prints to a Letter-size PDF. Nothing from the themes is committed: only the
list of themes used (name, version, license) and aggregate results.

Measured per theme, on the 16 personas: field F1 of the simple and
layout-aware parsers (the answer key is the persona) and of the app's
network (text only, trained on the synthetic corpus, which never saw these
themes), and the network's line accuracy.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BUILD = ROOT / "build" / "jsonresume"
PDF_DIR = ROOT / "data" / "resumes" / "jsonresume"
LIST = ROOT / "data" / "jsonresume_themes.json"
OUT = ROOT / "results" / "jsonresume"
PERMISSIVE = {"MIT", "ISC", "BSD-2-Clause", "BSD-3-Clause", "Apache-2.0", "0BSD", "Unlicense", "CC0-1.0"}
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"


def slug(name: str) -> str:
    return re.sub(r"^@[^/]+/", "", name).replace("jsonresume-theme-", "").replace("/", "-")


def list_themes() -> list[dict]:
    out, frm = [], 0
    while True:
        url = f"https://registry.npmjs.org/-/v1/search?text=keywords:jsonresume-theme&size=250&from={frm}"
        d = json.loads(urllib.request.urlopen(url, timeout=60).read())
        out += d["objects"]
        frm += len(d["objects"])
        if not d["objects"] or frm >= d["total"]:
            break
    themes = [{"name": o["package"]["name"], "version": o["package"]["version"],
               "license": o["package"].get("license")} for o in out]
    themes = sorted((t for t in themes if t["license"] in PERMISSIVE), key=lambda t: t["name"])
    LIST.write_text(json.dumps({"source": "npm registry, keyword jsonresume-theme", "themes": themes}, indent=1),
                    encoding="utf-8")
    print(f"{len(themes)} permissively licensed themes of {len(out)} -> {LIST}")
    return themes


def render_all() -> None:
    from playwright.sync_api import sync_playwright

    from ats_sim.data import load_personas
    from ats_sim.jsonresume import to_jsonresume

    themes = json.loads(LIST.read_text(encoding="utf-8"))["themes"]
    BUILD.mkdir(parents=True, exist_ok=True)
    if not (BUILD / "package.json").exists():
        (BUILD / "package.json").write_text('{"name": "jr-render", "private": true}', encoding="utf-8")
    for t in themes:
        if not (BUILD / "node_modules" / t["name"]).exists():
            subprocess.run(["npm", "install", "--no-audit", "--no-fund", "--ignore-scripts", f"{t['name']}@{t['version']}"],
                           cwd=BUILD, capture_output=True, timeout=300)
    personas = load_personas()
    (BUILD / "resumes").mkdir(exist_ok=True)
    jobs = []
    for p in personas:
        rp = BUILD / "resumes" / f"{p['id']}.json"
        rp.write_text(json.dumps(to_jsonresume(p), indent=1), encoding="utf-8")
        for t in themes:
            jobs.append({"theme": t["name"], "resume": str(rp), "out": str(BUILD / "html" / slug(t["name"]) / f"{p['id']}.html")})
    (BUILD / "jobs.json").write_text(json.dumps(jobs), encoding="utf-8")
    r = subprocess.run(["node", str(ROOT / "scripts" / "jsonresume" / "render.js"), str(BUILD / "jobs.json")],
                       cwd=BUILD, capture_output=True, text=True, timeout=3600)
    fails = sorted({line.split(" ", 2)[1] + ": " + line.split(" ", 2)[2] for line in r.stdout.splitlines()
                    if line.startswith("fail")})
    print(f"rendered {r.stdout.count('ok ')} of {len(jobs)}; failing themes:", *fails[:80], sep="\n  ")
    import os

    exe = os.environ.get("ATS_SIM_CHROMIUM")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(**({"executable_path": exe} if exe else {}))
        page = browser.new_page()
        for html in sorted((BUILD / "html").glob("*/*.html")):
            pdf = PDF_DIR / html.parent.name / f"{html.stem}.pdf"
            if pdf.exists():
                continue
            pdf.parent.mkdir(parents=True, exist_ok=True)
            try:
                page.goto(html.as_uri(), wait_until="networkidle", timeout=20000)
            except Exception:
                pass  # print what loaded (a font that never arrives falls back)
            page.pdf(path=str(pdf), format="Letter", print_background=True)
        browser.close()
    print("PDFs in", PDF_DIR)


def evaluate(seed: int = 0) -> dict:
    import numpy as np
    import pandas as pd

    from ats_sim.data import load_personas
    from ats_sim.evaluate import micro, score_resume
    from ats_sim.jsonresume import label_lines, theme_headings
    from ats_sim.learn.geometry import read
    from ats_sim.learn.tagger import LineTagger, parse_with_tagger, sections_from_labels
    from ats_sim.parser import parse_resume, parse_with_sections

    personas = {p["id"]: p for p in load_personas()}
    tagger = LineTagger(use_geometry=False, seed=seed).fit(_corpus())
    rows = []
    for d in sorted(PDF_DIR.iterdir()):
        for pdf in sorted(d.glob("*.pdf")):
            p = personas[pdf.stem]
            lines_geo = read(pdf)
            lines = [r.text for r in lines_geo]
            if sum(len(x) for x in lines) < 200:  # printed blank: the theme needs a browser feature or asset it did not get
                continue
            html = (BUILD / "html" / d.name / f"{pdf.stem}.html").read_text(encoding="utf-8", errors="replace")
            gold = label_lines(lines, p, theme_headings(html, p))
            text = "\n".join(lines)
            parsed, _, pred = parse_with_tagger(text, tagger, geo=[r.geo for r in lines_geo])
            sections, name = sections_from_labels(lines, gold)
            rows.append({
                "theme": d.name, "persona": pdf.stem,
                "naive": score_resume(p, parse_resume(pdf)), "layout_aware": score_resume(p, parse_resume(pdf, layout_aware=True)),
                "network": score_resume(p, parsed), "oracle": score_resume(p, parse_with_sections(text, sections, name=name)),
                "line_hits": sum(a == b for a, b in zip(pred, gold)), "lines": len(gold),
            })
    themes = sorted({r["theme"] for r in rows})
    per = []
    for t in themes:
        sub = [r for r in rows if r["theme"] == t]
        per.append({"theme": t, "resumes": len(sub),
                    **{k: round(micro([r[k] for r in sub]).f1, 3) for k in ("naive", "layout_aware", "network", "oracle")},
                    "line_acc": round(sum(r["line_hits"] for r in sub) / sum(r["lines"] for r in sub), 3)})
    df = pd.DataFrame(per)
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / "jsonresume_themes.csv", index=False)
    s = {"themes": len(themes), "resumes": len(rows),
         **{k: round(micro([r[k] for r in rows]).f1, 3) for k in ("naive", "layout_aware", "network", "oracle")},
         "line_acc": round(sum(r["line_hits"] for r in rows) / sum(r["lines"] for r in rows), 3),
         "naive_below_0_5": int((df.naive < 0.5).sum()),
         "per_theme_median": {k: float(np.median(df[k])) for k in ("naive", "layout_aware", "network")}}
    (OUT / "summary.json").write_text(json.dumps(s, indent=2), encoding="utf-8")
    chart(df, OUT / "jsonresume_themes.png")
    print(json.dumps(s, indent=2))
    return s


def _corpus() -> list:
    from ats_sim.formats import SPECS
    from ats_sim.learn.corpus import documents, format_documents

    return list(documents().values()) + list(format_documents(tuple(SPECS), per_persona=2).values())


def chart(df, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
        "text.color": INK, "axes.grid": True, "grid.color": GRID, "axes.axisbelow": True,
        "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False, "font.size": 9,
        "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlelocation": "left", "legend.frameon": False,
    })
    df = df.sort_values("naive")
    fig, ax = plt.subplots(figsize=(12, 4.6))
    x = range(len(df))
    ax.plot(x, df.naive, "o", color="#9a9893", ms=4, label="Simple parser")
    ax.plot(x, df.layout_aware, "o", color="#eb6834", ms=4, label="Layout-aware parser")
    ax.plot(x, df.network, "o", color="#2a78d6", ms=4, label="Network (app)")
    ax.set_xticks(list(x), df.theme, rotation=90, fontsize=6.5)
    ax.set_ylim(0, 1.02)
    ax.set_ylabel("Field F1 (16 personas)")
    ax.set_title(f"{len(df)} JSON Resume themes from npm, sorted by the simple parser's score")
    ax.legend(loc="lower right", ncol=3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--evaluate", action="store_true")
    a = ap.parse_args()
    if a.list:
        list_themes()
    if a.render:
        render_all()
    if a.evaluate:
        evaluate()


if __name__ == "__main__":
    main()
