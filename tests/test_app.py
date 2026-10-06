import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402


def test_dashboard_runs_and_switches_settings():
    at = AppTest.from_file("../app.py", default_timeout=180).run()
    assert not at.exception
    assert len(at.dataframe[0].value) == 16

    boxes = {s.label: s for s in at.selectbox}
    boxes["Template"].set_value("modern").run()
    boxes = {s.label: s for s in at.selectbox}
    boxes["Resume layout (all candidates)"].set_value("table").run()
    assert not at.exception

    at.text_input[0].set_value("(Python OR MATLAB) AND (").run()
    assert any("Query error" in e.value for e in at.error)
