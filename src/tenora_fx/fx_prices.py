"""Fetch daily FX spot bars from Yahoo Finance via yfinance."""

from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd

log = logging.getLogger(__name__)

PRICE_COLUMNS = ("open", "high", "low", "close")


class FxDataError(RuntimeError):
    """Yahoo returned no usable data for a ticker."""


def normalize_history(hist: pd.DataFrame | None, ticker: str) -> pd.DataFrame:
    """Tidy a yfinance ``history()`` frame.

    Keeps open/high/low/close as float64, drops rows without a close, and turns the
    tz-aware exchange-local index into a tz-naive calendar-date index named ``date``.
    """
    if hist is None or hist.empty:
        raise FxDataError(f"{ticker}: no price data returned")
    df = hist.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    missing = [c for c in PRICE_COLUMNS if c not in df.columns]
    if missing:
        raise FxDataError(f"{ticker}: missing columns {missing}")
    df = df[list(PRICE_COLUMNS)].astype("float64")

    idx = pd.DatetimeIndex(df.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)  # keep the wall-clock date Yahoo reports, drop the zone
    df.index = idx.normalize()
    df.index.name = "date"

    df = df.dropna(subset=["close"])
    df = df[~df.index.duplicated(keep="last")].sort_index()
    if df.empty:
        raise FxDataError(f"{ticker}: every row was empty after cleaning")
    return df


def fetch_pair(ticker: str, start: date, end: date) -> pd.DataFrame:
    """Download daily bars for one Yahoo symbol. Raises ``FxDataError`` if nothing usable comes back."""
    import yfinance as yf  # lazy: slow import, and unit tests never touch the network

    try:
        hist = yf.Ticker(ticker).history(
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),  # yfinance's end is exclusive
            interval="1d",
            auto_adjust=False,
            actions=False,
        )
    except Exception as exc:  # yfinance raises many exception types; all mean "no data"
        raise FxDataError(f"{ticker}: {type(exc).__name__}: {exc}") from exc
    return normalize_history(hist, ticker)
