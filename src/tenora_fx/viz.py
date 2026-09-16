"""Visual layer for the Streamlit dashboard: colour tokens, a Plotly template and figure builders.

Colour follows the dataviz method: four categorical slots in a fixed order (US, UK, EU and JP
always wear the same slot), validated for colour-vision deficiency and contrast against the
dashboard's dark surface; text always wears text tokens, never a series colour; 2px lines and
hairline grids; every multi-series chart has a legend plus selective direct labels.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

# --- tokens (dark theme; keep in step with .streamlit/config.toml) ----------------------------
SURFACE = "#0c1220"  # page and chart surface (theme.backgroundColor)
SURFACE_2 = "#141c2b"  # cards, widgets, tooltips (theme.secondaryBackgroundColor)
INK = "#e4e8f1"  # primary text
INK_2 = "#b6bdcc"  # secondary text: captions, legends, direct labels
MUTED = "#8a93a6"  # axis tick labels
GRID = "#1a2336"  # hairline gridlines, one step off the surface
AXIS = "#2a3550"  # baseline / zero line
ACCENT = "#3987e5"  # categorical slot 1, also theme.primaryColor
FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif"

# Categorical slots, dark steps. Validated on SURFACE with the dataviz palette validator:
# worst adjacent CVD dE 8.4, normal-vision dE 19.8, every slot >= 3:1 contrast.
SLOTS = ("#3987e5", "#d95926", "#199e70", "#c98500")
REGION_ORDER = ("US", "UK", "EU", "JP")
REGION_COLORS = dict(zip(REGION_ORDER, SLOTS))  # colour follows the entity, never its rank
REGION_LABELS = {"US": "United States", "UK": "United Kingdom", "EU": "Euro area", "JP": "Japan"}

CURRENCY_2Y = {"USD": "us_2y", "GBP": "uk_2y", "EUR": "eu_2y", "JPY": "jp_2y"}
YIELD_2Y_COLUMNS = {"us_2y": "US", "uk_2y": "UK", "eu_2y": "EU", "jp_2y": "JP"}
POLICY_COLUMNS = {"us_policy_rate": "US", "uk_policy_rate": "UK", "eu_policy_rate": "EU", "jp_policy_rate": "JP"}

RANGES: dict[str, pd.DateOffset | None] = {
    "1M": pd.DateOffset(months=1),
    "3M": pd.DateOffset(months=3),
    "6M": pd.DateOffset(months=6),
    "1Y": pd.DateOffset(years=1),
    "2Y": None,
}
DEFAULT_RANGE = "6M"

# Forward horizons for the VaR fan chart, in trading days (~21 per month).
HORIZON_DAYS: dict[str, int] = {"1M": 21, "3M": 63, "6M": 126}
DEFAULT_HORIZON = "1M"

CURRENCY_SYMBOLS = {"USD": "$", "GBP": "£", "EUR": "€", "JPY": "¥"}

METHODOLOGY_NOTE = (
    "2-year yields are not one methodology: the US figure is FRED's constant-maturity par yield, "
    "the UK and euro-area figures are zero-coupon spot rates from the Bank of England and ECB (AAA) "
    "fitted curves, and Japan is the Ministry of Finance benchmark JGB yield. UK and Japan policy "
    "rates are OECD monthly overnight-rate proxies and lag about three months."
)

# Content for the in-app "About this dashboard" popover (dashboard/app.py). Tab name -> markdown body.
DOCS: dict[str, str] = {
    "Overview": """
**Tenora** is an FX hedging company — it helps clients manage the risk of currency moves on their
international cash flows. This dashboard is the team's internal risk view: current FX prices and
the interest-rate backdrop that drives them, plus a set of tools for sizing how much an
*unhedged* position could actually cost.

**In one line:** prices on top, the interest-rate story underneath, and a risk toolkit (VaR,
volatility, a stress slider, carry cost, and drawdown) scoped to whichever pair you're looking at.

