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

LOOKBACK_YEARS = 2

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


@dataclass(frozen=True)
class FxPair:
    """A currency pair and the Yahoo Finance symbol(s) used to fetch it."""

    name: str  # "EURUSD" -- also the parquet file stem
    ticker: str  # primary Yahoo symbol, e.g. "EURUSD=X"
    fallbacks: tuple[str, ...] = ()  # alternative symbols tried if the primary fails

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
    FxPair("USDCNH", "USDCNH=X"),
)


@dataclass(frozen=True)
class RateSeries:
    """One interest-rate series. ``fred_id=None`` means FRED has no usable series for it."""

    key: str  # parquet file stem / column name, e.g. "us_2y"
    region: str  # "US" | "UK" | "EU" | "JP"
    kind: str  # "policy_rate" | "2y_yield"
    fred_id: str | None
    description: str
    frequency: str = "daily"  # "daily" | "monthly"
    note: str = ""  # caveats surfaced in the report (proxy series, lag, alternative sources)

    @property
    def available(self) -> bool:
        return self.fred_id is not None


RATE_SERIES: tuple[RateSeries, ...] = (
    RateSeries(
        "us_policy_rate", "US", "policy_rate", "DFEDTARU",
        "Fed funds target range, upper limit (%)",
    ),
    RateSeries(
        "us_2y", "US", "2y_yield", "DGS2",
        "US Treasury 2-year constant-maturity yield (%)",
    ),
    RateSeries(
        "uk_policy_rate", "UK", "policy_rate", "IRSTCI01GBM156N",
        "UK overnight interbank rate, monthly average (%)", "monthly",
        note="proxy for BoE Bank Rate (FRED's BOERUKM ends 2017); OECD data, ~3-month lag",
    ),
    RateSeries(
        "uk_2y", "UK", "2y_yield", None,
        "UK 2-year gilt yield (%)",
        note="candidate source: Bank of England IADB yield curves",
    ),
    RateSeries(
        "eu_policy_rate", "EU", "policy_rate", "ECBDFR",
        "ECB deposit facility rate (%)",
    ),
    RateSeries(
        "eu_2y", "EU", "2y_yield", None,
        "Euro area 2-year government yield (%)",
        note="candidate source: ECB Data Portal yield-curve dataset (YC, AAA 2-year spot)",
    ),
    RateSeries(
        "jp_policy_rate", "JP", "policy_rate", "IRSTCI01JPM156N",
        "Japan overnight call rate, monthly average (%)", "monthly",
        note="proxy for BoJ policy rate (FRED's IRSTCB01JPM156N ends Dec 2023); OECD data, ~3-month lag",
    ),
    RateSeries(
        "jp_2y", "JP", "2y_yield", None,
        "Japan 2-year JGB yield (%)",
        note="candidate source: Japan MoF JGB interest-rate CSV",
    ),
)
