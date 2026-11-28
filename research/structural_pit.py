#!/usr/bin/env python3
"""ECONINTEL v0.1 structural-inflation PIT backtest (CPI/PCE/PPI).

This replays the *same equations* as assets/inflation-structural.js,
using ALFRED observations as of the cutoff and BLS annual weights
available on that date. First-vintage label from ALFRED, not a
transcription of BLS/BEA printed news-release percentages.
No present-day revised historical values or 2026 weights for 2023.
"""
from __future__ import annotations
import argparse
from datetime import date, datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import statistics

from cpi_backtest import Fred, change, day, monthly_changes, score
from inflation_releases import SPECS, release_calendar

ROOT = Path(__file__).resolve().parents[1]
WEIGHTS_FILE = Path(__file__).parent / "data/cpi_annual_weights_pit.json"
INPUTS = {
    "cpi": "CPIAUCSL", "corecpi": "CPILFESL",
    "cpifood": "CPIUFDSL", "cpienergy": "CPIENGSL",
    "cpigoods": "CUSR0000SACL1E", "cpishelter": "CUSR0000SAH1",
    "cpiservices": "CUSR0000SASLE",
    "ppi": "PPIFIS", "pce": "PCEPI", "corepce": "PCEPILFE",
    "gasoline": "GASREGW", "brent": "DCOILBRENTEU",
}
FAMILIES = {
    "cpi": {"headline": "cpi", "core": "corecpi"},
    "pce": {"headline": "pce", "core": "corepce"},
    "ppi": {"headline": "ppi"},
}
PCE_FEATURES = ("cpi", "corecpi", "ppi", "prev_pce", "prev_corepce")


def month_index(s):
    # FRED source period is the first day of month YYYY-MM-01.
    d = day(s)
    return 12 * d.year + d.month - 1


def month_key(index):
    yr, mo = divmod(index, 12)
    return f"{yr:04d}-{mo+1:02d}-01"


def month_before(s):
    return month_key(month_index(s)-1)


def next_month(s):
    return month_key(month_index(s)+1)


def is_number(v):
    return isinstance(v, (int, float)) and math.isfinite(v)


def mean(vals):
    vals = list(vals)
    return statistics.mean(vals) if vals and all(is_number(v) for v in vals) else None


def month_change(history, period):
    if not history:
        return None
    return change(history.get(period), history.get(month_before(period)))


def trailing_rates(history, last, count=3):
    rates = [month_change(history, month_key(month_index(last)-i)) for i in range(count)]
    return rates if all(is_number(v) for v in rates) else None


def monthly_aggregate(history, minimum=1):
    monthly = {}
    for when, value in sorted(history.items()):
        if is_number(value):
            monthly.setdefault(when[:7]+"-01", []).append(value)
    return {m: statistics.mean(v) for m, v in monthly.items() if len(v) >= minimum}


def get_weights(vintages, cutoff):
    # The dated row must be publicly available on/before cutoff.
    candidates = [w for w in vintages if w["publishedOn"] <= cutoff]
    if not candidates:
        return None
    w = sorted(candidates, key=lambda item: item["publishedOn"])[-1]
    total = sum(w[k] for k in ("food","energy","goods","shelter","other"))
    if abs(total-100) > .01 or any(w[k] <= 0 for k in ("food","energy","goods","shelter","other")):
        raise ValueError("Invalid historical BLS weight partition")
    return w


def proxy_fit(outcomes, predictors, last, minimum=15):
    # Reproduces JS 43-month trailing penalised univariate regression.
    period = month_index(last)
    sample = []
    for i in range(period-42, period+1):
        m = month_key(i)
        x = month_change(predictors, m)
        y = month_change(outcomes, m)
        if is_number(x) and is_number(y):
            sample.append((x,y))
    if len(sample) < minimum:
        return None
    xm = statistics.mean(x for x,y in sample)
    ym = statistics.mean(y for x,y in sample)
    cov = sum((x-xm)*(y-ym) for x,y in sample)
    var = sum((x-xm)**2 for x,y in sample)
    slope = max(-1.5, min(1.5, cov/(var+10)))
    return {"alpha":ym-slope*xm,"beta":slope,"n":len(sample)}


