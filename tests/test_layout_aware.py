import numpy as np
import pandas as pd
import pytest

from ats_sim.data import load_kaggle_resumes, load_personas
from ats_sim.evaluate import micro, score_resume
from ats_sim.experiments import bootstrap_layout, bootstrap_mean
from ats_sim.parser import extract_text, find_gutter, parse_resume
from ats_sim.render import RenderOptions, plain_text, render
from ats_sim.scorers import chunk_text

PERSONAS = load_personas()
P01 = next(p for p in PERSONAS if p["id"] == "p01")


# ------------------------------------------------------------ layout-aware parser

@pytest.mark.parametrize("layout", ["two_column", "table", "textbox"])
def test_layout_aware_recovers_classic_pdf(tmp_path, layout):
    path = render(P01, layout, "pdf", tmp_path / f"{layout}.pdf")
    naive = micro([score_resume(P01, parse_resume(path))]).f1
    aware = micro([score_resume(P01, parse_resume(path, layout_aware=True))]).f1
    assert aware > naive
    assert aware >= 0.9


def test_layout_aware_is_identical_on_single_column(tmp_path):
    path = render(P01, "single", "pdf", tmp_path / "s.pdf")
    assert parse_resume(path, layout_aware=True).fields() == parse_resume(path).fields()


def test_layout_aware_docx_reads_text_boxes(tmp_path):
    path = render(P01, "textbox", "docx", tmp_path / "t.docx")
    assert "priya.raman@example.com" not in extract_text(path)
    r = parse_resume(path, layout_aware=True)
    assert r.email == "priya.raman@example.com"
    assert "pandas" in r.skills


def test_two_column_reading_order_keeps_columns_apart(tmp_path):
    text = extract_text(render(P01, "two_column", "pdf", tmp_path / "t.pdf"), layout_aware=True)
    lines = text.splitlines()
    assert "EXPERIENCE" in lines and "SKILLS" in lines  # headings back on their own lines
    assert lines.index("SKILLS") < lines.index("EXPERIENCE")  # sidebar read before main column


def test_find_gutter():
    def word(x0, x1, top):
        return {"x0": x0, "x1": x1, "top": top, "bottom": top + 10}

    two_col = [word(40, 150, t) for t in range(0, 300, 12)] + [word(220, 560, t) for t in range(0, 300, 12)]
    gutter = find_gutter(two_col, 612)
    assert gutter is not None and 150 < gutter < 220
    one_col = [word(40, 560, t) for t in range(0, 300, 12)]
    assert find_gutter(one_col, 612) is None


# ------------------------------------------------------------ held-out template

def test_modern_template_renders_and_differs(tmp_path):
    opts = RenderOptions(template="modern")
    text = plain_text(P01, opts)
    assert "Work History" in text and "Bachelor of Science, Computer Science" in text
    for layout in ("single", "two_column", "table", "textbox"):
        for fmt in ("pdf", "docx"):
            assert render(P01, layout, fmt, tmp_path / f"{layout}.{fmt}", opts).stat().st_size > 1000


def test_classic_parser_rules_do_not_cover_modern_template(tmp_path):
    """Guards the held-out claim: if someone tunes the parser on the modern
    template, this test fails and the README's held-out numbers are stale."""
    r = parse_resume(render(P01, "single", "pdf", tmp_path / "m.pdf", RenderOptions(template="modern")))
    assert r.email == "priya.raman@example.com" and r.grad_date == "2027-05"
    assert r.field_of_study is None  # "Bachelor of Science, Computer Science" has no "in"
    assert r.skills == []  # "Skills & Certifications" is not a known heading


# ------------------------------------------------------------ statistics

def test_bootstrap_layout_intervals_contain_point_estimate():
    rows = []
    rng = np.random.default_rng(1)
    for i in range(12):
        for layout in ("single", "two_column"):
            tp = 10 if layout == "single" else int(rng.integers(4, 9))
            rows.append(dict(persona=f"p{i}", template="classic", parser="naive", format="pdf", layout=layout,
                             field="x", tp=tp, fp=10 - tp, fn=10 - tp))
    out = bootstrap_layout(pd.DataFrame(rows), n_boot=500).set_index("layout")
    assert out.loc["single", "f1_lo"] == out.loc["single", "f1_hi"] == 1.0
    assert 0 < out.loc["two_column", "f1_lo"] < out.loc["two_column", "f1_hi"] < 1
    assert out.loc["two_column", "drop_lo"] > 0


def test_bootstrap_mean():
    lo, hi = bootstrap_mean([1, 2, 3, 4, 5], n_boot=500)
    assert lo < 3 < hi
    assert bootstrap_mean([2, 2, 2]) == (2.0, 2.0)


# ------------------------------------------------------------ misc

def test_chunker_windows_long_lines():
    chunks = chunk_text(" ".join(f"w{i}" for i in range(100)))
    assert len(chunks) == 3 and all(len(c.split()) <= 40 for c in chunks)


def test_public_loader_samples_per_category(tmp_path):
    csv = tmp_path / "r.csv"
    pd.DataFrame({"ID": range(6), "Resume_str": [f"text  {i}\n more" for i in range(6)],
                  "Category": ["ENGINEERING"] * 3 + ["CHEF"] * 3}).to_csv(csv, index=False)
    out = load_kaggle_resumes(csv, limit=2, category=["engineering"])
    assert len(out) == 2 and all(i.startswith("public-") for i, _ in out)
    assert out[0][1].startswith("text ")  # whitespace normalized


@pytest.mark.parametrize("template", ["classic", "modern", "latex", "career_center", "hybrid"])
def test_layout_aware_matches_naive_on_single_column_for_every_template(tmp_path, template):
    """Column detection must not fire on single-column pages, whatever the
    template does with right-aligned dates or long wrapped lines."""
    for p in PERSONAS[:6]:
        path = render(p, "single", "pdf", tmp_path / f"{p['id']}.pdf", RenderOptions(template=template))
        assert parse_resume(path, layout_aware=True).fields() == parse_resume(path).fields()
