"""Fetch FRED series via the public ``fredgraph.csv`` endpoint (no API key required)."""

from __future__ import annotations

import io
import logging
from datetime import date

import pandas as pd

from . import httpclient
from .config import FRED_CSV_URL
from .httpclient import HttpError

log = logging.getLogger(__name__)


class FredError(RuntimeError):
    """A FRED series could not be fetched or parsed."""


def parse_fred_csv(text: str, fred_id: str) -> pd.DataFrame:
    """Parse a fredgraph.csv payload into a frame with a ``date`` index and one ``value`` column.

    FRED marks missing observations with ``.`` (dropped here) and names the date column
    ``observation_date`` (older payloads used ``DATE``); both are handled.
    """
    stripped = text.lstrip()
    if not stripped or stripped[0] == "<":
        raise FredError(f"{fred_id}: response is not CSV (HTML page: series id probably does not exist)")
    try:
        raw = pd.read_csv(io.StringIO(text), na_values=["."])
    except Exception as exc:
        raise FredError(f"{fred_id}: could not parse CSV ({exc})") from exc
    if raw.shape[1] != 2:
        raise FredError(f"{fred_id}: unexpected columns {list(raw.columns)}")
    date_col, value_col = raw.columns
    if str(value_col).upper() != fred_id.upper():
        raise FredError(f"{fred_id}: value column is named {value_col!r}")

    out = pd.DataFrame(
        {
            "date": pd.to_datetime(raw[date_col], errors="coerce"),
            "value": pd.to_numeric(raw[value_col], errors="coerce").astype("float64"),
        }
    ).dropna()
    if out.empty:
        raise FredError(f"{fred_id}: no observations in the requested window")
    out = out.set_index("date").sort_index()
    return out[~out.index.duplicated(keep="last")]


def fetch_series(
    fred_id: str,
    start: date | None = None,
    end: date | None = None,
    *,
    session=None,
    timeout: float = 30,
    retries: int = 3,
    backoff: float = 1.5,
) -> pd.DataFrame:
    """Download one series. Raises ``FredError`` on any failure (404, bad payload, network)."""
    params = {"id": fred_id}
    if start is not None:
        params["cosd"] = start.isoformat()
    if end is not None:
        params["coed"] = end.isoformat()
    try:
        resp = httpclient.get(
            FRED_CSV_URL, session=session, params=params, timeout=timeout,
            retries=retries, backoff=backoff, label=fred_id,
        )
    except HttpError as exc:
        if exc.status == 404:
            raise FredError(f"{fred_id}: HTTP 404, series not found on FRED") from exc
        raise FredError(str(exc)) from exc
    return parse_fred_csv(resp.text, fred_id)