def proxy_predict(outcomes, predictors, last, target):
    fit = proxy_fit(outcomes,predictors,last)
    x = month_change(predictors,target)
    if fit is None or not is_number(x):
        return None
    rate = max(-12, min(12, fit["alpha"]+fit["beta"]*x))
    return {"rate":rate,"n":fit["n"],"beta":fit["beta"],"proxy_mom":x}


def last_month_equal(data, names):
    last = [max(data[name], default=None) for name in names]
    if any(x is None for x in last) or len(set(last)) != 1:
        return None
    return last[0]


def components(data, weights, target):
    # As before an actual CPI publication: category indices only through prior month.
    last = month_before(target)
    ids = ["cpi","corecpi","cpifood","cpienergy","cpigoods","cpishelter","cpiservices"]
    if last_month_equal(data,ids) != last:
        return None
    food = mean(trailing_rates(data["cpifood"],last) or [])
    shelter = mean(trailing_rates(data["cpishelter"],last) or [])
    goods = mean(trailing_rates(data["cpigoods"],last) or [])
    other = []
    for i in range(3):
        m = month_key(month_index(last)-i)
        services_rate = month_change(data["cpiservices"], m)
        shelter_rate = month_change(data["cpishelter"], m)
        if not (is_number(services_rate) and is_number(shelter_rate)):
            return None
        rate = ((weights["shelter"]+weights["other"])*services_rate -
                weights["shelter"]*shelter_rate)/weights["other"]
        other.append(rate)
    other_avg = mean(other)
    energy = proxy_predict(data["cpienergy"],data["gasoline"],last,target)
    if not all(is_number(v) for v in (food,shelter,goods,other_avg)) or energy is None:
        return None
    parts = {"food":food,"energy":energy["rate"],"goods":goods,"shelter":shelter,"other":other_avg}
    contributions = {k:weights[k]*rate/100 for k,rate in parts.items()}
    headline = sum(contributions.values())
    denominator = weights["goods"]+weights["shelter"]+weights["other"]
    core = 100*(contributions["goods"]+contributions["shelter"]+contributions["other"])/denominator
    return {"headline":headline,"core":core,"contributions":contributions,
            "component_rates":parts,"energy_proxy":energy,
            "weights_reference":weights["referenceMonth"]}


def ppi_model(data, target):
    last = month_before(target)
    if max(data["ppi"],default=None) != last:
        return None
    lag3 = trailing_rates(data["ppi"],last)
    if lag3 is None:
        return None
    fit = proxy_predict(data["ppi"],data["brent"],last,target)
    if fit is None:
        return None
    rate = (mean(lag3)+fit["rate"])/2
    return {"headline":rate,"brent_proxy":fit,"ppi_trend":mean(lag3)}


def solve(A,b):
    size=len(b)
    z=[list(A[i])+[b[i]] for i in range(size)]
    for k in range(size):
        pivot=max(range(k,size),key=lambda i:abs(z[i][k]))
        if abs(z[pivot][k])<1e-10:
            return None
        z[k],z[pivot]=z[pivot],z[k]
        scale=z[k][k]
        z[k]=[v/scale for v in z[k]]
        for i in range(size):
            if i==k:continue
            factor=z[i][k]
            z[i]=[u-factor*v for u,v in zip(z[i],z[k])]
    return [row[-1] for row in z]


def ridge(samples, x, alpha=16.0):
    # Reproduces inflation-structural.js 5-feature ridge regression.
    if len(samples)<24 or len(x)!=5 or not all(is_number(v) for v in x):
        return None
    cols=list(zip(*(r[0] for r in samples)))
    center=[statistics.mean(c) for c in cols]
    scales=[max(statistics.pstdev(c),1e-6) for c in cols]
    def transform(v):
        return [1.0]+[(a-center[i])/scales[i] for i,a in enumerate(v)]
    inputs=[transform(row[0]) for row in samples]
    targets=[row[1] for row in samples]
    count=6
    matrix=[[sum(row[i]*row[j] for row in inputs)+
             (alpha if i==j and i>0 else 0)
             for j in range(count)] for i in range(count)]
    vector=[sum(row[i]*y for row,y in zip(inputs,targets)) for i in range(count)]
    coeff=solve(matrix,vector)
    return sum(c*v for c,v in zip(coeff,transform(x))) if coeff is not None else None


