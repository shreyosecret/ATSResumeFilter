import pytest

from ats_sim.visual import compare, risks


def test_matching_readings_raise_nothing():
    text = "Ana Ruiz\nEDUCATION\nB.S. in Biology, Example University, 2026"
    seen = ["Ana Ruiz", "EDUCATION", "B.S. in Biology, Example University, 2026"]
    r = compare(text, seen)
    assert r["coverage"] == 1.0 and r["missing"] == [] and r["glued"] == []
    assert [x["level"] for x in risks(r)] == ["ok"]


def test_run_together_words_are_found():
    text = "Builtasurvivalmodelofpatentabandonment on 27 million records\nContact: ana@example.com"
    seen = ["Built a survival model of patent abandonment on 27 million records", "Contact: ana@example.com"]
    r = compare(text, seen)
    assert [g["read"] for g in r["glued"]] == ["Builtasurvivalmodelofpatentabandonment"]
    assert r["glued"][0]["seen"] == "Built a survival model of patent abandonment"
    assert "run-together" in risks(r)[0]["title"]


def test_ocr_noise_is_not_missing_text():
    # OCR reads "|" as "I" and drops a letter; neither is a dozen letters
    r = compare("Lakeshore State University | Chicago, IL", ["Lakeshore State Universty I Chicago, IL"])
    assert r["missing"] == []


def test_text_only_on_the_page_is_missing():
    text = "Ana Ruiz\nEXPERIENCE\nLab assistant"
    seen = ["Ana Ruiz", "SKILLS", "Python, MATLAB, SolidWorks, LabVIEW", "EXPERIENCE", "Lab assistant"]
    r = compare(text, seen)
    assert len(r["missing"]) == 1 and "SolidWorks" in r["missing"][0]
    assert risks(r)[0]["title"] == "Text on the page that an ATS cannot read"


def test_a_scanned_page_is_reported():
    r = compare("", ["Ana Ruiz", "Biology student at Example University with three years of lab work"] * 4)
    assert r["image_only"] and risks(r)[0]["title"] == "The page is an image"


def test_text_drawn_as_an_image_is_seen(tmp_path):
    pytest.importorskip("rapidocr_onnxruntime")
    from PIL import Image, ImageDraw, ImageFont
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    from ats_sim.parser import extract_text
    from ats_sim.visual import check

    img = Image.new("RGB", (1400, 60), "white")
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 36)
    except OSError:
        font = ImageFont.load_default(size=36)
    ImageDraw.Draw(img).text((4, 8), "Skills: Python, MATLAB, SolidWorks, LabVIEW", fill="black", font=font)
    img.save(tmp_path / "skills.png")
    path = tmp_path / "r.pdf"
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setFont("Helvetica", 11)
    c.drawString(72, 720, "Ana Ruiz")
    c.drawString(72, 700, "EDUCATION")
    c.drawString(72, 684, "B.S. in Biology, Example University, 2026")
    c.drawImage(str(tmp_path / "skills.png"), 72, 640, width=420, height=18)
    c.save()
    r = check(path, extract_text(path))
    assert any("SolidWorks" in m for m in r["missing"])
    assert r["glued"] == [] and not r["image_only"]
