from streamlit.testing.v1 import AppTest

from tenora_fx import storage
from tenora_fx.config import PROJECT_ROOT


def test_dashboard_script_runs_without_exceptions():
    at = AppTest.from_file(str(PROJECT_ROOT / "dashboard" / "app.py"), default_timeout=90)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    if storage.read_manifest() is None:
        assert len(at.warning) == 1  # fresh checkout: the page explains how to load data
    else:
        assert len(at.metric) == 10  # one stat tile per pair
        assert any("2-year yields are not one methodology" in c.value for c in at.caption)
