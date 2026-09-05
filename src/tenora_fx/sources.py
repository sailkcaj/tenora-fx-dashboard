"""Registry of rate-series fetchers, keyed by the ``source`` field of ``config.RateSeries``.

Every fetcher has the same shape: ``fetch(source_id, start, end, *, session=None) -> DataFrame``
with a tz-naive ``date`` index and one float ``value`` column, in percent.
"""

from __future__ import annotations

from typing import Callable

import pandas as pd

from . import boe, ecb, fred, mof

FETCHERS: dict[str, Callable[..., pd.DataFrame]] = {
    "fred": fred.fetch_series,
    "ecb": ecb.fetch_series,
    "boe_yield_curve": boe.fetch_series,
    "mof": mof.fetch_series,
}
