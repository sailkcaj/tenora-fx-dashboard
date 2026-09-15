"""Tenora FX Risk Dashboard - Streamlit entry point.

Milestone 2: the visual shell over the real parquet store (scenario logic comes next).
Run ``python -m tenora_fx.pipeline`` first, then ``streamlit run dashboard/app.py``.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tenora_fx import risk, storage, viz
from tenora_fx.config import FX_PAIRS

st.set_page_config(page_title="Tenora FX Risk", page_icon="📈", layout="wide",
                   initial_sidebar_state="collapsed")

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.75rem; padding-bottom: 2.5rem; max-width: 1440px;}
    header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"] {display: none;}
    .tn-title {font-size: 1.75rem; font-weight: 650; letter-spacing: -0.01em; line-height: 1.15; margin: 0;}
    .tn-sub {color: #b6bdcc; font-size: 0.95rem; margin: 0.2rem 0 0;}
    .tn-status {color: #8a93a6; font-size: 0.85rem; text-align: right; line-height: 1.5; margin: 0;}
    .tn-status b {color: #e4e8f1; font-weight: 600;}
    .tn-section {font-size: 1.05rem; font-weight: 600; color: #e4e8f1; margin: 1.4rem 0 0.2rem;}
    .tn-stats {color: #8a93a6; font-size: 0.85rem; margin: 0 0 0.25rem;}
    .tn-stats b {color: #b6bdcc; font-weight: 600;}
    .tn-chart-title {font-size: 0.95rem; font-weight: 600; color: #e4e8f1; margin: 0.4rem 0 0;}
    .tn-risk-headline {font-size: 1.15rem; font-weight: 650; color: #e4e8f1; margin: 0; line-height: 1.4;}
    </style>
    """,
    unsafe_allow_html=True,
)

CHART_CONFIG = {"displayModeBar": False, "responsive": True}
CONFIDENCE_LEVELS = {"95%": 0.95, "99%": 0.99}


@st.cache_data(ttl=300, show_spinner=False)
def load_store():
    manifest = storage.read_manifest()
    closes = viz.weekdays(storage.load_fx_closes())
    rates = viz.weekdays(storage.load_rates())
    return manifest, closes, rates


@st.cache_data(ttl=300, show_spinner=False)
def load_ohlc(pair_name: str) -> pd.DataFrame:
    return viz.weekdays(storage.load_parquet(storage.fx_path(pair_name)))


def section(title: str) -> None:
    st.markdown(f'<p class="tn-section">{title}</p>', unsafe_allow_html=True)


def stats_line(html: str) -> None:
    st.markdown(f'<p class="tn-stats">{html}</p>', unsafe_allow_html=True)


def chart_title(container, title: str) -> None:
    container.markdown(f'<p class="tn-chart-title">{title}</p>', unsafe_allow_html=True)


manifest, closes, rates = load_store()
if manifest is None or closes.empty:
    st.warning("No data yet. Run `python -m tenora_fx.pipeline` first.")
    st.stop()

pairs = [p for p in FX_PAIRS if p.name in closes.columns]
by_name = {p.name: p for p in pairs}
as_of = closes.index.max()
pulled = datetime.fromisoformat(manifest["generated_at"]).strftime("%-d %b %H:%M UTC")
summary = manifest["summary"]

# --- header -----------------------------------------------------------------------------------
head_left, head_right = st.columns([3, 1], vertical_alignment="top")
head_left.markdown(
    '<p class="tn-title">Tenora FX Risk</p>'
    '<p class="tn-sub">Spot, policy rates and 2-year yields across the hedging book</p>',
    unsafe_allow_html=True,
)
with head_right:
    with st.popover("📄", width=560,
                    help="About this dashboard: the stack, the data, and what everything means"):
        for doc_tab, content in zip(st.tabs(list(viz.DOCS)), viz.DOCS.values()):
            doc_tab.markdown(content)
    st.markdown(
        f'<p class="tn-status">Prices as of <b>{as_of:%a %-d %b %Y}</b><br>'
        f'{summary["ok"]}/{summary["total"]} series ok · pulled {pulled}</p>',
        unsafe_allow_html=True,
    )

# --- latest spot: one stat tile per pair ----------------------------------------------------------
proxy_notes = viz.proxy_notes(manifest)
for row in (pairs[:5], pairs[5:]):
    columns = st.columns(len(row), gap="small")
    for column, pair in zip(columns, row):
        series = closes[pair.name].dropna()
        change = viz.pct_change(series)
        column.metric(
            pair.label,
            viz.format_price(float(series.iloc[-1])),
            delta=None if change is None else viz.format_pct(change),
            border=True,
            chart_data=series.tail(30).tolist(),
            chart_type="line",
            help=proxy_notes.get(pair.label),
        )
for label, detail in proxy_notes.items():
    st.caption(f"{label}: {detail}. Daily change is versus the prior close.")
if not proxy_notes:
    st.caption("Daily change is versus the prior close.")

