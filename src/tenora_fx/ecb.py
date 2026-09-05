"""Euro-area series from the ECB Data Portal (SDMX REST API, CSV output, no API key)."""

from __future__ import annotations

import io
import logging
from datetime import date

import pandas as pd

from . import httpclient
from .httpclient import HttpError

log = logging.getLogger(__name__)

API_BASE = "https://data-api.ecb.europa.eu/service/data"


class EcbError(RuntimeError):
    """An ECB series could not be fetched or parsed."""


def parse_csvdata(text: str, key: str) -> pd.DataFrame:
    """Parse ``format=csvdata`` output (one row per observation) into a ``date``/``value`` frame."""
    if not text.strip():
        raise EcbError(f"{key}: empty response")
    try:
        raw = pd.read_csv(io.StringIO(text))
    except Exception as exc:
        raise EcbError(f"{key}: could not parse CSV ({exc})") from exc
    for col in ("TIME_PERIOD", "OBS_VALUE"):
        if col not in raw.columns:
            raise EcbError(f"{key}: column {col!r} missing from response")
    out = pd.DataFrame(
        {
            "date": pd.to_datetime(raw["TIME_PERIOD"], errors="coerce"),
            "value": pd.to_numeric(raw["OBS_VALUE"], errors="coerce").astype("float64"),
        }
    ).dropna()
    if out.empty:
        raise EcbError(f"{key}: no observations in the requested window")
    out = out.set_index("date").sort_index()
    return out[~out.index.duplicated(keep="last")]


def fetch_series(
    key: str,
    start: date | None = None,
    end: date | None = None,
    *,
    session=None,
    timeout: float = 60,
) -> pd.DataFrame:
    """Download one series. ``key`` is ``<dataflow>/<series key>``, e.g.
    ``YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y`` (euro area AAA 2-year spot rate)."""
    if "/" not in key:
        raise EcbError(f"{key}: expected '<dataflow>/<series key>'")
    flow, series_key = key.split("/", 1)
    params = {"format": "csvdata"}
    if start is not None:
        params["startPeriod"] = start.isoformat()
    if end is not None:
        params["endPeriod"] = end.isoformat()
    try:
        resp = httpclient.get(f"{API_BASE}/{flow}/{series_key}", session=session, params=params,
                              timeout=timeout, label=key)
    except HttpError as exc:
        if exc.status == 404:
            raise EcbError(f"{key}: HTTP 404, no such series (or no data in the window)") from exc
        raise EcbError(str(exc)) from exc
    return parse_csvdata(resp.text, key)
