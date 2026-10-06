import pytest

from ats_sim.jd import analyze_job, load_jobs
from ats_sim.knockout import PASS, REJECT, REVIEW, apply_knockouts
from ats_sim.models import JobPosting, Knockouts
from ats_sim.parser import parse_text
from ats_sim.scorers import EmbeddingScorer, KeywordScorer, TfidfScorer
from ats_sim.search import QueryError, parse_query, search

JOBS = {j.id: j for j in load_jobs()}


def resume(grad="May 2026", gpa="3.40", field="Chemical Engineering"):
    gpa_part = f" | GPA: {gpa}" if gpa else ""
    return parse_text(f"Sam Park\nEDUCATION\nB.S. in {field}\nRiver University\n{grad}{gpa_part}\n")


# ------------------------------------------------------------ job analyzer

def test_required_vs_preferred_and_alternatives():
    a = analyze_job(JOBS["process_engineer"])
    levels = {r.name: r for r in a.requirements if r.curated}
    assert levels["GMP"].level == "required"
    assert levels["HPLC"].level == "preferred"
    assert levels["Python"].group and levels["Python"].group == levels["MATLAB"].group


def test_preferred_cue_inside_a_required_line():
    a = analyze_job(JOBS["mechanical_design"])
    levels = {r.name: r.level for r in a.requirements}
    assert levels["CAD"] == "required"
    assert levels["SolidWorks"] == "preferred"  # "Proficiency in CAD, ideally SolidWorks"


def test_degree_lines_do_not_become_skills():
    a = analyze_job(JOBS["ml_intern"])
    assert {r.name: r.level for r in a.requirements}["statistics"] == "preferred"


# ------------------------------------------------------------ knockouts

def test_knockouts_pass_reject_review():
    rules = JOBS["process_engineer"].knockouts
    assert apply_knockouts(resume(), rules, {"work_authorized": True}).status == PASS
    low = apply_knockouts(resume(gpa="2.50"), rules)
    assert low.status == REJECT and "GPA" in low.reasons[0]
    assert apply_knockouts(resume(grad="May 2028"), rules).status == REJECT
    assert apply_knockouts(resume(field="History"), rules).status == REJECT
    assert apply_knockouts(resume(gpa=None), rules).status == REVIEW
    assert apply_knockouts(resume(gpa=None), rules, missing_policy="reject").status == REJECT
    assert apply_knockouts(resume(), rules, {"work_authorized": False}).status == REJECT


def test_sponsorship_rule_only_when_posting_says_so():
    assert apply_knockouts(resume(), Knockouts(no_sponsorship=True), {"needs_sponsorship": True}).status == REJECT
    assert apply_knockouts(resume(), Knockouts(), {"needs_sponsorship": True}).status == PASS


# ------------------------------------------------------------ scorers

@pytest.fixture(scope="module")
def mech():
    return analyze_job(JOBS["mechanical_design"], use_noun_phrases=False)


def test_keyword_scorer_is_exact_and_presence_based(mech):
    kw = KeywordScorer()
    base = "Designed parts in CAD with GD&T and FEA"
    assert kw.score(base, mech) == kw.score(base + " CAD CAD CAD", mech)
    assert kw.score("Designed parts in Onshape", mech) < kw.score("Designed parts in CAD", mech)


def test_taxonomy_credits_narrower_tools(mech):
    assert KeywordScorer(use_taxonomy=True).score("Onshape", mech) > KeywordScorer().score("Onshape", mech)


def test_alternatives_count_once():
    job = JobPosting("t", "t", "Requirements\n- Python or MATLAB\n- SQL")
    a = analyze_job(job, use_noun_phrases=False)
    kw = KeywordScorer()
    assert kw.score("MATLAB and SQL", a) == 1.0
    assert kw.score("Python", a) == pytest.approx(0.5)


def test_tfidf_and_embedding_rank_relevant_text_higher(mech):
    good = "Mechanical design engineer. CAD models in SolidWorks, GD&T drawings, FEA in ANSYS, 3D printing prototypes."
    bad = "Marketing coordinator. Grew newsletter signups with SEO and social media campaigns."
    corpus = [good, bad, mech.job.text]
    for s in (TfidfScorer().fit(corpus), EmbeddingScorer().fit(corpus)):
        assert s.score(good, mech) > s.score(bad, mech)


def test_tfidf_requires_fit(mech):
    with pytest.raises(RuntimeError):
        TfidfScorer().score("x", mech)


# ------------------------------------------------------------ search

DOCS = {
    "a": "Python developer with GMP experience",
    "b": "MATLAB and GMP, MATLAB scripting",
    "c": "Python only",
    "d": "good manufacturing practice and Python",
}


def test_boolean_search():
    ids = [h.id for h in search('(Python OR MATLAB) AND "GMP"', DOCS)]
    assert sorted(ids) == ["a", "b"]
    assert ids[0] == "b"  # MATLAB appears twice
    assert [h.id for h in search("Python NOT GMP", DOCS)] == ["c", "d"]
    assert [h.id for h in search("Python -GMP", DOCS)] == ["c", "d"]
    assert "d" in [h.id for h in search("Python GMP", DOCS, expand_synonyms=True)]


def test_search_top_k_and_errors():
    assert len(search("Python OR MATLAB", DOCS, k=2)) == 2
    for bad in ("", "(Python", "AND Python", "Python)"):
        with pytest.raises(QueryError):
            parse_query(bad)
