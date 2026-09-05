# Tenora FX Risk Dashboard

FX macro / geopolitical risk dashboard for **Tenora**, an FX hedging company. Python project: a data
pipeline pulls daily FX spot prices (Yahoo Finance via yfinance) and policy rates / 2-year yields
(FRED) into local parquet files; a Streamlit app sits on top of that store.

## Milestones
- **M1 - foundation + data pipeline (Sep 2026):** project skeleton, venv, FX + rates pull with
  per-series failure handling, parquet storage, pull manifest, unit tests, dashboard stub.
- **Next (not started - agree scope with the user first):** derived risk metrics (returns, realised
  vol, rate differentials / carry), dashboard pages, geopolitical / event overlays, and non-FRED
  sources for the yields FRED does not carry (see "Rates" below).

## Tech stack
- Python 3.13 in `.venv` (`python3 -m venv .venv`, Anaconda python3 on this Mac).
- pandas 3.x + pyarrow (parquet), yfinance 1.x, requests, python-dotenv, streamlit, pytest.
- Versions are pinned in `requirements.txt`. `pyproject.toml` reads that same file, and
  `pip install -e .` installs `tenora_fx` (under `src/`) as an editable package.

## Layout
```
data/raw/fx/<PAIR>.parquet     daily OHLC per pair                          (gitignored)
data/raw/rates/<key>.parquet   one FRED series per file                     (gitignored)
data/raw/manifest.json         last pull: status / rows / range / errors    (gitignored)
data/processed/                derived datasets, later milestones
src/tenora_fx/config.py        registry: pairs, FRED series, paths, lookback
src/tenora_fx/fred.py          fredgraph.csv fetcher + parser (no API key)
src/tenora_fx/fx_prices.py     yfinance fetcher + normaliser
src/tenora_fx/storage.py       parquet read/write, wide loaders, manifest
src/tenora_fx/pipeline.py      orchestration, report, CLI
dashboard/app.py               Streamlit app (M1: wiring check, tables only)
tests/                         pytest, no network (fetchers injected / monkeypatched)
```

## Commands
```
source .venv/bin/activate
python -m tenora_fx.pipeline                # full 2-year pull, then last 5 rows per file + summary line
python -m tenora_fx.pipeline --report-only  # re-print the report from what is on disk
python -m tenora_fx.pipeline --skip-fx      # rates only (also --skip-rates, --tail N, --years N)
pytest                                      # unit tests, no network
streamlit run dashboard/app.py
```

## Currency pairs (Yahoo Finance, daily bars, 2-year lookback)
EURUSD=X, GBPUSD=X, USDJPY=X, USDCHF=X, AUDUSD=X, USDCAD=X, NZDUSD=X, USDZAR=X, USDBRL=X, USDCNH=X.
Files are named by pair (`EURUSD.parquet`). Yahoo stamps bars in Europe/London time; the pipeline
keeps the wall-clock date and drops the timezone. Yahoo sometimes emits a partial Saturday bar for
the Friday NY session; it is stored as-is. USDCNH=X has patchy history on Yahoo (CNY=X, onshore
yuan, is the fallback if CNH becomes unusable).

## Rates (FRED public `fredgraph.csv` endpoint, no API key)
| key | FRED id | series | freq |
|---|---|---|---|
| us_policy_rate | DFEDTARU | Fed funds target range, upper limit | daily |
| us_2y | DGS2 | US Treasury 2-year constant maturity yield | daily |
| eu_policy_rate | ECBDFR | ECB deposit facility rate | daily |
| uk_policy_rate | IRSTCI01GBM156N | UK overnight interbank rate, monthly avg - **proxy** for Bank Rate (OECD, ~3-month lag) | monthly |
| jp_policy_rate | IRSTCI01JPM156N | Japan overnight call rate, monthly avg - **proxy** for BoJ rate (OECD, ~3-month lag) | monthly |
| uk_2y, eu_2y, jp_2y | none | **not on FRED**; the pipeline reports them as `unavailable` | - |

Why the gaps (verified Sep 2026): FRED's BoE Bank Rate series (BOERUKM) stops in 2017, its BoJ
policy-rate series (IRSTCB01JPM156N) stops in Dec 2023, and the OECD central-bank-rate ids for the
UK / euro area (IRSTCB01GBM156N, IRSTCB01EZM156N) return 404. FRED has no 2-year government yields
for the UK, euro area or Japan (only OECD 10-year monthly: IRLTLT01GBM156N, IRLTLT01EZM156N,
IRLTLT01JPM156N). Candidate sources for a later milestone: ECB Data Portal yield-curve dataset
(YC, AAA 2-year spot), Bank of England IADB yield curves, Japan MoF JGB interest-rate CSV.
Other useful FRED ids: DFF (effective fed funds), ECBMRRFR (ECB main refinancing rate).

FRED quirks the parser handles: missing values are `.`; the date column is `observation_date`
(older payloads: `DATE`); unknown ids return HTTP 404 with an HTML body; `cosd=YYYY-MM-DD` limits
the start date.

## Conventions
- Every parquet file has a tz-naive `DatetimeIndex` named `date`. FX files: `open, high, low, close`
  (float64). Rate files: a single `value` column, in percent.
- Fetchers raise per series (`FredError`, `FxDataError`). `pipeline.pull_fx` / `pull_rates` catch
  per item and return `PullResult`s, so one bad ticker never aborts the run. Statuses: `ok`,
  `failed` (transient / unexpected), `unavailable` (known gap, `fred_id=None`).
- Pipeline exit code is 1 if any series `failed`, else 0 (`unavailable` does not fail the run).
- Data files are gitignored; regenerate with the pipeline. `.env` is optional (see `.env.example`).
