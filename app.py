"""Streamlit dashboard for the ATS filter simulator.

    streamlit run app.py
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from ats_sim.data import RESUME_DIR, load_personas, resume_path
from ats_sim.jd import analyze_job, load_jobs
from ats_sim.pipeline import Candidate, candidates_from_personas, screen
from ats_sim.parser import parse_resume
from ats_sim.render import FORMATS, LAYOUTS, TEMPLATES
from ats_sim.scorers import EmbeddingScorer, KeywordScorer, TfidfScorer
from ats_sim.search import QueryError, search

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"

st.set_page_config(page_title="ATS Filter Simulator", layout="wide")
st.title("ATS Filter Simulator")
st.caption(
    "A simulator modeled on documented ATS behavior: parse, knockout questions, recruiter search and ranking. "
    "It is not a reproduction of any vendor's proprietary scoring. All candidates are fictional."
)


@st.cache_resource(show_spinner="Rendering resumes...")
def ensure_corpus() -> bool:
    if not all(resume_path("p16", "textbox", "docx", template=t).exists() for t in TEMPLATES):
        from scripts.build_corpus import main as build

        build(RESUME_DIR)
    return True


@st.cache_resource(show_spinner="Parsing resumes...")
def load_candidates(layout: str, fmt: str, template: str, layout_aware: bool) -> list[Candidate]:
    return candidates_from_personas(layout, fmt, template=template, layout_aware=layout_aware)


@st.cache_resource(show_spinner="Loading scorers (first run downloads all-MiniLM-L6-v2)...")
def load_scorers():
    base = candidates_from_personas("single", "pdf")
    corpus = [c.text for c in base] + [j.text for j in load_jobs()]
    return [KeywordScorer().fit(corpus), TfidfScorer().fit(corpus), EmbeddingScorer().fit(corpus)]


ensure_corpus()
jobs = {j.id: j for j in load_jobs()}
personas = {p["id"]: p for p in load_personas()}

with st.sidebar:
    job_id = st.selectbox("Job posting", list(jobs), format_func=lambda j: jobs[j].title)
    layout = st.selectbox("Resume layout (all candidates)", LAYOUTS, help="Same content, different visual layout.")
    fmt = st.selectbox("File format", FORMATS)
    template = st.selectbox("Template", TEMPLATES,
                            help="classic: the template the parser was developed on. The others are held out.")
    layout_aware = st.toggle("Layout-aware parser", value=False,
                             help="Detect tables, boxes and columns before reading. Field rules are unchanged.")
    missing_policy = st.radio("If a knockout field can't be parsed", ["review", "reject", "pass"],
                              help="Real systems differ; 'review' sends the candidate to a human.")
    primary = st.selectbox("Rank by", ["keyword", "tfidf", "embedding"], index=1)
    upload = st.file_uploader("Add your own resume (PDF or DOCX)", type=["pdf", "docx"],
                              help="Parsed locally in this session and not stored.")

analysis = analyze_job(jobs[job_id])
scorers = load_scorers()
emb = next(s for s in scorers if s.name == "embedding")
if emb.backend != "all-MiniLM-L6-v2":
    st.warning(f"Embedding scorer is using **{emb.backend}** because all-MiniLM-L6-v2 could not be loaded. "
               "Embedding scores here are not sentence-embedding results.")

candidates = list(load_candidates(layout, fmt, template, layout_aware))
if upload is not None:
    with tempfile.NamedTemporaryFile(suffix=Path(upload.name).suffix, delete=False) as fh:
        fh.write(upload.getvalue())
    candidates.append(Candidate("upload", parse_resume(fh.name, layout_aware=layout_aware), {}))
    Path(fh.name).unlink(missing_ok=True)
by_id = {c.id: c for c in candidates}

tab_screen, tab_search, tab_job, tab_exp = st.tabs(["Screening", "Recruiter search", "Job analysis", "Experiments"])

with tab_screen:
    df = screen(candidates, analysis, scorers, primary=primary, missing_policy=missing_policy)
    st.subheader(f"{analysis.job.title}: {len(df)} candidates, {(df.knockout != 'REJECT').sum()} past knockouts")
    st.dataframe(
        df, hide_index=True, width="stretch",
        column_config={s.name: st.column_config.ProgressColumn(s.name, min_value=0, max_value=1, format="%.3f")
                       for s in scorers},
    )
    pick = st.selectbox("Inspect a candidate", df.id.tolist(),
                        format_func=lambda i: f"{i} - {by_id[i].parsed.name or '(name not parsed)'}")
    c = by_id[pick]
    left, right = st.columns(2)
    with left:
        st.markdown("**Parsed fields**")
        fields = c.parsed.fields()
        fields["experience"] = [f"{e['title']} @ {e['company']}" for e in fields["experience"]]
        st.json(fields)
        if pick in personas:
            st.markdown("**Answer key** (what the resume actually says)")
            p = personas[pick]
            st.json({"name": p["name"], "email": p["email"], **p["education"], "skills": p["skills"]})
    with right:
        kw = scorers[0].explain(c.text, analysis)
        st.markdown(f"**Keyword match** {kw.score:.2f}")
        st.write("Matched:", ", ".join(kw.matched) or "none")
        st.write("Missing:", ", ".join(kw.missing) or "none")
        st.markdown("**Text the parser read, in order**")
        st.code(c.text, language=None)

with tab_search:
    q = st.text_input("Boolean query", '(Python OR MATLAB) AND "GMP"',
                      help='AND, OR, NOT (or -term), parentheses, "quoted phrases". Adjacent terms are ANDed.')
    k = st.slider("Top k", 1, 20, 5)
    syn = st.checkbox("Expand synonyms from the curated skills list", value=False)
    try:
        hits = search(q, {c.id: c.text for c in candidates}, k=k, expand_synonyms=syn)
        st.dataframe(pd.DataFrame([{"rank": i + 1, "id": h.id, "name": by_id[h.id].parsed.name, "score": h.score,
                                    **h.term_counts} for i, h in enumerate(hits)]),
                     hide_index=True, width="stretch")
        if not hits:
            st.info("No candidates match.")
    except QueryError as e:
        st.error(f"Query error: {e}")

with tab_job:
    st.markdown("**Extracted requirements** (curated skills list + spaCy noun phrases)")
    st.dataframe(pd.DataFrame([vars(r) for r in analysis.requirements]), hide_index=True, width="stretch")
    st.markdown("**Knockout rules**")
    st.json(vars(analysis.job.knockouts))
    with st.expander("Posting text"):
        st.text(analysis.job.text)

with tab_exp:
    md = RESULTS / "RESULTS.md"
    if not md.exists():
        st.info("Run `python scripts/run_experiments.py` to generate results.")
    else:
        for png, caption in [
            ("layout_f1.png", "1. Layout robustness"),
            ("layout_parsers.png", "Layout x template x parser"),
            ("layout_fields_classic_pdf.png", "Per-field F1 (classic template, PDF)"),
            ("layout_fields_modern_pdf.png", "Per-field F1 (modern template, PDF)"),
            ("synonyms.png", "2. Synonym sensitivity"),
            ("stuffing.png", "3. Keyword stuffing audit"),
            ("stability.png", "4. Ranking stability"),
        ]:
            if (RESULTS / png).exists():
                st.image(str(RESULTS / png), caption=caption)
        with st.expander("Full results tables"):
            st.markdown(md.read_text(encoding="utf-8"))