# --- filters: one row, scoping everything below ------------------------------------------------------
with st.container(horizontal=True, wrap=True, vertical_alignment="bottom", gap="medium"):
    range_code = st.segmented_control("Range", list(viz.RANGES), default=viz.DEFAULT_RANGE,
                                      key="range", width="content") or viz.DEFAULT_RANGE
    pair_name = st.pills("Pair", list(by_name), default=pairs[0].name, key="pair", width="content",
                         format_func=lambda name: by_name[name].label) or pairs[0].name
pair = by_name[pair_name]

# --- spot and 2-year spread for the selected pair --------------------------------------------------------
ohlc = viz.slice_range(load_ohlc(pair.name), range_code)
close = ohlc["close"].dropna()
stats = viz.range_stats(close)
spread = viz.two_year_spread(rates, pair.base, pair.quote)
missing = [c for c in (pair.base, pair.quote) if c not in viz.CURRENCY_2Y]
if spread is not None:
    spread = viz.slice_range(spread.to_frame(), range_code).iloc[:, 0]

spot_col, spread_col = st.columns([3, 2], gap="medium") if spread is not None else (st.container(), None)
with spot_col:
    section(f"{pair.label} spot")
    stats_line(
        f"{range_code} change <b>{viz.format_pct(stats['change_pct'])}</b> · "
        f"high <b>{viz.format_price(stats['high'])}</b> · low <b>{viz.format_price(stats['low'])}</b> · "
        f"last <b>{viz.format_price(stats['last'])}</b> on {stats['last_date']:%-d %b}"
    )
    st.plotly_chart(viz.spot_figure(close, pair.label), width="stretch", theme=None, config=CHART_CONFIG)
if spread_col is not None:
    with spread_col:
        section(f"2-year yield spread, {pair.base} minus {pair.quote}")
        stats_line(
            f"latest <b>{float(spread.iloc[-1]):+.2f} pp</b> · "
            f"{range_code} change <b>{float(spread.iloc[-1] - spread.iloc[0]):+.2f} pp</b>"
        )
        st.plotly_chart(viz.spread_figure(spread, f"{pair.base}-{pair.quote}"), width="stretch",
                        theme=None, config=CHART_CONFIG)
else:
    st.caption(f"No 2-year yield series for {' or '.join(missing)} yet, so no spread is shown. "
               "Spreads are available where both legs are USD, GBP, EUR or JPY.")

# --- unhedged exposure risk: historical VaR + a fan chart -------------------------------------------
section("Unhedged exposure risk")
full_close = load_ohlc(pair.name)["close"].dropna()
returns = risk.daily_returns(full_close)
spot = float(full_close.iloc[-1])

with st.container(horizontal=True, wrap=True, vertical_alignment="bottom", gap="medium"):
    notional = st.number_input(f"Notional exposure ({pair.base})", min_value=0.0, value=1_000_000.0,
                               step=50_000.0, format="%.0f", key="var_notional")
    confidence_label = st.segmented_control("Confidence", list(CONFIDENCE_LEVELS), default="95%",
                                            key="var_confidence", width="content") or "95%"
    horizon_label = st.segmented_control("Horizon", list(viz.HORIZON_DAYS), default=viz.DEFAULT_HORIZON,
                                         key="var_horizon", width="content") or viz.DEFAULT_HORIZON
if confidence_label == "99%":
    st.caption("99% confidence is less reliable here — it's drawn from the same ~2 years of daily "
               "history as everything else, which is a thin sample for a 1-in-100 tail.")

confidence = CONFIDENCE_LEVELS[confidence_label]
horizon_days = viz.HORIZON_DAYS[horizon_label]

if returns.empty or notional <= 0:
    st.caption("Not enough return history yet to estimate risk for this pair.")
else:
    var_amount = risk.historical_var(returns, confidence, horizon_days, notional)
    band = risk.confidence_band(spot, returns, confidence, horizon_days)
    tail_pct = (1 - confidence) * 100

    with st.container(border=True):
        st.markdown(
            f'<p class="tn-risk-headline">{tail_pct:.0f}% chance of losing more than '
            f'<b>{viz.format_notional(var_amount, pair.base)}</b> over {horizon_label} '
            f'({horizon_days} trading days) if unhedged</p>',
            unsafe_allow_html=True,
        )
    st.plotly_chart(viz.fan_chart(pair.label, band, spot), width="stretch", theme=None, config=CHART_CONFIG)
    st.caption("Historical simulation VaR: the empirical worst-case daily move from the pair's own "
               "history, scaled to the horizon by √days. The shaded band is a parametric envelope "
               "(mean ± z·σ·√days) shown for shape, not the headline number above.")

# --- realised volatility -----------------------------------------------------------------------------
section("Realised volatility")
VOL_WINDOW = 30
vol = risk.realised_vol(returns, window=VOL_WINDOW)
if vol.empty:
    st.caption("Not enough history yet for a rolling volatility estimate.")
