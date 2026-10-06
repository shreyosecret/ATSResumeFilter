import pytest

from ats_sim.data import load_personas
from ats_sim.evaluate import ALL_FIELDS, micro, score_resume
from ats_sim.parser import parse_resume, parse_text, split_sections
from ats_sim.render import LAYOUTS, RenderOptions, render

PERSONAS = load_personas()


@pytest.fixture(scope="module")
def p01():
    return next(p for p in PERSONAS if p["id"] == "p01")


@pytest.mark.parametrize("fmt", ["pdf", "docx"])
def test_single_column_is_parsed_exactly(tmp_path, p01, fmt):
    r = parse_resume(render(p01, "single", fmt, tmp_path / f"r.{fmt}"))
    assert r.name == "Priya Raman"
    assert r.email == "priya.raman@example.com"
    assert r.degree_level == "BS" and r.field_of_study == "Computer Science"
    assert r.school == "Lakeshore State University"
    assert r.grad_date == "2027-05" and r.gpa == 3.71
    assert "natural language processing" in r.skills
    assert micro([score_resume(p01, r)]).f1 == 1.0


def test_two_column_pdf_interleaves_and_loses_fields(tmp_path, p01):
    r = parse_resume(render(p01, "two_column", "pdf", tmp_path / "r.pdf"))
    assert r.email == "priya.raman@example.com"  # regexes over raw text survive
    assert r.experience == []  # the experience heading shares a line with the sidebar
    assert micro([score_resume(p01, r)]).f1 < 0.9


def test_table_pdf_merges_headings_with_content(tmp_path, p01):
    r = parse_resume(render(p01, "table", "pdf", tmp_path / "r.pdf"))
    assert "education" not in r.sections
    assert r.grad_date is None


def test_docx_text_boxes_are_invisible_to_python_docx(tmp_path, p01):
    r = parse_resume(render(p01, "textbox", "docx", tmp_path / "r.docx"))
    assert r.email is None and r.phone is None and r.skills == []
    assert r.grad_date == "2027-05"  # body text still parses


@pytest.mark.parametrize("layout", LAYOUTS)
def test_every_layout_renders_both_formats(tmp_path, p01, layout):
    for fmt in ("pdf", "docx"):
        assert render(p01, layout, fmt, tmp_path / f"{layout}.{fmt}").stat().st_size > 1000


def test_hidden_text_is_read_unless_defense_enabled(tmp_path, p01):
    path = render(p01, "single", "pdf", tmp_path / "h.pdf", RenderOptions(hidden_text="Kubernetes Kubernetes"))
    assert "Kubernetes" in parse_resume(path).raw_text
    assert "Kubernetes" not in parse_resume(path, drop_invisible=True).raw_text


def test_section_split_requires_heading_on_its_own_line():
    s = split_sections("Jane Doe\nSKILLS\nPython, SQL\nEXPERIENCE Engineer | Co | Jan 2024 – Present")
    assert s["skills"].startswith("Python, SQL\nEXPERIENCE")
    assert "experience" not in s


def test_numeric_dates_and_gpa_formats():
    r = parse_text("Ana Lima\nEDUCATION\nB.Sc. in Physics\nCoastal University\n05/2026 GPA: 3.5\n"
                   "EXPERIENCE\nAnalyst | Acme | 06/2024 - 08/2024")
    assert r.degree_level == "BS" and r.field_of_study == "Physics"
    assert r.grad_date == "2026-05" and r.gpa == 3.5
    assert r.experience[0].company == "Acme"


def test_evaluation_counts_wrong_scalar_as_fp_and_fn(p01):
    r = parse_text("Wrong Name\npriya.raman@example.com")
    c = score_resume(p01, r)
    assert (c["name"].fp, c["name"].fn) == (1, 1)
    assert c["email"].tp == 1
    assert set(c) == set(ALL_FIELDS)
