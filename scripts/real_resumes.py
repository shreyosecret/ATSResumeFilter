"""Experiment 9: parsing 2,484 real resumes, labeled from their own HTML.

Every other test of the parsers uses resumes this project rendered from
fictional personas. This one uses the public LiveCareer resumes (Kaggle
"Resume Dataset", snehaanbhawal/resume-dataset, CC0 1.0): real people's
wording and real headings, anonymized by the dataset's author. Each resume's
HTML marks its sections, so every PDF line gets a label without anyone
reading it (ats_sim/learn/livecareer.py).

Their layout is not varied: nearly all are the same plain single-column page.
So this tests real wording, not real layouts.

Measured, as share of lines labeled correctly (lines whose label could be
told; the name slot holds a job title and is not scored):

  rules      the heading-list parser: a line that exactly matches a known
             heading starts that section
  text, headings, geometry
             the three versions of the network from experiment 7, trained on
             the app's full synthetic corpus (the app ships "text")
  taught k   the app's network after the Teach tab's update on k corrected
             real resumes (3 draws each), tested on 500 others

Also: how often the real resumes' headings are in the parser's heading list.

    python scripts/fetch_public_resumes.py --pdfs   # once
    python scripts/real_resumes.py                  # -> results/real/

Only aggregate numbers are written to results/; the per-resume cache stays in
the gitignored results/_tmp/.
"""
from __future__ import annotations

import argparse
import collections
import copy
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import joblib  # noqa: E402
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from ats_sim.parser import _HEADING_LOOKUP, normalize_heading  # noqa: E402

CSV = ROOT / "data" / "kaggle" / "Resume.csv"
PDFS = ROOT / "data" / "kaggle" / "pdf"
CACHE = ROOT / "results" / "_tmp" / "livecareer_docs.joblib"
OUT = ROOT / "results" / "real"
SECTIONS = ("summary", "experience", "education", "skills", "heading", "other")
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
RULE_LABEL = {"education": "education", "experience": "experience", "skills": "skills", "projects": "projects",
              "contact": "contact"}  # the parser's other sections (and the header) map to "other"


def _one(args):
    rid, cat, html = args
    from ats_sim.learn.geometry import read
    from ats_sim.learn.livecareer import gold_labels

    path = PDFS / cat / f"{rid}.pdf"
    try:
        rows = read(path)
    except Exception:
        return None
    lines = [r.text for r in rows]
    return {"id": int(rid), "category": cat, "lines": lines, "geo": [r.geo for r in rows],
            "gold": gold_labels(lines, html)}


def load_docs(workers: int) -> list[dict]:
    if CACHE.exists():
        return joblib.load(CACHE)
    df = pd.read_csv(CSV)
    jobs = [(r.ID, r.Category, r.Resume_html) for r in df.itertuples()]
    print(f"reading and labeling {len(jobs)} PDFs ...", flush=True)
    with ProcessPoolExecutor(workers) as ex:
        docs = [d for d in ex.map(_one, jobs, chunksize=8) if d and d["lines"]]
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(docs, CACHE)
    return docs


def rules_labels(lines: list[str]) -> list[str]:
    """Line labels as the heading-list parser (parser.split_sections) assigns them."""
    out, current = [], "header"
    for line in lines:
        key = _HEADING_LOOKUP.get(normalize_heading(line))
        if key:
            current = key
            out.append("heading")
        else:
            out.append(RULE_LABEL.get(current, "other"))
    return out


def score(pred_docs: list[list[str]], docs: list[dict]) -> dict:
    hit = tot = 0
    per = collections.Counter()
    per_tot = collections.Counter()
    for pred, d in zip(pred_docs, docs):
        for p, g in zip(pred, d["gold"]):
            if g is None:
                continue
            tot += 1
            per_tot[g] += 1
            if p == g:
                hit += 1
                per[g] += 1
    return {"line_acc": round(hit / tot, 3), "lines": tot,
            **{f"recall_{s}": round(per[s] / per_tot[s], 3) for s in SECTIONS if per_tot[s]}}


def base_corpus() -> list:
    from ats_sim.formats import SPECS
    from ats_sim.learn.corpus import documents, format_documents

    docs = list(documents().values())
    docs += list(format_documents(tuple(SPECS), per_persona=2).values())
    return docs


def heading_coverage(docs: list[dict]) -> dict:
    heads = collections.Counter(normalize_heading(l) for d in docs for l, g in zip(d["lines"], d["gold"])
                                if g == "heading")
    known = sum(c for h, c in heads.items() if h in _HEADING_LOOKUP)
    return {"heading_lines": sum(heads.values()), "in_heading_list": round(known / sum(heads.values()), 3),
            "most_common_unknown": [[h, c] for h, c in heads.most_common(200) if h not in _HEADING_LOOKUP][:12]}


