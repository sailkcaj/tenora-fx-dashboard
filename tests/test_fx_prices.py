import sys
import types
from datetime import date

import pandas as pd
import pytest

from tenora_fx.fx_prices import FxDataError, fetch_pair, normalize_history


def yahoo_frame(n=3, tz="Europe/London"):
    """Shape of what yfinance.Ticker.history() returns for an FX ticker."""
    idx = pd.date_range("2026-09-01", periods=n, freq="D", tz=tz, name="Date")
    return pd.DataFrame(
        {"Open": 1.0, "High": 1.1, "Low": 0.9, "Close": 1.05, "Adj Close": 1.05, "Volume": 0},
        index=idx,
    )


def test_normalize_columns_and_naive_date_index():
    df = normalize_history(yahoo_frame(), "EURUSD=X")
    assert list(df.columns) == ["open", "high", "low", "close"]
    assert df.index.name == "date"
    assert df.index.tz is None
    assert df.index[0] == pd.Timestamp("2026-09-01")  # wall-clock date kept, not shifted via UTC
    assert (df.dtypes == "float64").all()


def test_normalize_drops_empty_and_duplicate_rows():
    raw = yahoo_frame(3)
    raw.loc[raw.index[1], "Close"] = float("nan")
    raw = pd.concat([raw, raw.iloc[[2]]])  # duplicated last bar
    df = normalize_history(raw, "EURUSD=X")
    assert len(df) == 2
    assert df.index.is_monotonic_increasing


def test_normalize_rejects_empty_input():
    with pytest.raises(FxDataError, match="no price data"):
        normalize_history(pd.DataFrame(), "EURUSD=X")
    with pytest.raises(FxDataError, match="no price data"):
        normalize_history(None, "EURUSD=X")


def test_normalize_rejects_missing_columns():
    with pytest.raises(FxDataError, match="missing columns"):
        normalize_history(yahoo_frame().drop(columns=["Close"]), "EURUSD=X")


class FakeTicker:
    frame = None
    error = None
    calls = []

    def __init__(self, symbol):
        self.symbol = symbol

    def history(self, **kwargs):
        FakeTicker.calls.append((self.symbol, kwargs))
        if FakeTicker.error is not None:
            raise FakeTicker.error
        return FakeTicker.frame


@pytest.fixture
def fake_yfinance(monkeypatch):
    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=FakeTicker))
    FakeTicker.frame, FakeTicker.error, FakeTicker.calls = None, None, []
    return FakeTicker


def test_fetch_pair_requests_daily_bars_with_exclusive_end(fake_yfinance):
    fake_yfinance.frame = yahoo_frame()
    df = fetch_pair("EURUSD=X", date(2024, 9, 5), date(2026, 9, 5))
    symbol, kwargs = fake_yfinance.calls[0]
    assert symbol == "EURUSD=X"
    assert kwargs["start"] == "2024-09-05"
    assert kwargs["end"] == "2026-09-06"
    assert kwargs["interval"] == "1d"
    assert len(df) == 3


def test_fetch_pair_wraps_library_errors(fake_yfinance):
    fake_yfinance.error = RuntimeError("rate limited")
    with pytest.raises(FxDataError, match="rate limited"):
        fetch_pair("EURUSD=X", date(2024, 9, 5), date(2026, 9, 5))


def test_fetch_pair_treats_empty_frame_as_error(fake_yfinance):
    fake_yfinance.frame = pd.DataFrame()
    with pytest.raises(FxDataError, match="no price data"):
        fetch_pair("NOPE=X", date(2024, 9, 5), date(2026, 9, 5))
