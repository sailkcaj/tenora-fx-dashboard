# Tenora FX Risk Dashboard

FX macro / geopolitical risk dashboard for **Tenora**, an FX hedging company. Python project: a data
pipeline pulls daily FX spot prices (Yahoo Finance via yfinance) and policy rates / 2-year yields
(FRED, ECB, Bank of England, Japan MoF) into local parquet files; a Streamlit app sits on top.

## Milestones
- **M1 - foundation + data pipeline (done, Sep 2026):** project skeleton, venv, FX + rates pull
  with per-series failure handling, parquet storage, pull manifest, unit tests, dashboard stub.
  Verified pull on 2026-09-05: **18/18 series ok** (after adding the ECB / BoE / MoF sources and
  the CNY fallback for USDCNH, see "Approximations" below).
- **Next (not started - agree scope with the user first):** derived risk metrics (returns, realised
  vol, rate differentials / carry), dashboard pages, geopolitical / event overlays.

## Tech stack
- Python 3.13 in `.venv` (`python3 -m venv .venv`, Anaconda python3 on this Mac).
- pandas 3.x + pyarrow (parquet), openpyxl (BoE Excel workbooks), yfinance 1.x, requests,
  python-dotenv, streamlit, pytest.
- Versions are pinned in `requirements.txt`. `pyproject.toml` reads that same file, and
  `pip install -e .` installs `tenora_fx` (under `src/`) as an editable package.

## Layout
```
data/raw/fx/<PAIR>.parquet     daily OHLC per pair                          (gitignored)
data/raw/rates/<key>.parquet   one rate series per file                     (gitignored)
data/raw/manifest.json         last pull: status / rows / range / errors    (gitignored)
data/raw/cache/boe/            BoE archive zip + parsed series, reused across runs (gitignored)
data/processed/                derived datasets, later milestones
src/tenora_fx/config.py        registry: pairs, rate series (source + id), paths, lookback
src/tenora_fx/sources.py       maps a series' `source` name to its fetcher
src/tenora_fx/fred.py          FRED fredgraph.csv fetcher + parser
src/tenora_fx/ecb.py           ECB Data Portal SDMX/CSV fetcher
src/tenora_fx/boe.py           BoE yield-curve workbooks fetcher (zip + Excel, cached)
src/tenora_fx/mof.py           Japan MoF JGB yield CSV fetcher
src/tenora_fx/httpclient.py    shared GET with retries / User-Agent
src/tenora_fx/fx_prices.py     yfinance fetcher + normaliser
src/tenora_fx/storage.py       parquet read/write, wide loaders, manifest
src/tenora_fx/pipeline.py      orchestration, report, CLI
dashboard/app.py               Streamlit app (M1: wiring check, tables only, no charts yet)
tests/                         pytest, no network (fake sessions in tests/fakes.py);
                               test_dashboard.py runs the Streamlit script headlessly via AppTest
```

## Commands
```
source .venv/bin/activate
python -m tenora_fx.pipeline                # full 2-year pull, then last 5 rows per file + summary line
python -m tenora_fx.pipeline --report-only  # re-print the report from what is on disk
python -m tenora_fx.pipeline --skip-fx      # rates only (also --skip-rates, --tail N, --years N, -q)
pytest                                      # unit tests, no network
streamlit run dashboard/app.py
```

## Currency pairs (Yahoo Finance, daily bars, 2-year lookback)
EURUSD=X, GBPUSD=X, USDJPY=X, USDCHF=X, AUDUSD=X, USDCAD=X, NZDUSD=X, USDZAR=X, USDBRL=X, USDCNH=X
(with CNY=X as fallback, see "Approximations"). Files are named by pair (`EURUSD.parquet`). Yahoo
stamps bars in Europe/London time; the pipeline keeps the wall-clock date and drops the timezone.
Yahoo sometimes emits a flat Saturday bar (open = high = low = close) for the Friday NY session;
it is stored as-is, so filter weekends in the processing layer, not in the raw store.

## Rate series (all free, no API key)
| key | source | source_id | series | freq |
|---|---|---|---|---|
| us_policy_rate | fred | DFEDTARU | Fed funds target range, upper limit | daily |
| us_2y | fred | DGS2 | US Treasury 2-year constant-maturity (par) yield | daily |
| eu_policy_rate | fred | ECBDFR | ECB deposit facility rate | daily |
| eu_2y | ecb | YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y | euro area AAA government 2-year spot yield, ECB Svensson curve | daily |
| uk_policy_rate | fred | IRSTCI01GBM156N | UK overnight interbank rate, monthly avg - **proxy** for Bank Rate (OECD, ~3-month lag) | monthly |
| uk_2y | boe_yield_curve | 2.0 | UK nominal gilt 2-year spot yield, BoE fitted curve | daily |
| jp_policy_rate | fred | IRSTCI01JPM156N | Japan overnight call rate, monthly avg - **proxy** for BoJ rate (OECD, ~3-month lag) | monthly |
| jp_2y | mof | 2Y | 2-year JGB benchmark yield, Ministry of Finance | daily |

