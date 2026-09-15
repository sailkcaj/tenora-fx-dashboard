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
