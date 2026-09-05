import io
import json
import zipfile
from datetime import date, datetime

import pandas as pd
import pytest
from openpyxl import Workbook

from tenora_fx import httpclient, storage
from tenora_fx.boe import (
    ARCHIVE_ZIP_URL, LATEST_ZIP_URL, SPOT_SHEET, BoeError, fetch_series, parse_spot_curve, workbook_years,
)
from tests.fakes import FakeResponse, FakeSession

MATURITIES = (0.5, 1, 1.5, 2, 2.5)
LAST_MODIFIED = "Thu, 03 Sep 2026 14:52:10 GMT"


def workbook(rows, maturities=MATURITIES) -> bytes:
    """A GLC Nominal workbook with the real sheet layout: title rows, a 'years:' header, a junk row."""
    wb = Workbook()
    info = wb.active
    info.title = "info"
    info["A1"] = "Bank of England UK yield curve data"
    ws = wb.create_sheet(SPOT_SHEET)
    ws.append([None, "UK nominal spot curve"])
    ws.append([])
    ws.append(["Maturity"])
    ws.append(["years:", *maturities])
    ws.append(["Refresh"] * (len(maturities) + 1))
    for day, values in rows:
        ws.append([datetime.combine(day, datetime.min.time()), *values])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def curve(day, two_year):
    return (day, [two_year - 0.3, two_year - 0.2, two_year - 0.1, two_year, two_year + 0.1])