Everything on this page is built from real data pulled daily from public sources — nothing here
is simulated or made up, though a few series are best-available proxies (flagged wherever
they're used, and covered in the Caveats tab).
""",
    "Tech stack": """
#### Language & core libraries
- **Python 3.13** — the whole project, pipeline and dashboard, is one Python codebase.
- **pandas** — every dataset (prices, rates) is a pandas time series; almost all the math
  (returns, volatility, VaR, drawdown) is pandas operations.
- **pyarrow** — reads/writes the on-disk data format, **Parquet** (a fast, compact columnar file
  format — the actual "database" for this project, no separate database server involved).
- **yfinance** — a Python wrapper around Yahoo Finance, used to pull daily FX prices.
- **requests** — used directly for the interest-rate sources (FRED, ECB, BoE, MoF), which don't
  have a ready-made Python package.
- **python-dotenv** — loads optional local settings from a `.env` file.
- **Streamlit** — turns a plain Python script (`dashboard/app.py`) into the interactive web app
  you're looking at right now — no HTML/JS written by hand.
- **Plotly** — draws every chart; Streamlit embeds Plotly figures directly.
- **pytest** — the test suite (67 tests as of the risk-tools update), runs with no network access
  using fake HTTP responses, so it can't accidentally hit a live data source.

#### How it's structured
1. **`src/tenora_fx/`** — the data pipeline and math, as an installable Python package. Each rate
   source (FRED, ECB, BoE, MoF) has its own fetcher module; `pipeline.py` orchestrates a full
   pull; `storage.py` reads/writes Parquet; `viz.py` builds every chart; `risk.py` has the
   VaR / volatility / carry / drawdown math.
2. **`dashboard/app.py`** — the Streamlit script that lays out this page: it loads the *stored*
   data (never fetches live on page load) and calls into `viz.py` / `risk.py` for everything on
   screen.
3. **`data/raw/`** — the actual data, as Parquet files, one file per currency pair or rate series,
   plus a `manifest.json` recording exactly what was pulled and when.

#### Deployment
The code lives on GitHub; **Streamlit Community Cloud** hosts the live app and rebuilds it
automatically whenever new code is pushed to `main`. The data itself doesn't regenerate on
deploy — the last pipeline run's Parquet files are committed to the repo, so the live app always
has something to show without needing to re-run the pipeline on the server.
""",
    "Data & sources": """
#### FX prices — Yahoo Finance
10 pairs, daily bars, 2 years of history: EUR/USD, GBP/USD, USD/JPY, USD/CHF, AUD/USD, USD/CAD,
NZD/USD, USD/ZAR, USD/BRL, USD/CNH.

*Caveat:* Yahoo has no real history for offshore USD/CNH, so it falls back to **CNY=X** (onshore
yuan) as a proxy — flagged on the USD/CNH tile and in the sources table below.

#### Interest rates — four regions, two rates each

| Region | Policy rate source | 2-year yield source |
|---|---|---|
| US | FRED (Fed funds target, upper limit) | FRED (Treasury 2Y par yield) |
| UK | FRED, OECD monthly proxy (~3mo lag) | Bank of England (fitted gilt curve) |
| EU | FRED (ECB deposit rate) | ECB Data Portal (AAA curve) |
| Japan | FRED, OECD monthly proxy (~3mo lag) | Japan MoF (JGB benchmark yield) |

No single free source publishes all of this, so each region uses its own official source
directly — this is why four separate fetcher modules exist (`fred.py`, `ecb.py`, `boe.py`,
`mof.py`), each handling that source's own file format and quirks.

*Caveat:* the four 2-year yields aren't computed the same way (US = par yield, UK/EU =
zero-coupon spot from a fitted curve, Japan = benchmark compound yield) — fine for direction and
differentials, not for precise cross-country comparison.

#### Provenance
Every pipeline run writes a `manifest.json`: which series succeeded, how many rows, the date
range, and any caveat. The **"Data sources and freshness"** table at the bottom of the dashboard
is this manifest, shown raw — the receipt for every number on the page.
""",
    "Dashboard guide": """
Walking down the page in order:

**Stat tiles (top)** — latest price, % change vs prior close, and a 30-day sparkline for all 10
pairs at a glance.

**Range / Pair filters** — control everything below: how far back the charts look, and which
single pair the detail charts focus on.

**Spot chart** — the selected pair's price history over the chosen range.

