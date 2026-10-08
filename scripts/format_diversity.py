"""Experiment 6: does training on more resume formats help on formats never seen?

The line tagger is trained on the classic template plus k of the 40
training formats from ats_sim/formats.py (k = 0, 5, 10, 20, 40), and tested
on two things it never trained on:

  hand-written   the four held-out templates in render.py (modern, latex,
                 career_center, hybrid), every layout and file type. These were
                 written separately from the generator, so they are the fair test.
  generated      the 10 held-out generated formats (f41 to f50). Same generator
                 as the training formats, so expect this to flatter the model.

Personas are split too (10 train, 6 test), so the network is never tested on a
person whose text it saw in training. Repeated over seeds (split, format
subset and initial weights). Field F1 is shown next to the heading-list parser
and the "perfect sections" ceiling, as in experiment 5.

    python scripts/format_diversity.py               # results/formats/
    python scripts/format_diversity.py --replot
"""
from __future__ import annotations

import argparse
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

from ats_sim.data import RESUME_DIR, load_personas  # noqa: E402
from ats_sim.evaluate import micro, score_resume  # noqa: E402
from ats_sim.formats import HELD_OUT_FORMATS, TRAIN_FORMATS, describe  # noqa: E402
from ats_sim.learn.corpus import documents, format_documents  # noqa: E402
from ats_sim.learn.tagger import LineTagger, parse_with_tagger, sections_from_labels  # noqa: E402
from ats_sim.parser import parse_text, parse_with_sections  # noqa: E402
from ats_sim.render import HELD_OUT_TEMPLATES  # noqa: E402

OUT = ROOT / "results" / "formats"
KS = (0, 5, 10, 20, 40)
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
GROUP_COLORS = {"hand-written": "#2a78d6", "generated": "#eb6834"}


def scores(tagger, docs, personas) -> tuple[float, float]:
    counts, hits, total = [], 0, 0
    for (pid, *_), (lines, labels) in docs.items():
        parsed, _, pred = parse_with_tagger("\n".join(lines), tagger)
        counts.append(score_resume(personas[pid], parsed))
        hits += sum(a == b for a, b in zip(pred, labels))
        total += len(labels)
    return micro(counts).f1, hits / total


def reference_f1(docs, personas) -> tuple[float, float]:
    rules, oracle = [], []
    for (pid, *_), (lines, labels) in docs.items():
        text = "\n".join(lines)
        rules.append(score_resume(personas[pid], parse_text(text)))
        sections, name = sections_from_labels(lines, labels)
        oracle.append(score_resume(personas[pid], parse_with_sections(text, sections, name=name)))
    return micro(rules).f1, micro(oracle).f1


def run(n_seeds: int) -> pd.DataFrame:
    plist = load_personas()
    personas = {p["id"]: p for p in plist}
    print("rendering, extracting and labeling ...", flush=True)
    templates = documents(templates=("classic", *HELD_OUT_TEMPLATES))
    generated = format_documents(TRAIN_FORMATS + HELD_OUT_FORMATS, per_persona=2, cache=RESUME_DIR)
    rows = []
    for seed in range(n_seeds):
        rng = np.random.default_rng(seed)
        ids = [p["id"] for p in plist]
        rng.shuffle(ids)
        train_ids, test_ids = set(ids[:10]), set(ids[10:])
        tests = {"hand-written": {k: d for k, d in templates.items() if k[1] in HELD_OUT_TEMPLATES and k[0] in test_ids},
                 "generated": {k: d for k, d in generated.items() if k[1] in HELD_OUT_FORMATS and k[0] in test_ids}}
        for group, docs in tests.items():
            r, o = reference_f1(docs, personas)
            rows += [dict(seed=seed, k=k, group=group, model=m, f1=v, line_acc=None)
                     for k in KS for m, v in (("rules", r), ("oracle", o))]
        order = list(TRAIN_FORMATS)
        rng.shuffle(order)
        classic = [d for k, d in templates.items() if k[1] == "classic" and k[0] in train_ids]
        for k in KS:
            chosen = set(order[:k])
            extra = [d for key, d in generated.items() if key[1] in chosen and key[0] in train_ids]
            tagger = LineTagger(seed=seed).fit(classic + extra)
            for group, docs in tests.items():
                f1, acc = scores(tagger, docs, personas)
                rows.append(dict(seed=seed, k=k, group=group, model="tagger", f1=f1, line_acc=acc))
                print(f"seed {seed} k={k:2d} {group:12s} lines {acc:.3f}  F1 {f1:.3f}  "
                      f"({len(classic) + len(extra)} training files)", flush=True)
            for t in HELD_OUT_TEMPLATES:  # per-template detail for the hand-written group
                docs = {key: d for key, d in tests["hand-written"].items() if key[1] == t}
                f1, acc = scores(tagger, docs, personas)
                r, o = reference_f1(docs, personas)
                rows.append(dict(seed=seed, k=k, group=f"template:{t}", model="tagger", f1=f1, line_acc=acc))
                rows.append(dict(seed=seed, k=k, group=f"template:{t}", model="rules", f1=r, line_acc=None))
                rows.append(dict(seed=seed, k=k, group=f"template:{t}", model="oracle", f1=o, line_acc=None))
    return pd.DataFrame(rows)


