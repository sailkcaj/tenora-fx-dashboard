from streamlit.testing.v1 import AppTest

from tenora_fx.config import PROJECT_ROOT


def test_dashboard_script_runs_without_exceptions():
    at = AppTest.from_file(str(PROJECT_ROOT / "dashboard" / "app.py"), default_timeout=60)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