**2-year yield spread** — only shown when *both* currencies in the pair are USD, GBP, EUR or JPY
(the four regions with yield data). It's the base currency's 2-year yield minus the quote
currency's — currencies mostly move on interest-rate differences, so this is the "why is it
moving" chart next to the "what happened" chart.

**Unhedged exposure risk (VaR)** — "if you don't hedge this position, how much could you
realistically lose?" See the Risk methods tab for the maths.

**Realised volatility** — how much the pair has actually been swinging day to day, as a rolling
annualised percentage. Rising vol = rising risk, independent of direction.

**Stress test** — a manual slider: pick a shock size, see the instant currency impact on the
notional. No modelling, just "what if."

**Carry: cost of staying unhedged** — turns the yield spread into a yearly currency cost or
benefit — directly the pitch for why hedging has a price attached to *not* doing it.

**Historical drawdown** — the worst real peak-to-trough loss the pair has actually had over the
lookback — a genuine historical event, not a model output.

**Rates charts** — all four regions' 2-year yields and policy rates side by side, the macro
backdrop behind every pair.

**Table view / Data sources** — the raw numbers and the provenance receipt, for when someone
wants to check a figure rather than read a chart.
""",
    "Risk methods": """
#### Value at Risk (VaR) — historical simulation
Takes the pair's own daily log returns over its full history, finds the empirical percentile
matching your confidence level (e.g. the worst 5% of days for 95% confidence), scales it to the
chosen horizon by **√(horizon in trading days)**, and applies it to the notional. No assumption
that returns are normally distributed — it uses what actually happened.

#### Confidence band (the fan chart's shape)
A simpler, parametric envelope — `spot × (1 ± z·σ·√day)` — using the empirical daily volatility
(σ) but a standard normal z-score (1.645 at 95%, 2.33 at 99%). This exists to draw a
sensible-looking fan, not to carry the headline number — that's the VaR figure above it.

#### Realised volatility
Rolling standard deviation of daily log returns, annualised by multiplying by **√252** (the
standard trading-days-per-year convention), expressed as a percentage.

#### Stress test
Pure arithmetic: `notional × shock% ÷ 100`. No volatility, correlation, or hedging response is
modelled — it's a single "what if the rate moved by exactly this much, right now" snapshot.

#### Carry (cost of staying unhedged)
Uses **covered interest-rate parity** as a stand-in: the 2-year yield spread approximates the
forward points a real hedge would be priced off. `notional × spread(pp) ÷ 100` gives a rough
annual cost or benefit. A real trading desk would use matched-tenor forward rates, not the
2-year point — this is a simplification for a quick read, not a dealing price.

#### Drawdown
`price ÷ running peak so far − 1`, as a percentage. The worst point in that series, plus the
dates either side of it, is the headline "worst drawdown" stat.
""",
    "Caveats": """
- **USD/CNH** is really onshore CNY (Yahoo has no offshore CNH history) — usually tracks within a
  few tenths of a percent, can diverge under stress.
- **UK and Japan policy rates** are OECD monthly proxies with roughly a 3-month lag, not the live
  BoE / BoJ decision rate (FRED carries no current series for either).
- **2-year yields aren't methodologically identical** across the four regions — fine for
  direction and spreads, not exact comparison.
- **7 of the 10 pairs have no yield-based tools** (spread chart and carry figure) — AUD, CAD,
  NZD, ZAR and BRL have no rate data wired up yet, so those sections show a fallback message
  instead of a number.
- **VaR and volatility only see ~2 years of history** — 99% confidence is explicitly flagged as
  thin-sample for a claimed 1-in-100 event.
- **Stress test is a snapshot, not a simulation** — it doesn't account for how volatility or
  correlated markets would actually behave during a real shock.
- **Carry is an approximation, not a forward price** — see the Risk methods tab.
- **This is a risk-awareness tool, not a trading or pricing system** — none of these numbers
  should be used to place a real hedge without a proper pricing desk.
