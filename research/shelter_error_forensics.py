#!/usr/bin/env python3
"""ECONINTEL Shelter V2 error forensics.

Use forecast objects FROZEN seven days before CPI release, fetch RENT,
OER, shelter and lodging as of their first release-date ALFRED vintage
to decompose forecast error. All 'actual' category observations below are
ex-post diagnostics only; NEVER used as pre-release predictors.

NOTE: BLS relative-importance weights are approximate annual snapshots
and seasonally-adjusted category index arithmetic is not exactly additive.
"""
from __future__ import annotations
import argparse
from datetime import date
import json
import math
from pathlib import Path
import statistics
import os
from cpi_backtest import Fred
from shelter_v2_pit import rate, ix, month, WEIGHTS_FILE

SERIES={
 "shelter":"CUSR0000SAH1",
 "rent":"CUSR0000SEHA",
 "oer":"CUSR0000SEHC",
 "lodging":"CUSR0000SEHB",
}

def finite(value):
    return isinstance(value,(float,int)) and math.isfinite(value)

def first_release_rates(fred,release,target):
    begin=f"{int(release[:4])-2}-01-01"
    readings={}
    missing=[]
    for name,code in SERIES.items():
        vintage=fred.observations(code,release,begin)
        if max(vintage,default="")!=target:
            missing.append(name)
            continue
        value=rate(vintage,target)
        if not finite(value):
            missing.append(name)
        else:
            readings[name]=value
    return readings,missing

def prior_lodging_volatility(fred,cutoff,target):
    begin=f"{int(cutoff[:4])-3}-01-01"
    s=fred.observations(SERIES["lodging"],cutoff,begin)
    prior=month(ix(target)-1)
    rates=[rate(s,month(ix(prior)-i)) for i in range(3)]
    if not all(finite(x) for x in rates):
        return {"available":False,"reason":"Insufficient 3-month lodging vintage"}
    return {"available":True,"last_lodging_mom":rates[0],
            "three_month_lodging_rates":rates,
            "lodging_volatility_std":statistics.pstdev(rates),
            "lodging_trailing_range":max(rates)-min(rates)}

def attribute(case, rates, w):
    p=case["prediction"]
    observed=case["actual"]
    # We use the independently frozen shelter first-release label from the
    # pilot to preserve exactly the originally evaluated outcome.
    rent=rates["rent"]
    oer=rates["oer"]
    remaining_actual=(w["shelter"]*observed -
        w["rent"]*rent-w["oer"]*oer)/w["residual"]
    portions={
      "rent":w["rent"]/w["shelter"]*(rent-p["rent_projected"]),
      "oer":w["oer"]/w["shelter"]*(oer-p["oer_projected"]),
      "remaining_shelter_implied":w["residual"]/w["shelter"]*(
          remaining_actual-p["residual_projected"]),
    }
    realized_err=observed-p["v2"]
    error_sum=sum(portions.values())
    # If exact index aggregation differs slightly from linear decomposition,
    # record discrepancy instead of hiding it.
    return {
      "actual_shelter_mom":observed,
      "actual_rent_mom":rent,
      "actual_oer_mom":oer,
      "actual_lodging_mom":rates.get("lodging"),
      "actual_remaining_shelter_implied_mom":remaining_actual,
      "predicted_rent_mom":p["rent_projected"],
      "predicted_oer_mom":p["oer_projected"],
      "predicted_remaining_shelter_mom":p["residual_projected"],
      "attributed_error_pp":portions,
      "attributed_error_sum_pp":error_sum,
      "shelter_model_error_pp":realized_err,
      "recomposition_error_pp":realized_err-error_sum,
      "largest_absolute_component":max(portions,key=lambda x:abs(portions[x])),
    }

