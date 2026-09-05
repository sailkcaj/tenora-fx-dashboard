from datetime import date

import pandas as pd
import pytest
import requests

from tenora_fx import fred
from tenora_fx.fred import FredError, fetch_series, parse_fred_csv

CSV_NEW = "observation_date,DGS2\n2026-08-31,3.60\n2026-09-01,.\n2026-09-02,3.58\n2026-09-03,3.55\n"
CSV_OLD = "DATE,DGS2\n2026-09-02,3.58\n2026-09-03,3.55\n"
HTML = "<!DOCTYPE html>\n<html><body>Not found</body></html>"


def test_parse_drops_missing_values_and_uses_new_header():
    df = parse_fred_csv(CSV_NEW, "DGS2")
    assert list(df.columns) == ["value"]
    assert df.index.name == "date"
    assert df.index.tz is None
    assert len(df) == 3  # the "." row is dropped
    assert df.loc[pd.Timestamp("2026-09-03"), "value"] == pytest.approx(3.55)
    assert df["value"].dtype == "float64"


def test_parse_accepts_legacy_date_header():
    df = parse_fred_csv(CSV_OLD, "DGS2")
    assert len(df) == 2
    assert df.index[0] == pd.Timestamp("2026-09-02")


def test_parse_rejects_html():
    with pytest.raises(FredError, match="not CSV"):
        parse_fred_csv(HTML, "DGS2")


def test_parse_rejects_wrong_series():
    with pytest.raises(FredError, match="value column"):
        parse_fred_csv(CSV_NEW, "DFF")


def test_parse_rejects_empty_window():
    with pytest.raises(FredError, match="no observations"):
        parse_fred_csv("observation_date,DGS2\n", "DGS2")


class FakeResponse:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


class FakeSession:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None, headers=None):
        self.calls.append(params)
        return self.responses.pop(0)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(fred.time, "sleep", lambda seconds: None)


def test_fetch_passes_window_and_parses():
    session = FakeSession(FakeResponse(200, CSV_NEW))
    df = fetch_series("DGS2", date(2024, 9, 5), date(2026, 9, 5), session=session)
    assert len(df) == 3
    assert session.calls == [{"id": "DGS2", "cosd": "2024-09-05", "coed": "2026-09-05"}]


def test_fetch_404_raises_without_retry():
    session = FakeSession(FakeResponse(404, HTML))
    with pytest.raises(FredError, match="404"):
        fetch_series("NOPE", session=session)
    assert len(session.calls) == 1


def test_fetch_retries_server_errors():
    session = FakeSession(FakeResponse(503), FakeResponse(200, CSV_NEW))
    df = fetch_series("DGS2", session=session, retries=3)
    assert len(df) == 3
    assert len(session.calls) == 2


def test_fetch_gives_up_after_retries():
    session = FakeSession(FakeResponse(503), FakeResponse(503), FakeResponse(503))
    with pytest.raises(FredError, match="503"):
        fetch_series("DGS2", session=session, retries=3)
    assert len(session.calls) == 3


def test_fetch_wraps_network_errors():
    class BrokenSession:
        def get(self, *args, **kwargs):
            raise requests.ConnectionError("boom")

    with pytest.raises(FredError, match="request failed"):
        fetch_series("DGS2", session=BrokenSession(), retries=2)
