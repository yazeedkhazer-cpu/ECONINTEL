# ECONINTEL — reverse engineering the official US CPI release BEFORE forecasting

Research-state: **not production-ready, not an exact reproduction of official CPI**. Prepared 2026-11-28.

## Step 1 — Know what BLS actually computes

1. BLS surveys individual item-by-area price quotes, adjusts comparability for quality/missing quotes, and produces *basic item-area index relatives*. Most basic items use a **weighted geometric mean** of price relatives, and selected strata a form of **Laspeyres** relative. Private quote-level observations and complete exact quote weights are not all accessible outside BLS.
2. It aggregates individual **non-overlapping** component indexes using expenditure **cost weights**. The correct published special aggregate example updates each component's base cost weight using its **index ratio from the base month to the comparison month**, adds nominal cost weights, and computes their month-over-month ratio. In notation:

   `CW_{i,t} = CW_{i,b} × I_{i,t}/I_{i,b}`

   `Aggregate_MoM(t) = 100 × (sum(CW_{i,t}) / sum(CW_{i,t-1}) − 1)`

   This is a documented BLS higher-level *cost-weight arithmetic* illustration, **not** an exact calculation of the national release from just five seasonally adjusted categories.
3. **Rent/OER:** BLS surveys six panels and estimates a weighted **six-month price relative** for each, then applies its **sixth root** to the prior index. OER is based on pure rent excluding utilities and uses owner-equivalent weighting; Rent uses economic rent. Unit transitions and missing values introduce imputations. The exact private survey panel cannot be replicated from published macro data.
4. **Headline/Core CPI seasonally adjusted MoM** results are built from component aggregation and BLS seasonal adjustments. BLS explicitly states nationally adjusted CPI is derived from about **81 seasonal components** and that relative-importance and factors can evolve; applying fixed weights to five published SA component MoM values does not replicate the exact news print. YoY should be computed from **NSA** indexes separately.

Official BLS documentation:
- https://www.bls.gov/opub/hom/cpi/calculation.htm
- https://www.bls.gov/cpi/factsheets/constructing-special-cpis.htm
- https://www.bls.gov/cpi/factsheets/owners-equivalent-rent-and-rent.htm
- https://www.bls.gov/cpi/seasonal-adjustment/questions-and-answers.htm
- https://www.bls.gov/cpi/tables/relative-importance/

## Step 2 — Use research-backed mechanisms to forecast those inputs, before the release

| CPI basket mechanism | Early inputs and evidence | Predictive model and measured delay |
| --- | --- | --- |
| Energy and gasoline | Weekly EIA retail gasoline + daily Brent crude (dated ALFRED) | Mixed-frequency time series with real-time data availability; historical passthrough coefficients across multiple regimes |
| Rent and OER | CPI survey six-panel 6-month relative; rental asking prices/new tenant rent lag through continuing tenant renewals | New-tenant/all-tenant gap, estimated state-dependent turnover and pass-through; first-release vintages only |
| Food | PPI food/input prices, agriculture, shipping, restaurant wages | Dedicated basket models. Test food-at-home separately from food away from home |
| Goods and imported products | PPI costs, import prices, USD, freight, inventory and tariff regime | Multilag, interaction, regime-varying cost passthrough; do not feed unreleased current-month CPI back into prediction |
| Services | Labor costs, medical provider contracts, insurance rate filings and air ticket listings | Mechanism-specific lags rather than one uniform service inflation equation |

External research informing the model hypotheses (NOT validation of this ECONINTEL model):
- Cleveland Fed, [Nowcasting Inflation, working paper 2024](https://www.clevelandfed.org/publications/working-paper/2024/wp-2406-nowcasting-inflation): mixed-frequency oil/gas/macro information available before news can help nowcast CPI and PCE; still uncertain.
- Cleveland Fed, [New-Tenant Rent Passthrough and the Future of Rent Inflation](https://www.clevelandfed.org/publications/economic-commentary/2024/ec-202417-new-tenant-rent-passthrough-and-future-of-rent-inflation): new-tenant-to-continuing-tenant rents adjust with mobility and renewal lag; avoid treating quoted new leases as contemporaneous OER.
- SF Fed, [When Is Rent Inflation Coming Down?](https://www.frbsf.org/research-and-insights/publications/economic-letter/2024/09/when-is-shelter-services-inflation-coming-down/): under-construction and completed rental supply relative to household formation as early shelter information.
- BLS [Research Consumer Price Index for New Tenant Rent](https://www.bls.gov/cpi/research-series/r-cpi-ntr.htm): R-CPI-NTR **paused publication in April 2026**; do NOT assume a live monthly feed exists.

Some proposed signals (e.g. Zillow asking rents, transportation fares, insurers' rate filings) have **no confirmed date-preserved source connection** in ECONINTEL and must not be invented in historical replay.

## Step 3 — Research implementation and validation

- **Accounting engine**: `research/bls_cpi_accounting.py`, reproduces BLS beverage materials December 2022 to January 2023 **1.7%** example from official component index and cost weights; offers micro quote formula examples and six-month rent root. It refuses post-cutoff sources and duplicate categories.
- **Input provenance registry**: `research/data/cpi_official_method_and_leading_drivers.json` includes status of each candidate, release-frequency, official measurement stage, evidence, and what data is NOT available.
- **First economic driver prototype**: `research/cpi_macro_dynamic.py` measures whether observed oil, gasoline, USD, weekly claims, PPI and wages can predict headline and core CPI numeric releases **seven calendar days before each event**, using cutoff-specific ALFRED records.
- Evaluate numeric predictions on first-release vintage actual **and manually audit original news print to the nearest 0.1 pp**. Reject claims that the exact official print is reproduced from published 5-basket approximate SA weights.
- Preserve separate historical windows, including untouched post-development time; compare forecast MAE, outlier errors, exact 0.1pp matches, error interval coverage and the contemporaneous Cleveland Fed consensus when an archived forecast date is available.

## Acceptance gates

**Gate A**: arithmetic engine reproduces BLS sample; branch tests pass.

**Gate B**: all price regressors and official rent proxies are actually known by 7-day pre-release cutoff. No future revision or partial-month market mean substitutes are allowed.

**Gate C**: dynamic macro and housing model beats the existing lagged CPI baseline for original Headline and Core CPI releases independently. A model that only improves Rent or fits the training period does not pass.

**Gate D**: forecast can be archived *before* announcement with hashes and unmodified later; published CPI CPI-U SA MoM should be scored exactly at published first-release precision, annual NSA separately.

Never label accuracy as 100% without multiple independent samples. Live `main` must stay unchanged until all gates and user authorization.