""",
}


# --- data helpers -----------------------------------------------------------------------------

def weekdays(df: pd.DataFrame) -> pd.DataFrame:
    """Drop Saturday/Sunday rows (Yahoo emits a flat weekend bar for the Friday NY session)."""
    if df.empty:
        return df
    return df[df.index.dayofweek < 5]


def slice_range(df: pd.DataFrame, code: str) -> pd.DataFrame:
    """Rows within the named range (``"1M"`` .. ``"2Y"``) measured back from the last row."""
    offset = RANGES[code]
    if offset is None or df.empty:
        return df
    return df[df.index >= df.index.max() - offset]


def price_decimals(value: float) -> int:
    return 2 if abs(value) >= 50 else 4


def format_price(value: float) -> str:
    return f"{value:,.{price_decimals(value)}f}"


def format_pct(value: float) -> str:
    return f"{value:+.2f}%"


def format_notional(amount: float, currency: str) -> str:
    symbol = CURRENCY_SYMBOLS.get(currency)
    return f"{symbol}{amount:,.0f}" if symbol else f"{amount:,.0f} {currency}"


def pct_change(series: pd.Series, periods: int = 1) -> float | None:
    """Percent change between the last value and the one ``periods`` observations earlier."""
    s = series.dropna()
    if len(s) <= periods:
        return None
    return (float(s.iloc[-1]) / float(s.iloc[-1 - periods]) - 1) * 100


def range_stats(series: pd.Series) -> dict:
    s = series.dropna()
    first, last = float(s.iloc[0]), float(s.iloc[-1])
    return {
        "change_pct": (last / first - 1) * 100,
        "high": float(s.max()),
        "low": float(s.min()),
        "last": last,
        "last_date": s.index[-1],
    }


def two_year_spread(rates: pd.DataFrame, base: str, quote: str) -> pd.Series | None:
    """``base`` 2-year yield minus ``quote`` 2-year yield, in percentage points, or None if
    either leg has no 2-year series."""
    base_key, quote_key = CURRENCY_2Y.get(base), CURRENCY_2Y.get(quote)
    if not base_key or not quote_key or base_key not in rates.columns or quote_key not in rates.columns:
        return None
    spread = (rates[base_key] - rates[quote_key]).dropna()
    spread.name = f"{base}-{quote}"
    return spread


def proxy_notes(manifest: dict | None) -> dict[str, str]:
    """Pair label -> caveat, for every FX pair whose last pull came through a fallback ticker."""
    notes = {}
    for entry in (manifest or {}).get("results", []):
        note = entry.get("note") or ""
        if entry.get("group") == "fx" and entry.get("status") == "ok" and "fallback" in note:
            key = entry["key"]
            detail = note.split("; ", 1)[1] if "; " in note else note
            notes[f"{key[:3]}/{key[3:]}"] = detail
    return notes


def labelable(ends: dict[str, float], min_gap: float) -> set[str]:
    """Series whose end value sits at least ``min_gap`` from both neighbours, so a direct end
    label will not collide. Colliding series fall back to the legend and tooltip."""
    ordered = sorted(ends.items(), key=lambda item: item[1])
    keep = set()
    for i, (name, y) in enumerate(ordered):
        below_ok = i == 0 or y - ordered[i - 1][1] >= min_gap
        above_ok = i == len(ordered) - 1 or ordered[i + 1][1] - y >= min_gap
        if below_ok and above_ok:
            keep.add(name)
    return keep


# --- Plotly template and figures --------------------------------------------------------------

def _template() -> go.layout.Template:
    template = go.layout.Template()
    template.layout = go.Layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, color=INK_2, size=12),
        colorway=list(SLOTS),
        margin=dict(l=8, r=56, t=40, b=8),
        hovermode="x unified",
        hoverlabel=dict(bgcolor=SURFACE_2, bordercolor=GRID, font=dict(family=FONT, color=INK, size=12)),
        xaxis=dict(
            showgrid=False, zeroline=False, showline=True, linecolor=AXIS, linewidth=1,
            ticks="outside", tickcolor=AXIS, ticklen=4, tickfont=dict(color=MUTED),
            hoverformat="%a %-d %b %Y",
        ),
        yaxis=dict(
            showgrid=True, gridcolor=GRID, gridwidth=1, zeroline=False, showline=False,
            tickfont=dict(color=MUTED),
        ),
        legend=dict(orientation="h", x=0, xanchor="left", y=1.0, yanchor="bottom",
                    font=dict(color=INK_2), bgcolor="rgba(0,0,0,0)"),
    )
    return template


TEMPLATE = _template()


def _figure(height: int, *, legend: bool = False) -> go.Figure:
    """A figure on the shared template. Titles live in the page, not the plot, so the legend
    (when there is one) sits alone above the plot area; axes grow their own margins."""
    fig = go.Figure()
    fig.update_layout(
        template=TEMPLATE, height=height,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=56, t=30 if legend else 12, b=0),
        xaxis=dict(automargin=True), yaxis=dict(automargin=True),
    )
    return fig


def _padded_range(low: float, high: float, pad: float = 0.08) -> list[float]:
    span = (high - low) or abs(high) * 0.01 or 1.0
    return [low - span * pad, high + span * pad]


def spot_figure(close: pd.Series, label: str, height: int = 360) -> go.Figure:
    """One pair's close: 2px accent line, a faint area wash, an end marker with a direct label."""
    s = close.dropna()
    decimals = price_decimals(float(s.iloc[-1]))
    fig = _figure(height)
    fig.add_trace(go.Scatter(
        x=s.index, y=s.values, mode="lines", name=label,
        line=dict(color=ACCENT, width=2, shape="linear"),
        fill="tozeroy", fillcolor="rgba(57,135,229,0.08)",
        hovertemplate=f"<b>%{{y:,.{decimals}f}}</b><extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=[s.index[-1]], y=[s.iloc[-1]], mode="markers", showlegend=False, hoverinfo="skip",
        marker=dict(size=9, color=ACCENT, line=dict(width=2, color=SURFACE)),
    ))
    fig.add_annotation(x=s.index[-1], y=float(s.iloc[-1]), text=format_price(float(s.iloc[-1])),
                       showarrow=False, xanchor="left", xshift=10, font=dict(color=INK_2, size=12))
    fig.update_layout(showlegend=False, yaxis=dict(range=_padded_range(float(s.min()), float(s.max())),
                                                    tickformat=f",.{decimals}f"))
    return fig