def chart(s: dict, path: Path) -> None:
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
        "text.color": INK, "axes.grid": True, "grid.color": GRID, "axes.axisbelow": True,
        "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False, "font.size": 10,
        "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlelocation": "left", "legend.frameon": False,
    })
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.2), gridspec_kw={"width_ratios": [1.15, 1]})
    names = [("rules", "Heading list"), ("text", "Network: text\n(app)"), ("headings", "Network:\nheadings"),
             ("geometry", "Network:\ngeometry")]
    vals = [s["models"][k]["line_acc"] for k, _ in names]
    bars = a1.bar(range(len(names)), vals, color=["#9a9893", "#2a78d6", "#7aa9e8", "#eb6834"], width=0.6)
    for b, v in zip(bars, vals):
        a1.text(b.get_x() + b.get_width() / 2, v + 0.01, f"{v:.2f}", ha="center", va="bottom", fontsize=9, color=INK2)
    a1.set_xticks(range(len(names)), [n for _, n in names], fontsize=9)
    a1.set_ylim(0, 1.05)
    a1.set_title(f"Lines labeled correctly, {s['resumes']} real resumes")
    ks = sorted(s["taught"], key=int)
    mean = [s["taught"][k]["mean"] for k in ks]
    lo = [s["taught"][k]["mean"] - s["taught"][k]["min"] for k in ks]
    hi = [s["taught"][k]["max"] - s["taught"][k]["mean"] for k in ks]
    a2.errorbar(range(len(ks)), mean, yerr=[lo, hi], color="#2a78d6", marker="o", capsize=3, lw=2)
    for i, v in enumerate(mean):
        a2.text(i, v + 0.012, f"{v:.2f}", ha="center", va="bottom", fontsize=9, color=INK2)
    a2.set_xticks(range(len(ks)), [f"{k}" for k in ks])
    a2.set_xlabel("Corrected real resumes taught")
    a2.set_ylim(0.5, 1.02)
    a2.set_title("Teaching the app's network (500 other resumes)")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--teach", default="0,10,50,200")
    ap.add_argument("--draws", type=int, default=3)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--replot", action="store_true")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    if a.replot:
        chart(json.loads((a.out / "summary.json").read_text(encoding="utf-8")), a.out / "real_resumes.png")
        return
    from ats_sim.learn.tagger import LineTagger

    docs = load_docs(a.workers)
    labeled = sum(g is not None for d in docs for g in d["gold"])
    total = sum(len(d["gold"]) for d in docs)
    print(f"{len(docs)} resumes, {labeled}/{total} lines labeled", flush=True)
    s = {"resumes": len(docs), "lines": total, "labeled_lines": labeled,
         "gold_mix": dict(collections.Counter(g for d in docs for g in d["gold"] if g)),
         "headings": heading_coverage(docs), "models": {}, "taught": {}}
    s["models"]["rules"] = score([rules_labels(d["lines"]) for d in docs], docs)
    print("rules", s["models"]["rules"], flush=True)

    print("training the three networks on the synthetic corpus ...", flush=True)
    corpus = base_corpus()
    taggers = {}
    for name, mode in (("text", False), ("headings", "headings"), ("geometry", True)):
        tg = LineTagger(use_geometry=mode).fit(corpus)
        taggers[name] = tg
        s["models"][name] = score([tg.predict(d["lines"], d["geo"]) for d in docs], docs)
        print(name, s["models"][name], flush=True)

    rng = np.random.default_rng(0)
    order = rng.permutation(len(docs))
    test = [docs[i] for i in order[:500]]
    pool = [docs[i] for i in order[500:]]
    for k in map(int, a.teach.split(",")):
        accs = []
        for draw in range(a.draws if k else 1):
            tg = copy.deepcopy(taggers["text"])
            for i in np.random.default_rng(100 + draw).choice(len(pool), size=k, replace=False):
                d = pool[i]
                keep = [j for j, g in enumerate(d["gold"]) if g is not None]
                tg.learn([d["lines"][j] for j in keep], [d["gold"][j] for j in keep], [d["geo"][j] for j in keep])
            accs.append(score([tg.predict(d["lines"], d["geo"]) for d in test], test)["line_acc"])
        s["taught"][str(k)] = {"mean": round(float(np.mean(accs)), 3), "min": min(accs), "max": max(accs)}
        print("taught", k, s["taught"][str(k)], flush=True)

    (a.out / "summary.json").write_text(json.dumps(s, indent=2), encoding="utf-8")
    chart(s, a.out / "real_resumes.png")
    print(json.dumps(s, indent=2))


if __name__ == "__main__":
    main()
