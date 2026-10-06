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
from .render import FORMATS, LAYOUTS, RenderOptions, clone, render
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


def build_context(workdir: Path | None = None, extra_pool: list[tuple[str, str]] | None = None) -> Context:
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

def layout_robustness(ctx: Context) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Field extraction accuracy per layout and format, plus downstream effects.

    Returns (field_counts, downstream). field_counts has one row per
    persona x format x layout x field with tp/fp/fn. downstream has one row per
    persona x format x layout x job with the knockout status and keyword score,
    so layout-induced knockout flips can be counted.
    """
    rows, down = [], []
    kw = ctx.scorers[0]
    for p in ctx.personas:
        for fmt in FORMATS:
            for layout in LAYOUTS:
                path = resume_path(p["id"], layout, fmt)
                if not path.exists():
                    render(p, layout, fmt, path)
                parsed = parse_resume(path)
                for f, c in score_resume(p, parsed).items():
                    rows.append(dict(persona=p["id"], format=fmt, layout=layout, field=f, tp=c.tp, fp=c.fp, fn=c.fn))
                for a in ctx.analyses:
                    rules, app = a.job.knockouts, p.get("application")
                    down.append(dict(
                        persona=p["id"], format=fmt, layout=layout, job=a.job.id,
                        knockout=apply_knockouts(parsed, rules, app, "review").status,
                        knockout_strict=apply_knockouts(parsed, rules, app, "reject").status,
                        keyword=kw.score(parsed.raw_text, a),
                    ))
    return pd.DataFrame(rows), pd.DataFrame(down)


def summarize_layout(field_counts: pd.DataFrame, downstream: pd.DataFrame) -> dict[str, pd.DataFrame]:
    def f1(g):
        c = Counts(int(g.tp.sum()), int(g.fp.sum()), int(g.fn.sum()))
        return pd.Series({"precision": c.precision, "recall": c.recall, "f1": c.f1})

    overall = field_counts.groupby(["format", "layout"]).apply(f1, include_groups=False).reset_index()
    per_field = (field_counts.groupby(["format", "layout", "field"]).apply(f1, include_groups=False)
                 .reset_index().pivot_table(index=["format", "field"], columns="layout", values="f1")
                 [list(LAYOUTS)].reindex(pd.MultiIndex.from_product([list(FORMATS), list(ALL_FIELDS)])))
    base = downstream[downstream.layout == "single"].set_index(["persona", "format", "job"])
    d = downstream.join(base[["knockout", "knockout_strict", "keyword"]], on=["persona", "format", "job"],
                        rsuffix="_single")
    d["keyword_change"] = d.keyword - d.keyword_single
    for col in ("knockout", "knockout_strict"):
        d[f"{col}_flip"] = d[col] != d[f"{col}_single"]
    d["wrongly_rejected"] = (d.knockout_strict == "REJECT") & (d.knockout_strict_single != "REJECT")
    d["wrongly_passed"] = (d.knockout_strict != "REJECT") & (d.knockout_strict_single == "REJECT")
    effects = (d.groupby(["format", "layout"])
               .agg(pairs=("knockout_flip", "size"),
                    flips_review_policy=("knockout_flip", "sum"),
                    flips_reject_policy=("knockout_strict_flip", "sum"),
                    newly_rejected_reject_policy=("wrongly_rejected", "sum"),
                    newly_passed_reject_policy=("wrongly_passed", "sum"),
                    mean_keyword_change=("keyword_change", "mean"))
               .reset_index())
    transitions = (d[d.knockout_flip].groupby(["format", "layout", "knockout_single", "knockout"])
                   .size().rename("count").reset_index()
                   .rename(columns={"knockout_single": "single_column_status", "knockout": "status"}))
    single = overall[overall.layout == "single"].set_index("format")["f1"]
    overall["f1_drop_vs_single_pct"] = overall.apply(
        lambda r: 100 * (single[r.format] - r.f1) / single[r.format] if single[r.format] else float("nan"), axis=1)
    return {"overall": overall, "per_field": per_field, "effects": effects, "transitions": transitions}


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