def spread_figure(spread: pd.Series, label: str, height: int = 360) -> go.Figure:
    """A yield spread against its zero baseline (percentage points)."""
    s = spread.dropna()
    fig = _figure(height)
    fig.add_trace(go.Scatter(
        x=s.index, y=s.values, mode="lines", name=label,
        line=dict(color=ACCENT, width=2),
        hovertemplate="<b>%{y:+.2f} pp</b><extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=[s.index[-1]], y=[s.iloc[-1]], mode="markers", showlegend=False, hoverinfo="skip",
        marker=dict(size=9, color=ACCENT, line=dict(width=2, color=SURFACE)),
    ))
    fig.add_annotation(x=s.index[-1], y=float(s.iloc[-1]), text=f"{float(s.iloc[-1]):+.2f}",
                       showarrow=False, xanchor="left", xshift=10, font=dict(color=INK_2, size=12))
    fig.add_hline(y=0, line=dict(color=AXIS, width=1))
    low, high = min(float(s.min()), 0.0), max(float(s.max()), 0.0)
    fig.update_layout(showlegend=False, yaxis=dict(range=_padded_range(low, high), ticksuffix=" pp"))
    return fig


def rates_figure(wide: pd.DataFrame, columns: dict[str, str], *, step: bool = False,
                 height: int = 340, unit: str = "%") -> go.Figure:
    """Up to four regional series in fixed slot order, with a legend and non-colliding end labels.
    The chart's title belongs in the page above it, so the legend has the top edge to itself."""
    fig = _figure(height, legend=True)
    ends: dict[str, tuple[pd.Timestamp, float]] = {}
    values: list[float] = []
    for region in REGION_ORDER:
        key = next((k for k, r in columns.items() if r == region and k in wide.columns), None)
        if key is None:
            continue
        s = wide[key].dropna()
        if s.empty:
            continue
        name = REGION_LABELS[region]
        fig.add_trace(go.Scatter(
            x=s.index, y=s.values, mode="lines", name=name,
            line=dict(color=REGION_COLORS[region], width=2, shape="hv" if step else "linear"),
            hovertemplate=f"<b>%{{y:.2f}}{unit}</b> {name}<extra></extra>",
        ))
        ends[region] = (s.index[-1], float(s.iloc[-1]))
        values.extend([float(s.min()), float(s.max())])
    if values:
        low, high = min(values), max(values)
        for region in labelable({r: y for r, (_, y) in ends.items()}, min_gap=((high - low) or 1.0) * 0.06):
            x, y = ends[region]
            fig.add_annotation(x=x, y=y, text=region, showarrow=False, xanchor="left", xshift=8,
                               font=dict(color=INK_2, size=12))
        fig.update_layout(yaxis=dict(range=_padded_range(low, high)))  # keep lines off the legend
    fig.update_layout(showlegend=True, yaxis=dict(ticksuffix=unit))
    return fig


