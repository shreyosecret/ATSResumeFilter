import time

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from ats_sim.data import load_personas  # noqa: E402
from ats_sim.learn.store import ModelStore  # noqa: E402
from ats_sim.render import RenderOptions, render  # noqa: E402
from ats_sim.webapp.server import create_app  # noqa: E402


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    store = ModelStore(tmp_path_factory.mktemp("model"),
                       corpus={"templates": ("classic",), "layouts": ("single",), "fmts": ("pdf",),
                               "formats": ()})
    c = TestClient(create_app({"public_pool": False}, model_store=store))
    for _ in range(240):
        s = c.get("/api/status").json()
        if (s["ready"] and s["model"]["ready"]) or s["status"] == "error" or "error" in s["model"]["status"]:
            break
        time.sleep(0.5)
    assert s["ready"] and s["model"]["ready"], s
    return c


def test_front_end_is_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "ATS Simulator" in r.text
    assert client.get("/app.js").status_code == 200


def test_meta(client):
    m = client.get("/api/meta").json()
    assert {"mechanical_design", "process_engineer"} <= {p["id"] for p in m["postings"]}
    assert m["pool"]["synthetic"] == 16


def test_screen_and_candidate(client):
    data = client.get("/api/screen", params={"posting": "process_engineer"}).json()
    assert len(data["rows"]) == 16 and data["rows"][0]["id"] == "p07"
    table = client.get("/api/screen", params={"posting": "process_engineer", "layout": "table"}).json()
    assert {r["knockout"] for r in table["rows"]} <= {"PASS", "REVIEW", "REJECT"}
    c = client.get("/api/candidate/p07").json()
    assert c["parsed"]["school"] == c["truth"]["school"]
    assert client.get("/api/candidate/nope").status_code == 404
    assert client.get("/api/screen", params={"posting": "process_engineer", "layout": "bogus"}).status_code == 400


def test_search(client):
    hits = client.get("/api/search", params={"q": '(Python OR MATLAB) AND "GMP"'}).json()["hits"]
    assert {"p07", "p09"} <= {h["id"] for h in hits}
    assert client.get("/api/search", params={"q": "(Python"}).status_code == 400


@pytest.mark.parametrize("fmt", ["pdf", "docx"])
def test_analyze_upload(client, tmp_path, fmt):
    p = next(x for x in load_personas() if x["id"] == "p12")
    path = render(p, "single", fmt, tmp_path / f"r.{fmt}", RenderOptions())
    with open(path, "rb") as fh:
        r = client.post("/api/analyze", files={"file": (f"r.{fmt}", fh)},
                        data={"posting_id": "mechanical_design", "engines": "false"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["parsers"][j["best"]]["name"] == "Tomas Lindqvist"
    assert j["parsers"]["learned"]["name"] == "Tomas Lindqvist"
    assert j["lines"][0] == {**j["lines"][0], "text": "Tomas Lindqvist", "label": "name"}
    assert all(len(x["geo"]) == 20 for x in j["lines"])
    m = j["matches"][0]
    assert m["posting"]["id"] == "mechanical_design" and m["scores"][0]["rank"] <= 2
    assert any(x["level"] == "ok" for x in j["risks"])


def test_analyze_pasted_posting_and_bad_files(client, tmp_path):
    p = next(x for x in load_personas() if x["id"] == "p01")
    path = render(p, "single", "pdf", tmp_path / "r.pdf", RenderOptions())
    with open(path, "rb") as fh:
        j = client.post("/api/analyze", files={"file": ("r.pdf", fh)},
                        data={"posting_text": "Data Scientist\n\nRequirements\n- Python and SQL", "engines": "false"}).json()
    assert len(j["matches"]) == 1 and not j["matches"][0]["posting"]["has_knockouts"]
    assert client.post("/api/analyze", files={"file": ("x.txt", b"hello")}).status_code == 400
    assert client.post("/api/analyze", files={"file": ("x.pdf", b"not a pdf")}).status_code == 422


def test_research_and_image_guard(client):
    d = client.get("/api/research").json()
    assert d["available"] and d["charts"]
    assert {"layout", "synonyms", "stuffing"} <= set(d["series"])
    assert all("f1" in r and "f1_lo" in r for r in d["series"]["layout"])
    assert client.get(d["charts"][0]["src"]).status_code == 200
    assert client.get("/results/../README.md").status_code == 404
    assert client.get("/results/summary.json").status_code == 404


def test_teach_and_reset(client):
    lines = ["Ana Ruiz", "ana@x.com", "Academic Background", "B.S. in Biology, State University", "Toolbox", "Python, R"]
    labels = ["name", "contact", "heading", "education", "heading", "skills"]
    r = client.post("/api/learn", json={"lines": lines, "labels": labels})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["model"]["taught"] == 1 and len(j["lines"]) == len(lines)
    assert client.get("/api/model").json()["taught"] == 1
    assert client.post("/api/learn", json={"lines": lines, "labels": labels[:2]}).status_code == 400
    assert client.post("/api/learn", json={"lines": ["x"], "labels": ["salary"]}).status_code == 400
    assert client.post("/api/learn", json={"lines": lines, "labels": labels, "geo": [[0.0] * 3] * 6}).status_code == 400
    geo = [[1.0] + [0.0] * 19 for _ in lines]
    r = client.post("/api/learn", json={"lines": lines, "labels": labels, "geo": geo})
    assert r.status_code == 200 and r.json()["lines"][0]["geo"] == geo[0]
    assert client.post("/api/model/reset").json()["model"]["taught"] == 0
    assert True


def test_learning_can_be_turned_off():
    c = TestClient(create_app(start=False, model_store=False))
    assert c.get("/api/model").json() == {"enabled": False}
    assert c.post("/api/learn", json={"lines": ["a"], "labels": ["name"]}).status_code == 404