def pce_features(data, m, rates=None):
    # CPI/PPI for current target month are used ONLY if they are already
    # present in cutoff vintage. Otherwise use separate forecasts, never
    # actual observations from after cutoff.
    rates = rates or {}
    vals=[
        rates.get("cpi",month_change(data["cpi"],m)),
        rates.get("corecpi",month_change(data["corecpi"],m)),
        rates.get("ppi",month_change(data["ppi"],m)),
        month_change(data["pce"],month_before(m)),
        month_change(data["corepce"],month_before(m)),
    ]
    return vals if all(is_number(v) for v in vals) else None


def pce_models(data, target, weights):
    last=month_before(target)
    if last_month_equal(data,["pce","corepce"])!=last:
        return None
    rates={}
    for src,ratekey in (("cpi","headline"),("corecpi","core")):
        rates[src]=month_change(data[src],target)
    if not all(is_number(rates[s]) for s in ("cpi","corecpi")):
        projected = components(data, weights, target)
        if projected is None:
            return None
        rates["cpi"]=projected["headline"]
        rates["corecpi"]=projected["core"]
    rates["ppi"]=month_change(data["ppi"],target)
    if not is_number(rates["ppi"]):
        ppi=ppi_model(data,target)
        if ppi is None:
            return None
        rates["ppi"]=ppi["headline"]
    future=pce_features(data,target,rates)
    if future is None:
        return None
    output={"inputs":dict(zip(PCE_FEATURES,future)),"same_month_actual_published_at_cutoff":{
            k:month_change(data[k],target) is not None for k in ("cpi","corecpi","ppi")}}
    for id,name in (("pce","headline"),("corepce","core")):
        samples=[]
        for i in range(month_index(last)-78,month_index(last)+1):
            m=month_key(i)
            x=pce_features(data,m)
            y=month_change(data[id],m)
            if x is not None and is_number(y):
                samples.append((x,y))
        rate=ridge(samples,future)
        if rate is None:
            return None
        output[name]=max(-3,min(3,rate))
        output[name+"_n"]=len(samples)
    return output


def cutoff_snapshot(client, cutoff):
    # As-of reconstruction with 8-year window supports the PCE ridge model.
    begin=f"{day(cutoff).year-9:04d}-01-01"
    raw={key:client.observations(series,cutoff,begin) for key,series in INPUTS.items()}
    out={k:monthly_aggregate(v) if k in ("gasoline","brent") else v
         for k,v in raw.items()}
    return out


def first_labels(client,family,released,period):
    # Use same initial-vintage criterion as the existing research engine.
    required=FAMILIES[family]
    start=f"{day(released).year-2:04d}-01-01"
    for k in range(5):
        vintage=(day(released)+timedelta(days=k)).isoformat()
        sampled={n:client.observations(INPUTS[key],vintage,start)
                 for n,key in required.items()}
        if any(max(hist,default=None)!=period for hist in sampled.values()):
            continue
        actual={name:month_change(hist,period) for name,hist in sampled.items()}
        if all(is_number(x) for x in actual.values()):
            return actual,vintage
    return None,None


def baseline(data, family, target):
    out={}
    for label,id in FAMILIES[family].items():
        prior=trailing_rates(data[id],month_before(target))
        if prior is None:
            return None
        out[label]=mean(prior)
    return out


