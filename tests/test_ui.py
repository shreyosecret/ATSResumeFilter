"""Click through the real app in a browser: upload, analyze, tabs, About, Research.

Runs when Playwright and a Chromium build are installed (the "ui" job in
.github/workflows/tests.yml); skipped otherwise.
"""
import socket
import threading
import time

import pytest

playwright = pytest.importorskip("playwright.sync_api")
uvicorn = pytest.importorskip("uvicorn")

from ats_sim.webapp.server import create_app  # noqa: E402

JOB = ("Data Analyst Intern\nRequirements\n- Pursuing a Bachelor's degree in Statistics or a related field\n"
       "- Minimum GPA of 3.0\n- Experience with Python and SQL\n- Must be authorized to work in the United States")


@pytest.fixture(scope="module")
def base_url():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app({"public_pool": False}, model_store=False),
                                           host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    url = f"http://127.0.0.1:{port}"
    import urllib.request

    for _ in range(240):
        try:
            if b'"ready":true' in urllib.request.urlopen(url + "/api/status", timeout=2).read():
                break
        except OSError:
            pass
        time.sleep(0.5)
    yield url
    server.should_exit = True
    t.join(timeout=10)


@pytest.fixture(scope="module")
def page(base_url):
    with playwright.sync_playwright() as p:
        import os

        exe = os.environ.get("ATS_SIM_CHROMIUM")  # a Chromium that is not Playwright's own build
        try:
            browser = p.chromium.launch(**({"executable_path": exe} if exe else {}))
        except Exception as e:  # no browser installed
            pytest.skip(f"no Chromium for Playwright: {e}")
        pg = browser.new_page(viewport={"width": 1300, "height": 900})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.errors = errors
        yield pg
        browser.close()


@pytest.fixture(scope="module")
def resume(tmp_path_factory):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    path = tmp_path_factory.mktemp("ui") / "ana.pdf"
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setFont("Helvetica", 11)
    lines = ["Ana Ruiz", "ana.ruiz@example.com | (555) 201-4432", "EDUCATION",
             "B.S. in Statistics, Example University, May 2027, GPA 3.6", "EXPERIENCE",
             "Data Intern, Example Labs, Jun 2026 - Aug 2026", "- Built SQL dashboards and Python reports",
             "SKILLS", "Python, SQL, R, Excel"]
    for k, line in enumerate(lines):
        c.drawString(72, 720 - 16 * k, line)
    c.save()
    return path


def test_analyze_a_resume_against_a_pasted_job(page, base_url, resume):
    page.goto(base_url + "/#/check")
    page.wait_for_selector("#go")
    page.set_input_files("#file", str(resume))
    page.fill("#paste", JOB)
    page.click("#go")
    page.wait_for_selector(".tabs", timeout=180_000)
    body = page.inner_text("main")
    assert "Ana Ruiz" in body
    assert "Match for this job" in body
    for tab in page.query_selector_all(".tab"):  # every tab opens without a script error
        tab.click()
        page.wait_for_timeout(150)
    assert page.errors == []


def test_about_and_research_render(page, base_url):
    page.goto(base_url + "/#/about")
    page.wait_for_selector(".about-hero img")
    assert page.is_visible("#check-updates") and not page.is_checked("#check-updates")
    page.goto(base_url + "/#/research")
    page.wait_for_selector("text=Reading the page as an image", timeout=60_000)
    assert len(page.query_selector_all(".card")) >= 5
    assert page.errors == []
