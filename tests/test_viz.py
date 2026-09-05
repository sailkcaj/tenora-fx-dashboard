import pandas as pd
import pytest

from tenora_fx import viz


def series(values, start="2026-08-03"):
    idx = pd.bdate_range(start, periods=len(values), name="date")
    return pd.Series(values, index=idx, dtype="float64")


def test_weekdays_drops_weekend_bars():
    idx = pd.DatetimeIndex(["2026-09-03", "2026-09-04", "2026-09-05", "2026-09-06"], name="date")
    df = pd.DataFrame({"close": [1.0, 1.1, 1.1, 1.1]}, index=idx)
    assert list(viz.weekdays(df).index.strftime("%Y-%m-%d")) == ["2026-09-03", "2026-09-04"]


def test_slice_range_measures_back_from_last_row():
    df = pd.DataFrame({"close": 1.0}, index=pd.bdate_range("2024-09-05", "2026-09-04", name="date"))
    assert viz.slice_range(df, "2Y") is df
    one_month = viz.slice_range(df, "1M")
    assert one_month.index.min() >= pd.Timestamp("2026-08-04")
    assert one_month.index.max() == pd.Timestamp("2026-09-04")
    assert len(viz.slice_range(df, "6M")) > len(viz.slice_range(df, "3M")) > len(one_month)


def test_price_formatting_by_magnitude():
    assert viz.format_price(1.162115) == "1.1621"
    assert viz.format_price(156.220993) == "156.22"
    assert viz.format_price(6.7013) == "6.7013"
    assert viz.format_pct(0.3141) == "+0.31%"
    assert viz.format_pct(-1.0) == "-1.00%"


def test_pct_change_and_range_stats():
    s = series([1.00, 1.02, 1.01])
    assert viz.pct_change(s) == pytest.approx(-0.980392)
    assert viz.pct_change(series([1.0])) is None
    stats = viz.range_stats(s)
    assert stats["change_pct"] == pytest.approx(1.0)
    assert (stats["high"], stats["low"], stats["last"]) == (1.02, 1.00, 1.01)
    assert stats["last_date"] == s.index[-1]


def test_two_year_spread_needs_both_legs():
    rates = pd.DataFrame({"us_2y": series([4.0, 4.1, 4.2]), "eu_2y": series([2.0, 2.0, 2.1])})
    spread = viz.two_year_spread(rates, "EUR", "USD")
    assert spread.name == "EUR-USD"
    assert list(spread.round(2)) == [-2.0, -2.1, -2.1]
    assert viz.two_year_spread(rates, "AUD", "USD") is None
    assert viz.two_year_spread(rates.drop(columns=["eu_2y"]), "EUR", "USD") is None


def test_proxy_notes_only_for_fallback_pulls():
    manifest = {"results": [
        {"group": "fx", "key": "EURUSD", "status": "ok", "note": ""},
        {"group": "fx", "key": "USDCNH", "status": "ok",
         "note": "fetched via fallback CNY=X after USDCNH=X failed; CNY=X is onshore CNY, a proxy for CNH"},
        {"group": "rates", "key": "uk_2y", "status": "ok", "note": "fallback-ish wording in a rates note"},
    ]}
    assert viz.proxy_notes(manifest) == {"USD/CNH": "CNY=X is onshore CNY, a proxy for CNH"}
    assert viz.proxy_notes(None) == {}


def test_labelable_skips_colliding_end_labels():
    ends = {"US": 4.34, "UK": 4.34, "EU": 2.89, "JP": 1.85}
    assert viz.labelable(ends, min_gap=0.15) == {"EU", "JP"}
    assert viz.labelable({"US": 1.0}, min_gap=0.5) == {"US"}


def test_spot_and_spread_figures_have_no_legend_and_an_end_label():
    fig = viz.spot_figure(series([1.10, 1.12, 1.11]), "EUR/USD")
    assert len(fig.data) == 2  # line + end marker
    assert fig.layout.showlegend is False
    assert fig.data[0].line.width == 2
    assert fig.layout.annotations[0].text == "1.1100"

    spread = viz.spread_figure(series([-1.5, -1.4, -1.45]), "EUR-USD")
    assert spread.layout.showlegend is False
    assert spread.layout.annotations[0].text == "-1.45"
    assert any(shape.y0 == 0 for shape in spread.layout.shapes)  # zero baseline


def test_rates_figure_keeps_fixed_region_colours_and_legend():
    wide = pd.DataFrame({"jp_2y": series([1.8, 1.85]), "us_2y": series([4.3, 4.34]), "eu_2y": series([2.8, 2.89])})
    fig = viz.rates_figure(wide, viz.YIELD_2Y_COLUMNS)
    assert [trace.name for trace in fig.data] == ["United States", "Euro area", "Japan"]  # fixed slot order
    assert [trace.line.color for trace in fig.data] == [viz.REGION_COLORS[r] for r in ("US", "EU", "JP")]
    assert fig.layout.showlegend is True
    assert {a.text for a in fig.layout.annotations} == {"US", "EU", "JP"}

    stepped = viz.rates_figure(wide.rename(columns={"us_2y": "us_policy_rate"}), viz.POLICY_COLUMNS, step=True)
    assert stepped.data[0].line.shape == "hv"
    assert stepped.data[0].line.color == viz.REGION_COLORS["US"]  # colour follows the entity, not its row
