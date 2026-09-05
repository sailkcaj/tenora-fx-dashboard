"""Parquet storage helpers and the pull manifest."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import pandas as pd

from . import config
from .config import FxPair, RateSeries


def fx_path(pair_name: str, fx_dir: Path | None = None) -> Path:
    return Path(fx_dir or config.FX_DIR) / f"{pair_name}.parquet"


def rate_path(key: str, rates_dir: Path | None = None) -> Path:
    return Path(rates_dir or config.RATES_DIR) / f"{key}.parquet"


def save_parquet(df: pd.DataFrame, path: Path) -> Path:
    """Write ``df`` atomically (temp file + rename) so a crash never leaves a half-written file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    df.to_parquet(tmp, engine="pyarrow", index=True)
    tmp.replace(path)
    return path


def load_parquet(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path, engine="pyarrow")
    df.index = pd.DatetimeIndex(df.index, name="date")
    return df


def load_fx_closes(pairs: Iterable[FxPair] = config.FX_PAIRS, fx_dir: Path | None = None) -> pd.DataFrame:
    """Wide frame of close prices, one column per pair. Pairs without a file are skipped."""
    cols = {}
    for pair in pairs:
        path = fx_path(pair.name, fx_dir)
        if path.exists():
            cols[pair.name] = load_parquet(path)["close"]
    return pd.DataFrame(cols).sort_index()


def load_rates(series: Iterable[RateSeries] = config.RATE_SERIES, rates_dir: Path | None = None) -> pd.DataFrame:
    """Wide frame of rate series (percent), one column per key. Series without a file are skipped."""
    cols = {}
    for s in series:
        path = rate_path(s.key, rates_dir)
        if path.exists():
            cols[s.key] = load_parquet(path)["value"]
    return pd.DataFrame(cols).sort_index()


def write_manifest(payload: dict, path: Path | None = None) -> Path:
    path = Path(path or config.MANIFEST_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    tmp.replace(path)
    return path


def read_manifest(path: Path | None = None) -> dict | None:
    path = Path(path or config.MANIFEST_PATH)
    if not path.exists():
        return None
    return json.loads(path.read_text())