The four 2-year series are not methodologically identical (US = par yield, UK/EU = zero-coupon
spot from fitted curves, JP = benchmark compound yield). Fine for differentials and direction;
say so if precision matters.

### Source notes
- **FRED** (`fredgraph.csv?id=...&cosd=YYYY-MM-DD`): missing values are `.`; the date column is
  `observation_date` (older payloads: `DATE`); unknown ids return HTTP 404 with an HTML body;
  discontinued series return 200 with no rows inside the window (treated as failed). Other useful
  ids: DFF (effective fed funds), ECBMRRFR (ECB main refinancing rate).
- **ECB Data Portal** (`data-api.ecb.europa.eu/service/data/<flow>/<key>?format=csvdata&startPeriod=&endPeriod=`):
  one row per observation, `TIME_PERIOD` / `OBS_VALUE` columns; HTTP 404 for an unknown key or an
  empty window. All-issuer variant of the 2-year: `YC/B.U2.EUR.4F.G_N_C.SV_C_YM.SR_2Y`.
- **Bank of England**: the IADB CSV API (`boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes&
  SeriesCodes=...&CSVF=TN&UsingCodes=Y&Datefrom=DD/Mon/YYYY&Dateto=now`) only has daily par yields
  at 5/10/20 years (IUDSNPY / IUDMNPY / IUDLNPY) plus the Official Bank Rate (IUDBEDR, daily),
  so the 2-year comes from the yield-curve dataset (`/-/media/boe/files/statistics/yield-curves/`):
  `latest-yield-curve-data.zip` (current month, refreshed daily, ~200 KB) and `glcnominalddata.zip`
  (full history, ~39 MB). Sheet `4. spot curve` of each `GLC Nominal daily data*.xlsx` has a
  `years:` header row and one row per date. The archive is cached in `data/raw/cache/boe/` with
  its Last-Modified / ETag and re-requested (conditional GET) only when the cached, accumulated
  series has a gap or does not reach the window start. First run costs the 39 MB download.
- **Japan MoF** (`mof.go.jp/english/policy/jgbs/reference/interest_rate/`): `historical/jgbcme_all.csv`
  (full history, updated monthly) + `jgbcme.csv` (current month, daily); cp932-encoded, title row,
  `Date,1Y,2Y,...,40Y` header, `-` for missing, trailing free-text note row. Current-month file is
  best effort (missing at the start of a month); the history file is required.

## Approximations and known caveats (verified 2026-09-05)
- **USDCNH uses onshore CNY (CNY=X) as a proxy.** Every CNH symbol on Yahoo (USDCNH=X, CNH=X,
  CNHUSD=X) returns only the current bar, so the pipeline's minimum-history check rejects it and
  falls back to CNY=X. The manifest / report note records the fallback on every run. Onshore and
  offshore yuan usually track within a few tenths of a percent but can diverge under stress.
- **UK and Japan policy rates are OECD monthly overnight-rate proxies** (FRED has no live BoE Bank
  Rate or BoJ policy-rate series: BOERUKM stops 2017, IRSTCB01JPM156N stops Dec 2023). A daily
  Bank Rate is available from the BoE IADB API (IUDBEDR) if the proxy ever matters.
- **jp_2y is real data, not a proxy** (MoF benchmark yields), as are uk_2y and eu_2y.

## Conventions
- Every parquet file has a tz-naive `DatetimeIndex` named `date`. FX files: `open, high, low, close`
  (float64). Rate files: a single `value` column, in percent.
- Rate fetchers share one signature, `fetch(source_id, start, end, *, session=None) -> DataFrame`,
  and are registered in `sources.FETCHERS` under the `source` name used in `config.RATE_SERIES`.
- Fetchers raise per series (`FredError`, `EcbError`, `BoeError`, `MofError`, `FxDataError`).
  `pipeline.pull_fx` / `pull_rates` catch per item and return `PullResult`s, so one bad series never
  aborts the run. Statuses: `ok`, `failed` (transient / unexpected / insufficient history),
  `unavailable` (registry entry with `source=None`).
- FX minimum-history check: a ticker must return at least 50% of the expected business days
  (`min_history` in `pull_fx`); `FxPair.fallbacks` lists alternative Yahoo symbols tried in order and
  `FxPair.fallback_note` is recorded whenever one is used.
- Pipeline exit code is 1 if any series `failed`, else 0 (`unavailable` does not fail the run).
- Partial runs (`--skip-fx` / `--skip-rates`) keep the untouched group's manifest entries.
- Data files and the BoE cache are gitignored; regenerate with the pipeline. `.env` is optional
  (see `.env.example`).
