import pytest

from ats_sim.data import DATA_DIR
from ats_sim.jd import load_jobs
from ats_sim.jd_rules import extract_knockouts, guess_title
from ats_sim.knockout import check_rules
from ats_sim.models import ParsedResume


@pytest.mark.parametrize("job", load_jobs(DATA_DIR / "jobs") + load_jobs(DATA_DIR / "jobs_extra"), ids=lambda j: j.id)
def test_rules_read_from_the_sample_postings_match_their_answer_keys(job):
    k, found = extract_knockouts(job.text)
    truth = job.knockouts
    assert k.min_degree_level == truth.min_degree_level
    assert k.require_work_authorization == truth.require_work_authorization
    assert k.no_sponsorship == truth.no_sponsorship
    # the answer key's window can be wider than the text says ("by June 2027" has no start)
    assert k.grad_window[1] == truth.grad_window[1]
    if k.degree_fields:  # enforced only when the posting gives a closed list
        assert set(k.degree_fields) <= set(truth.degree_fields)
    assert all(f["source"] for f in found)


@pytest.mark.parametrize("text, rule, value", [
    ("Minimum GPA of 3.2 required.", "gpa", "3.20 or higher"),
    ("3.5/4.0 GPA or higher", "gpa", "3.50 or higher"),
    ("Currently pursuing a Master's or Ph.D. in Electrical Engineering", "degree", "Master's or higher"),
    ("Bachelor's degree in Computer Science, Statistics, or a related field", "field",
     "Computer Science, Statistics or a related field"),
    ("Class of 2027 students only", "graduation", "2027-01 to 2027-12"),
    ("Expected graduation in Spring 2027", "graduation", "2027-03 to 2027-06"),
    ("We will not sponsor H-1B visas for this role.", "sponsorship", "No visa sponsorship"),
    ("Must be legally authorized to work in the United States", "authorization", "Must be authorized to work"),
])
def test_common_phrasings(text, rule, value):
    _, found = extract_knockouts(text)
    assert {(f["rule"], f["value"]) for f in found} >= {(rule, value)}


def test_related_field_is_shown_but_not_enforced():
    k, found = extract_knockouts("Bachelor's degree in Physics or a related field")
    assert k.degree_fields is None and k.min_degree_level == "BS"
    assert [f["enforced"] for f in found if f["rule"] == "field"] == [False]


def test_nothing_is_guessed_from_plain_text():
    k, found = extract_knockouts("We build friendly robots. You will write Python and test hardware.")
    assert found == [] and k.min_degree_level is None and k.grad_window is None


def test_title_and_rule_checks():
    assert guess_title("Data Analyst Intern\n\nAbout us\nWe are a team.") == "Data Analyst Intern"
    assert guess_title("We are hiring a data analyst who loves dashboards and clean data.") == "Pasted job description"
    k, found = extract_knockouts("B.S. in Mechanical Engineering. Minimum GPA 3.0. Graduating by June 2027. "
                                 "Must be authorized to work in the US. We do not sponsor visas.")
    r = ParsedResume(source="x", raw_text="", degree_level="BS", field_of_study="Mechanical Engineering",
                     gpa=2.9, grad_date="2027-05")
    rows = {c["rule"]: c["status"] for c in check_rules(r, k, {"work_authorized": True}, found)}
    assert rows == {"Degree": "pass", "Field of study": "pass", "GPA": "fail", "Graduation": "pass",
                    "Work authorization": "pass", "Visa sponsorship": "ask"}