def evaluate(client,family,start,end,weights,horizon=7,max_events=0):
    assert family in FAMILIES
    days=release_calendar(client,SPECS[family]["release_id"],start,end)
    if max_events:
        days=days[:max_events]
    records,skipped,seen=[],[],set()
    for i,released in enumerate(days):
        asof=(day(released)-timedelta(days=horizon)).isoformat()
        w=get_weights(weights,asof)
        if not w:
            skipped.append({"release_date":released,"reason":"No published historical BLS weights by cutoff"})
            continue
        try:
            data=cutoff_snapshot(client,asof)
            current=last_month_equal(data,FAMILIES[family].values())
            if not current:
                raise ValueError("Target families have missing/misaligned last observation")
            target=next_month(current)
            if target in seen:
                skipped.append({"release_date":released,"reason":"Duplicate target month"})
                continue
            base=baseline(data,family,target)
            if base is None:
                raise ValueError("Missing baseline history")
            if family=="cpi":
                model=components(data,w,target)
            elif family=="ppi":
                model=ppi_model(data,target)
            else:
                model=pce_models(data,target,w)
            if model is None:
                raise ValueError("Insufficient strictly-as-of structural model inputs")
            actual,actual_vintage=first_labels(client,family,released,target)
            if actual is None:
                raise ValueError("Could not find initial ALFRED CPI/PCE/PPI target")
            if actual_vintage!=released:
                skipped.append({"release_date":released,
                                "reason":"Calendar preceding first ALFRED target publication: "+actual_vintage})
                continue
            predictions={label:{"baseline":base[label],"structural":model[label]}
                         for label in FAMILIES[family]}
            row={
                "release_date":released,"as_of":asof,"target_period":target[:7],
                "official_weights_reference":w["referenceMonth"],
                "official_weights_published_on":w["publishedOn"],
                "model":"ECONINTEL structural-proxy v0.1 as-of backtest",
                "model_details":model,"actual_vintage":actual_vintage,
                "predictions":predictions,
                "previous":{label:month_change(data[id],current)
                            for label,id in FAMILIES[family].items()},
                "actual":actual,
            }
            records.append(row)
            seen.add(target)
        except (ValueError,TypeError,KeyError) as exc:
            skipped.append({"release_date":released,"reason":str(exc)[:180]})
        if (i+1)%8==0:
            print(f"{family} historical candidates {i+1}/{len(days)}",flush=True)
    return {
        "schemaVersion":1,"status":"complete" if records else "insufficient",
        "family":family,"generatedAt":datetime.now(timezone.utc).isoformat(),
        "horizon_days":horizon,"calendar_candidates":len(days),
        "evaluated_cases":len(records),"skipped_cases":len(skipped),
        "metrics":{name:{method:score(records,name,method)
                    for method in ("baseline","structural")} for name in FAMILIES[family]},
        "results":records,"skipped":skipped,
        "source_weights":str(WEIGHTS_FILE.relative_to(ROOT)),
        "methodology":"Historical ALFRED vintages frozen at each release's forecast cutoff; "
             "BLS annual weights pre-published as of cutoff; same structural proxy equations; "
             "no training on realized target event.",
        "limitations":[
            "BLS annual December weight is a dated approximation, not monthly current relative importance.",
            "ALFRED first-observation MoM is not the rounded initial BLS/BEA/PPI printed reading.",
            "Gasoline and Brent vintage observations resampled monthly from weekly/daily quotes; EIA value revisions possible.",
            "PCE/PPI stage-specific CPI/PPI source availability is enforced and may differ from front-page pre-release simultaneous stage.",
            "Strict same-day FRED initial-vintage requirement drops valid source publications lagged by FRED.",
            "No contemporaneous market analyst consensus available to score yet.",
            "No historical hyperparameter optimisation; fixed research v0.1 weights and penalty.",
        ],
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--family",choices=list(FAMILIES),required=True)
    p.add_argument("--start",default="2022-04-01")
    p.add_argument("--end",default="2026-11-28")
    p.add_argument("--horizon",type=int,default=7)
    p.add_argument("--max-events",type=int,default=16)
    p.add_argument("--cache",default=".cache/econintel-alfred")
    p.add_argument("--output")
    args=p.parse_args()
    if not (1<=args.horizon<=90) or args.max_events<0 or args.start>args.end:
        p.error("Invalid date, horizon or candidate limit")
    if day(args.end)>date.today():
        p.error("End in future")
    weight_data=json.loads(WEIGHTS_FILE.read_text(encoding="utf-8"))["weights"]
    client=Fred(os.getenv("FRED_API_KEY"),args.cache)
    report=evaluate(client,args.family,args.start,args.end,weight_data,args.horizon,args.max_events)
    outfile=Path(args.output or f"data/{args.family}-structural-pit.json")
    outfile.parent.mkdir(parents=True,exist_ok=True)
    outfile.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"status":report["status"],"family":args.family,
                      "evaluated":report["evaluated_cases"],"skipped":report["skipped_cases"],
                      "metrics":report["metrics"]},ensure_ascii=False,indent=2))
    if not report["evaluated_cases"]:
        raise SystemExit("No valid historical cases — accuracy is not measurable yet")


if __name__=="__main__":
    main()
