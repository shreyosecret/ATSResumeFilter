import json

from ats_sim.learn.export import FORMAT, export, load
from ats_sim.learn.geometry import N_GEO


def test_contact_details_are_masked(tmp_path):
    lines = ["Priya Raman", "priya.raman@school.edu | (312) 555-0142 | linkedin.com/in/priyaraman",
             "EXPERIENCE", "Raman, P. and Lee, J. (2025). A study of things. Built 2,000,000 widgets."]
    labels = ["name", "contact", "heading", "experience"]
    out = export(lines, labels, [[0.5] * N_GEO] * 4, "test")
    text = "\n".join(out["lines"])
    for secret in ("Priya", "Raman", "priya.raman@school.edu", "555-0142", "priyaraman"):
        assert secret not in text
    assert out["lines"][2] == "EXPERIENCE" and "2,000,000 widgets" in out["lines"][3]
    assert out["labels"] == labels and out["format"] == FORMAT and out["masked"] >= 5
    path = tmp_path / "x.json"
    path.write_text(json.dumps(out), encoding="utf-8")
    assert load(path) == (out["lines"], labels, out["geo"])

