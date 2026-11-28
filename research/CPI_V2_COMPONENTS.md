# ECONINTEL CPI and Core CPI component model V2

Research status: experimental; not calibrated or validated as a whole. November 28, 2026.

## Objective
Independently nowcast CPI and Core CPI month-on-month before the BLS release; show each category contribution, compare against the date-stamped market consensus, and score the forecast against first-release outcomes.

## Actual changes
- scripts/update_inflation.py: added eight detailed BLS CPI series for lodging, apparel, new vehicles, used cars, medical services, transportation services, auto insurance, and airfares.
- Motor-vehicle insurance series CUSR0000SETE is collected directly from the BLS public API when FRED fails to provide it, with fail-closed parsing.
- 50/50 official inflation sources connected in the feature-branch data snapshot on Nov 28, 2026. Production main still has 42.
- assets/cpi-components-v2.js: independent nested CPI forecast contributions for shelter rent/OER, goods vehicles/apparel, medical services, transport services, motor insurance, and airfare; residual weights avoid double counting.
- inflation-nowcast.html: separate V2 detail panel, preserving the existing V1 estimates. No V2 full CPI accuracy claim.
- tests/test_cpi_components_v2.js and tests/test_inflation_bls_components.py verify calculations, data isolation and missing-data behavior.
- research/snapshots/2026-11-28_CPI_V2_experimental_component_decomposition.json: first timestamped real-data component forecast and full limitations.

## Official weighting reference and nested categories
BLS CPI-U September 2026 relative importance, published with October 2026 CPI news release: https://www.bls.gov/news.release/archives/cpi_11102026.htm

| CPI category | Weight in headline CPI basket |
| --- | ---: |
| Food | 13.447% |
| Energy | 7.649% |
| Core goods | 18.807% |
| Shelter | 35.238% |
| Core services other than shelter | 24.860% |

BLS published rounding makes these add to 100.001%; normalize contributions. Shelter contains rent (7.707%) and OER (25.853%), with remaining shelter 1.678%. Core goods contain apparel (2.489%), new vehicles (3.729%) and used cars (2.670%). Core services outside shelter contain medical care services (6.813%) and transport services (6.256%); the latter includes auto insurance (2.510%) and airfares (1.055%). Do not double count nested groups.

## Current experimental November 2026 readings
Headline CPI +0.0143% MoM and Core CPI +0.3097% MoM from the 2026-11-28T16:46:56Z snapshot. Categories contribute approximately: Food +0.029 pp, Energy -0.259 pp, Core goods +0.024 pp, Shelter +0.116 pp and other Core services +0.104 pp. November energy uses a partial-month gasoline average and carries material forecast instability.

Rent estimated +0.205% MoM, OER +0.299%, used vehicles -0.353%, motor insurance +0.290% and airfare +1.163% in the V2 research model. These are NOT official November prices or historically validated predictions.

## Model methodology and limitations
Slow-moving rent, OER, medical and insurance rates use 40% latest MoM and 60% average last 3 MoM. Volatile apparel, cars and airfares use 25% latest MoM and 75% last 3-month average. Unobserved remainder categories use an implied series from published parent indices and published weights; small residual buckets may create large noise. All formulas are deliberately pre-registered heuristic assumptions, not optimized coefficients.

Seasonally adjusted CPI component indices and rounded CPI relative importance are not exactly additive; this is a research first-order approximation, not a reproduction of the official BLS calculation. PPI/PCE V1 models are not affected by the nested detail.

## Historical validation
Previous V1 test (2023-2024) recorded 14 Core CPI releases, mean absolute error 0.0792 percentage points against baseline 0.0790, meaning V1 does NOT improve Core CPI.

V2 full Core CPI and CPI have not yet been backtested. The isolated shelter V2 decomposition is separately studied in research/shelter_v2_pit.py using point-in-time ALFRED vintages, published-as-of-date BLS Rent/OER shelter weights in research/data/cpi_shelter_weights_pit.json, and a matched three-month shelter baseline. Do not interpret the shelter-only test as overall CPI V2 accuracy.

Before promoting V2, (1) review the shelter pilot, (2) obtain all historical category weights at each forecast cutoff, (3) validate official original report figures and BLS publication timestamps, (4) run a full walk-forward test on unseen releases, and (5) compare identically dated pre-news market consensus and Cleveland Fed nowcast.

Production site remains unchanged until explicitly approved.
