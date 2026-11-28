# ECONINTEL Structural Inflation PIT Replay

This is the first **direct retrospective evaluation of the component model** used in
assets/inflation-structural.js. It is distinct from the earlier experimental,
univariate/multivariate ridge-only benchmark.

## What is tested

- **Headline CPI and Core CPI:** same five categories and underlying calculation
  as the structural JS: food, energy, core goods, shelter, core services excluding
  shelter. Headline CPI is a weighted contribution sum; Core CPI is the core
  portion renormalised to exclude food and energy.
- Food, shelter and core goods: average of three latest monthly growth rates.
- Core services excluding shelter: derived from services ex energy minus shelter
  using contemporaneously **available BLS category weights**; averaged over
  three months.
- Energy: as-of-date weekly EIA gasoline prices resampled into monthly means,
  fit to previous CPI energy monthly movements with the **same univariate
  regularization beta = covariance/(variance+10)** as the JS prototype.
- Headline PPI: 50/50 fixed blend of previous PPI monthly momentum and an
  analogous Brent-to-PPI historical regression.
- Headline PCE and Core PCE: same 5-feature ridge structure as the JS prototype,
  using CPI, Core CPI, PPI, prior PCE and prior Core PCE. Any **same-month CPI/PPI
  readings already published at cutoff** are used in the PCE nowcast. This is
  intentionally different from predicting all releases simultaneously on
  November 28, and replicates how the model should operate at each specific
  seven-day-before-release horizon.

## No future information

Every FRED series is requested with ALFRED realtime_start = realtime_end =
release date minus seven full calendar days. Historical output labels use the
earliest matching ALFRED vintage on the release date; source publication could
precede or lag FRED availability. The program skips late initial-vintage cases
instead of silently retroactively including them. Each target month is evaluated
at most once.

To avoid using 2026 CPI weights for 2023 predictions, BLS annual December
CPI-U relative-importance snapshots in research/data/cpi_annual_weights_pit.json
include first official publication dates. At each cutoff the backtester selects
the latest row published on/before that date. Annual weights are **proxies for
the month-specific relative importance**, not a reproduction of BLS's precise
monthly Laspeyres aggregation. The five weights sum exactly to 100%.

The current weight snapshots cover December 2021 through December 2025. Further
2017–2020 weight vintages are required for a complete 2018–2026 historical
backtest. Do not extend the study into those years using later weights.

## Run the Python unit tests

    python -m unittest discover -s tests -p "test_structural_pit.py" -v

Unit tests verify dated weights, no future-target leakage, Core CPI independence
from a gasoline-price shock, inclusion of available CPI and PPI in a later PCE
prediction, and duplicate month exclusion.

## Run historical tests with FRED API access

Store FRED_API_KEY in GitHub Actions secrets or local environment. No API keys
are embedded in source files.

    python research/structural_pit.py --family cpi \
      --start 2023-01-01 --end 2024-12-31 --max-events 16 \
      --horizon 7 --output data/cpi-structural-pit.json

Repeat with --family pce or --family ppi.

Each report includes N, MAE/RMSE, matching-month baseline, direction hit
fraction, rounded-to-0.1 indicator hit rate, detailed per-release forecast and
actual from first ALFRED vintage, date/cutoff/weight vintage, and reasons for
excluded months. The script exits nonzero instead of claiming a successful
backtest if no valid comparison cases were collected.

The GitHub workflow structural-inflation-pit.yml runs the pilot for all three
families and saves downloadable research artifacts; it does not overwrite the
public website or its live inflation dashboard.

## Critical limitations

1. The current model is only a first **research hypothesis**, not a fully
   calibrated, audited forecasting model or source of trading signals.
2. First ALFRED seasonally adjusted index changes need a separate comparison
   to the literal *first published* BLS/BEA news-release figures, as historical
   seasonal revisions and rounding may differ.
3. Annual CPI relative weights do not replace monthly expenditure-component
   weighting. PPI/PCE are **proxies** and are not yet based on official detailed
   PPI/BEA expenditure component weights.
4. The number of usable cases is smaller than the number of scheduled
   announcements, both because of missing periods and because the strict
   same-day ALFRED vintage requirement can exclude legitimate official
   releases.
5. Current parameters (shelter 3-month momentum, regression penalty 10, PPI
   blend 50/50, PCE ridge penalty 16) were fixed by the prototype and are
   NOT fitted to this retrospective sample. If tuned later, evaluate on a
   *fresh holdout interval*.
6. Sources and dates of historical market consensus are not linked yet.
   No claim of outperformance against professional forecasts is warranted.
7. Historical PIB test at seven days before each distinct news release,
   rather than at one shared calendar date, matches the actual information
   traders have ahead of each announcement.
