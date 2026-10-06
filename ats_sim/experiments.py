"""The four experiments.

Every experiment changes one thing about a resume, runs it through the same
parse -> score pipeline, and measures the effect. Scoring experiments (2-4)
rank candidates on score alone, ignoring knockouts, so the scorer is the only
moving part.
"""
from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .data import load_personas, resume_path
from .evaluate import ALL_FIELDS, Counts, micro, score_resume
from .jd import analyze_job, load_jobs
from .knockout import apply_knockouts
from .parser import parse_resume
from .render import FORMATS, HELD_OUT_TEMPLATES, LAYOUTS, TEMPLATES, RenderOptions, clone, render
from .scorers import EmbeddingScorer, KeywordScorer, TfidfScorer

TOP_K = 5


@dataclass
class Context:
    personas: list[dict]
    analyses: list
    scorers: list  # keyword, tfidf, embedding
    reference: list  # keyword+taxonomy (synonym experiment only)
    base_text: dict[str, str]  # persona id -> parsed single-column PDF text
    workdir: Path

    @property
    def embedding_backend(self) -> str:
        return next(s.backend for s in self.scorers if s.name == "embedding")


def build_context(workdir: Path | None = None, extra_pool: list[tuple[str, str]] | None = None,
                  extra_scorers: list | None = None) -> Context:
    """Parse the single-column PDFs and fit the scorers.

    `extra_pool` adds (id, text) candidates, e.g. Kaggle resumes, to every
    ranking pool and to the scorer corpus. They are never edited themselves.
    """
    personas = load_personas()
    analyses = [analyze_job(j) for j in load_jobs()]
    base_text = {}
    for p in personas:
        path = resume_path(p["id"], "single", "pdf")
        if not path.exists():
            render(p, "single", "pdf", path)
        base_text[p["id"]] = parse_resume(path).raw_text
    for cid, text in extra_pool or []:
        base_text[cid] = text
    corpus = list(base_text.values()) + [a.job.text for a in analyses]
    scorers = [KeywordScorer().fit(corpus), TfidfScorer().fit(corpus), EmbeddingScorer().fit(corpus)]
    scorers += [s.fit(corpus) for s in extra_scorers or []]
    reference = [KeywordScorer(use_taxonomy=True)]
    workdir = Path(workdir or tempfile.mkdtemp(prefix="ats_sim_"))
    workdir.mkdir(parents=True, exist_ok=True)
    return Context(personas, analyses, scorers, reference, base_text, workdir)


def _variant_text(ctx: Context, p: dict, key: str, opts: RenderOptions | None = None,
                  drop_invisible: bool = False) -> str:
    path = render(p, "single", "pdf", ctx.workdir / f"{p['id']}-{key}.pdf", opts)
    return parse_resume(path, drop_invisible=drop_invisible).raw_text


def _rank_of(target_id: str, target_score: float, pool_scores: dict[str, float]) -> int:
    """Rank (1 = best, ties share the better rank) of target among the pool
    with the target's own pool entry replaced by `target_score`."""
    others = [s for pid, s in pool_scores.items() if pid != target_id]
    return 1 + sum(s > target_score + 1e-12 for s in others)


def _pool_scores(ctx: Context, analysis, scorer) -> dict[str, float]:
    return {pid: scorer.score(t, analysis) for pid, t in ctx.base_text.items()}


# --------------------------------------------------------------------- 1

PARSERS = {"naive": False, "layout_aware": True}
CELL = ["template", "parser", "format", "layout"]


