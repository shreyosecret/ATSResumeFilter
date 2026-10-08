import numpy as np
import pytest

from ats_sim.data import load_personas
from ats_sim.learn.corpus import document
from ats_sim.learn.labels import LABELS, split_lines
from ats_sim.learn.store import ModelStore
from ats_sim.learn.tagger import LineTagger, load, parse_with_tagger, save, sections_from_labels

SMALL = {"templates": ("classic",), "layouts": ("single", "two_column"), "fmts": ("pdf",), "formats": ("f01", "f02"),
         "per_persona": 1}


@pytest.fixture(scope="module")
def personas():
    return load_personas()


@pytest.fixture(scope="module")
def base(personas, tmp_path_factory):
    cache = tmp_path_factory.mktemp("corpus")
    docs = [document(p, "classic", lay, "pdf", cache=cache, root=cache)
            for p in personas[:10] for lay in ("single", "two_column")]
    return LineTagger(seed=0).fit(docs)


def test_labels_follow_the_source(personas, tmp_path):
    p = personas[3]
    lines, labels, _ = document(p, "hybrid", "table", "pdf", root=tmp_path, cache=tmp_path)
    assert labels[0] == "name" and lines[0] == p["name"]
    assert set(labels) <= set(LABELS)
    # "Education &" / "Certifications" wrap in a narrow cell; both are heading fragments
    assert labels[lines.index("Certifications")] == "heading"
    edu = [l for l, y in zip(lines, labels) if y == "education"]
    assert any(p["education"]["school"] in l for l in edu)


def test_sections_from_labels():
    lines = ["Ana Ruiz", "ana@x.com", "SCHOOLING", "B.S. in Biology", "TOOLS", "Python, R"]
    labels = ["name", "contact", "heading", "education", "heading", "skills"]
    sections, name = sections_from_labels(lines, labels)
    assert name == "Ana Ruiz"
    assert sections == {"header": "Ana Ruiz\nana@x.com", "education": "B.S. in Biology", "skills": "Python, R"}


def test_tagger_reads_known_layouts(base, personas, tmp_path):
    p = personas[12]  # not in the training set
    lines, labels, geo = document(p, "classic", "single", "pdf", root=tmp_path, cache=tmp_path)
    pred = base.predict(lines, geo)
    assert np.mean([a == b for a, b in zip(pred, labels)]) > 0.9
    parsed, _, _ = parse_with_tagger("\n".join(lines), base, geo=geo)
    assert parsed.name == p["name"] and parsed.school == p["education"]["school"]


def test_learning_one_resume_fixes_a_new_template(base, personas, tmp_path):
    teach = document(personas[11], "hybrid", "single", "pdf", root=tmp_path, cache=tmp_path)
    test = document(personas[13], "hybrid", "single", "pdf", root=tmp_path, cache=tmp_path)
    acc = lambda tg: np.mean([a == b for a, b in zip(tg.predict(test[0], test[2]), test[1])])  # noqa: E731
    before = acc(base)
    import copy
    tg = copy.deepcopy(base)
    event = tg.learn(*teach)
    assert event["accuracy_after"] >= event["accuracy_before"]
    assert acc(tg) > before  # generalizes to a different person in the same template
    assert tg.info()["taught"] == 1 and base.info()["taught"] == 0


def test_learn_rejects_bad_input(base):
    with pytest.raises(ValueError):
        base.learn(["a", "b"], ["name"])
    with pytest.raises(ValueError):
        base.learn(["a"], ["salary"])


def test_save_and_load(base, tmp_path):
    save(base, tmp_path / "m.joblib")
    again = load(tmp_path / "m.joblib")
    lines = ["Ana Ruiz", "ana@x.com", "EDUCATION", "B.S. in Biology"]
    assert again.predict(lines) == base.predict(lines)
    (tmp_path / "bad.joblib").write_bytes(b"nope")
    assert load(tmp_path / "bad.joblib") is None


def test_store_learns_and_resets(personas, tmp_path):
    store = ModelStore(tmp_path / "model", corpus=SMALL).load()
    assert store.ready() and store.base_path.exists() and not store.current_path.exists()
    lines = split_lines("Ana Ruiz\nana@x.com\nAcademic Background\nB.S. in Biology, State University\nToolbox\nPython, R")
    labels = ["name", "contact", "heading", "education", "heading", "skills"]
    store.learn(lines, labels)
    assert store.current_path.exists() and store.info()["taught"] == 1
    reloaded = ModelStore(tmp_path / "model", corpus=SMALL).load()
    assert reloaded.info()["taught"] == 1
    store.reset()
    assert not store.current_path.exists() and store.info()["taught"] == 0


def test_geometry_lines_match_the_text_reader(personas, tmp_path):
    from ats_sim.learn.geometry import GEO_FEATURES, read
    from ats_sim.parser import extract_text
    from ats_sim.render import RenderOptions, render

    for fmt in ("pdf", "docx"):
        path = render(personas[0], "two_column", fmt, tmp_path / f"r.{fmt}", RenderOptions(template="modern"))
        rows = read(path)
        assert [r.text for r in rows] == split_lines(extract_text(path, layout_aware=True))
        assert all(len(r.geo) == len(GEO_FEATURES) for r in rows)
    size, bold = GEO_FEATURES.index("size_ratio"), GEO_FEATURES.index("bold")
    pdf = read(render(personas[0], "single", "pdf", tmp_path / "s.pdf", RenderOptions()))
    assert pdf[0].geo[size] > max(r.geo[size] for r in pdf[1:])  # the name is the largest text
    assert pdf[[r.text for r in pdf].index("EDUCATION")].geo[bold] == 1.0


def test_text_only_tagger_ignores_geometry(base):
    lines = ["Ana Ruiz", "ana@x.com", "EDUCATION", "B.S. in Biology"]
    text_only = LineTagger(use_geometry=False)
    text_only.fit([(lines, ["name", "contact", "heading", "education"], [[1.0] * 22] * 4)], epochs=2)
    a = text_only.predict_proba(lines, [[1.0] * 22] * 4)
    b = text_only.predict_proba(lines, None)
    assert np.allclose(a, b)
