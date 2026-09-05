from datetime import date

import pandas as pd

from tenora_fx import pipeline, storage
from tenora_fx.config import FxPair, RateSeries
from tenora_fx.fred import FredError
from tenora_fx.fx_prices import FxDataError
from tenora_fx.pipeline import (
    FAILED, OK, UNAVAILABLE, PullResult, lookback_window, print_report, pull_fx, pull_rates, run,
    summary_line,
)

START, END = date(2024, 9, 5), date(2026, 9, 5)


def price_frame(n):
    idx = pd.date_range(START, periods=n, freq="B", name="date")
    return pd.DataFrame({"open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05}, index=idx)


def rate_frame(n):
    idx = pd.date_range(START, periods=n, freq="B", name="date")
    return pd.DataFrame({"value": 4.0}, index=idx)


def fx_ok(ticker, start, end):
    return price_frame(500)


def rates_ok(source_id, start, end, session=None):
    return rate_frame(400)


def test_lookback_window():
    assert lookback_window(END, 2) == (START, END)
    assert lookback_window(date(2028, 2, 29), 1) == (date(2027, 2, 28), date(2028, 2, 29))


def test_pull_fx_isolates_failures_and_tries_fallbacks(tmp_path):
    pairs = (
        FxPair("EURUSD", "EURUSD=X"),
        FxPair("USDCNH", "USDCNH=X", fallbacks=("CNH=X",)),
        FxPair("GBPUSD", "GBPUSD=X"),
    )

    def fake_fetch(ticker, start, end):
        if ticker == "USDCNH=X":
            return price_frame(1)  # Yahoo's one-bar answer for a symbol it does not really carry
        if ticker == "CNH=X":
            raise FxDataError("CNH=X: no price data returned")
        if ticker == "GBPUSD=X":
            raise RuntimeError("boom")  # unexpected exception type
        return price_frame(500)

    results = pull_fx(pairs, START, END, fx_dir=tmp_path, fetch=fake_fetch, pause=0)
    by_key = {r.key: r for r in results}
    assert [r.key for r in results] == ["EURUSD", "USDCNH", "GBPUSD"]  # nothing dropped, order kept
    assert by_key["EURUSD"].status == OK
    assert (tmp_path / "EURUSD.parquet").exists()
    assert by_key["USDCNH"].status == FAILED
    assert "insufficient history" in by_key["USDCNH"].error
    assert "CNH=X: no price data" in by_key["USDCNH"].error
    assert not (tmp_path / "USDCNH.parquet").exists()
    assert by_key["GBPUSD"].status == FAILED
    assert "boom" in by_key["GBPUSD"].error


def test_pull_fx_fallback_success_is_noted(tmp_path):
    pairs = (FxPair("USDCNH", "USDCNH=X", fallbacks=("CNY=X",), fallback_note="onshore CNY proxy"),)

    def fake_fetch(ticker, start, end):
        if ticker == "USDCNH=X":
            raise FxDataError("USDCNH=X: no price data returned")
        return price_frame(500)

    (result,) = pull_fx(pairs, START, END, fx_dir=tmp_path, fetch=fake_fetch, pause=0)
    assert result.status == OK
    assert result.source == "yfinance:CNY=X"
    assert result.note == "fetched via fallback CNY=X after USDCNH=X failed; onshore CNY proxy"


def test_pull_rates_dispatches_by_source_and_isolates_failures(tmp_path):
    series = (
        RateSeries("us_2y", "US", "2y_yield", "fred", "DGS2", "US 2y"),
        RateSeries("uk_2y", "UK", "2y_yield", None, None, "UK 2y", note="nobody supplies it yet"),
        RateSeries("jp_policy_rate", "JP", "policy_rate", "fred", "BAD", "JP policy"),
        RateSeries("eu_2y", "EU", "2y_yield", "ecb", "YC/KEY", "EU 2y"),
        RateSeries("jp_2y", "JP", "2y_yield", "martian", "2Y", "JP 2y"),
    )
    seen = []

    def fake_fred(fred_id, start, end, session=None):
        seen.append(("fred", fred_id))
        if fred_id == "BAD":
            raise FredError("BAD: HTTP 404, series not found on FRED")
        return rate_frame(24)

    def fake_ecb(key, start, end, session=None):
        seen.append(("ecb", key))
        return rate_frame(10)

    results = pull_rates(series, START, END, rates_dir=tmp_path, pause=0,
                         fetchers={"fred": fake_fred, "ecb": fake_ecb})
    assert {r.key: r.status for r in results} == {
        "us_2y": OK, "uk_2y": UNAVAILABLE, "jp_policy_rate": FAILED, "eu_2y": OK, "jp_2y": FAILED,
    }
    assert seen == [("fred", "DGS2"), ("fred", "BAD"), ("ecb", "YC/KEY")]
    assert (tmp_path / "us_2y.parquet").exists() and (tmp_path / "eu_2y.parquet").exists()
    assert not (tmp_path / "jp_policy_rate.parquet").exists()
    by_key = {r.key: r for r in results}
    assert by_key["uk_2y"].source == "none"
    assert by_key["uk_2y"].error == "no source configured"
    assert by_key["uk_2y"].note == "nobody supplies it yet"
    assert by_key["eu_2y"].source == "ecb:YC/KEY"
    assert "no fetcher registered for source 'martian'" in by_key["jp_2y"].error


def test_run_writes_manifest_and_report(tmp_path, capsys):
    pairs = (FxPair("EURUSD", "EURUSD=X"),)
    series = (
        RateSeries("us_2y", "US", "2y_yield", "fred", "DGS2", "US 2y"),
        RateSeries("uk_2y", "UK", "2y_yield", None, None, "UK 2y"),
    )
    manifest_path = tmp_path / "manifest.json"
    results = run(
        pairs=pairs, series=series, end=END,
        fx_dir=tmp_path / "fx", rates_dir=tmp_path / "rates", manifest_path=manifest_path,
        fx_fetch=fx_ok, rates_fetchers={"fred": rates_ok}, pause=0,
    )
    manifest = storage.read_manifest(manifest_path)
    assert manifest["summary"] == {"total": 3, "ok": 2, "failed": 0, "unavailable": 1}
    assert manifest["lookback"] == {"years": 2, "start": "2024-09-05", "end": "2026-09-05"}
    assert pipeline.results_from_manifest(manifest) == results

    print_report(results, tail=2)
    out = capsys.readouterr().out
    assert "=== fx/EURUSD  [yfinance:EURUSD=X]  500 rows" in out
    assert "=== rates/uk_2y  [none]  UNAVAILABLE: no source configured" in out
    assert out.count("\n2026-") == 4  # two tail rows for each of the two files
    assert out.strip().splitlines()[-1] == (
        "SUMMARY: 2/3 series ok | FX 1/1 | rates 1/2 | NOT OK: uk_2y [unavailable: no source configured]"
    )


def test_partial_run_keeps_previous_manifest_entries(tmp_path):
    common = dict(
        pairs=(FxPair("EURUSD", "EURUSD=X"),),
        series=(RateSeries("us_2y", "US", "2y_yield", "fred", "DGS2", "US 2y"),),
        end=END, fx_dir=tmp_path / "fx", rates_dir=tmp_path / "rates", manifest_path=tmp_path / "m.json",
        fx_fetch=fx_ok, rates_fetchers={"fred": rates_ok}, pause=0,
    )
    run(**common)
    results = run(skip_fx=True, **common)
    assert {(r.group, r.key) for r in results} == {("fx", "EURUSD"), ("rates", "us_2y")}
    assert storage.read_manifest(tmp_path / "m.json")["summary"]["total"] == 2


def test_summary_line_when_everything_succeeds():
    result = PullResult("fx", "EURUSD", "yfinance:EURUSD=X", OK, rows=5)
    assert summary_line([result]) == "SUMMARY: 1/1 series ok | FX 1/1 | everything succeeded"


def test_main_exit_code_reflects_failures(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "run", lambda **kwargs: [
        PullResult("fx", "EURUSD", "yfinance:EURUSD=X", FAILED, error="boom"),
    ])
    assert pipeline.main([]) == 1
    monkeypatch.setattr(pipeline, "run", lambda **kwargs: [
        PullResult("rates", "uk_2y", "none", UNAVAILABLE, error="no source configured"),
    ])
    assert pipeline.main(["--quiet"]) == 0
