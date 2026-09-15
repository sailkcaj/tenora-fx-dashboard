"""Unhedged FX exposure risk: historical VaR and a fan-chart confidence band.

The headline VaR figure is historical simulation: the loss at a given confidence is the empirical
``(1 - confidence)`` percentile of a pair's own daily log returns (no normal-distribution assumption),
scaled to the horizon by ``sqrt(horizon_days)`` (the standard scaling under an i.i.d. daily-returns
assumption) and applied to the notional. The fan chart's band is parametric (empirical daily vol, a
normal z-score) since it only needs to trace a plausible envelope shape, not carry the headline number.
"""

from __future__ import annotations

import math

import pandas as pd

# Two-sided normal z-scores, used only for the fan chart's envelope shape.
CONFIDENCE_Z = {0.95: 1.645, 0.99: 2.33}


def daily_returns(prices: pd.Series) -> pd.Series:
    """Log returns from a pair's close prices (e.g. ``storage.load_parquet(storage.fx_path(name))["close"]``)."""
    prices = prices.dropna()
    return (prices / prices.shift(1)).apply(math.log).dropna()


def historical_var(returns: pd.Series, confidence: float, horizon_days: int, notional: float) -> float:
    """Historical-simulation VaR: the empirical ``(1 - confidence)`` percentile daily return, scaled
    to the horizon by ``sqrt(horizon_days)`` and applied to ``notional``. Positive = a loss amount."""
    tail_return = returns.dropna().quantile(1 - confidence)
    scaled_return = tail_return * math.sqrt(horizon_days)
    return float(-scaled_return * notional)


def confidence_band(spot: float, returns: pd.Series, confidence: float, horizon_days: int) -> pd.DataFrame:
    """Upper/lower bounds for each day out to ``horizon_days``, widening with ``sqrt(day)``."""
    z = CONFIDENCE_Z[confidence]
    daily_vol = returns.dropna().std()
    days = range(horizon_days + 1)
    spread = [z * daily_vol * math.sqrt(day) for day in days]
    return pd.DataFrame(
        {"upper": [spot * (1 + s) for s in spread], "lower": [spot * (1 - s) for s in spread]},
        index=pd.Index(days, name="day"),
    )
