"""Benchmark this project's parsers against open-source parsers on the labeled corpus.

    bash scripts/setup_external.sh          # once: installs OpenResume and pyresparser
    python scripts/benchmark_parsers.py     # -> results/parsers/

Every parser reads the same 640 rendered resumes (16 personas x 5 templates x
2 formats x 4 layouts; OpenResume reads PDF only) and is scored on the same
answer key with lenient matching (see evaluate.score_resume_lenient). Fields
an engine does not attempt are excluded from its score rather than counted as
misses; `common` restricts every engine to the fields all of them attempt.
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

from ats_sim.data import load_personas, resume_path  # noqa: E402
from ats_sim.engines import ATTEMPTED, OpenResumeParser, PyresparserParser, vote  # noqa: E402
from ats_sim.evaluate import LENIENT_FIELDS, score_resume_lenient  # noqa: E402
from ats_sim.parser import parse_resume  # noqa: E402
from ats_sim.render import FORMATS, LAYOUTS, TEMPLATES, RenderOptions, render  # noqa: E402
from scripts.run_experiments import INK2, LAYOUT_LABELS, SERIES, grouped_bars, style  # noqa: E402

OUT = ROOT / "results" / "parsers"
COMMON = ("name", "email", "phone", "degree_level", "field_of_study", "school", "skills", "job_titles")
PARSER_LABELS = {"naive": "ours, naive", "layout_aware": "ours, layout-aware", "openresume": "OpenResume",
                 "pyresparser": "pyresparser", "ensemble": "ensemble (vote)"}
ENSEMBLE_ORDER = ["layout_aware", "openresume", "pyresparser"]  # tie-break priority


def f1(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return 2 * p * r / (p + r) if p + r else 0.0


def boot_f1(df: pd.DataFrame, n_boot: int = 1000, seed: int = 0) -> tuple[float, float]:
    """95% CI for micro-F1, resampling personas."""
    per = df.groupby("persona")[["tp", "fp", "fn"]].sum().to_numpy()
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(per), size=(n_boot, len(per)))
    s = per[idx].sum(axis=1)
    vals = [f1(*row) for row in s]
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def main():
    warnings.filterwarnings("ignore")
    OUT.mkdir(parents=True, exist_ok=True)
    personas = {p["id"]: p for p in load_personas()}
    files = {}  # path -> (persona, template, format, layout)
    for pid, p in personas.items():
        for t in TEMPLATES:
            for fmt in FORMATS:
                for layout in LAYOUTS:
                    path = resume_path(pid, layout, fmt, template=t)
                    if not path.exists():
                        render(p, layout, fmt, path, RenderOptions(template=t))
                    files[str(path)] = (pid, t, fmt, layout)

    parsed: dict[str, dict[str, object]] = {"naive": {}, "layout_aware": {}}
    for f in files:
        parsed["naive"][f] = parse_resume(f)
        parsed["layout_aware"][f] = parse_resume(f, layout_aware=True)
    engines = [e for e in (OpenResumeParser(), PyresparserParser()) if e.available()]
    skipped = [e.name for e in (OpenResumeParser(), PyresparserParser()) if not e.available()]
    cache_dir = ROOT / "results" / "_tmp" / "engine_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    for e in engines:
        todo = [f for f, meta in files.items() if meta[2] in e.formats]
        cache = cache_dir / f"{e.name}.json"
        raw = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
        missing = [f for f in todo if f not in raw]
        print(f"running {e.name} on {len(missing)} of {len(todo)} files (rest cached)")
        if missing:
            raw.update(e.raw_many(missing))
            cache.write_text(json.dumps(raw), encoding="utf-8")
        parsed[e.name] = {f: e.convert(raw[f].get("resume"), f) for f in todo if f in raw}

    members = [m for m in ENSEMBLE_ORDER if m in parsed]
    if len(members) >= 2:
        parsed["ensemble"] = {f: vote([parsed[m][f] for m in members if f in parsed[m]],
                                      [m for m in members if f in parsed[m]]) for f in files}

    rows = []
    for parser, results in parsed.items():
        attempted = ATTEMPTED.get(parser) or set(LENIENT_FIELDS)
        for f, r in results.items():
            pid, t, fmt, layout = files[f]
            for field, c in score_resume_lenient(personas[pid], r).items():
                if field in attempted:
                    rows.append(dict(parser=parser, persona=pid, template=t, format=fmt, layout=layout,
                                     field=field, tp=c.tp, fp=c.fp, fn=c.fn))
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "parser_field_counts.csv", index=False)

    def summarize(d: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
        out = []
        for key, g in d.groupby(keys):
            lo, hi = boot_f1(g)
            out.append(dict(zip(keys, key), f1=f1(g.tp.sum(), g.fp.sum(), g.fn.sum()), f1_lo=lo, f1_hi=hi))
        return pd.DataFrame(out)

    overall = summarize(df, ["parser", "format", "layout"])
    common = summarize(df[df.field.isin(COMMON)], ["parser", "format", "layout"])
    by_template = summarize(df[(df.layout == "single") & (df.format == "pdf")], ["parser", "template"])
    per_field = (df[(df.layout == "single") & (df.format == "pdf")].groupby(["parser", "field"])
                 .apply(lambda g: f1(g.tp.sum(), g.fp.sum(), g.fn.sum()), include_groups=False)
                 .unstack("parser").reindex(list(LENIENT_FIELDS)))
    overall.to_csv(OUT / "parser_overall.csv", index=False)
    common.to_csv(OUT / "parser_common_fields.csv", index=False)
    by_template.to_csv(OUT / "parser_by_template.csv", index=False)
    per_field.to_csv(OUT / "parser_per_field_single_pdf.csv")

    # chart: common-field F1 by layout, PDF and DOCX
    style()
    order = [p for p in PARSER_LABELS if p in parsed]
    fig, axes = plt.subplots(1, 2, figsize=(14, 4.6), sharey=True)
    for ax, fmt in zip(axes, FORMATS):
        series, errors = {}, {}
        for p in order:
            s = common[(common.parser == p) & (common.format == fmt)].set_index("layout").reindex(LAYOUTS)
            if s["f1"].notna().any():
                series[PARSER_LABELS[p]] = s["f1"].tolist()
                errors[PARSER_LABELS[p]] = (s["f1_lo"].tolist(), s["f1_hi"].tolist())
        palette = SERIES + ["#e87ba4"]
        colors = [palette[order.index(next(k for k, v in PARSER_LABELS.items() if v == name))] for name in series]
        grouped_bars(ax, [LAYOUT_LABELS[l] for l in LAYOUTS], series, colors, errors=errors)
        for t in ax.texts:
            t.set_fontsize(7)
        ax.set_title(fmt.upper(), fontsize=11)
        ax.set_ylim(0, 1.12)
    axes[0].set_ylabel("Field F1, fields all engines attempt")
    fig.legend(*axes[0].get_legend_handles_labels(), loc="upper right", ncols=5)
    fig.suptitle("Our parsers vs. open-source parsers (all 5 templates pooled)", x=0.01, ha="left",
                 fontweight="bold")
    fig.text(0.01, 0.01, "Lenient matching. OpenResume reads PDF only. Whiskers: 95% bootstrap CI over personas.",
             fontsize=8, color=INK2)
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    fig.savefig(OUT / "parsers.png", dpi=150)
    plt.close(fig)

    pivot = lambda d: d.pivot_table(index=["format", "layout"], columns="parser", values="f1")[order]  # noqa: E731
    md = [
        "# Parser benchmark",
        "",
        "Generated by `scripts/benchmark_parsers.py`. Lenient matching; fields an engine does not attempt are "
        "excluded. " + (f"Skipped (not installed): {', '.join(skipped)}." if skipped else ""),
        "",
        "## Fields every engine attempts (" + ", ".join(COMMON) + ")",
        "",
        pivot(common).reset_index().to_markdown(index=False, floatfmt=".2f"),
        "",
        "## All attempted fields",
        "",
        pivot(overall).reset_index().to_markdown(index=False, floatfmt=".2f"),
        "",
        "## Single-column PDF by template (all attempted fields)",
        "",
        by_template.pivot_table(index="template", columns="parser", values="f1")[order]
        .reindex(list(TEMPLATES)).reset_index().to_markdown(index=False, floatfmt=".2f"),
        "",
        "## Per-field F1, single-column PDF, all templates",
        "",
        per_field[order].reset_index().to_markdown(index=False, floatfmt=".2f"),
        "",
    ]
    (OUT / "PARSERS.md").write_text("\n".join(md), encoding="utf-8")
    (OUT / "summary.json").write_text(json.dumps({"engines": order, "skipped": skipped}, indent=2), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
