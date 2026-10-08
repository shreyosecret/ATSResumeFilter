"""Run all four experiments and write CSVs, charts and a markdown summary.

    python scripts/run_experiments.py                       # results/
    python scripts/run_experiments.py --require-minilm      # fail instead of falling back to LSA
    python scripts/run_experiments.py --public-pool data/kaggle/Resume.csv --out results/public_pool
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
from ats_sim.render import HELD_OUT_TEMPLATES, LAYOUTS, TEMPLATES  # noqa: E402

OUT = ROOT / "results"

# Reference palette (dataviz skill), light mode; slots in fixed order.
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
SERIES_5 = SERIES + ["#e87ba4"]
SCORER_ORDER = ["keyword", "tfidf", "embedding", "skillner", "keyword+taxonomy"]
# Color follows the scorer, never its position, so adding SkillNer repaints nothing.
SCORER_COLORS = {"keyword": "#2a78d6", "tfidf": "#eb6834", "embedding": "#1baf7a", "keyword+taxonomy": "#eda100",
                 "skillner": "#e87ba4"}
RANKERS = ["keyword", "tfidf", "embedding", "skillner"]
CELL_COLS = ["template", "parser", "format", "layout"]
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


def grouped_bars(ax, categories, series: dict[str, list[float]], colors, fmt="{:.2f}", label_values=True,
                 errors: dict[str, tuple[list[float], list[float]]] | None = None):
    """Grouped bars; `errors` maps a series name to (lo, hi) interval bounds."""
    n = len(series)
    width = 0.8 / n
    x = np.arange(len(categories))
    for i, ((name, vals), c) in enumerate(zip(series.items(), colors)):
        pos = x - 0.4 + width * (i + 0.5)
        bars = ax.bar(pos, vals, width * 0.9, color=c, label=name, edgecolor=SURFACE, linewidth=1)
        tops = list(vals)
        if errors and name in errors:
            lo, hi = (np.asarray(e, dtype=float) for e in errors[name])
            v = np.asarray(vals, dtype=float)
            ax.errorbar(pos, v, yerr=[np.clip(v - lo, 0, None), np.clip(hi - v, 0, None)], fmt="none",
                        ecolor=INK2, elinewidth=1, capsize=2)
            tops = list(np.maximum(v, hi))
        if label_values:
            for b, v, top in zip(bars, vals, tops):
                if not np.isnan(v):
                    ax.annotate(fmt.format(v), (b.get_x() + b.get_width() / 2, max(top, 0)), xytext=(0, 2),
                                textcoords="offset points", ha="center", va="bottom", fontsize=8, color=INK2)
    ax.set_xticks(x, categories)
    ax.grid(axis="x", visible=False)


TEMPLATE_LABELS = {"classic": "classic (dev)", "modern": "modern", "latex": "latex",
                   "career_center": "career center", "hybrid": "hybrid", ex.POOLED: "held-out, pooled"}


def chart_layout(overall: pd.DataFrame, path: Path):
    """Headline: naive parser, development template vs the held-out templates pooled, with 95% CIs."""
    d = overall[overall.parser == "naive"]
    combos = [("pdf", "classic", "PDF, dev template"), ("pdf", ex.POOLED, "PDF, held-out templates"),
              ("docx", "classic", "DOCX, dev template"), ("docx", ex.POOLED, "DOCX, held-out templates")]
    fig, ax = plt.subplots(figsize=(9.5, 4.4))
    series, errors = {}, {}
    for fmt, template, label in combos:
        s = d[(d.format == fmt) & (d.template == template)].set_index("layout").reindex(LAYOUTS)
        series[label] = s["f1"].tolist()
        errors[label] = (s["f1_lo"].tolist(), s["f1_hi"].tolist())
    grouped_bars(ax, [LAYOUT_LABELS[l] for l in LAYOUTS], series, SERIES, errors=errors)
    for t in ax.texts:
        t.set_fontsize(7)
    ax.set_ylim(0, 1.32)
    ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_ylabel("Field extraction F1 (micro)")
    ax.set_title("Same content, different layout: what the naive parser recovers")
    ax.legend(loc="upper center", ncols=4, fontsize=8)
    ax.text(0, -0.16, "Held-out = 4 templates the parser never saw, pooled. Whiskers: 95% bootstrap CI "
            "(dev: over personas; held-out: over templates and personas).",
            transform=ax.transAxes, fontsize=8, color=INK2)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def chart_layout_templates(overall: pd.DataFrame, path: Path):
    """Every template, both parser modes, both formats (2 x 2 small multiples)."""
    fig, axes = plt.subplots(2, 2, figsize=(13, 7.4), sharey=True)
    for r, parser in enumerate(("naive", "layout_aware")):
        for c, fmt in enumerate(("pdf", "docx")):
            ax = axes[r, c]
            d = overall[(overall.parser == parser) & (overall.format == fmt)]
            series, errors = {}, {}
            for template in TEMPLATES:
                s = d[d.template == template].set_index("layout").reindex(LAYOUTS)
                series[TEMPLATE_LABELS[template]] = s["f1"].tolist()
                errors[TEMPLATE_LABELS[template]] = (s["f1_lo"].tolist(), s["f1_hi"].tolist())
            grouped_bars(ax, [LAYOUT_LABELS[l] for l in LAYOUTS], series, SERIES_5, errors=errors,
                         label_values=False)
            ax.set_title(f"{fmt.upper()}, {parser.replace('_', '-')} parser", fontsize=11)
            ax.set_ylim(0, 1.08)
            ax.tick_params(axis="x", labelsize=9)
        axes[r, 0].set_ylabel("Field extraction F1 (micro)")
    fig.legend(*axes[0, 0].get_legend_handles_labels(), loc="upper right", ncols=5)
    fig.suptitle("Layout x template x parser (exact values in RESULTS.md)", x=0.01, ha="left", fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def chart_field_heatmap(per_field: pd.DataFrame, template: str, fmt: str, path: Path):
    from matplotlib.colors import LinearSegmentedColormap

    data = per_field.xs((template, fmt), level=[0, 1])[list(LAYOUTS)]
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
    ax.set_title(f"Per-field F1 by layout ({template} template, {fmt.upper()}, naive parser)", fontsize=10)
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
    for i, sc in enumerate(scorers):
        c = SCORER_COLORS[sc]
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
    ax.legend(loc="upper center", bbox_to_anchor=(0.45, -0.08 - 0.5 / len(pairs)), ncols=len(scorers))
    ax.set_title("Synonym sensitivity: posting term → candidate's wording")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def chart_stuffing(df: pd.DataFrame, backend: str, path: Path, pool_n: int):
    outside = df[df.was_outside_top_k]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    for ax, defense, title in ((axes[0], "none", "Default parser"),
                               (axes[1], "drop_invisible", "Parser drops white/tiny text")):
        d = outside[outside.defense == defense]
        attacks = [a for a in ex.STUFFING_ATTACKS if a in set(d.attack)]
        present = [s for s in RANKERS if s in set(d.scorer)]
        series = {scorer_label(s, backend): [100 * d[(d.attack == a) & (d.scorer == s)].beats_best_genuine.mean()
                                             for a in attacks] for s in present}
        grouped_bars(ax, [a.replace("_", " ") for a in attacks], series, [SCORER_COLORS[s] for s in present],
                     fmt="{:.0f}%")
        ax.set_title(title, fontsize=11)
        ax.set_ylim(0, 112)
    axes[0].set_ylabel("% that outrank the best unstuffed resume")
    fig.legend(*axes[0].get_legend_handles_labels(), loc="upper right", ncols=3)
    fig.suptitle(f"Keyword-stuffing audit: which scorers are fooled (pool of {pool_n} resumes)",
                 x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def chart_stability(df: pd.DataFrame, backend: str, path: Path, pool_n: int):
    g = df.groupby(["edit", "scorer"])["abs_rank_change"].mean().reset_index()
    fig, ax = plt.subplots(figsize=(9, 4.2))
    present = [s for s in RANKERS if s in set(g.scorer)]
    series = {scorer_label(s, backend): g[g.scorer == s].set_index("edit").reindex(ex.EDITS)["abs_rank_change"].tolist()
              for s in present}
    grouped_bars(ax, [e.replace("_", " ") for e in ex.EDITS], series, [SCORER_COLORS[s] for s in present])
    ax.set_ylabel("Mean |rank change| (positions)")
    ax.set_title(f"Ranking stability: movement after small edits to one resume (pool of {pool_n})")
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def md_table(df: pd.DataFrame, floatfmt: str = ".3f") -> str:
    return df.to_markdown(index=False, floatfmt=floatfmt)


def ci_cols(df: pd.DataFrame, group: list[str], col: str, n_boot: int) -> pd.DataFrame:
    rows = []
    for key, g in df.groupby(group):
        lo, hi = ex.bootstrap_mean(g[col].astype(float), n_boot)
        rows.append(dict(zip(group, key if isinstance(key, tuple) else (key,)), **{f"{col}_lo": lo, f"{col}_hi": hi}))
    return pd.DataFrame(rows)


def main():
    import argparse

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(OUT), help="output directory (default: results/)")
    ap.add_argument("--public-pool", "--kaggle-csv", dest="public_pool",
                    help="Resume CSV (Kaggle 'Resume Dataset' format) whose rows join every ranking pool as distractors")
    ap.add_argument("--public-column", default="Resume_str")
    ap.add_argument("--public-categories", default="ENGINEERING,INFORMATION-TECHNOLOGY,AVIATION,AUTOMOBILE",
                    help="comma-separated Category values to sample from")
    ap.add_argument("--public-per-category", type=int, default=50)
    ap.add_argument("--require-minilm", action="store_true",
                    help="fail if all-MiniLM-L6-v2 cannot be loaded instead of using the LSA fallback")
    ap.add_argument("--n-boot", type=int, default=2000)
    ap.add_argument("--with-skillner", action="store_true",
                    help="add SkillNer (EMSI/Lightcast taxonomy) as a fourth scorer; needs skillNer + a spaCy model")
    args = ap.parse_args()

    import os

    if args.require_minilm:
        os.environ["ATS_SIM_EMBEDDING_BACKEND"] = "minilm"
    out = Path(args.out)
    warnings.filterwarnings("ignore", category=FutureWarning)
    out.mkdir(parents=True, exist_ok=True)
    style()
    extra = None
    if args.public_pool:
        from ats_sim.data import load_kaggle_resumes

        extra = load_kaggle_resumes(args.public_pool, args.public_column, args.public_per_category,
                                    args.public_categories.split(","))
        print(f"added {len(extra)} public resumes to the ranking pool")
    extra_scorers = []
    if args.with_skillner:
        from ats_sim.engines import SkillNerScorer, skillner_available

        if not skillner_available():
            raise SystemExit("--with-skillner: pip install skillNer ipython && python -m spacy download en_core_web_lg")
        extra_scorers.append(SkillNerScorer())
    ctx = ex.build_context(ROOT / "results" / "_tmp", extra_pool=extra, extra_scorers=extra_scorers)
    backend = ctx.embedding_backend
    print(f"embedding backend: {backend}")

    print("1/4 layout robustness")
    counts, downstream = ex.layout_robustness(ctx)
    lay = ex.summarize_layout(counts, downstream, args.n_boot)
    counts.to_csv(out / "layout_field_counts.csv", index=False)
    downstream.to_csv(out / "layout_downstream.csv", index=False)
    lay["overall"].to_csv(out / "layout_summary.csv", index=False)
    lay["per_field"].to_csv(out / "layout_per_field.csv")
    lay["effects"].to_csv(out / "layout_effects.csv", index=False)
    lay["transitions"].to_csv(out / "layout_knockout_transitions.csv", index=False)
    chart_layout(lay["overall"], out / "layout_f1.png")
    chart_layout_templates(lay["overall"], out / "layout_templates.png")
    for template in TEMPLATES:
        for fmt in ("pdf", "docx"):
            chart_field_heatmap(lay["per_field"], template, fmt, out / f"layout_fields_{template}_{fmt}.png")

    print("2/4 synonym sensitivity")
    syn = ex.synonym_sensitivity(ctx)
    syn.to_csv(out / "synonyms.csv", index=False)
    chart_synonyms(syn, backend, out / "synonyms.png")

    print("3/4 keyword stuffing")
    stuff = ex.keyword_stuffing(ctx)
    stuff.to_csv(out / "stuffing.csv", index=False)
    chart_stuffing(stuff, backend, out / "stuffing.png", len(ctx.base_text))

    print("4/4 ranking stability")
    stab = ex.ranking_stability(ctx)
    stab.to_csv(out / "stability.csv", index=False)
    chart_stability(stab, backend, out / "stability.png", len(ctx.base_text))

    # ----------------------------------------------------------- summary
    syn_s = (syn.groupby("scorer").agg(cases=("delta", "size"), mean_rel_delta=("rel_delta", "mean"),
                                       mean_rank_change=("rank_change", "mean"),
                                       share_dropped=("rank_change", lambda s: (s > 0).mean()))
             .reindex([s for s in SCORER_ORDER if s in set(syn.scorer)]).reset_index())
    syn_s = syn_s.merge(ci_cols(syn, ["scorer"], "rel_delta", args.n_boot), on="scorer")
    out_k = stuff[stuff.was_outside_top_k]
    stuff_s = (out_k.groupby(["attack", "defense", "scorer"])
               .agg(candidates=("entered_top_k", "size"), entered_top_k=("entered_top_k", "mean"),
                    beats_best_genuine=("beats_best_genuine", "mean"),
                    median_score_vs_best=("score_vs_best_genuine", "median"),
                    mean_rank_gain=("rank_gain", "mean"))
               .reset_index())
    stuff_s = stuff_s.merge(ci_cols(out_k, ["attack", "defense", "scorer"], "beats_best_genuine", args.n_boot),
                            on=["attack", "defense", "scorer"])
    stab_s = (stab.groupby(["scorer", "edit"]).agg(mean_abs_rank_change=("abs_rank_change", "mean"),
                                                   max_abs_rank_change=("abs_rank_change", "max"),
                                                   top_k_flips=("top_k_flip", "sum"),
                                                   cases=("top_k_flip", "size")).reset_index())
    syn_s.to_csv(out / "synonyms_summary.csv", index=False)
    stuff_s.to_csv(out / "stuffing_summary.csv", index=False)
    stab_s.to_csv(out / "stability_summary.csv", index=False)

    ov = lay["overall"]
    n_resumes = counts.groupby(["persona", "template", "format", "layout"]).ngroups
    summary = {
        "embedding_backend": backend,
        "n_personas": len(ctx.personas),
        "pool_size": len(ctx.base_text),
        "n_layout_resumes": n_resumes,
        "layout": {f"{r.template}/{r.parser}/{r.format}/{r.layout}": {
            "f1": round(r.f1, 4), "f1_ci": [round(r.f1_lo, 4), round(r.f1_hi, 4)],
            "drop_pct": round(r.f1_drop_vs_single_pct, 1), "drop_ci": [round(r.drop_lo, 1), round(r.drop_hi, 1)],
        } for r in ov.itertuples()},
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    def per_field_md(template):
        return (lay["per_field"].loc[template].reset_index()
                .rename(columns={"level_0": "format", "level_1": "field"}).to_markdown(index=False, floatfmt=".2f"))

    md = [
        "# Experiment results",
        "",
        f"Generated by `scripts/run_experiments.py`. Embedding backend: **{backend}**. "
        f"Ranking pool: {len(ctx.base_text)} resumes. Intervals are 95% bootstrap CIs ({args.n_boot} resamples).",
        "",
        "## 1. Layout robustness (field extraction F1)",
        "",
        f"{n_resumes} rendered resumes (16 personas x {len(TEMPLATES)} templates x 2 formats x 4 layouts), each "
        "read by both parser modes. `drop` is relative to single column in the same template, parser and format. "
        "Per-template CIs are a paired bootstrap over personas; `held_out_pooled` pools the "
        f"{len(HELD_OUT_TEMPLATES)} held-out templates ({', '.join(HELD_OUT_TEMPLATES)}) with a two-level "
        "bootstrap over templates and personas.",
        "",
        md_table(ov[CELL_COLS + ["precision", "recall", "f1", "f1_lo", "f1_hi",
                                 "f1_drop_vs_single_pct", "drop_lo", "drop_hi"]]),
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
        *[line for t in TEMPLATES for line in (f"Per-field F1, naive parser, {t} template:", "", per_field_md(t), "")],
        "## 2. Synonym sensitivity",
        "",
        "`rank_change` > 0 means the resume dropped when it used the alternative wording. "
        "`rel_delta_lo/hi`: 95% CI for the mean relative score change.",
        "",
        md_table(syn_s),
        "",
        "## 3. Keyword stuffing (candidates that started outside the top 5)",
        "",
        "`entered_top_k`: share pushed into the top 5. `beats_best_genuine`: share whose stuffed score beats "
        "every unstuffed resume in the pool (with 95% CI). `median_score_vs_best`: stuffed score / best "
        "unstuffed score.",
        "",
        md_table(stuff_s),
        "",
        "## 4. Ranking stability",
        "",
        md_table(stab_s),
        "",
    ]
    (out / "RESULTS.md").write_text("\n".join(md), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "layout"}, indent=2))


if __name__ == "__main__":
    main()