def zipped(members: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buf.getvalue()


def bdays(start, end):
    return [ts.date() for ts in pd.bdate_range(start, end)]


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(httpclient.time, "sleep", lambda seconds: None)


def test_parse_spot_curve_picks_maturity_and_skips_junk_and_holidays():
    rows = [curve(date(2026, 9, 1), 4.38), (date(2026, 9, 2), [None] * 5), curve(date(2026, 9, 3), 4.42)]
    df = parse_spot_curve(workbook(rows), 2.0)
    assert list(df.columns) == ["value"]
    assert df.index.name == "date"
    assert len(df) == 2
    assert df.loc[pd.Timestamp("2026-09-03"), "value"] == pytest.approx(4.42)


def test_parse_spot_curve_unknown_maturity_raises():
    with pytest.raises(BoeError, match="7-year"):
        parse_spot_curve(workbook([curve(date(2026, 9, 1), 4.0)]), 7.0)


def test_parse_spot_curve_without_rows_is_empty():
    df = parse_spot_curve(workbook([]), 2.0)
    assert df.empty
    assert list(df.columns) == ["value"]


def test_workbook_years():
    assert workbook_years("GLC Nominal daily data_2016 to 2024.xlsx") == (2016, 2024)
    assert workbook_years("GLC Nominal daily data_2025 to present.xlsx") == (2025, 9999)
    assert workbook_years("GLC Nominal daily data current month.xlsx") is None


def make_session(latest_rows, archive_members, archive_status=200):
    latest_zip = zipped({"GLC Nominal daily data current month.xlsx": workbook(latest_rows)})
    archive_zip = zipped(archive_members)

    def archive_response():
        content = archive_zip if archive_status == 200 else b""
        return FakeResponse(archive_status, content=content, headers={"Last-Modified": LAST_MODIFIED, "ETag": '"abc"'})

    return FakeSession({LATEST_ZIP_URL: FakeResponse(200, content=latest_zip), ARCHIVE_ZIP_URL: archive_response})


def archive_calls(session):
    return [c for c in session.calls if c["url"] == ARCHIVE_ZIP_URL]


def test_fetch_downloads_archive_once_then_serves_from_cache(tmp_path):
    latest_rows = [curve(d, 4.4) for d in bdays("2026-09-01", "2026-09-02")]
    old_rows = [curve(d, 3.5) for d in bdays("2024-12-02", "2024-12-31")]
    recent_rows = [curve(d, 4.3) for d in bdays("2025-01-02", "2026-08-31")]
    members = {
        # outside the window: must be skipped (it has no 2-year column, so parsing it would raise)
        "GLC Nominal daily data_1979 to 1984.xlsx": workbook([(date(1980, 1, 2), [12.0, 11.0])], maturities=(5, 10)),
        "GLC Nominal daily data_2016 to 2024.xlsx": workbook(old_rows),
        "GLC Nominal daily data_2025 to present.xlsx": workbook(recent_rows),
    }
    session = make_session(latest_rows, members)

    df = fetch_series("2.0", date(2024, 9, 5), date(2026, 9, 5), session=session, cache_dir=tmp_path)
    assert df.index[0] == pd.Timestamp("2024-12-02")
    assert df.index[-1] == pd.Timestamp("2026-09-02")
    assert len(df) == len(old_rows) + len(recent_rows) + len(latest_rows)
    assert df.loc[pd.Timestamp("2026-09-02"), "value"] == pytest.approx(4.4)
    assert len(archive_calls(session)) == 1
    assert (tmp_path / "glcnominalddata.zip").exists()
    assert (tmp_path / "glc_nominal_spot_2y.parquet").exists()
    meta = json.loads((tmp_path / "glcnominalddata.zip.meta.json").read_text())
    assert meta["last_modified"] == LAST_MODIFIED

    again = fetch_series("2.0", date(2024, 9, 5), date(2026, 9, 5), session=session, cache_dir=tmp_path)
    assert len(archive_calls(session)) == 1  # cache covered the window: archive not requested again
    pd.testing.assert_frame_equal(again, df)


def seed_cache(tmp_path, through="2026-08-20"):
    cached = pd.DataFrame({"value": 4.0}, index=pd.DatetimeIndex(pd.bdate_range("2024-09-05", through), name="date"))
    storage.save_parquet(cached, tmp_path / "glc_nominal_spot_2y.parquet")
    (tmp_path / "glcnominalddata.zip").write_bytes(b"stale")
    (tmp_path / "glcnominalddata.zip.meta.json").write_text(
        json.dumps({"last_modified": "Mon, 03 Aug 2026 10:00:00 GMT", "etag": '"old"'})
    )
    return cached


def test_fetch_refreshes_archive_when_cache_leaves_a_gap(tmp_path):
    cached = seed_cache(tmp_path)  # stops 20 Aug; current month starts 1 Sep -> business days missing
    latest_rows = [curve(d, 4.4) for d in bdays("2026-09-01", "2026-09-02")]
    fill_rows = [curve(d, 4.3) for d in bdays("2026-08-21", "2026-08-31")]
    session = make_session(latest_rows, {"GLC Nominal daily data_2025 to present.xlsx": workbook(fill_rows)})

    df = fetch_series("2.0", date(2024, 9, 5), date(2026, 9, 5), session=session, cache_dir=tmp_path)
    (call,) = archive_calls(session)
    assert call["headers"]["If-Modified-Since"] == "Mon, 03 Aug 2026 10:00:00 GMT"
    assert call["headers"]["If-None-Match"] == '"old"'
    assert call["stream"] is True
    assert len(df) == len(cached) + len(fill_rows) + len(latest_rows)
    assert df.loc[pd.Timestamp("2026-08-20"), "value"] == pytest.approx(4.0)
    assert df.loc[pd.Timestamp("2026-08-21"), "value"] == pytest.approx(4.3)
    assert json.loads((tmp_path / "glcnominalddata.zip.meta.json").read_text())["last_modified"] == LAST_MODIFIED


def test_fetch_304_keeps_cached_history(tmp_path):
    cached = seed_cache(tmp_path)
    latest_rows = [curve(d, 4.4) for d in bdays("2026-09-01", "2026-09-02")]
    session = make_session(latest_rows, {}, archive_status=304)

    df = fetch_series("2.0", date(2024, 9, 5), date(2026, 9, 5), session=session, cache_dir=tmp_path)
    assert len(archive_calls(session)) == 1
    assert len(df) == len(cached) + len(latest_rows)
    assert (tmp_path / "glcnominalddata.zip").read_bytes() == b"stale"  # untouched


def test_fetch_rejects_non_numeric_maturity():
    with pytest.raises(BoeError, match="maturity"):
        fetch_series("two", session=FakeSession([]), cache_dir="/nonexistent")
