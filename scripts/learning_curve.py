"""Experiment 5: does the line tagger get better as corrected resumes arrive?

The network starts from the classic template only. For each held-out
template, 8 personas are a teaching stream and the other 8 a test set. The
stream arrives one resume at a time (a random layout and format each), and
after every resume we measure field F1 on all 64 test files (8 personas x
4 layouts x 2 formats) of that template. Conditions:

  corrected   learn() with the true line labels (what a user's corrections give)
  self        learn() with the network's own predictions (no human in the loop)
  frozen      no learning (the starting network)
  rules       the heading-list parser (layout-aware text), for reference
  oracle      sections from the true line labels: the best any tagger can do
              with the current field rules, so the gap above it is not the
              network's to close

Two metrics: line accuracy (what the network learns directly) and field F1
(what a recruiter would see downstream).

Repeated over seeds (different persona splits, stream orders and network
initializations). Also reports classic-template F1 after the stream, to check
that learning a new template does not erase the old one.

    python scripts/learning_curve.py              # results/learning/
    python scripts/learning_curve.py --seeds 2    # quicker
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from ats_sim.data import load_personas  # noqa: E402
from ats_sim.evaluate import micro, score_resume  # noqa: E402
from ats_sim.learn.corpus import documents  # noqa: E402
from ats_sim.learn.tagger import LineTagger, parse_with_tagger, sections_from_labels  # noqa: E402
from ats_sim.parser import parse_text, parse_with_sections  # noqa: E402
from ats_sim.render import FORMATS, HELD_OUT_TEMPLATES, LAYOUTS  # noqa: E402

OUT = ROOT / "results" / "learning"
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
COLORS = {"corrected": "#2a78d6", "self": "#eb6834", "frozen": "#52514e", "rules": "#1baf7a", "oracle": "#eda100"}
NAMES = {"corrected": "Learns from corrections", "self": "Learns from its own guesses",
         "frozen": "No learning", "rules": "Heading-list parser",
         "oracle": "Perfect sections (ceiling)"}


def evaluate(tagger, docs, personas) -> tuple[float, float]:
    counts, hits, total = [], 0, 0
    for (pid, *_), (lines, labels, geo) in docs.items():
        parsed, _, pred = parse_with_tagger("\n".join(lines), tagger, geo=geo)
        counts.append(score_resume(personas[pid], parsed))
        hits += sum(a == b for a, b in zip(pred, labels))
        total += len(labels)
    return micro(counts).f1, hits / total


def rules_f1(docs, personas) -> float:
    return micro([score_resume(personas[pid], parse_text("\n".join(lines)))
                  for (pid, *_), (lines, *_) in docs.items()]).f1


def oracle_f1(docs, personas) -> float:
    counts = []
    for (pid, *_), (lines, labels, _) in docs.items():
        sections, name = sections_from_labels(lines, labels)
        counts.append(score_resume(personas[pid], parse_with_sections("\n".join(lines), sections, name=name)))
    return micro(counts).f1


def run(n_seeds: int, n_teach: int) -> pd.DataFrame:
    plist = load_personas()
    personas = {p["id"]: p for p in plist}
    print("extracting and labeling the corpus ...", flush=True)
    docs = documents(fmts=FORMATS)
    base_docs = {k: d for k, d in docs.items() if k[1] == "classic"}
    rows = []
    for seed in range(n_seeds):
        rng = np.random.default_rng(seed)
        base = LineTagger(seed=seed).fit(list(base_docs.values()))
        for template in HELD_OUT_TEMPLATES:
            ids = [p["id"] for p in plist]
            rng.shuffle(ids)
            teach_ids, test_ids = ids[:n_teach], ids[n_teach:]
            test = {k: d for k, d in docs.items() if k[1] == template and k[0] in test_ids}
            stream = [(pid, LAYOUTS[rng.integers(len(LAYOUTS))], FORMATS[rng.integers(len(FORMATS))])
                      for pid in teach_ids]
            r, o = rules_f1(test, personas), oracle_f1(test, personas)
            f0, a0 = evaluate(base, test, personas)
            for k in range(n_teach + 1):
                rows.append(dict(seed=seed, template=template, step=k, condition="rules", f1=r, line_acc=None))
                rows.append(dict(seed=seed, template=template, step=k, condition="frozen", f1=f0, line_acc=a0))
                rows.append(dict(seed=seed, template=template, step=k, condition="oracle", f1=o, line_acc=1.0))
            for cond in ("corrected", "self"):
                tg = copy.deepcopy(base)
                rows.append(dict(seed=seed, template=template, step=0, condition=cond, f1=f0, line_acc=a0))
                for k, (pid, lay, fmt) in enumerate(stream, 1):
                    lines, labels, geo = docs[(pid, template, lay, fmt)]
                    tg.learn(lines, labels if cond == "corrected" else tg.predict(lines, geo), geo)
                    f, a = evaluate(tg, test, personas)
                    rows.append(dict(seed=seed, template=template, step=k, condition=cond, f1=f, line_acc=a))
                classic_after, _ = evaluate(tg, base_docs, personas)
                rows.append(dict(seed=seed, template=template, step=n_teach, condition=f"{cond}:classic_after",
                                 f1=classic_after, line_acc=None))
                print(f"seed {seed} {template:14s} {cond:9s} lines {a0:.3f} -> {a:.3f}  F1 {f0:.3f} -> {f:.3f} "
                      f"(rules {r:.3f}, oracle {o:.3f}; classic after {classic_after:.3f})", flush=True)
    return pd.DataFrame(rows)


def chart(df: pd.DataFrame, path: Path) -> None:
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
        "text.color": INK, "axes.grid": True, "grid.color": GRID, "axes.axisbelow": True,
        "axes.spines.top": False, "axes.spines.right": False, "font.size": 10, "axes.titlesize": 11,
        "axes.titleweight": "bold", "axes.titlelocation": "left", "legend.frameon": False,
    })
    templates = list(HELD_OUT_TEMPLATES)
    fig, grid = plt.subplots(2, len(templates), figsize=(3.3 * len(templates), 6.6), sharey="row")
    panels = (("line_acc", "Lines labeled correctly", ("frozen", "self", "corrected")),
              ("f1", "Field F1", ("oracle", "rules", "frozen", "self", "corrected")))
    for row, (metric, ylabel, conds) in zip(grid, panels):
        for ax, t in zip(row, templates):
            sub = df[df.template == t]
            for cond in conds:
                g = sub[sub.condition == cond].groupby("step")[metric]
                m, lo, hi = g.mean(), g.min(), g.max()
                ls = ":" if cond == "oracle" else "--" if cond in ("rules", "frozen") else "-"
                ax.plot(m.index, m.values, ls, color=COLORS[cond], lw=2, label=NAMES[cond])
                if cond in ("self", "corrected"):
                    ax.fill_between(m.index, lo.values, hi.values, color=COLORS[cond], alpha=0.12, lw=0)
            if metric == "line_acc":
                ax.set_title({"latex": "LaTeX"}.get(t, t.replace("_", " ").title()))
            else:
                ax.set_xlabel("Resumes taught")
        row[0].set_ylabel(ylabel)
    handles, labels = grid[1][0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=len(labels), fontsize=9)
    fig.suptitle("Learning a new template, one resume at a time (mean; band = min to max over seeds)",
                 x=0.01, ha="left", fontsize=11, color=INK2)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def summarize(df: pd.DataFrame, n_teach: int) -> dict:
    out = {}
    for t in HELD_OUT_TEMPLATES:
        sub = df[df.template == t]
        def at(cond, step, metric="f1"):
            v = sub[(sub.condition == cond) & (sub.step == step)][metric]
            return {"mean": round(float(v.mean()), 3), "min": round(float(v.min()), 3), "max": round(float(v.max()), 3)}
        out[t] = {"line_acc": {"start": at("frozen", 0, "line_acc"), "after_1_corrected": at("corrected", 1, "line_acc"),
                               f"after_{n_teach}_corrected": at("corrected", n_teach, "line_acc"),
                               f"after_{n_teach}_self": at("self", n_teach, "line_acc")},
                  "oracle": at("oracle", 0), "rules": at("rules", 0), "start": at("frozen", 0),
                  "after_1_corrected": at("corrected", 1), "after_3_corrected": at("corrected", 3),
                  f"after_{n_teach}_corrected": at("corrected", n_teach), f"after_{n_teach}_self": at("self", n_teach),
                  "classic_after_corrected": at("corrected:classic_after", n_teach),
                  "classic_after_self": at("self:classic_after", n_teach)}
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--teach", type=int, default=8, help="resumes in each teaching stream (rest are test)")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--replot", action="store_true", help="redraw the chart from the saved CSV")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    if a.replot:
        chart(pd.read_csv(a.out / "learning_curve.csv"), a.out / "learning_curve.png")
        return
    df = run(a.seeds, a.teach)
    df.to_csv(a.out / "learning_curve.csv", index=False)
    chart(df, a.out / "learning_curve.png")
    s = summarize(df, a.teach)
    (a.out / "summary.json").write_text(json.dumps({"seeds": a.seeds, "teach": a.teach, "templates": s}, indent=2), encoding="utf-8")
    print(json.dumps(s, indent=2))


if __name__ == "__main__":
    main()
