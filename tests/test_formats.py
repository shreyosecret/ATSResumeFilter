import pytest

from ats_sim.data import load_personas
from ats_sim.formats import GENERATED_FORMATS, HELD_OUT_FORMATS, SPECS, TRAIN_FORMATS, describe
from ats_sim.learn.corpus import document, format_combos
from ats_sim.learn.labels import tokens
from ats_sim.render import heading_for


def test_fifty_distinct_formats_with_a_held_out_split():
    assert len(GENERATED_FORMATS) == 50 and len(TRAIN_FORMATS) == 40 and len(HELD_OUT_FORMATS) == 10
    assert not set(TRAIN_FORMATS) & set(HELD_OUT_FORMATS)
    assert len({r["headings"] for r in describe()}) == 50
    assert heading_for("education", "f07") == SPECS["f07"].headings["education"]


@pytest.mark.parametrize("name", GENERATED_FORMATS)
def test_every_format_renders_and_labels(name, tmp_path):
    p = load_personas()[5]
    fmt = "pdf" if int(name[1:]) % 2 else "docx"
    lines, labels = document(p, name, "single", fmt, root=tmp_path, cache=tmp_path)
    assert labels[0] == "name"
    spec = SPECS[name]
    found = {" ".join(tokens(l)) for l, y in zip(lines, labels) if y == "heading"}
    assert {" ".join(tokens(spec.headings[k])) for k in spec.order} <= found
    for key in ("education", "experience", "skills"):
        assert key in labels
    if spec.extras:
        assert "other" in labels


def test_combos_are_seeded():
    ps = load_personas()[:3]
    a = format_combos(("f01", "f02"), ps, per_persona=2, seed=1)
    assert a == format_combos(("f01", "f02"), ps, per_persona=2, seed=1) and len(a) == 12
