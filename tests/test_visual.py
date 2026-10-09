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


def test_a_scanned_resume_is_read_with_ocr(tmp_path):
    pytest.importorskip("rapidocr_onnxruntime")
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    from ats_sim.report import Analyzer
    from ats_sim.visual import render

    text = tmp_path / "text.pdf"
    c = canvas.Canvas(str(text), pagesize=letter)
    c.setFont("Helvetica", 12)
    for k, line in enumerate(["Ana Ruiz", "ana.ruiz@example.com", "EDUCATION",
                              "B.S. in Biology, Example University, May 2026", "SKILLS", "Python, MATLAB, R"]):
        c.drawString(72, 720 - 20 * k, line)
    c.save()
    render(text, scale=2)[0].save(tmp_path / "page.png")
    scan = tmp_path / "scan.pdf"  # the same page as a picture, like a scanner makes
    c = canvas.Canvas(str(scan), pagesize=letter)
    c.drawImage(str(tmp_path / "page.png"), 0, 0, width=letter[0], height=letter[1])
    c.save()
    r = Analyzer(public_pool=False).analyze(scan, use_engines=False, with_skillner=False)
    assert r["visual"]["image_only"]
    assert r["parsers"]["naive"]["email"] is None
    # what OCR reads varies a little across platforms; the email and degree are the stable signals
    assert r["parsers"]["ocr"]["email"] == "ana.ruiz@example.com"
    assert "Biology" in r["visual"]["text"] and r["parser_labels"]["ocr"] == "With OCR (scanned)"


def test_doubled_letters_are_reported(tmp_path):
    from ats_sim.report import diagnose
    from ats_sim.parser import parse_text

    text = "PPrriiyyaa RRaammaann\nEEDDUUCCAATTIIOONN\nBBaacchheelloorr ooff SScciieennccee\nPPyytthhoonn SSQQLL"
    path = tmp_path / "x.txt"
    path.write_text(text, encoding="utf-8")
    parsed = {"naive": parse_text(text)}
    assert any(r["title"] == "Every letter is read twice" for r in diagnose(path, parsed))
