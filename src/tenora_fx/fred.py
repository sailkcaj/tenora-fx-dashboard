"""Fetch FRED series via the public ``fredgraph.csv`` endpoint (no API key required)."""

from __future__ import annotations

import io
import logging
import time
from datetime import date

import pandas as pd
import requests

from .config import FRED_CSV_URL

log = logging.getLogger(__name__)

USER_AGENT = "tenora-fx-dashboard/0.1 (data pipeline)"


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
    session: requests.Session | None = None,
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
    sess = session or requests.Session()
    headers = {"User-Agent": USER_AGENT}

    last_error: FredError | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = sess.get(FRED_CSV_URL, params=params, timeout=timeout, headers=headers)
        except requests.RequestException as exc:
            last_error = FredError(f"{fred_id}: request failed ({exc})")
        else:
            if resp.status_code == 200:
                return parse_fred_csv(resp.text, fred_id)
            last_error = FredError(f"{fred_id}: HTTP {resp.status_code} from FRED")
            if resp.status_code == 404:
                raise FredError(f"{fred_id}: HTTP 404, series not found on FRED")
            if 400 <= resp.status_code < 500 and resp.status_code != 429:
                raise last_error  # other client errors will not fix themselves
        if attempt < retries:
            log.warning("%s (attempt %d/%d), retrying", last_error, attempt, retries)
            time.sleep(backoff * attempt)
    assert last_error is not None
    raise last_error