def fan_chart(pair: str, band_df: pd.DataFrame, spot: float, height: int = 360) -> go.Figure:
    """A VaR confidence band fanning out from today's spot: filled envelope between ``band_df``'s
    ``upper``/``lower`` columns (indexed by trading day out from today), plus a dashed spot line."""
    decimals = price_decimals(spot)
    fig = _figure(height)
    fig.add_trace(go.Scatter(
        x=band_df.index, y=band_df["upper"], mode="lines", line=dict(color=ACCENT, width=0),
        showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=band_df.index, y=band_df["lower"], mode="lines", line=dict(color=ACCENT, width=0),
        fill="tonexty", fillcolor="rgba(57,135,229,0.14)", name=f"{pair} confidence band",
        showlegend=False, hovertemplate=f"<b>%{{y:,.{decimals}f}}</b><extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=[band_df.index.min(), band_df.index.max()], y=[spot, spot], mode="lines",
        line=dict(color=ACCENT, width=2, dash="dash"), showlegend=False,
        hovertemplate=f"<b>{format_price(spot)}</b> current spot<extra></extra>",
    ))
    low, high = float(band_df["lower"].min()), float(band_df["upper"].max())
    fig.update_layout(
        showlegend=False,
        xaxis=dict(title=dict(text="Trading days ahead", font=dict(color=MUTED, size=11))),
        yaxis=dict(range=_padded_range(low, high), tickformat=f",.{decimals}f"),
    )
    return fig


def vol_figure(vol: pd.Series, height: int = 300) -> go.Figure:
    """Rolling realised volatility (annualised %), as a filled line with an end label."""
    s = vol.dropna()
    fig = _figure(height)
    fig.add_trace(go.Scatter(
        x=s.index, y=s.values, mode="lines", name="Realised vol",
        line=dict(color=ACCENT, width=2), fill="tozeroy", fillcolor="rgba(57,135,229,0.08)",
        hovertemplate="<b>%{y:.1f}%</b> annualised<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=[s.index[-1]], y=[s.iloc[-1]], mode="markers", showlegend=False, hoverinfo="skip",
        marker=dict(size=9, color=ACCENT, line=dict(width=2, color=SURFACE)),
    ))
    fig.add_annotation(x=s.index[-1], y=float(s.iloc[-1]), text=f"{float(s.iloc[-1]):.1f}%",
                       showarrow=False, xanchor="left", xshift=10, font=dict(color=INK_2, size=12))
    fig.update_layout(showlegend=False,
                      yaxis=dict(range=_padded_range(0.0, float(s.max())), ticksuffix="%"))
    return fig


def drawdown_figure(dd: pd.Series, height: int = 300) -> go.Figure:
    """Underwater chart: percent drawdown from the running peak, filled below a zero baseline."""
    s = dd.dropna()
    fig = _figure(height)
    fig.add_trace(go.Scatter(
        x=s.index, y=s.values, mode="lines", name="Drawdown",
        line=dict(color=SLOTS[1], width=2), fill="tozeroy", fillcolor="rgba(217,89,38,0.14)",
        hovertemplate="<b>%{y:.1f}%</b><extra></extra>",
    ))
    fig.add_hline(y=0, line=dict(color=AXIS, width=1))
    fig.update_layout(showlegend=False,
                      yaxis=dict(range=_padded_range(float(s.min()), 0.0), ticksuffix="%"))
    return fig
