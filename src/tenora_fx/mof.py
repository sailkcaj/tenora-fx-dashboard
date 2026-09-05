"""Japanese Government Bond yields from the Ministry of Finance (public CSV files, no API key).

Two files are combined: the full history (``historical/jgbcme_all.csv``, updated monthly) and the
current month (``jgbcme.csv``, updated daily). Both are cp932-encoded, start with a title row,
use ``-`` for missing values and may end with a free-text note row.
"""

from __future__ import annotations

import io
import logging
from datetime import date

import pandas as pd

from . import httpclient
from .httpclient import HttpError

log = logging.getLogger(__name__)

BASE_URL = "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate"
HISTORY_URL = f"{BASE_URL}/historical/jgbcme_all.csv"
CURRENT_URL = f"{BASE_URL}/jgbcme.csv"
ENCODING = "cp932"


class MofError(RuntimeError):
    """MoF JGB data could not be fetched or parsed."""


def parse_jgb_csv(raw: bytes, column: str) -> pd.DataFrame:
    """Extract one maturity column (e.g. ``"2Y"``) into a ``date``/``value`` frame."""
    text = raw.decode(ENCODING, errors="replace")
    lines = text.splitlines()
    header_at = next((i for i, line in enumerate(lines) if line.startswith("Date,")), None)
    if header_at is None:
        raise MofError("header row starting with 'Date,' not found")
    try:
        table = pd.read_csv(io.StringIO("\n".join(lines[header_at:])), na_values=["-"],
                            on_bad_lines="skip", dtype=str)
    except Exception as exc:
        raise MofError(f"could not parse CSV ({exc})") from exc
    if column not in table.columns:
        raise MofError(f"column {column!r} not found (have {list(table.columns)})")
    out = pd.DataFrame(
        {
            "date": pd.to_datetime(table["Date"], format="%Y/%m/%d", errors="coerce"),
            "value": pd.to_numeric(table[column], errors="coerce").astype("float64"),
        }
    ).dropna()
    out = out.set_index("date").sort_index()
    return out[~out.index.duplicated(keep="last")]


def fetch_series(
    column: str,
    start: date | None = None,
    end: date | None = None,
    *,
    session=None,
    timeout: float = 60,
) -> pd.DataFrame:
    """Daily JGB yield for ``column`` (``"1Y"`` .. ``"40Y"``) between ``start`` and ``end``.

    The history file is required; the current-month file is best effort (it is missing on the
    first days of a month before the Ministry publishes it).
    """
    frames = []
    for url, required in ((HISTORY_URL, True), (CURRENT_URL, False)):
        label = url.rsplit("/", 1)[-1]
        try:
            resp = httpclient.get(url, session=session, timeout=timeout, label=label)
            frames.append(parse_jgb_csv(resp.content, column))
        except (HttpError, MofError) as exc:
            if required:
                raise MofError(str(exc)) from exc
            log.warning("MoF current-month file unavailable, using history only (%s)", exc)

    df = pd.concat(frames).sort_index()
    df = df[~df.index.duplicated(keep="last")]  # later file (current month) wins on overlap
    if start is not None:
        df = df[df.index >= pd.Timestamp(start)]
    if end is not None:
        df = df[df.index <= pd.Timestamp(end)]
    if df.empty:
        raise MofError(f"{column}: no observations between {start} and {end}")
    return df
