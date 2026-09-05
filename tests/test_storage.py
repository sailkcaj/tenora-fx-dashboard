import pandas as pd

from tenora_fx import storage
from tenora_fx.config import FX_PAIRS, RATE_SERIES


def frame(cols, n=3):
    idx = pd.date_range("2026-09-01", periods=n, freq="D", name="date")
    return pd.DataFrame({c: [float(i) for i in range(n)] for c in cols}, index=idx)


def test_parquet_roundtrip_is_atomic(tmp_path):
    df = frame(["open", "high", "low", "close"])
    path = storage.save_parquet(df, tmp_path / "fx" / "EURUSD.parquet")
    assert path.exists()
    assert not path.with_name(path.name + ".tmp").exists()
    back = storage.load_parquet(path)
    pd.testing.assert_frame_equal(back, df, check_freq=False)
    assert back.index.name == "date"


def test_load_fx_closes_builds_wide_frame_and_skips_missing(tmp_path):
    storage.save_parquet(frame(["open", "high", "low", "close"]), storage.fx_path("EURUSD", tmp_path))
    wide = storage.load_fx_closes(FX_PAIRS[:3], tmp_path)  # only EURUSD exists on disk
    assert list(wide.columns) == ["EURUSD"]
    assert len(wide) == 3


def test_load_rates_builds_wide_frame(tmp_path):
    storage.save_parquet(frame(["value"]), storage.rate_path("us_2y", tmp_path))
    storage.save_parquet(frame(["value"], n=2), storage.rate_path("us_policy_rate", tmp_path))
    wide = storage.load_rates(RATE_SERIES, tmp_path)
    assert set(wide.columns) == {"us_2y", "us_policy_rate"}
    assert len(wide) == 3  # union of dates
    assert wide["us_policy_rate"].isna().sum() == 1


def test_manifest_roundtrip(tmp_path):
    path = tmp_path / "raw" / "manifest.json"
    assert storage.read_manifest(path) is None
    storage.write_manifest({"summary": {"ok": 1}}, path)
    assert storage.read_manifest(path) == {"summary": {"ok": 1}}
