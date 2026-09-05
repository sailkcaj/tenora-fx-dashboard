from datetime import date

import pandas as pd
import pytest

from tenora_fx import httpclient
from tenora_fx.mof import CURRENT_URL, HISTORY_URL, MofError, fetch_series, parse_jgb_csv
from tests.fakes import FakeResponse, FakeSession

COLUMNS = "Date,1Y,2Y,3Y,4Y,5Y,6Y,7Y,8Y,9Y,10Y,15Y,20Y,25Y,30Y,40Y"
NOTE = '"  ※If you cannot download the latest csv data, please clear the browser\'s cache and download again.",,,,,,,,,,,,,,,'


def jgb_bytes(rows, title="Interest Rate,,,,,,,,,,,,,,,(Unit : %)"):
    lines = [title, COLUMNS]
    for day, one_year, two_year in rows:
        lines.append(",".join([day, one_year, two_year] + ["1.0"] * 13))
    lines.append(NOTE)
    return ("\r\n".join(lines) + "\r\n").encode("cp932")


HISTORY = jgb_bytes([("2024/9/4", "0.2", "0.36"), ("2024/9/5", "0.25", "0.37"), ("2026/8/31", "1.50", "1.740")])
CURRENT = jgb_bytes(
    [("2026/8/31", "1.502", "1.743"), ("2026/9/1", "1.527", "1.802")],
    title="Interest Rate (September 2026),,,,,,,,,,,,,,,(Unit : %)",
)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(httpclient.time, "sleep", lambda seconds: None)


def test_parse_skips_title_note_and_missing_values():
    raw = jgb_bytes([("2026/8/28", "1.483", "1.719"), ("2026/8/29", "-", "-"), ("2026/8/31", "1.502", "1.743")])
    df = parse_jgb_csv(raw, "2Y")
    assert list(df.columns) == ["value"]
    assert df.index.name == "date"
    assert len(df) == 2  # the "-" row is dropped, the note row is not a date
    assert df.index[0] == pd.Timestamp("2026-08-28")
    assert df.loc[pd.Timestamp("2026-08-31"), "value"] == pytest.approx(1.743)


def test_parse_rejects_unknown_column_and_missing_header():
    with pytest.raises(MofError, match="column"):
        parse_jgb_csv(HISTORY, "2YR")
    with pytest.raises(MofError, match="header"):
        parse_jgb_csv(b"nothing here\n", "2Y")


def test_fetch_combines_history_and_current_month_within_window():
    session = FakeSession({HISTORY_URL: FakeResponse(200, content=HISTORY), CURRENT_URL: FakeResponse(200, content=CURRENT)})
    df = fetch_series("2Y", date(2024, 9, 5), date(2026, 9, 5), session=session)
    assert df.index[0] == pd.Timestamp("2024-09-05")  # 2024-09-04 falls outside the window
    assert df.index[-1] == pd.Timestamp("2026-09-01")
    assert len(df) == 3
    assert df.loc[pd.Timestamp("2026-08-31"), "value"] == pytest.approx(1.743)  # current month wins on overlap
    assert [c["url"] for c in session.calls] == [HISTORY_URL, CURRENT_URL]


def test_fetch_tolerates_missing_current_month_file():
    session = FakeSession({HISTORY_URL: FakeResponse(200, content=HISTORY), CURRENT_URL: FakeResponse(404, "nope")})
    df = fetch_series("2Y", session=session)
    assert len(df) == 3


def test_fetch_requires_history_file():
    session = FakeSession({HISTORY_URL: FakeResponse(404, "nope"), CURRENT_URL: FakeResponse(200, content=CURRENT)})
    with pytest.raises(MofError, match="404"):
        fetch_series("2Y", session=session)