def layout_robustness(ctx: Context) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Field extraction accuracy per template, parser mode, format and layout.

    Returns (field_counts, downstream). field_counts has one row per
    persona x template x parser x format x layout x field with tp/fp/fn.
    downstream has one row per persona x template x parser x format x layout x
    job with knockout status and keyword score, so layout-induced knockout
    flips can be counted.
    """
    rows, down = [], []
    kw = ctx.scorers[0]
    for p in ctx.personas:
        for template in TEMPLATES:
            for fmt in FORMATS:
                for layout in LAYOUTS:
                    path = resume_path(p["id"], layout, fmt, template=template)
                    if not path.exists():
                        render(p, layout, fmt, path, RenderOptions(template=template))
                    for parser, aware in PARSERS.items():
                        parsed = parse_resume(path, layout_aware=aware)
                        key = dict(persona=p["id"], template=template, parser=parser, format=fmt, layout=layout)
                        for f, c in score_resume(p, parsed).items():
                            rows.append(dict(key, field=f, tp=c.tp, fp=c.fp, fn=c.fn))
                        for a in ctx.analyses:
                            rules, app = a.job.knockouts, p.get("application")
                            down.append(dict(
                                key, job=a.job.id,
                                knockout=apply_knockouts(parsed, rules, app, "review").status,
                                knockout_strict=apply_knockouts(parsed, rules, app, "reject").status,
                                keyword=kw.score(parsed.raw_text, a),
                            ))
    return pd.DataFrame(rows), pd.DataFrame(down)


def _f1(tp, fp, fn):
    import numpy as np

    p = np.divide(tp, tp + fp, out=np.zeros_like(tp, dtype=float), where=(tp + fp) > 0)
    r = np.divide(tp, tp + fn, out=np.zeros_like(tp, dtype=float), where=(tp + fn) > 0)
    return np.divide(2 * p * r, p + r, out=np.zeros_like(p), where=(p + r) > 0)


def bootstrap_layout(field_counts: pd.DataFrame, n_boot: int = 2000, seed: int = 0) -> pd.DataFrame:
    """95% percentile intervals for F1 and for the drop vs single column.

    Personas are resampled with replacement, and the same resample is used
    for every cell, so each layout's drop is compared with its own
    single-column baseline on the same people (a paired bootstrap).
    """
    import numpy as np

    per = field_counts.groupby(CELL + ["persona"])[["tp", "fp", "fn"]].sum()
    cells = per.index.droplevel("persona").unique()
    personas = sorted(field_counts.persona.unique())
    arr = np.stack([per.loc[c].reindex(personas).to_numpy() for c in cells])  # cells x personas x 3
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(personas), size=(n_boot, len(personas)))
    sums = arr[:, idx, :].sum(axis=2)  # cells x boot x 3
    f1 = _f1(sums[..., 0], sums[..., 1], sums[..., 2])
    cell_list = list(cells)
    base_idx = [cell_list.index((t, pa, fm, "single")) for t, pa, fm, _ in cell_list]
    base = f1[base_idx]
    drop = 100 * np.divide(base - f1, base, out=np.full_like(f1, np.nan), where=base > 0)
    out = pd.DataFrame(cell_list, columns=CELL)
    out["f1_lo"], out["f1_hi"] = np.percentile(f1, 2.5, axis=1), np.percentile(f1, 97.5, axis=1)
    out["drop_lo"], out["drop_hi"] = np.nanpercentile(drop, 2.5, axis=1), np.nanpercentile(drop, 97.5, axis=1)
    return out


POOLED = "held_out_pooled"


def bootstrap_pooled(field_counts: pd.DataFrame, templates=HELD_OUT_TEMPLATES, n_boot: int = 2000,
                     seed: int = 0) -> pd.DataFrame:
    """F1 and drop for all held-out templates pooled, with a two-level
    bootstrap: each resample draws templates with replacement, then personas
    with replacement, so the interval reflects both sources of variation.
    With only a handful of templates the template level is coarse; treat the
    interval as a lower bound on the real uncertainty.
    """
    import numpy as np

    fc = field_counts[field_counts.template.isin(templates)]
    cells = sorted(fc.groupby(["parser", "format", "layout"]).groups)
    personas = sorted(fc.persona.unique())
    per = fc.groupby(["template", "parser", "format", "layout", "persona"])[["tp", "fp", "fn"]].sum()
    arr = np.zeros((len(templates), len(personas), len(cells), 3))
    for ti, t in enumerate(templates):
        for ci, c in enumerate(cells):
            arr[ti, :, ci, :] = per.loc[(t, *c)].reindex(personas).to_numpy()
    rng = np.random.default_rng(seed)
    ti = rng.integers(0, len(templates), size=(n_boot, len(templates)))
    pi = rng.integers(0, len(personas), size=(n_boot, len(personas)))
    sums = np.stack([arr[ti[b]][:, pi[b]].sum(axis=(0, 1)) for b in range(n_boot)])  # boot x cells x 3
    f1 = _f1(sums[..., 0], sums[..., 1], sums[..., 2])
    point_sums = arr.sum(axis=(0, 1))
    point = _f1(point_sums[:, 0], point_sums[:, 1], point_sums[:, 2])
    base_idx = [cells.index((pa, fm, "single")) for pa, fm, _ in cells]
    drop = 100 * np.divide(f1[:, base_idx] - f1, f1[:, base_idx], out=np.full_like(f1, np.nan),
                           where=f1[:, base_idx] > 0)
    point_drop = 100 * (point[base_idx] - point) / point[base_idx]
    out = pd.DataFrame(cells, columns=["parser", "format", "layout"])
    out.insert(0, "template", POOLED)
    tp, fp, fn = point_sums[:, 0], point_sums[:, 1], point_sums[:, 2]
    out["precision"], out["recall"], out["f1"] = tp / np.maximum(tp + fp, 1), tp / np.maximum(tp + fn, 1), point
    out["f1_drop_vs_single_pct"] = point_drop
    out["f1_lo"], out["f1_hi"] = np.percentile(f1, 2.5, axis=0), np.percentile(f1, 97.5, axis=0)
    out["drop_lo"], out["drop_hi"] = np.nanpercentile(drop, 2.5, axis=0), np.nanpercentile(drop, 97.5, axis=0)
    return out


def summarize_layout(field_counts: pd.DataFrame, downstream: pd.DataFrame, n_boot: int = 2000) -> dict[str, pd.DataFrame]:
    def f1(g):
        c = Counts(int(g.tp.sum()), int(g.fp.sum()), int(g.fn.sum()))
        return pd.Series({"precision": c.precision, "recall": c.recall, "f1": c.f1})

    overall = field_counts.groupby(CELL).apply(f1, include_groups=False).reset_index()
    single = overall[overall.layout == "single"].set_index(["template", "parser", "format"])["f1"]
    overall["f1_drop_vs_single_pct"] = overall.apply(
        lambda r: 100 * (single[(r.template, r.parser, r.format)] - r.f1) / single[(r.template, r.parser, r.format)],
        axis=1)
    overall = overall.merge(bootstrap_layout(field_counts, n_boot), on=CELL)
    if set(HELD_OUT_TEMPLATES) <= set(field_counts.template):
        overall = pd.concat([overall, bootstrap_pooled(field_counts, n_boot=n_boot)], ignore_index=True)
    per_field = (field_counts[field_counts.parser == "naive"]
                 .groupby(["template", "format", "layout", "field"]).apply(f1, include_groups=False)
                 .reset_index().pivot_table(index=["template", "format", "field"], columns="layout", values="f1")
                 [list(LAYOUTS)]
                 .reindex(pd.MultiIndex.from_product([list(TEMPLATES), list(FORMATS), list(ALL_FIELDS)])))

    keys = ["persona", "template", "parser", "format", "job"]
    base = downstream[downstream.layout == "single"].set_index(keys)
    d = downstream.join(base[["knockout", "knockout_strict", "keyword"]], on=keys, rsuffix="_single")
    d["keyword_change"] = d.keyword - d.keyword_single
    for col in ("knockout", "knockout_strict"):
        d[f"{col}_flip"] = d[col] != d[f"{col}_single"]
    d["wrongly_rejected"] = (d.knockout_strict == "REJECT") & (d.knockout_strict_single != "REJECT")
    d["wrongly_passed"] = (d.knockout_strict != "REJECT") & (d.knockout_strict_single == "REJECT")
    effects = (d.groupby(CELL)
               .agg(pairs=("knockout_flip", "size"),
                    flips_review_policy=("knockout_flip", "sum"),
                    flips_reject_policy=("knockout_strict_flip", "sum"),
                    newly_rejected_reject_policy=("wrongly_rejected", "sum"),
                    newly_passed_reject_policy=("wrongly_passed", "sum"),
                    mean_keyword_change=("keyword_change", "mean"))
               .reset_index())
    transitions = (d[d.knockout_flip].groupby(CELL + ["knockout_single", "knockout"])
                   .size().rename("count").reset_index()
                   .rename(columns={"knockout_single": "single_column_status", "knockout": "status"}))
    return {"overall": overall, "per_field": per_field, "effects": effects, "transitions": transitions}


def bootstrap_mean(values, n_boot: int = 2000, seed: int = 0) -> tuple[float, float]:
    """95% percentile interval for a mean."""
    import numpy as np

    v = np.asarray([x for x in values if x == x], dtype=float)
    if len(v) == 0:
        return float("nan"), float("nan")
    means = v[np.random.default_rng(seed).integers(0, len(v), size=(n_boot, len(v)))].mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


# --------------------------------------------------------------------- 2

# (term as written in the posting, alternative wording a candidate might use)
SYNONYM_PAIRS = [
    ("machine learning", "ML"),
    ("natural language processing", "NLP"),
    ("GMP", "good manufacturing practice"),
    ("SOPs", "standard operating procedures"),
    ("CAPA", "corrective and preventive action"),
    ("root cause analysis", "RCA"),
    ("CAD", "Onshape"),
    ("FEA", "finite element analysis"),
    ("3D printing", "additive manufacturing"),
]


def _sub(text: str, old: str, new: str) -> str:
    flags = 0 if len(old) <= 3 else re.IGNORECASE
    return re.sub(rf"(?<![\w+#&]){re.escape(old)}(?![\w+#&])", new, text, flags=flags)


def replace_term(p: dict, old: str, new: str) -> dict:
    """Swap wording in skills, bullets and projects. Titles and companies stay put."""
    q = clone(p)
    q["skills"] = [_sub(s, old, new) for s in q["skills"]]
    for x in q["experience"]:
        x["bullets"] = [_sub(b, old, new) for b in x["bullets"]]
    for pr in q.get("projects", []):
        pr["bullets"] = [_sub(b, old, new) for b in pr["bullets"]]
    return q


def _mentions(p: dict, term: str) -> bool:
    blob = "\n".join(p["skills"] + [b for x in p["experience"] for b in x["bullets"]]
                     + [b for pr in p.get("projects", []) for b in pr["bullets"]])
    return _sub(blob, term, "\0") != blob


def synonym_sensitivity(ctx: Context) -> pd.DataFrame:
    """For each posting term with a common alternative, compare a resume that
    uses the posting's wording with the same resume using the alternative.

    Both directions are used: resumes that already use the posting's wording
    get the alternative swapped in, and resumes that use the alternative get
    the posting's wording swapped in. `delta` is always
    score(alternative wording) - score(posting wording).
    """
    rows = []
    scorers = ctx.scorers + ctx.reference
    for a in ctx.analyses:
        surfaces = {r.surface.lower() for r in a.requirements}
        pools = {s.name: _pool_scores(ctx, a, s) for s in scorers}
        for jd_form, alt in SYNONYM_PAIRS:
            if jd_form.lower() not in surfaces:
                continue
            for p in ctx.personas:
                if _mentions(p, jd_form):
                    jd_version, alt_version = p, replace_term(p, jd_form, alt)
                    direction = "posting->alt"
                elif _mentions(p, alt):
                    jd_version, alt_version = replace_term(p, alt, jd_form), p
                    direction = "alt->posting"
                else:
                    continue
                key = re.sub(r"\W+", "_", f"{jd_form}-{alt}")
                t_jd = ctx.base_text[p["id"]] if jd_version is p else _variant_text(ctx, jd_version, key + "-jd")
                t_alt = ctx.base_text[p["id"]] if alt_version is p else _variant_text(ctx, alt_version, key + "-alt")
                for s in scorers:
                    s_jd, s_alt = s.score(t_jd, a), s.score(t_alt, a)
                    pool = pools[s.name]
                    rows.append(dict(
                        job=a.job.id, posting_term=jd_form, alternative=alt, persona=p["id"],
                        direction=direction, scorer=s.name, score_posting_wording=s_jd, score_alternative=s_alt,
                        delta=s_alt - s_jd, rel_delta=(s_alt - s_jd) / s_jd if s_jd else float("nan"),
                        rank_posting_wording=_rank_of(p["id"], s_jd, pool),
                        rank_alternative=_rank_of(p["id"], s_alt, pool),
                    ))
    df = pd.DataFrame(rows)
    df["rank_change"] = df.rank_alternative - df.rank_posting_wording  # positive = dropped
    return df


# --------------------------------------------------------------------- 3

def _jd_keywords(a) -> list[str]:
    return [r.surface for r in a.requirements if r.curated]


STUFFING_ATTACKS = ("visible_repeat", "hidden_keywords", "hidden_jd")


def stuffing_options(attack: str, a) -> RenderOptions:
    words = ", ".join(_jd_keywords(a) * 3)
    if attack == "visible_repeat":
        return RenderOptions(extra_sections=[("Keywords", words)])
    if attack == "hidden_keywords":
        return RenderOptions(hidden_text=words)
    if attack == "hidden_jd":
        return RenderOptions(hidden_text=a.job.text.replace("\n", " "))
    raise ValueError(attack)


def keyword_stuffing(ctx: Context) -> pd.DataFrame:
    """Audit: does adding keywords a human reviewer would not credit (repeated
    lists, white text, a pasted copy of the posting) move a candidate up?

    Hidden attacks are also re-parsed with the `drop_invisible` defense to
    show where the fix belongs (the parser, not the scorer).
    """
    rows = []
    for a in ctx.analyses:
        pools = {s.name: _pool_scores(ctx, a, s) for s in ctx.scorers}
        for p in ctx.personas:
            for attack in STUFFING_ATTACKS:
                opts = stuffing_options(attack, a)
                texts = {"none": _variant_text(ctx, p, f"{a.job.id}-{attack}", opts)}
                if attack.startswith("hidden"):
                    texts["drop_invisible"] = _variant_text(ctx, p, f"{a.job.id}-{attack}", opts, drop_invisible=True)
                for defense, text in texts.items():
                    for s in ctx.scorers:
                        base = pools[s.name][p["id"]]
                        new = s.score(text, a)
                        r0 = _rank_of(p["id"], base, pools[s.name])
                        r1 = _rank_of(p["id"], new, pools[s.name])
                        best_other = max(v for pid, v in pools[s.name].items() if pid != p["id"])
                        rows.append(dict(
                            job=a.job.id, persona=p["id"], attack=attack, defense=defense, scorer=s.name,
                            base_score=base, stuffed_score=new, delta=new - base,
                            base_rank=r0, stuffed_rank=r1, rank_gain=r0 - r1,
                            entered_top_k=(r0 > TOP_K and r1 <= TOP_K), was_outside_top_k=r0 > TOP_K,
                            reached_rank_1=(r0 > 1 and r1 == 1),
                            beats_best_genuine=new > best_other,
                            score_vs_best_genuine=new / best_other if best_other else float("nan"),
                        ))
    return pd.DataFrame(rows)


# --------------------------------------------------------------------- 4

VERB_SWAPS = {
    "Built": "Developed", "Designed": "Created", "Trained": "Developed", "Wrote": "Authored",
    "Ran": "Performed", "Used": "Applied", "Led": "Headed", "Analyzed": "Evaluated", "Modeled": "Simulated",
    "Supported": "Assisted with", "Managed": "Oversaw", "Created": "Produced", "Maintained": "Kept up",
    "Followed": "Adhered to", "Revised": "Updated", "Applied": "Used", "Grew": "Increased",
    "Tracked": "Monitored", "Prepared": "Made", "Mentored": "Coached", "Resolved": "Fixed",
    "Tutored": "Taught", "Fine-tuned": "Adapted", "Shipped": "Delivered", "Optimized": "Improved",
}
EDITS = ("verb_swap", "reorder_bullets", "date_format", "add_teamwork_bullet", "all_edits")


def apply_edit(p: dict, edit: str) -> tuple[dict, RenderOptions]:
    q, opts = clone(p), RenderOptions()
    edits = ("verb_swap", "reorder_bullets", "date_format", "add_teamwork_bullet") if edit == "all_edits" else (edit,)
    for e in edits:
        if e == "verb_swap":
            for x in q["experience"] + q.get("projects", []):
                x["bullets"] = [
                    (VERB_SWAPS[b.split()[0]] + b[len(b.split()[0]):]) if b.split()[0] in VERB_SWAPS else b
                    for b in x["bullets"]
                ]
        elif e == "reorder_bullets":
            for x in q["experience"]:
                x["bullets"] = list(reversed(x["bullets"]))
        elif e == "date_format":
            opts.date_style = "numeric"
        elif e == "add_teamwork_bullet":
            q["experience"][0]["bullets"].append("Collaborated with cross-functional teams to meet project deadlines")
        else:
            raise ValueError(e)
    return q, opts


def ranking_stability(ctx: Context) -> pd.DataFrame:
    """Small wording edits to one resume while the rest of the pool stays fixed:
    how far does that resume move?"""
    rows = []
    texts = {}
    for p in ctx.personas:
        for edit in EDITS:
            q, opts = apply_edit(p, edit)
            texts[(p["id"], edit)] = _variant_text(ctx, q, f"edit-{edit}", opts)
    for a in ctx.analyses:
        for s in ctx.scorers:
            pool = _pool_scores(ctx, a, s)
            for p in ctx.personas:
                r0 = _rank_of(p["id"], pool[p["id"]], pool)
                for edit in EDITS:
                    new = s.score(texts[(p["id"], edit)], a)
                    r1 = _rank_of(p["id"], new, pool)
                    rows.append(dict(job=a.job.id, scorer=s.name, persona=p["id"], edit=edit,
                                     base_score=pool[p["id"]], edited_score=new, base_rank=r0, edited_rank=r1,
                                     abs_rank_change=abs(r1 - r0),
                                     top_k_flip=(r0 <= TOP_K) != (r1 <= TOP_K)))
    return pd.DataFrame(rows)
