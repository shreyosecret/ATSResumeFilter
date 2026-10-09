"""Experiment 7: does reading the page (geometry) help the line tagger?

Three versions of the network, identical except for how they use the page:

  text       only the text of each line and its neighbors
  geometry   also how each line looks on the page, measured from its characters
             (ats_sim/learn/geometry.py: margin, indent, size, bold, color,
             letter spacing, gaps, rules, shading), for every label
  headings   geometry only in a second small network that finds headings and
             the name; sections are assigned by the text network (the app's
             default, chosen after the first run of this experiment showed
             "geometry" learning a layout shortcut on a real resume)

Both train on the classic template plus the 40 training formats and the 8
training designer formats, for 10 of the 16 personas. Both are tested on the
other 6 personas in four groups none of them trained on:

  hand-written  the four held-out templates (every layout and file type)
  generated     the 10 held-out generated formats
  designer      the 4 held-out designer formats (letter-spaced headings,
                shaded sidebars, rating dots, ...)
  reference     the 22 formats built from public templates and career-center
                guides (data/format_sources.json), never used in training

Three seeds (persona split and initial weights). With --private-labels, a
hand-labeled real resume is also scored, and with --real-dir every file in a
folder of resumes saved with the Teach tab's *Export labels*; those results
are printed and written under private/ only, never to results/.

    python scripts/geometry_ablation.py                     # results/geometry/
    python scripts/geometry_ablation.py --private-labels private/x.lines.json --private-file private/x.pdf
    python scripts/geometry_ablation.py --real-dir private/real
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
from ats_sim.formats import (  # noqa: E402
    HELD_OUT_DESIGNER, HELD_OUT_FORMATS, REFERENCE_FORMATS, TRAIN_DESIGNER, TRAIN_FORMATS,
)
from ats_sim.learn.corpus import documents, format_documents  # noqa: E402
from ats_sim.learn.tagger import LineTagger, parse_with_tagger, sections_from_labels  # noqa: E402
from ats_sim.parser import parse_text, parse_with_sections  # noqa: E402
from ats_sim.render import HELD_OUT_TEMPLATES  # noqa: E402

OUT = ROOT / "results" / "geometry"
GROUPS = ("hand-written", "generated", "designer", "reference")
MODELS = {"text": "Text only", "geometry": "Geometry for every label", "headings": "Geometry for headings (app)"}
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
COLORS = {"text": "#9a9893", "geometry": "#eb6834", "headings": "#2a78d6"}


def scores(tagger, docs, personas) -> tuple[float, float]:
    counts, hits, total = [], 0, 0
    for (pid, *_), (lines, labels, geo) in docs.items():
        parsed, _, pred = parse_with_tagger("\n".join(lines), tagger, geo=geo)
        counts.append(score_resume(personas[pid], parsed))
        hits += sum(a == b for a, b in zip(pred, labels))
        total += len(labels)
    return micro(counts).f1, hits / total


def reference_f1(docs, personas) -> tuple[float, float]:
    rules, oracle = [], []
    for (pid, *_), (lines, labels, _) in docs.items():
        text = "\n".join(lines)
        rules.append(score_resume(personas[pid], parse_text(text)))
        sections, name = sections_from_labels(lines, labels)
        oracle.append(score_resume(personas[pid], parse_with_sections(text, sections, name=name)))
    return micro(rules).f1, micro(oracle).f1


def map_labels(raw: list[str], raw_labels: list[str], lines: list[str]) -> list[str]:
    """Labels for lines the reader joined (wrapped bullets): each joined line
    takes the label of its first part. `raw` are the unjoined lines."""
    out, i = [], 0
    for line in lines:
        out.append(raw_labels[i])
        acc = raw[i]
        i += 1
        while acc != line and i < len(raw):
            spaced = acc + " " + raw[i]
            acc = spaced if line.startswith(spaced) else acc[:-1] + raw[i]
            i += 1
        if acc != line:
            raise SystemExit("the private labels do not match the file's lines")
    return out


def private_score(tagger, labels_path: Path, file_path: Path) -> dict:
    from ats_sim.learn.geometry import read

    gold = json.loads(labels_path.read_text(encoding="utf-8"))
    if [r.text for r in read(file_path, merge_wrapped=False)] != gold["lines"]:
        raise SystemExit("the private labels do not match the file's lines")
    rows = read(file_path)
    lines = [r.text for r in rows]
    labels = map_labels(gold["lines"], gold["labels"], lines)
    pred = tagger.predict(lines, [r.geo for r in rows])
    return {"line_acc": round(sum(a == b for a, b in zip(pred, labels)) / len(lines), 3)}


def real_score(tagger, folder: Path) -> dict:
    """Line accuracy on every exported file in `folder` (the Teach tab's
    *Export labels*), pooled over lines and averaged over resumes."""
    from ats_sim.learn.export import load

    per, hits, total = [], 0, 0
    for f in sorted(folder.glob("*.json")):
        lines, labels, geo = load(f)
        pred = tagger.predict(lines, geo)
        ok = sum(a == b for a, b in zip(pred, labels))
        per.append(ok / len(lines))
        hits, total = hits + ok, total + len(lines)
    if not per:
        raise SystemExit(f"no exported label files in {folder}")
    return {"resumes": len(per), "line_acc": round(hits / total, 3), "mean_per_resume": round(sum(per) / len(per), 3)}


def run(n_seeds: int, private: tuple[Path, Path] | None, real_dir: Path | None = None
        ) -> tuple[pd.DataFrame, list[dict]]:
    plist = load_personas()
    personas = {p["id"]: p for p in plist}
    print("rendering, reading and labeling ...", flush=True)
    templates = documents(templates=("classic", *HELD_OUT_TEMPLATES))
    generated = format_documents(TRAIN_FORMATS + HELD_OUT_FORMATS + TRAIN_DESIGNER + HELD_OUT_DESIGNER
                                 + REFERENCE_FORMATS, per_persona=2, cache=RESUME_DIR)
    test_formats = {"generated": set(HELD_OUT_FORMATS), "designer": set(HELD_OUT_DESIGNER),
                    "reference": set(REFERENCE_FORMATS)}
    train_formats = set(TRAIN_FORMATS) | set(TRAIN_DESIGNER)
    rows, private_rows = [], []
    for seed in range(n_seeds):
        rng = np.random.default_rng(seed)
        ids = [p["id"] for p in plist]
        rng.shuffle(ids)
        train_ids, test_ids = set(ids[:10]), set(ids[10:])
        tests = {"hand-written": {k: d for k, d in templates.items()
                                  if k[1] in HELD_OUT_TEMPLATES and k[0] in test_ids}}
        for g, names in test_formats.items():
            tests[g] = {k: d for k, d in generated.items() if k[1] in names and k[0] in test_ids}
        train = [d for k, d in templates.items() if k[1] == "classic" and k[0] in train_ids]
        train += [d for k, d in generated.items() if k[1] in train_formats and k[0] in train_ids]
        for group, docs in tests.items():
            r, o = reference_f1(docs, personas)
            rows += [dict(seed=seed, group=group, model=m, f1=v, line_acc=None) for m, v in (("rules", r), ("oracle", o))]
        for model in MODELS:
            tagger = LineTagger(seed=seed, use_geometry={"text": False, "geometry": True, "headings": "headings"}[model]
                                ).fit(train)
            for group, docs in tests.items():
                f1, acc = scores(tagger, docs, personas)
                rows.append(dict(seed=seed, group=group, model=model, f1=f1, line_acc=acc))
                print(f"seed {seed} {model:8s} {group:12s} lines {acc:.3f}  F1 {f1:.3f}", flush=True)
            if private:
                private_rows.append({"seed": seed, "model": model, **private_score(tagger, *private)})
                print(f"seed {seed} {model:8s} real resume  lines {private_rows[-1]['line_acc']:.3f}", flush=True)
            if real_dir:
                private_rows.append({"seed": seed, "model": model, "set": str(real_dir), **real_score(tagger, real_dir)})
                print(f"seed {seed} {model:8s} real set     lines {private_rows[-1]['line_acc']:.3f} "
                      f"({private_rows[-1]['resumes']} resumes)", flush=True)
    return pd.DataFrame(rows), private_rows


def chart(df: pd.DataFrame, path: Path) -> None:
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
        "text.color": INK, "axes.grid": True, "grid.color": GRID, "axes.axisbelow": True,
        "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False, "font.size": 10,
        "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlelocation": "left", "legend.frameon": False,
    })
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4))
    x = np.arange(len(GROUPS))
    for ax, metric, title in ((axes[0], "line_acc", "Lines labeled correctly"), (axes[1], "f1", "Field F1")):
        for i, m in enumerate(MODELS):
            sub = df[df.model == m].groupby("group")[metric]
            mean = [sub.mean()[g] for g in GROUPS]
            lo = [sub.mean()[g] - sub.min()[g] for g in GROUPS]
            hi = [sub.max()[g] - sub.mean()[g] for g in GROUPS]
            bars = ax.bar(x + (i - 1) * 0.27, mean, 0.25, color=COLORS[m], label=MODELS[m],
                          yerr=[lo, hi], error_kw=dict(ecolor=INK2, lw=1, capsize=2))
            for b, v in zip(bars, mean):
                ax.text(b.get_x() + b.get_width() / 2, v + 0.012, f"{v:.2f}", ha="center", va="bottom",
                        fontsize=7.5, color=INK2)
        if metric == "f1":
            for j, g in enumerate(GROUPS):
                o = df[(df.group == g) & (df.model == "oracle")].f1.mean()
                ax.plot([j - 0.4, j + 0.4], [o, o], ":", color=INK, lw=1.2,
                        label="Perfect sections (ceiling)" if j == 0 else None)
        ax.set_xticks(x, [g.replace("-", "-\n") if g == "hand-written" else g for g in GROUPS])
        ax.set_title(title)
        ax.set_ylim(0.4, 1.05)
    handles, labels = axes[1].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=len(labels), fontsize=9)
    fig.suptitle("Reading the page: three ways to use geometry, on formats and people never trained on "
                 "(mean of 3 seeds; whiskers = min to max)", x=0.01, ha="left", fontsize=10.5, color=INK2)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def summarize(df: pd.DataFrame) -> dict:
    out = {}
    for g in GROUPS:
        sub = df[df.group == g]
        out[g] = {m: {"line_acc": round(float(sub[sub.model == m].line_acc.mean()), 3),
                      "f1": round(float(sub[sub.model == m].f1.mean()), 3)} for m in MODELS}
        out[g]["rules_f1"] = round(float(sub[sub.model == "rules"].f1.mean()), 3)
        out[g]["oracle_f1"] = round(float(sub[sub.model == "oracle"].f1.mean()), 3)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--private-labels", type=Path)
    ap.add_argument("--private-file", type=Path)
    ap.add_argument("--real-dir", type=Path, help="a folder of files saved with Export labels (kept under private/)")
    ap.add_argument("--replot", action="store_true")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    if a.replot:
        chart(pd.read_csv(a.out / "geometry_ablation.csv"), a.out / "geometry_ablation.png")
        return
    private = (a.private_labels, a.private_file) if a.private_labels and a.private_file else None
    df, private_rows = run(a.seeds, private, a.real_dir)
    df.to_csv(a.out / "geometry_ablation.csv", index=False)
    chart(df, a.out / "geometry_ablation.png")
    s = summarize(df)
    (a.out / "summary.json").write_text(json.dumps({"seeds": a.seeds, "groups": s}, indent=2), encoding="utf-8")
    print(json.dumps(s, indent=2))
    if private_rows:
        out = ROOT / "private" / "geometry_ablation_private.json"
        out.write_text(json.dumps(private_rows, indent=2), encoding="utf-8")
        print("private result written to", out)


if __name__ == "__main__":
    main()