else:
    stats_line(
        f"{VOL_WINDOW}-day annualised vol, latest <b>{float(vol.iloc[-1]):.1f}%</b> · "
        f"2Y range <b>{float(vol.min()):.1f}%–{float(vol.max()):.1f}%</b>"
    )
    st.plotly_chart(viz.vol_figure(vol), width="stretch", theme=None, config=CHART_CONFIG)
    st.caption("Rolling standard deviation of daily log returns, annualised (×√252) and "
               "expressed as a percentage — the market's realised risk, not a forecast.")

# --- stress test --------------------------------------------------------------------------------------
section("Stress test")
shock_pct = st.slider("Instant shock to spot (%)", min_value=-20.0, max_value=20.0, value=-10.0,
                      step=0.5, key="stress_shock")
shocked_spot = spot * (1 + shock_pct / 100)
shock_pnl = risk.scenario_pnl(notional, shock_pct)
direction = "loss" if shock_pnl < 0 else "gain"
with st.container(border=True):
    st.markdown(
        f'<p class="tn-risk-headline">A {shock_pct:+.1f}% move takes {pair.label} to '
        f'<b>{viz.format_price(shocked_spot)}</b> — a {direction} of '
        f'<b>{viz.format_notional(abs(shock_pnl), pair.base)}</b> on the notional above</p>',
        unsafe_allow_html=True,
    )
st.caption("A simple instantaneous re-pricing of the notional at the shocked spot — no vol, "
           "correlation or hedging response modelled, just \"what if the rate moved by this much.\"")

# --- carry: cost of staying unhedged -------------------------------------------------------------------
section("Carry: cost of staying unhedged")
if spread is None:
    st.caption(f"No 2-year yield series for {' or '.join(missing)} yet, so carry can't be estimated. "
               "Available where both legs are USD, GBP, EUR or JPY.")
else:
    carry_pp = float(spread.iloc[-1])
    carry_amount = risk.carry_cost(notional, carry_pp)
    verb = "earns" if carry_amount >= 0 else "costs"
    with st.container(border=True):
        st.markdown(
            f'<p class="tn-risk-headline">Staying unhedged {verb} roughly '
            f'<b>{viz.format_notional(abs(carry_amount), pair.base)}</b> a year, from the '
            f'{pair.base}-{pair.quote} 2-year rate gap ({carry_pp:+.2f} pp)</p>',
            unsafe_allow_html=True,
        )
    st.caption("Approximation via covered interest-rate parity: the 2-year yield spread stands in for "
               "forward points. Assumes the notional is held as a base-currency exposure for a year; "
               "real forward pricing would use matched-tenor rates, not the 2-year point.")

# --- historical drawdown ------------------------------------------------------------------------------
section("Historical drawdown")
dd = risk.drawdown(full_close)
worst = risk.max_drawdown(full_close)
stats_line(
    f"worst over the period <b>{worst['magnitude']:.1f}%</b>, "
    f"{worst['peak_date']:%-d %b %Y} → {worst['trough_date']:%-d %b %Y}"
)
st.plotly_chart(viz.drawdown_figure(dd), width="stretch", theme=None, config=CHART_CONFIG)
st.caption("Percent below the running high so far — a real historical event, not a model estimate.")

# --- rates -----------------------------------------------------------------------------------------
section("Rates")
two_year = viz.slice_range(rates[[k for k in viz.YIELD_2Y_COLUMNS if k in rates.columns]], range_code)
policy = viz.slice_range(rates[[k for k in viz.POLICY_COLUMNS if k in rates.columns]], range_code)
rates_left, rates_right = st.columns(2, gap="medium")
chart_title(rates_left, "2-year government yields")
rates_left.plotly_chart(viz.rates_figure(two_year, viz.YIELD_2Y_COLUMNS),
                        width="stretch", theme=None, config=CHART_CONFIG)
chart_title(rates_right, "Policy rates")
rates_right.plotly_chart(viz.rates_figure(policy, viz.POLICY_COLUMNS, step=True),
                         width="stretch", theme=None, config=CHART_CONFIG)
st.caption(viz.METHODOLOGY_NOTE)

# --- table view and provenance ---------------------------------------------------------------------
with st.expander("Table view"):
    tab_spot, tab_rates = st.tabs([f"{pair.label} daily OHLC", "Rates (%)"])
    decimals = viz.price_decimals(stats["last"])
    tab_spot.dataframe(
        ohlc.sort_index(ascending=False),
        column_config={
            "_index": st.column_config.DateColumn("Date", format="D MMM YYYY"),
            **{c: st.column_config.NumberColumn(c.title(), format=f"%.{decimals}f") for c in ohlc.columns},
        },
        height=320,
    )
    rates_view = viz.slice_range(rates, range_code).sort_index(ascending=False)
    tab_rates.dataframe(
        rates_view,
        column_config={
            "_index": st.column_config.DateColumn("Date", format="D MMM YYYY"),
            **{c: st.column_config.NumberColumn(c, format="%.2f") for c in rates_view.columns},
        },
        height=320,
    )

with st.expander("Data sources and freshness"):
    status = pd.DataFrame(manifest["results"])
    st.dataframe(status[["group", "key", "source", "status", "rows", "first", "last", "note"]], hide_index=True)
