"""Run all four experiments and write CSVs, charts and a markdown summary to results/.

    python scripts/run_experiments.py
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from ats_sim import experiments as ex  # noqa: E402
from ats_sim.render import LAYOUTS  # noqa: E402

OUT = ROOT / "results"

# Reference palette (dataviz skill), light mode; slots in fixed order.
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
SCORER_ORDER = ["keyword", "tfidf", "embedding", "keyword+taxonomy"]
LAYOUT_LABELS = {"single": "Single column", "two_column": "Two column", "table": "Table", "textbox": "Text boxes"}


def style():
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
        "text.color": INK, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
        "axes.axisbelow": True, "axes.spines.top": False, "axes.spines.right": False,
        "axes.spines.left": False, "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold",
        "axes.titlelocation": "left", "legend.frameon": False,
    })


def scorer_label(name: str, backend: str) -> str:
    if name == "embedding" and backend != "all-MiniLM-L6-v2":
        return f"embedding ({backend})"
    return name


def grouped_bars(ax, categories, series: dict[str, list[float]], colors, fmt="{:.2f}", label_values=True):
    n = len(series)
    width = 0.8 / n
    x = np.arange(len(categories))
    for i, ((name, vals), c) in enumerate(zip(series.items(), colors)):
        pos = x - 0.4 + width * (i + 0.5)
        bars = ax.bar(pos, vals, width * 0.9, color=c, label=name, edgecolor=SURFACE, linewidth=1)
        if label_values:
            for b, v in zip(bars, vals):
                if not np.isnan(v):
                    ax.annotate(fmt.format(v), (b.get_x() + b.get_width() / 2, max(v, 0)), xytext=(0, 2),
                                textcoords="offset points", ha="center", va="bottom", fontsize=8, color=INK2)
    ax.set_xticks(x, categories)
    ax.grid(axis="x", visible=False)


def chart_layout(overall: pd.DataFrame, path: Path):
    fig, ax = plt.subplots(figsize=(8, 4.2))
    series = {}
    for fmt, label in (("pdf", "PDF"), ("docx", "DOCX")):
        s = overall[overall.format == fmt].set_index("layout").reindex(LAYOUTS)["f1"]
        series[label] = s.tolist()
    grouped_bars(ax, [LAYOUT_LABELS[l] for l in LAYOUTS], series, SERIES[:2])
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("Field extraction F1 (micro)")
    ax.set_title("Same content, different layout: what the naive parser recovers")
    ax.legend(loc="upper right", ncols=2)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def chart_field_heatmap(per_field: pd.DataFrame, fmt: str, path: Path):
    from matplotlib.colors import LinearSegmentedColormap

    data = per_field.loc[fmt][list(LAYOUTS)]
    cmap = LinearSegmentedColormap.from_list("blue", ["#f0efec", "#86b6ef", "#2a78d6", "#104281"])
    fig, ax = plt.subplots(figsize=(6.4, 4.6))
    im = ax.imshow(data.values, cmap=cmap, vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(LAYOUTS)), [LAYOUT_LABELS[l] for l in LAYOUTS])
    ax.set_yticks(range(len(data.index)), data.index)
    ax.grid(False)
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            v = data.values[i, j]
            ax.text(j, i, "n/a" if np.isnan(v) else f"{v:.2f}", ha="center", va="center", fontsize=8,
                    color="#ffffff" if v > 0.6 else INK)
    ax.set_title(f"Per-field F1 by layout ({fmt.upper()})")
    fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02, label="F1")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def chart_synonyms(df: pd.DataFrame, backend: str, path: Path):
    g = df.groupby(["posting_term", "alternative", "scorer"])["rel_delta"].mean().reset_index()
    g["pair"] = g.posting_term + " → " + g.alternative
    pairs = [f"{a} → {b}" for a, b in ex.SYNONYM_PAIRS if f"{a} → {b}" in set(g.pair)]
    scorers = [s for s in SCORER_ORDER if s in set(g.scorer)]
    fig, ax = plt.subplots(figsize=(9, 0.42 * len(pairs) * len(scorers) / 2 + 1.8))
    height = 0.8 / len(scorers)
    y = np.arange(len(pairs))
    for i, (sc, c) in enumerate(zip(scorers, SERIES)):
        vals = 100 * g[g.scorer == sc].set_index("pair").reindex(pairs)["rel_delta"].to_numpy()
        pos = y - 0.4 + height * (i + 0.5)
        ax.barh(pos, vals, height * 0.9, color=c, label=scorer_label(sc, backend), edgecolor=SURFACE)
        for yy, v in zip(pos, vals):
            if not np.isnan(v) and abs(v) >= 0.5:
                ax.annotate(f"{v:+.0f}%", (v, yy), xytext=(-3 if v < 0 else 3, 0), textcoords="offset points",
                            ha="right" if v < 0 else "left", va="center", fontsize=7, color=INK2)
    ax.set_yticks(y, pairs)
    ax.invert_yaxis()
    ax.axvline(0, color=INK2, linewidth=0.8)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Mean score change when the resume uses the alternative wording (%)")
    ax.legend(loc="lower center", bbox_to_anchor=(0.4, 1.0), ncols=4)
    ax.set_title("Synonym sensitivity: posting term → candidate's wording", pad=30)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def chart_stuffing(df: pd.DataFrame, backend: str, path: Path):
    outside = df[df.was_outside_top_k]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    for ax, defense, title in ((axes[0], "none", "Default parser"),
                               (axes[1], "drop_invisible", "Parser drops white/tiny text")):
        d = outside[outside.defense == defense]
        attacks = [a for a in ex.STUFFING_ATTACKS if a in set(d.attack)]
        series = {scorer_label(s, backend): [100 * d[(d.attack == a) & (d.scorer == s)].beats_best_genuine.mean()
                                             for a in attacks] for s in SCORER_ORDER[:3]}
        grouped_bars(ax, [a.replace("_", " ") for a in attacks], series, SERIES[:3], fmt="{:.0f}%")
        ax.set_title(title, fontsize=11)
        ax.set_ylim(0, 112)
    axes[0].set_ylabel("% that outrank the best unstuffed resume")
    fig.legend(*axes[0].get_legend_handles_labels(), loc="upper right", ncols=3)
    fig.suptitle("Keyword-stuffing audit: which scorers are fooled", x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def chart_stability(df: pd.DataFrame, backend: str, path: Path):
    g = df.groupby(["edit", "scorer"])["abs_rank_change"].mean().reset_index()
    fig, ax = plt.subplots(figsize=(9, 4.2))
    series = {scorer_label(s, backend): g[g.scorer == s].set_index("edit").reindex(ex.EDITS)["abs_rank_change"].tolist()
              for s in SCORER_ORDER[:3]}
    grouped_bars(ax, [e.replace("_", " ") for e in ex.EDITS], series, SERIES[:3])
    ax.set_ylabel("Mean |rank change| (positions)")
    ax.set_title("Ranking stability: movement after small wording edits to one resume")
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def md_table(df: pd.DataFrame, floatfmt: str = ".3f") -> str:
    return df.to_markdown(index=False, floatfmt=floatfmt)


def main():
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kaggle-csv", help="Optional Kaggle resume CSV whose rows join the ranking pool as distractors")
    ap.add_argument("--kaggle-column", default="Resume_str")
    ap.add_argument("--kaggle-category", help="Only rows with this Category (e.g. ENGINEERING)")
    ap.add_argument("--kaggle-limit", type=int, default=200)
    args = ap.parse_args()

    warnings.filterwarnings("ignore", category=FutureWarning)
    OUT.mkdir(exist_ok=True)
    style()
    extra = None
    if args.kaggle_csv:
        from ats_sim.data import load_kaggle_resumes

        extra = load_kaggle_resumes(args.kaggle_csv, args.kaggle_column, args.kaggle_limit, args.kaggle_category)
        print(f"added {len(extra)} Kaggle resumes to the ranking pool")
    ctx = ex.build_context(OUT / "_tmp", extra_pool=extra)
    backend = ctx.embedding_backend
    print(f"embedding backend: {backend}")

    print("1/4 layout robustness")
    counts, downstream = ex.layout_robustness(ctx)
    lay = ex.summarize_layout(counts, downstream)
    counts.to_csv(OUT / "layout_field_counts.csv", index=False)
    downstream.to_csv(OUT / "layout_downstream.csv", index=False)
    lay["overall"].to_csv(OUT / "layout_summary.csv", index=False)
    lay["per_field"].to_csv(OUT / "layout_per_field.csv")
    lay["effects"].to_csv(OUT / "layout_effects.csv", index=False)
    lay["transitions"].to_csv(OUT / "layout_knockout_transitions.csv", index=False)
    chart_layout(lay["overall"], OUT / "layout_f1.png")
    chart_field_heatmap(lay["per_field"], "pdf", OUT / "layout_fields_pdf.png")
    chart_field_heatmap(lay["per_field"], "docx", OUT / "layout_fields_docx.png")

    print("2/4 synonym sensitivity")
    syn = ex.synonym_sensitivity(ctx)
    syn.to_csv(OUT / "synonyms.csv", index=False)
    chart_synonyms(syn, backend, OUT / "synonyms.png")

    print("3/4 keyword stuffing")
    stuff = ex.keyword_stuffing(ctx)
    stuff.to_csv(OUT / "stuffing.csv", index=False)
    chart_stuffing(stuff, backend, OUT / "stuffing.png")

    print("4/4 ranking stability")
    stab = ex.ranking_stability(ctx)
    stab.to_csv(OUT / "stability.csv", index=False)
    chart_stability(stab, backend, OUT / "stability.png")

    # ----------------------------------------------------------- summary
    syn_s = (syn.groupby("scorer").agg(cases=("delta", "size"), mean_rel_delta=("rel_delta", "mean"),
                                       mean_rank_change=("rank_change", "mean"),
                                       share_dropped=("rank_change", lambda s: (s > 0).mean()))
             .reindex([s for s in SCORER_ORDER if s in set(syn.scorer)]).reset_index())
    out_k = stuff[stuff.was_outside_top_k]
    stuff_s = (out_k.groupby(["attack", "defense", "scorer"])
               .agg(candidates=("entered_top_k", "size"), entered_top_k=("entered_top_k", "mean"),
                    beats_best_genuine=("beats_best_genuine", "mean"),
                    median_score_vs_best=("score_vs_best_genuine", "median"),
                    mean_rank_gain=("rank_gain", "mean"))
               .reset_index())
    stab_s = (stab.groupby(["scorer", "edit"]).agg(mean_abs_rank_change=("abs_rank_change", "mean"),
                                                   max_abs_rank_change=("abs_rank_change", "max"),
                                                   top_k_flips=("top_k_flip", "sum")).reset_index())
    syn_s.to_csv(OUT / "synonyms_summary.csv", index=False)
    stuff_s.to_csv(OUT / "stuffing_summary.csv", index=False)
    stab_s.to_csv(OUT / "stability_summary.csv", index=False)

    n_resumes = counts.groupby(["persona", "format", "layout"]).ngroups
    summary = {
        "embedding_backend": backend,
        "n_personas": len(ctx.personas),
        "pool_size": len(ctx.base_text),
        "n_layout_resumes": n_resumes,
        "layout_f1": {f"{r.format}/{r.layout}": round(r.f1, 4) for r in lay["overall"].itertuples()},
        "layout_f1_drop_pct": {f"{r.format}/{r.layout}": round(r.f1_drop_vs_single_pct, 1)
                               for r in lay["overall"].itertuples()},
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2))

    md = [
        "# Experiment results",
        "",
        f"Generated by `scripts/run_experiments.py`. Embedding backend: **{backend}**.",
        "",
        "## 1. Layout robustness (field extraction F1)",
        "",
        md_table(lay["overall"]),
        "",
        "Downstream effect vs the single-column version of the same resume. Each row covers "
        "16 personas x 3 postings. Under the review policy a missing field sends the candidate to a human; "
        "under the reject policy it is an automatic reject.",
        "",
        md_table(lay["effects"]),
        "",
        "Knockout transitions under the review policy (single-column status -> status in this layout):",
        "",
        md_table(lay["transitions"]),
        "",
        "Per-field F1:",
        "",
        lay["per_field"].reset_index().rename(columns={"level_0": "format", "level_1": "field"})
        .to_markdown(index=False, floatfmt=".2f"),
        "",
        "## 2. Synonym sensitivity",
        "",
        "`rank_change` > 0 means the resume dropped when it used the alternative wording.",
        "",
        md_table(syn_s),
        "",
        "## 3. Keyword stuffing (candidates that started outside the top 5)",
        "",
        "`entered_top_k`: share pushed into the top 5. `beats_best_genuine`: share whose stuffed score beats "
        "every unstuffed resume in the pool. `median_score_vs_best`: stuffed score / best unstuffed score.",
        "",
        md_table(stuff_s),
        "",
        "## 4. Ranking stability",
        "",
        md_table(stab_s),
        "",
    ]
    (OUT / "RESULTS.md").write_text("\n".join(md))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