def chart(df: pd.DataFrame, path: Path) -> None:
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
        "text.color": INK, "axes.grid": True, "grid.color": GRID, "axes.axisbelow": True,
        "axes.spines.top": False, "axes.spines.right": False, "font.size": 10, "axes.titlesize": 11,
        "axes.titleweight": "bold", "axes.titlelocation": "left", "legend.frameon": False,
    })
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.2))
    names = {"hand-written": "Hand-written templates (fair test)", "generated": "Held-out generated formats"}
    for group, color in GROUP_COLORS.items():
        sub = df[(df.group == group) & (df.model == "tagger")]
        for ax, metric in ((a1, "line_acc"), (a2, "f1")):
            g = sub.groupby("k")[metric]
            ax.plot(g.mean().index, g.mean().values, "-o", color=color, lw=2, ms=4, label=names[group])
            ax.fill_between(g.min().index, g.min().values, g.max().values, color=color, alpha=0.12, lw=0)
        for model, ls in (("rules", "--"), ("oracle", ":")):
            v = df[(df.group == group) & (df.model == model)].f1.mean()
            a2.axhline(v, ls=ls, color=color, lw=1.5)
    a1.set_title("Lines labeled correctly")
    a2.set_title("Field F1 (dashed: heading list; dotted: perfect sections)")
    for ax in (a1, a2):
        ax.set_xlabel("Generated formats in training (plus the classic template)")
        ax.set_xticks(KS)
    a1.legend(loc="lower right", fontsize=9)
    fig.suptitle("Training on more formats, tested on formats and people never seen (mean; band = min to max)",
                 x=0.01, ha="left", fontsize=11, color=INK2)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def summarize(df: pd.DataFrame) -> dict:
    out = {}
    groups = ["hand-written", "generated"] + [f"template:{t}" for t in HELD_OUT_TEMPLATES]
    for g in groups:
        sub = df[df.group == g]
        t = sub[sub.model == "tagger"].groupby("k")
        out[g] = {"line_acc": {int(k): round(float(v), 3) for k, v in t.line_acc.mean().items()},
                  "f1": {int(k): round(float(v), 3) for k, v in t.f1.mean().items()},
                  "rules_f1": round(float(sub[sub.model == "rules"].f1.mean()), 3),
                  "oracle_f1": round(float(sub[sub.model == "oracle"].f1.mean()), 3)}
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--replot", action="store_true")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(describe()).to_csv(a.out / "formats.csv", index=False)
    if a.replot:
        chart(pd.read_csv(a.out / "format_diversity.csv"), a.out / "format_diversity.png")
        return
    df = run(a.seeds)
    df.to_csv(a.out / "format_diversity.csv", index=False)
    chart(df, a.out / "format_diversity.png")
    s = summarize(df)
    (a.out / "summary.json").write_text(json.dumps({"seeds": a.seeds, "groups": s}, indent=2))
    print(json.dumps(s, indent=2))


if __name__ == "__main__":
    main()
