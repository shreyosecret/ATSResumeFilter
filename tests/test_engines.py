"""Adapters, lenient scoring and the vote. Engine-backed tests skip when the
engine is not installed (CI does not install them)."""
import pytest

from ats_sim.data import load_personas
from ats_sim.engines import (
    OpenResumeParser, PyresparserParser, clean_skill_name, skillner_available, vote,
)
from ats_sim.evaluate import LENIENT_FIELDS, micro, score_resume_lenient
from ats_sim.models import ExperienceEntry, ParsedResume
from ats_sim.render import render

P07 = next(p for p in load_personas() if p["id"] == "p07")


def test_openresume_convert_maps_fields():
    raw = {"profile": {"name": "Elena Petrova", "email": "elena.petrova@example.com", "phone": "(555) 415-2287"},
           "educations": [{"school": "Piedmont State University, Raleigh, NC", "degree": "B.S. in Chemical Engineering",
                           "gpa": "3.64", "date": "May 2026"}],
           "workExperiences": [{"company": "Tarheel Biologics", "jobTitle": "Process Engineering Co-op"}],
           "skills": {"featuredSkills": [{"skill": ""}], "descriptions": ["GMP, CAPA", "Python"]}}
    r = OpenResumeParser.convert(raw, "x.pdf")
    assert (r.degree_level, r.field_of_study, r.grad_date, r.gpa) == ("BS", "Chemical Engineering", "2026-05", 3.64)
    assert r.skills == ["GMP", "CAPA", "Python"]
    c = score_resume_lenient(P07, r)
    assert c["school"].tp == 1  # trailing location tolerated
    assert c["job_titles"].tp == 1


def test_pyresparser_convert_marks_missing_fields():
    r = PyresparserParser.convert({"name": "A B", "mobile_number": "415-2287", "degree": ["B.S. in Chemistry"],
                                   "designation": ["Lab Intern"], "skills": ["Python"]}, "x.pdf")
    assert r.grad_date is None and r.gpa is None and r.degree_level == "BS"
    assert r.experience[0].title == "Lab Intern" and r.experience[0].company is None


def test_lenient_scoring_rejects_truncated_phone_and_wrong_values():
    good = ParsedResume(source="", raw_text="", name="Elena Petrova", phone="(555) 415-2287")
    bad = ParsedResume(source="", raw_text="", name="CONTACT", phone="415-2287")
    assert score_resume_lenient(P07, good)["phone"].tp == 1
    c = score_resume_lenient(P07, bad)
    assert (c["phone"].fp, c["name"].fp) == (1, 1)


def test_vote_majority_and_tiebreak():
    a = ParsedResume(source="", raw_text="", name="Elena Petrova", school="Piedmont State University",
                     skills=["Python", "GMP"], experience=[ExperienceEntry("Co-op", "Tarheel")])
    b = ParsedResume(source="", raw_text="", name="CONTACT", school="Piedmont State University, Raleigh, NC",
                     skills=["Python", "HPLC"], experience=[ExperienceEntry("Co-op", "Tarheel Biologics")])
    c = ParsedResume(source="", raw_text="", name="CONTACT", skills=["HPLC", "Design"])
    v = vote([a, b, c], ["a", "b", "c"])
    assert v.name == "CONTACT"  # two of three agree, even though it is wrong
    assert v.school == "Piedmont State University"  # tie between distinct values goes to the first engine
    assert set(v.skills) == {"Python", "GMP", "HPLC"}  # "Design" has no second supporter
    assert len(v.experience) == 1


def test_clean_skill_name():
    assert clean_skill_name("Python (Programming Language)") == "Python"


@pytest.mark.skipif(not OpenResumeParser().available(), reason="OpenResume not installed")
def test_openresume_end_to_end(tmp_path):
    path = render(P07, "single", "pdf", tmp_path / "r.pdf")
    r = OpenResumeParser().parse_many([path])[str(path)]
    assert r.email == "elena.petrova@example.com"
    assert micro([score_resume_lenient(P07, r)], LENIENT_FIELDS).f1 > 0.9


@pytest.mark.skipif(not PyresparserParser().available(), reason="pyresparser not installed")
def test_pyresparser_end_to_end(tmp_path):
    path = render(P07, "single", "pdf", tmp_path / "r.pdf")
    r = PyresparserParser().parse_many([path])[str(path)]
    assert r.name == "Elena Petrova"


@pytest.mark.skipif(not skillner_available(), reason="SkillNer not installed")
def test_skillner_scorer():
    from ats_sim.engines import SkillNerScorer, skillner_skills
    from ats_sim.jd import analyze_job, load_jobs

    assert "MATLAB" in skillner_skills("Analyzed data in MATLAB and Python")
    job = next(j for j in load_jobs() if j.id == "process_engineer")
    a = analyze_job(job)
    s = SkillNerScorer()
    assert s.score("GMP process validation Python bioreactor chromatography", a) > s.score("Marketing and SEO", a)
