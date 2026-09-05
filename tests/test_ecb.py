from datetime import date

import pandas as pd
import pytest

from tenora_fx import httpclient
from tenora_fx.ecb import API_BASE, EcbError, fetch_series, parse_csvdata
from tests.fakes import FakeResponse, FakeSession

KEY = "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y"
HEADER = "KEY,FREQ,REF_AREA,CURRENCY,PROVIDER_FM,INSTRUMENT_FM,PROVIDER_FM_ID,DATA_TYPE_FM,TIME_PERIOD,OBS_VALUE,OBS_STATUS"


def row(day, value):
    return f"YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y,B,U2,EUR,4F,G_N_A,SV_C_YM,SR_2Y,{day},{value},A"


CSV = "\n".join([HEADER, row("2026-09-02", "2.85"), row("2026-09-03", "2.8856641467"), row("2026-09-03", "2.9")]) + "\n"


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(httpclient.time, "sleep", lambda seconds: None)


def test_parse_csvdata_keeps_last_value_per_date():
    df = parse_csvdata(CSV, KEY)
    assert list(df.columns) == ["value"]
    assert df.index.name == "date"
    assert len(df) == 2
    assert df.loc[pd.Timestamp("2026-09-03"), "value"] == pytest.approx(2.9)
    assert df["value"].dtype == "float64"


def test_parse_rejects_empty_and_malformed_payloads():
    with pytest.raises(EcbError, match="empty"):
        parse_csvdata("  \n", KEY)
    with pytest.raises(EcbError, match="TIME_PERIOD"):
        parse_csvdata("a,b\n1,2\n", KEY)
    with pytest.raises(EcbError, match="no observations"):
        parse_csvdata(HEADER + "\n" + row("not-a-date", "x") + "\n", KEY)


def test_fetch_builds_url_and_window():
    session = FakeSession([FakeResponse(200, CSV)])
    df = fetch_series(KEY, date(2024, 9, 5), date(2026, 9, 5), session=session)
    assert len(df) == 2
    call = session.calls[0]
    assert call["url"] == f"{API_BASE}/YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y"
    assert call["params"] == {"format": "csvdata", "startPeriod": "2024-09-05", "endPeriod": "2026-09-05"}


def test_fetch_404_is_a_clear_error():
    session = FakeSession([FakeResponse(404, '{"title":"Not Found"}')])
    with pytest.raises(EcbError, match="404"):
        fetch_series(KEY, session=session)
    assert len(session.calls) == 1


def test_fetch_rejects_key_without_dataflow():
    with pytest.raises(EcbError, match="dataflow"):
        fetch_series("B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y", session=FakeSession([]))
