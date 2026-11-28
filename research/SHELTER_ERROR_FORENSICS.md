# Why ECONINTEL CPI Shelter V2 is nearly exact in some months but badly wrong in others

Research note — November 28, 2026. This is **ex-post error attribution**, not proof of a reliably forecastable pre-release signal.

## Same 14 cases, two distinct questions

1. **Forecast score**: seven calendar days before BLS CPI, the V2 model forecast the next month's shelter MoM from historically available BLS weights and ALFRED index observations. In 14 original cases, V2 MAE = 0.11607 pp, 3m shelter baseline MAE = 0.11381 pp. V2 did not beat the baseline.
2. **Why it missed**: after the CPI announcement we separately retrieved first-available release-day vintage CPI Rent, OER, and Lodging indices, then allocated the **signed shelter forecast error** to Rent, OER, and the algebraic remainder (shelter minus Rent and OER). The actual category readings are **never used as forecast predictors**.

Code: research/shelter_error_forensics.py. Source workflow: https://github.com/yazeedkhazer-cpu/ECONINTEL/actions/runs/46168574893 . The first-release detailed 14-month JSON is preserved as the GitHub Actions artifact shelter-surprise-forensics-14-months.

## Aggregate attribution to absolute category forecast errors

| Category | Mean absolute component contribution to shelter forecast error |
| --- | ---: |
| Rent of primary residence | 0.01361 pp |
| Owners' equivalent rent (OER) | 0.05479 pp |
| Implied remaining shelter | 0.07309 pp |

These absolute means **do not add** to total forecast MAE: positive and negative contribution errors cancel each other. The 'remaining shelter' value is inferred algebraically from an annual relative-importance partition. It includes lodging but also other small shelter groups and non-additivity/seasonal adjustment of CPI component indices. **Do not assert that all residual misses are hotel prices**.

## Specific diagnostic months (all numbers in shelter MoM percentage points)

| Month | Forecast | Actual | Rent error contribution | OER error contribution | Remainder error contribution | Release-day lodging MoM |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| May 2023 (close hit) | 0.565 | 0.556 | -0.020 | -0.029 | +0.040 | +1.800% |
| April 2023 (miss) | 0.630 | 0.422 | -0.008 | -0.014 | -0.185 | -2.964% |
| September 2023 (miss) | 0.350 | 0.647 | +0.004 | +0.106 | +0.186 | +3.653% |
| January 2024 (miss) | 0.412 | 0.634 | -0.018 | +0.071 | +0.169 | +1.776% |
| March 2023 (miss) | 0.755 | 0.557 | -0.059 | -0.167 | +0.029 | +2.697% |

**Major finding 1 — a correct total can conceal incorrect components.** May 2023 model underperformed on separate category predictions; the signed errors offset and the headline shelter miss was just 0.009 pp. A near-perfect headline score is not evidence that the model understood each driver.

**Major finding 2 — sudden component changes dominate misses.** April 2023 hotel/lodging fell about 3.0%, while the model extrapolated previous months. September 2023 lodging rose 3.7% after three declines; OER rose about 0.6%. January 2024 lodging rose ~1.8% and OER ~0.6%, contrasting with Rent ~0.4%. BLS stated that the January annual structure-type weighting update increased the share of OER allocated to single-family detached homes by approximately 5 percentage points. These facts can explain historical misses after release, but one must not pretend the size of the February 2024 publication was known before release.

Official sources: September 2023 https://www.bls.gov/news.release/archives/cpi_10122023.htm ; April 2023 https://www.bls.gov/news.release/archives/cpi_05102023.htm ; January 2024 https://www.bls.gov/news.release/archives/cpi_02132024.htm ; BLS January 2024 OER reweighting https://www.bls.gov/cpi/notices/2024/rent-oer-information.htm .

## Pre-release hypothesis discovered in this sample — not yet validated

On only these 14 historical episodes, **three consecutive previously published CPI lodging MoM changes with the same sign** happened ahead of March 2023, April 2023 and September 2023.

| Previously observed 3-month lodging same-sign run | Cases | Shelter V2 MAE | Misses over 0.15 pp |
| --- | ---: | ---: | ---: |
| Yes | 3 | 0.234 pp | 3 / 3 |
| No | 11 | 0.084 pp | 3 / 11 |

Potential interpretation: repeated same-direction lodging changes can precede an unstable shelter month. But in March 2023 hotel prices CONTINUED higher rather than reversing; the OER shortfall dominated that miss. Hence **same-sign run may be a regime-risk warning, not a forecast of hotel direction**. This flag was selected AFTER inspecting the sample, so it is a post-hoc hypothesis subject to serious overfitting.

Another pre-release hypothesis FAILED this sample: simply assuming greater previous-three-month hotel price volatility means larger shelter errors. The descriptive correlation here was **-0.553**, the opposite sign. Do not launch a 'high volatility means bad forecast' rule.

## Next clean experiment / pre-registration

1. Keep the **same-sign three-month lodging run** rule unchanged. Test on 2018–2022 and 2024–2026 ALFRED point-in-time first-release episodes. Do not tune threshold and present the same 14 months as out-of-sample evidence.
2. Independently model **Lodging away from home**, not as a noisy tiny implicit remainder. Test training-only seasonal calendar features and as-of historical rates. Report MAE vs simple average, direction and actual hit count.
3. Independently model **Rent and OER** using historically released market rent ZORI and other new-rent indices, with publication date embargo and multiple *trained-only* lag lengths. BLS's six-panel, six-month housing sample and January weighting changes justify testing these as separate regimes.
4. Derive **interval predictions**, not just a point: historical 80% error-band coverage and error magnitude conditional on regime indicators. Calibrate intervals on separate months and compare to unconditional baseline.
5. Recompute with **monthly BLS category relative importance** (rather than annual reference weights) and original BLS release print whenever available, to isolate arithmetic residual from genuinely unmodeled housing components.
6. For the entire CPI and Core CPI engine, evaluate both **individual component forecast errors** and **aggregate forecast errors** to avoid mistaken success from cancellation.

The target is not to celebrate a coincidence but to identify which information, provably available before release, reduces expected forecast error on months never used to choose the rule.
