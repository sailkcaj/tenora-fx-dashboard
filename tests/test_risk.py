import math
import statistics

import pandas as pd
import pytest

from tenora_fx import risk


def series(values, start="2026-01-05"):
    idx = pd.bdate_range(start, periods=len(values), name="date")
    return pd.Series(values, index=idx, dtype="float64")


def test_daily_returns_are_log_returns_and_drop_the_first_row():
    prices = series([100.0, 101.0, 99.99])
    returns = risk.daily_returns(prices)
    assert list(returns.index) == list(prices.index[1:])
    assert returns.iloc[0] == pytest.approx(math.log(101.0 / 100.0))
    assert returns.iloc[1] == pytest.approx(math.log(99.99 / 101.0))


def test_historical_var_matches_hand_computed_percentile():
    # 100 evenly spaced returns from -0.050 to 0.049; pandas' linear-interpolation 5th percentile
    # (index 0.05*99=4.95) sits between the 5th and 6th smallest values: -0.046 and -0.045.
    returns = series([(i - 50) / 1000 for i in range(100)])
    var = risk.historical_var(returns, confidence=0.95, horizon_days=1, notional=1_000_000)
    assert var == pytest.approx(45_050.0, rel=1e-6)


def test_historical_var_scales_with_sqrt_horizon_and_notional():
    returns = series([(i - 50) / 1000 for i in range(100)])
    one_day = risk.historical_var(returns, confidence=0.95, horizon_days=1, notional=1_000_000)
    four_day = risk.historical_var(returns, confidence=0.95, horizon_days=4, notional=1_000_000)
    assert four_day == pytest.approx(one_day * 2, rel=1e-9)  # sqrt(4) == 2
    double_notional = risk.historical_var(returns, confidence=0.95, horizon_days=1, notional=2_000_000)
    assert double_notional == pytest.approx(one_day * 2, rel=1e-9)


def test_confidence_band_widens_monotonically_with_horizon():
    returns = series([-0.01, 0.005, -0.003, 0.012, -0.007] * 20)
    band = risk.confidence_band(spot=1.10, returns=returns, confidence=0.95, horizon_days=10)
    assert band.index.tolist() == list(range(11))
    assert band["upper"].iloc[0] == pytest.approx(1.10)
    assert band["lower"].iloc[0] == pytest.approx(1.10)
    widths = (band["upper"] - band["lower"]).tolist()
    assert all(b > a for a, b in zip(widths, widths[1:]))  # strictly widens each extra day


def test_confidence_band_uses_a_higher_z_score_at_99_percent():
    returns = series([-0.01, 0.005, -0.003, 0.012, -0.007] * 20)
    band_95 = risk.confidence_band(spot=1.0, returns=returns, confidence=0.95, horizon_days=5)
    band_99 = risk.confidence_band(spot=1.0, returns=returns, confidence=0.99, horizon_days=5)
    assert band_99["upper"].iloc[-1] > band_95["upper"].iloc[-1]
    assert band_99["lower"].iloc[-1] < band_95["lower"].iloc[-1]


def test_realised_vol_matches_independently_computed_std():
    # Every 5-value window of this alternating series has the same sample std by symmetry.
    pattern = [0.01, -0.01] * 15
    returns = series(pattern)
    vol = risk.realised_vol(returns, window=5)
    expected = statistics.stdev(pattern[:5]) * math.sqrt(252) * 100
    assert len(vol) == len(returns) - 5 + 1
    assert vol.iloc[0] == pytest.approx(expected, rel=1e-9)
    assert vol.iloc[-1] == pytest.approx(expected, rel=1e-9)


def test_scenario_pnl_sign_and_scale():
    assert risk.scenario_pnl(1_000_000, -10) == pytest.approx(-100_000)
    assert risk.scenario_pnl(500_000, 4) == pytest.approx(20_000)
    assert risk.scenario_pnl(1_000_000, 0) == pytest.approx(0)


def test_carry_cost_sign_follows_the_spread():
    assert risk.carry_cost(2_000_000, -1.46) == pytest.approx(-29_200)
    assert risk.carry_cost(1_000_000, 0.5) == pytest.approx(5_000)


def test_drawdown_measures_percent_below_the_running_peak():
    prices = series([100.0, 110.0, 90.0, 95.0, 120.0, 80.0])
    dd = risk.drawdown(prices)
    expected = [0.0, 0.0, (90 / 110 - 1) * 100, (95 / 110 - 1) * 100, 0.0, (80 / 120 - 1) * 100]
    assert dd.tolist() == pytest.approx(expected)


def test_max_drawdown_finds_the_worst_peak_to_trough_move():
    prices = series([100.0, 110.0, 90.0, 95.0, 120.0, 80.0])
    worst = risk.max_drawdown(prices)
    assert worst["magnitude"] == pytest.approx((80 / 120 - 1) * 100)
    assert worst["peak_date"] == prices.index[4]
    assert worst["trough_date"] == prices.index[5]
