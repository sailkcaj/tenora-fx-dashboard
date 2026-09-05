"""End-to-end data pull: FX spot (Yahoo Finance) and rates (FRED, ECB, BoE, MoF) into parquet.

    python -m tenora_fx.pipeline                # full pull, then a report
    python -m tenora_fx.pipeline --report-only  # report on what is already on disk

A failure in any single series is recorded in its ``PullResult`` and never aborts the run.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Mapping

import pandas as pd
import requests

from . import config, storage
from .config import FX_PAIRS, LOOKBACK_YEARS, RATE_SERIES, FxPair, RateSeries
from .fx_prices import FxDataError, fetch_pair
from .sources import FETCHERS

log = logging.getLogger(__name__)

OK = "ok"
FAILED = "failed"
UNAVAILABLE = "unavailable"


@dataclass
class PullResult:
    """Outcome of pulling one series. Serialised into ``data/raw/manifest.json``."""

    group: str  # "fx" | "rates"
    key: str  # "EURUSD" | "us_2y"
    source: str  # "yfinance:EURUSD=X" | "fred:DGS2" | "ecb:YC/..." | "none"
    status: str  # OK | FAILED | UNAVAILABLE
    rows: int = 0
    first: str | None = None  # first observation date, YYYY-MM-DD
    last: str | None = None  # last observation date, YYYY-MM-DD
    path: str | None = None  # parquet file written (None unless status is OK)
    error: str | None = None
    note: str = ""  # caveats worth surfacing: proxy series, fallback ticker, lag
    pulled_at: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == OK


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ymd(ts) -> str:
    return pd.Timestamp(ts).strftime("%Y-%m-%d")


def _ok_result(group: str, key: str, source: str, df: pd.DataFrame, path: Path, note: str = "") -> PullResult:
    return PullResult(
        group, key, source, OK,
        rows=len(df), first=_ymd(df.index[0]), last=_ymd(df.index[-1]),
        path=str(path), note=note, pulled_at=_now(),
    )


def lookback_window(end: date | None = None, years: int = LOOKBACK_YEARS) -> tuple[date, date]:
    end = end or date.today()
    start = (pd.Timestamp(end) - pd.DateOffset(years=years)).date()
    return start, end


def expected_business_days(start: date, end: date) -> int:
    return int(((end - start).days + 1) * 5 / 7)


# --- FX ---------------------------------------------------------------------------------------

def pull_fx(
    pairs: Iterable[FxPair] = FX_PAIRS,
    start: date | None = None,
    end: date | None = None,
    *,
    fx_dir: Path | None = None,
    fetch: Callable[[str, date, date], pd.DataFrame] = fetch_pair,
    min_history: float = 0.5,
    pause: float = 0.5,
) -> list[PullResult]:
    """Fetch every pair into its own parquet file. A pair fails only after all its tickers fail.

    ``min_history`` is the fraction of expected business days a ticker must return; Yahoo
    sometimes answers with a single bar for a symbol it does not really carry.
    """
    if start is None or end is None:
        start, end = lookback_window(end)
    min_rows = max(1, int(expected_business_days(start, end) * min_history))

    results: list[PullResult] = []
    for pair in pairs:
        errors: list[str] = []
        result: PullResult | None = None
        for ticker in pair.tickers:
            try:
                df = fetch(ticker, start, end)
                if len(df) < min_rows:
                    raise FxDataError(f"{ticker}: insufficient history ({len(df)} rows, need >= {min_rows})")
                path = storage.save_parquet(df, storage.fx_path(pair.name, fx_dir))
                note = ""
                if ticker != pair.ticker:
                    note = f"fetched via fallback {ticker} after {pair.ticker} failed"
                    if pair.fallback_note:
                        note += f"; {pair.fallback_note}"
                result = _ok_result("fx", pair.name, f"yfinance:{ticker}", df, path, note)
                log.info("fx %-7s %4d rows  %s -> %s  (%s)", pair.name, len(df), result.first, result.last, ticker)
                break
            except Exception as exc:  # one bad ticker must not sink the run
                errors.append(str(exc))
                log.warning("fx %s via %s failed: %s", pair.name, ticker, exc)
            finally:
                if pause:
                    time.sleep(pause)
        if result is None:
            result = PullResult("fx", pair.name, f"yfinance:{pair.ticker}", FAILED,
                                error="; ".join(errors), pulled_at=_now())
        results.append(result)
    return results


# --- Rates ------------------------------------------------------------------------------------

def pull_rates(
    series: Iterable[RateSeries] = RATE_SERIES,
    start: date | None = None,
    end: date | None = None,
    *,
    rates_dir: Path | None = None,
    fetchers: Mapping[str, Callable[..., pd.DataFrame]] | None = None,
    pause: float = 0.5,
) -> list[PullResult]:
    """Fetch every rate series into its own parquet file, dispatching on ``RateSeries.source``.

    Series with no source are reported as unavailable; a source with no registered fetcher, or
    any exception from a fetcher, is recorded as a failure for that series only.
    """
    if start is None or end is None:
        start, end = lookback_window(end)
    fetchers = FETCHERS if fetchers is None else fetchers
    session = requests.Session()

    results: list[PullResult] = []
    for s in series:
        if not s.available:
            results.append(PullResult("rates", s.key, "none", UNAVAILABLE,
                                      error="no source configured", note=s.note, pulled_at=_now()))
            log.info("rates %-15s unavailable (%s)", s.key, s.note)
            continue
        source = f"{s.source}:{s.source_id}"
        fetch = fetchers.get(s.source)
        if fetch is None:
            results.append(PullResult("rates", s.key, source, FAILED, note=s.note, pulled_at=_now(),
                                      error=f"no fetcher registered for source {s.source!r}"))
            log.warning("rates %s failed: no fetcher for source %r", s.key, s.source)
            continue
        try:
            df = fetch(s.source_id, start, end, session=session)
            path = storage.save_parquet(df, storage.rate_path(s.key, rates_dir))
            result = _ok_result("rates", s.key, source, df, path, note=s.note)
            log.info("rates %-15s %4d rows  %s -> %s  (%s)", s.key, len(df), result.first, result.last, source)
        except Exception as exc:  # one bad series must not sink the run
            result = PullResult("rates", s.key, source, FAILED, error=str(exc), note=s.note, pulled_at=_now())
            log.warning("rates %s failed: %s", s.key, exc)
        results.append(result)
        if pause:
            time.sleep(pause)
    return results


# --- Orchestration ----------------------------------------------------------------------------

def build_manifest(results: list[PullResult], start: date, end: date, years: int) -> dict:
    return {
        "generated_at": _now(),
        "lookback": {"years": years, "start": start.isoformat(), "end": end.isoformat()},
        "summary": {
            "total": len(results),
            "ok": sum(r.status == OK for r in results),
            "failed": sum(r.status == FAILED for r in results),
            "unavailable": sum(r.status == UNAVAILABLE for r in results),
        },
        "results": [asdict(r) for r in results],
    }


def results_from_manifest(manifest: dict) -> list[PullResult]:
    return [PullResult(**entry) for entry in manifest.get("results", [])]


def run(
    *,
    pairs: Iterable[FxPair] = FX_PAIRS,
    series: Iterable[RateSeries] = RATE_SERIES,
    years: int = LOOKBACK_YEARS,
    end: date | None = None,
    skip_fx: bool = False,
    skip_rates: bool = False,
    fx_dir: Path | None = None,
    rates_dir: Path | None = None,
    manifest_path: Path | None = None,
    fx_fetch: Callable[[str, date, date], pd.DataFrame] = fetch_pair,
    rates_fetchers: Mapping[str, Callable[..., pd.DataFrame]] | None = None,
    pause: float = 0.5,
) -> list[PullResult]:
    """Pull everything, write the manifest, and return one ``PullResult`` per series.

    A partial run (``skip_fx`` / ``skip_rates``) keeps the previous manifest entries for the
    groups it did not touch, so the manifest always describes the whole store.
    """
    start, end = lookback_window(end, years)
    log.info("pulling %d years: %s -> %s", years, start, end)

    results: list[PullResult] = []
    if not skip_fx:
        results += pull_fx(pairs, start, end, fx_dir=fx_dir, fetch=fx_fetch, pause=pause)
    if not skip_rates:
        results += pull_rates(series, start, end, rates_dir=rates_dir, fetchers=rates_fetchers, pause=pause)

    previous = storage.read_manifest(manifest_path)
    if previous and (skip_fx or skip_rates):
        touched = {(r.group, r.key) for r in results}
        results += [r for r in results_from_manifest(previous) if (r.group, r.key) not in touched]

    storage.write_manifest(build_manifest(results, start, end, years), manifest_path)
    return results


# --- Reporting --------------------------------------------------------------------------------

def summary_line(results: list[PullResult]) -> str:
    """One line: how many series succeeded, per group, and which did not with the reason."""
    fx = [r for r in results if r.group == "fx"]
    rates = [r for r in results if r.group == "rates"]
    parts = [f"{sum(r.ok for r in results)}/{len(results)} series ok"]
    if fx:
        parts.append(f"FX {sum(r.ok for r in fx)}/{len(fx)}")
    if rates:
        parts.append(f"rates {sum(r.ok for r in rates)}/{len(rates)}")
    problems = [r for r in results if not r.ok]
    if problems:
        parts.append("NOT OK: " + ", ".join(f"{r.key} [{r.status}: {r.error}]" for r in problems))
    else:
        parts.append("everything succeeded")
    return "SUMMARY: " + " | ".join(parts)


def _display_path(path: str) -> str:
    try:
        return str(Path(path).relative_to(config.PROJECT_ROOT))
    except ValueError:
        return path


def print_report(results: list[PullResult], tail: int = 5, out=None) -> None:
    """Print the last ``tail`` rows of every file, then the one-line summary."""
    out = out or sys.stdout
    for r in results:
        head = f"=== {r.group}/{r.key}  [{r.source}]"
        if r.ok and r.path and Path(r.path).exists():
            df = storage.load_parquet(Path(r.path))
            print(f"\n{head}  {r.rows} rows, {r.first} -> {r.last}  ({_display_path(r.path)}) ===", file=out)
            if r.note:
                print(f"    note: {r.note}", file=out)
            print(df.tail(tail).to_string(), file=out)
        elif r.ok:
            print(f"\n{head}  file missing on disk: {r.path} ===", file=out)
        else:
            print(f"\n{head}  {r.status.upper()}: {r.error} ===", file=out)
            if r.note:
                print(f"    note: {r.note}", file=out)
    print("\n" + summary_line(results), file=out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tenora_fx.pipeline",
        description="Pull FX spot prices and interest-rate series into local parquet files and report on them.",
    )
    parser.add_argument("--report-only", action="store_true", help="skip fetching; report on the last pull")
    parser.add_argument("--skip-fx", action="store_true", help="do not pull FX prices")
    parser.add_argument("--skip-rates", action="store_true", help="do not pull rate series")
    parser.add_argument("--years", type=int, default=LOOKBACK_YEARS, help="lookback window (default %(default)s)")
    parser.add_argument("--tail", type=int, default=5, help="rows to print per file (default %(default)s)")
    parser.add_argument("-q", "--quiet", action="store_true", help="log warnings only")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("yfinance").setLevel(logging.ERROR)

    if args.report_only:
        manifest = storage.read_manifest()
        if manifest is None:
            print("No manifest found; run the pipeline without --report-only first.", file=sys.stderr)
            return 2
        results = results_from_manifest(manifest)
    else:
        results = run(years=args.years, skip_fx=args.skip_fx, skip_rates=args.skip_rates)

    print_report(results, tail=args.tail)
    return 1 if any(r.status == FAILED for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