def study(pilot,fred,wrows):
    rows,unavailable=[],[]
    for original in pilot["cases"]:
        target=original["target"]+"-01"
        available,missing=first_release_rates(fred,original["release"],target)
        if any(k in missing for k in ("rent","oer")):
            unavailable.append({"month":original["target"],
                                "missing_first_vintage":missing})
            continue
        w=next((w for w in wrows if w["reference"]==original["weightRef"]),None)
        if not w or w["publishedOn"]>original["cutoff"]:
            raise ValueError("Missing or future-dated BLS weights")
        attribution=attribute(original,available,w)
        if abs(attribution["recomposition_error_pp"])>1e-5:
            # The computation is an algebraic accounting identity under
            # the SAME parent/weight setup, except for model rounding.
            raise ValueError("Attribution does not reconcile")
        pre=prior_lodging_volatility(fred,original["cutoff"],target)
        rows.append({
            "month":original["target"],"release":original["release"],
            "as_of":original["cutoff"],"weightRef":w["reference"],
            "baseline_forecast":original["prediction"]["baseline"],
            "v2_forecast":original["prediction"]["v2"],
            "actual_shelter":original["actual"],
            "v2_abs_error_pp":abs(original["actual"]-original["prediction"]["v2"]),
            "v2_minus_baseline_forecast_pp":original["prediction"]["v2"]-original["prediction"]["baseline"],
            "ex_ante_rent_oer_gap_pp":abs(original["prediction"]["rent_projected"]-
                                       original["prediction"]["oer_projected"]),
            "pre_release_lodging_warning_inputs":pre,
            "post_release_error_attribution":attribution,
            "interpretation":"Ex-post error accounting only; actual category readings not available to forecaster before the event",
        })
        print("decomposed",original["target"],flush=True)
    ranked=sorted(rows,key=lambda r:r["v2_abs_error_pp"],reverse=True)
    if rows:
        source_means={
            k:round(statistics.mean(abs(r["post_release_error_attribution"]["attributed_error_pp"][k])
                  for r in rows),5)
            for k in ("rent","oer","remaining_shelter_implied")
        }
    else:source_means={}
    def safe_corr(xs,ys):
        if len(xs)<5:return None
        sx=statistics.pstdev(xs)
        sy=statistics.pstdev(ys)
        if sx<1e-9 or sy<1e-9:return None
        mx,my=statistics.mean(xs),statistics.mean(ys)
        return round(statistics.mean((x-mx)*(y-my) for x,y in zip(xs,ys))/sx/sy,3)
    withvol=[r for r in rows if r["pre_release_lodging_warning_inputs"]["available"]]
    v_corr=safe_corr([r["pre_release_lodging_warning_inputs"]["lodging_volatility_std"]
                      for r in withvol],[r["v2_abs_error_pp"] for r in withvol])
    return {
      "schemaVersion":1,"status":"descriptive_not_predictive_validation",
      "asof_window":"exact cutoff from previous 7-day CPI V2 shelter pilot",
      "total_pilot_cases":len(pilot["cases"]),
      "decomposed_cases":len(rows),"skipped":unavailable,
      "mean_abs_attribution_by_component_pp":source_means,
      "pre_release_3m_lodging_volatility_vs_absolute_shelter_error_corr":v_corr,
      "warning":"Correlations across 14 episodes are descriptive, not a verified trading or nowcasting signal.",
      "top_misses":[{"month":r["month"],"error_pp":r["v2_abs_error_pp"],
                    "largest_abs_component":r["post_release_error_attribution"]["largest_absolute_component"]}
                    for r in ranked[:5]],
      "rows":rows,
      "limitations":[
        "Only 14 historical eligible CPI releases and category first-vintage checks",
        "Ex-post Rent/OER/lodging outcome is only used to EXPLAIN error, not to predict",
        "Implied remainder is arithmetic, not a direct official measured category and may include seasonal/index reconciliation error",
        "Historical BLS December relative importances approximate month-specific weights",
        "ALFRED original seasonal-adjusted first vintage may not reproduce BLS text rounding",
        "Prior lodging volatility and any risk classification must be cross-validated over a broad independent sample",
        "A small correlation or good near-miss cannot establish a causal forecasting relationship"
      ]
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pilot",required=True)
    p.add_argument("--cache",default=".cache/econintel-alfred")
    p.add_argument("--output",default="data/shelter-v2-error-forensics.json")
    args=p.parse_args()
    pilot=json.loads(Path(args.pilot).read_text(encoding="utf-8"))
    weights=json.loads(WEIGHTS_FILE.read_text(encoding="utf-8"))["rows"]
    client=Fred(os.getenv("FRED_API_KEY"),args.cache)
    report=study(pilot,client,weights)
    path=Path(args.output)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k not in ("rows","limitations")},
      ensure_ascii=False,indent=2),flush=True)
    if not report["decomposed_cases"]:
        raise SystemExit("No ALFRED first-vintage category observations to decompose")

if __name__=="__main__":
    main()
