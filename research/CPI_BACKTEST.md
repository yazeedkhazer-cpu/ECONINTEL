# ECONINTEL · CPI Point-in-Time Accuracy Lab

## Scope — version 0.1
This study replays historical CPI announcements and asks what was knowable before release, NOT what revised FRED data say today.

* Calendar: FRED release_id 10, CPI releases. Default history 2018-01-01 through 2026-11-28.
* Cutoff: 7 full calendar days before announcement (configurable).
* Input: ALFRED real-time observations with realtime_start and realtime_end both set to cutoff date. Eight source series are fetched: CPIAUCSL, CPILFESL, PPIFIS, rent CPI, OER, wages, Brent, gasoline.
* Targets: first-available matching ALFRED headline and core monthly CPI changes derived from seasonally adjusted index values within four days of CPI release. This is not yet a verified transcription of the printed BLS release.
* Baseline: average of last three consecutive CPI monthly changes.
* Experimental model: 9-feature ridge regression trained with expanding windows. Every test case is predicted before its outcome enters model training. Features use only vintage data available at cutoff.
* Evaluation: MAE, RMSE in percentage points; one-decimal approximation hit rate; acceleration direction accuracy. Models compared on the identical post-warmup set.
* Missing months and invalid vintages are skipped, documented and never interpolated. The BLS has explicitly confirmed absence of October 2025 headline and core CPI observations after the government shutdown.

## Status and limitations
This is a working *test harness*, not a proof of CPI forecasting skill. The initial results JSON intentionally says not_run. No verified backtest performance is available until a historical API replay completes.

The ridge model is a prototype and DOES NOT implement the seven-axis ECONINTEL judgment rules, an expenditure-weighted CPI component forecast, or comparison with as-of-dated economist consensus/Cleveland Fed nowcasts. First ALFRED index values may round differently from BLS printed one-decimal MoM; an archive-based reconciliation is necessary. Date-only ALFRED cannot prove intra-day availability. Do not claim predictive superiority without paired out-of-sample evidence.

## How to run offline tests

    python -m py_compile research/cpi_backtest.py tests/test_cpi_backtest.py
    python -m unittest discover -s tests -p "test_cpi_backtest.py" -v

## How to run a real replay

Set environment variable FRED_API_KEY locally or as GitHub Actions secret; do not write its value to a frontend file, GitHub commit, URL shown to users, or artifact.

    python research/cpi_backtest.py --start 2018-01-01 --end 2026-11-28 --horizon 7 --min-train 18 --output data/cpi-backtest-results.json

The engine caches non-secret FRED responses under .cache/econintel-alfred. It intentionally stops on API failures and does not silently substitute revised data.

The GitHub Actions workflow tests code on push/PR. Historical replay is manually triggered after the workflow is present on the default branch and uploads its JSON as an artifact, without updating the live dashboard automatically. Review vintage and exclusion details before publishing.

## Next scientific steps
1. Verify each target against first published BLS CPI news-release MoM and YoY.
2. Build a model of CPI expenditure categories using contemporaneous BLS weights.
3. Acquire point-in-time Cleveland Fed nowcasts and contemporaneous consensus benchmarks.
4. Replay 30-day, 7-day and 1-day prediction horizons separately.
5. Archive the first November 2026 CPI forecast BEFORE December 10, 2026, 08:30 New York / 16:30 Amman.
6. Keep immutable timestamps and compare all models on the same post-warmup months.

References:
- https://fred.stlouisfed.org/docs/api/fred/realtime_period.html
- https://fred.stlouisfed.org/docs/api/fred/series_observations.html
- https://fred.stlouisfed.org/docs/api/fred/release_dates.html
- https://www.bls.gov/bls/news-release/cpi.htm
- https://www.bls.gov/bls/2025-lapse-revised-release-dates.htm
