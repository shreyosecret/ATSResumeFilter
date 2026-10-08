import pytest

from ats_sim.data import load_personas
from ats_sim.formats import (
    DESIGNER_FORMATS, GENERATED_FORMATS, HELD_OUT_FORMATS, REFERENCE_FORMATS, SPECS, TRAIN_FORMATS, describe,
)
from ats_sim.learn.corpus import document, format_combos
from ats_sim.learn.labels import tokens
from ats_sim.render import heading_for


def test_fifty_distinct_formats_with_a_held_out_split():
    assert len(GENERATED_FORMATS) == 50 and len(TRAIN_FORMATS) == 40 and len(HELD_OUT_FORMATS) == 10
    assert not set(TRAIN_FORMATS) & set(HELD_OUT_FORMATS)
    assert len({r["headings"] for r in describe() if r["format"] in GENERATED_FORMATS}) == 50
    assert heading_for("education", "f07") == SPECS["f07"].headings["education"]


@pytest.mark.parametrize("name", GENERATED_FORMATS + DESIGNER_FORMATS + REFERENCE_FORMATS)
def test_every_format_renders_and_labels(name, tmp_path):
    p = load_personas()[5]
    fmt = "pdf" if int(name[1:]) % 2 else "docx"
    lines, labels, geo = document(p, name, "single", fmt, root=tmp_path, cache=tmp_path)
    assert labels[0] == "name" and len(geo) == len(lines) and all(g[0] == 1.0 for g in geo)
    spec = SPECS[name]
    found = {"".join(tokens(l)) for l, y in zip(lines, labels) if y == "heading"}
    assert {"".join(tokens(spec.headings[k])) for k in spec.order} <= found
    for key in ("education", "experience", "skills"):
        assert key in labels
    if spec.extras:
        assert "other" in labels


def test_combos_are_seeded():
    ps = load_personas()[:3]
    a = format_combos(("f01", "f02"), ps, per_persona=2, seed=1)
    assert a == format_combos(("f01", "f02"), ps, per_persona=2, seed=1) and len(a) == 12


def test_designer_features_show_up_in_geometry(tmp_path):
    p = load_personas()[4]
    spec = SPECS["d02"]  # tracked, colored, ruled headings
    assert spec.design["tracked"] and spec.design["rule"]
    lines, labels, geo = document(p, "d02", "single", "docx", root=tmp_path, cache=tmp_path)
    heads = [g for g, y in zip(geo, labels) if y == "heading"]
    body = [g for g, y in zip(geo, labels) if y in ("experience", "skills")]
    i = {n: k for k, n in enumerate(__import__("ats_sim.learn.geometry", fromlist=["x"]).GEO_FEATURES)}
    assert all(h[i["colored"]] == 1 and h[i["letter_spacing"]] > 0 and h[i["rule_below"]] == 1 for h in heads)
    assert not any(b[i["colored"]] for b in body)


def test_reference_formats_keep_their_published_headings():
    import json
    from pathlib import Path

    records = json.loads((Path(__file__).resolve().parent.parent / "data" / "format_sources.json").read_text(encoding="utf-8"))
    assert len(REFERENCE_FORMATS) == len(records) >= 15
    for name, r in zip(REFERENCE_FORMATS, records):
        spec = SPECS[name]
        assert spec.notes["source"] == r["id"] and r["license"] and r["source_url"].startswith("http")
        for key in ("education", "experience"):
            if key in (r.get("headings") or {}):
                assert spec.headings[key] == r["headings"][key]
