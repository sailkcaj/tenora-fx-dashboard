"""Project configuration: paths, instruments and the data-series registry."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

DATA_DIR = Path(os.getenv("TENORA_DATA_DIR") or PROJECT_ROOT / "data")
RAW_DIR = DATA_DIR / "raw"
FX_DIR = RAW_DIR / "fx"
RATES_DIR = RAW_DIR / "rates"
PROCESSED_DIR = DATA_DIR / "processed"
MANIFEST_PATH = RAW_DIR / "manifest.json"
CACHE_DIR = RAW_DIR / "cache"  # source downloads worth keeping between runs (e.g. the BoE archive)
BOE_CACHE_DIR = CACHE_DIR / "boe"

LOOKBACK_YEARS = 2

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


@dataclass(frozen=True)
class FxPair:
    """A currency pair and the Yahoo Finance symbol(s) used to fetch it."""

    name: str  # "EURUSD" -- also the parquet file stem
    ticker: str  # primary Yahoo symbol, e.g. "EURUSD=X"
    fallbacks: tuple[str, ...] = ()  # alternative symbols tried, in order, if the primary fails
    fallback_note: str = ""  # caveat recorded in the manifest whenever a fallback is used

    @property
    def base(self) -> str:
        return self.name[:3]

    @property
    def quote(self) -> str:
        return self.name[3:]

    @property
    def label(self) -> str:
        return f"{self.base}/{self.quote}"

    @property
    def tickers(self) -> tuple[str, ...]:
        return (self.ticker, *self.fallbacks)


FX_PAIRS: tuple[FxPair, ...] = (
    FxPair("EURUSD", "EURUSD=X"),
    FxPair("GBPUSD", "GBPUSD=X"),
    FxPair("USDJPY", "USDJPY=X"),
    FxPair("USDCHF", "USDCHF=X"),
    FxPair("AUDUSD", "AUDUSD=X"),
    FxPair("USDCAD", "USDCAD=X"),
    FxPair("NZDUSD", "NZDUSD=X"),
    FxPair("USDZAR", "USDZAR=X"),
    FxPair("USDBRL", "USDBRL=X"),
    FxPair(
        "USDCNH", "USDCNH=X", fallbacks=("CNY=X",),
        fallback_note="CNY=X is onshore CNY, used as a proxy for offshore CNH (Yahoo carries no CNH history)",
    ),
)


@dataclass(frozen=True)
class RateSeries:
    """One interest-rate series and where it comes from.

    ``source`` names a fetcher in ``tenora_fx.sources.FETCHERS`` and ``source_id`` is what that
    fetcher needs: a FRED series id, an ECB ``flow/key``, a BoE curve maturity in years, or a
    MoF column name. ``source=None`` marks a series nobody supplies yet.
    """

    key: str  # parquet file stem / column name, e.g. "us_2y"
    region: str  # "US" | "UK" | "EU" | "JP"
    kind: str  # "policy_rate" | "2y_yield"
    source: str | None
    source_id: str | None
    description: str
    frequency: str = "daily"  # "daily" | "monthly"
    note: str = ""  # caveats surfaced in the report (proxy series, lag, methodology)

    @property
    def available(self) -> bool:
        return bool(self.source and self.source_id)


RATE_SERIES: tuple[RateSeries, ...] = (
    RateSeries(
        "us_policy_rate", "US", "policy_rate", "fred", "DFEDTARU",
        "Fed funds target range, upper limit (%)",
    ),
    RateSeries(
        "us_2y", "US", "2y_yield", "fred", "DGS2",
        "US Treasury 2-year constant-maturity yield (%)",
    ),
    RateSeries(
        "uk_policy_rate", "UK", "policy_rate", "fred", "IRSTCI01GBM156N",
        "UK overnight interbank rate, monthly average (%)", "monthly",
        note="proxy for BoE Bank Rate (FRED's BOERUKM ends 2017); OECD data, ~3-month lag",
    ),
    RateSeries(
        "uk_2y", "UK", "2y_yield", "boe_yield_curve", "2.0",
        "UK nominal gilt spot yield, 2-year point of the BoE fitted curve (%)",
        note="BoE yield-curve dataset (the IADB API only has 5/10/20-year par yields)",
    ),
    RateSeries(
        "eu_policy_rate", "EU", "policy_rate", "fred", "ECBDFR",
        "ECB deposit facility rate (%)",
    ),
    RateSeries(
        "eu_2y", "EU", "2y_yield", "ecb", "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y",
        "Euro area AAA-rated government 2-year spot yield, ECB Svensson curve (%)",
        note="AAA curve; all-issuer variant is YC/B.U2.EUR.4F.G_N_C.SV_C_YM.SR_2Y",
    ),
    RateSeries(
        "jp_policy_rate", "JP", "policy_rate", "fred", "IRSTCI01JPM156N",
        "Japan overnight call rate, monthly average (%)", "monthly",
        note="proxy for BoJ policy rate (FRED's IRSTCB01JPM156N ends Dec 2023); OECD data, ~3-month lag",
    ),
    RateSeries(
        "jp_2y", "JP", "2y_yield", "mof", "2Y",
        "Japan 2-year JGB yield, Ministry of Finance benchmark (%)",
    ),
)
