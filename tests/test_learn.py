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
    lines, labels = document(p, "hybrid", "table", "pdf", root=tmp_path, cache=tmp_path)
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
    lines, labels = document(p, "classic", "single", "pdf", root=tmp_path, cache=tmp_path)
    pred = base.predict(lines)
    assert np.mean([a == b for a, b in zip(pred, labels)]) > 0.9
    parsed, _, _ = parse_with_tagger("\n".join(lines), base)
    assert parsed.name == p["name"] and parsed.school == p["education"]["school"]


def test_learning_one_resume_fixes_a_new_template(base, personas, tmp_path):
    teach = document(personas[11], "hybrid", "single", "pdf", root=tmp_path, cache=tmp_path)
    test = document(personas[13], "hybrid", "single", "pdf", root=tmp_path, cache=tmp_path)
    acc = lambda tg: np.mean([a == b for a, b in zip(tg.predict(test[0]), test[1])])  # noqa: E731
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
