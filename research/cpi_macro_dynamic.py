#!/usr/bin/env python3
"""ECONINTEL MACRO-first CPI / Core CPI regime-adaptive research.

Unlike inflation-component extrapolation this experiment begins with observable
UPSTREAM market signals: retail gasoline, Brent, trade-weighted dollar,
producer prices, wage costs and weekly jobless claims. A past-inflation average
is retained ONLY as a benchmark and a residual anchor.

All signals are reconstructed as ALFRED vintages seven calendar days BEFORE
the initial CPI announcement. Target labels are FIRST release-day ALFRED
seasonally adjusted CPI index changes. No revised values or current CPI
components are used as explanatory features, and NO professional consensus
is assumed.

Train-only regularization, scaling, and local regime weights. A strict 2026
holdout is never used for hyperparameter adjustment in this experiment.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json, math, os, statistics
from pathlib import Path

from cpi_backtest import Fred, solve, market_change, monthly_changes, change
from shelter_v2_pit import ix, month, rate

SOURCE = {
    "cpi": "CPIAUCSL",
    "core": "CPILFESL",
    "gas": "GASREGW",            # EIA regular gasoline retail, weekly
    "oil": "DCOILBRENTEU",       # Brent spot, daily
    "dollar": "DTWEXBGS",        # Fed broad trade-weighted USD, daily
    "claims": "ICSA",            # DOL initial jobless claims, weekly
    "ppi": "PPIFIS",             # BLS PPI final demand (SA monthly)
    "commodities": "PPIACO",     # PPI all commodities (NONSA monthly)
    "wages": "CES0500000003",    # BLS private AHE, monthly (SA)
}
FEATURES = ("retail_gasoline_change","brent_price_change",
            "usd_broad_change","weekly_claims_change",
            "ppi_latest_change","producer_commodity_change",
            "private_wages_latest_change")
SOURCE_DAY_LIMITS={"gas":22,"oil":15,"dollar":18,"claims":15}
SOURCE_MONTH_LIMIT=105
TRAIN_MIN=10
HOLDOUT_START="2026-01"
RIDGE_ALPHA=25.0
REGIME_ALPHA=40.0

def is_number(v):
    return isinstance(v,(int,float)) and math.isfinite(v)

def avg_or_none(xs):
    return statistics.mean(xs) if xs and all(map(is_number,xs)) else None

def pct_means(x,n,cutoff,stale_days):
    if len(x)<n*2:
        return None
    days=sorted(x)
    if (date.fromisoformat(cutoff)-date.fromisoformat(days[-1])).days>stale_days:
        return None
    old=avg_or_none([x[k] for k in days[-2*n:-n]])
    new=avg_or_none([x[k] for k in days[-n:]])
    return change(new,old) if old is not None and new is not None else None

def monthly_asof(v,cutoff):
    if len(v)<2:return None
    last=max(v)
    if last!=month(ix(last)):return None
    # Monthly last print can be delayed; distinguish genuinely stale feeds.
    if (date.fromisoformat(cutoff)-date.fromisoformat(last)).days>SOURCE_MONTH_LIMIT:
        return None
    return rate(v,last)

def extract(snapshot,cutoff):
    v={
        "retail_gasoline_change":pct_means(snapshot["gas"],4,cutoff,22),
        "brent_price_change":pct_means(snapshot["oil"],20,cutoff,15),
        "usd_broad_change":pct_means(snapshot["dollar"],20,cutoff,18),
        "weekly_claims_change":pct_means(snapshot["claims"],4,cutoff,15),
        "ppi_latest_change":monthly_asof(snapshot["ppi"],cutoff),
        "producer_commodity_change":monthly_asof(snapshot["commodities"],cutoff),
        "private_wages_latest_change":monthly_asof(snapshot["wages"],cutoff),
    }
    # Missing indicators are not silently read from revised or later data.
    missing=[key for key,x in v.items() if not is_number(x)]
    if missing:
        raise ValueError("Missing or stale cutoff market source(s): "+",".join(missing))
    return v

def normalise(rows,features):
    columns={k:[x["features"][k] for x in rows] for k in FEATURES}
    mean={k:statistics.mean(xs) for k,xs in columns.items()}
    std={k:max(statistics.pstdev(xs),1e-5) for k,xs in columns.items()}
    def transform(x):
        return [1.0]+[(x[k]-mean[k])/std[k] for k in FEATURES]
    return transform

def weighted_ridge(rows,current,target,base_name,regime=False):
    if len(rows)<TRAIN_MIN:return None
    transform=normalise(rows,current)
    cx=transform(current)
    xmat=[transform(r["features"]) for r in rows]
    ys=[r["actual"][target]-(r["baseline"][target] if base_name else 0.0) for r in rows]
    if regime:
        # Similarity on EX-ANTE oil/gas/dollar/claims; all scales derived
        # from historical labeled rows alone. Recent observations get
        # somewhat more weight, yet no forward label can influence the fit.
        n=len(rows)
        weights=[]
        for i,x in enumerate(xmat):
            dist2=sum((cx[j]-x[j])**2 for j in (1,2,3,4))
            similarity=math.exp(-dist2/12.0)
            age=n-1-i
            temporal=math.exp(-age/18.0)
            weights.append(0.30+0.70*similarity*temporal)
        alpha=REGIME_ALPHA
    else:
        weights=[1.0]*len(rows)
        alpha=RIDGE_ALPHA
    dim=len(FEATURES)+1
    lhs=[[sum(w*x[i]*x[j] for x,w in zip(xmat,weights))+
          (alpha if i==j and i>0 else 0.0)
          for j in range(dim)] for i in range(dim)]
    rhs=[sum(w*x[i]*y for x,w,y in zip(xmat,weights,ys))
         for i in range(dim)]
    coefs=solve(lhs,rhs)
    if coefs is None:return None
    return sum(a*b for a,b in zip(cx,coefs))

def forecast_one(prior,current,target,base):
    # Both dynamic candidate specifications are fixed before evaluating 2026.
    raw=weighted_ridge(prior,current,target,base_name=False)
    resid=weighted_ridge(prior,current,target,base_name=True,regime=True)
    if raw is None or resid is None:
        return {"macro_only":None,"regime_adjusted":None}
    # Shrink extreme extrapolations: not tuned against validation outcomes.
    return {
        "macro_only":max(-1.0,min(1.0,raw)),
        "regime_adjusted":base+max(-0.35,min(0.35,resid)),
    }

def first_release(client,release,target,cutoff):
    begin=f"{int(cutoff[:4])-3:04d}-01-01"
    d={}
    for name in ("cpi","core"):
        x=client.observations(SOURCE[name],release,begin)
        if max(x,default="")!=target:
            raise ValueError(name+" was not first released on selected CPI calendar date")
        value=rate(x,target)
        if not is_number(value):raise ValueError("Initial CPI index change incomplete")
        d[name]=value
    return d

def event(client,row):
    cutoff=row["cutoff"];release=row["release"];target=row["target"]+"-01"
    if cutoff>=release:raise ValueError("Invalid cutoff date >= release")
    begin=f"{int(cutoff[:4])-3:04d}-01-01"
    snap={name:client.observations(series,cutoff,begin)
          for name,series in SOURCE.items()}
    for name in ("cpi","core"):
        latest=max(snap[name],default="")
        if latest!=month(ix(target)-1):
            raise ValueError("CPI label already published or previous period not aligned")
    baselines={}
    for name in ("cpi","core"):
        v=[rate(snap[name],month(ix(target)-1-j)) for j in range(3)]
        if not all(is_number(x) for x in v):
            raise ValueError("Missing recent CPI control baseline")
        baselines[name]=statistics.mean(v)
    x=extract(snap,cutoff)
    actual=first_release(client,release,target,cutoff)
    return {
      "release":release,"cutoff":cutoff,"target":row["target"],
      "features":x,"baseline":baselines,"actual":actual,
      "marketSourceLatest":{
         k:max(snap[k],default=None) for k in SOURCE
      }
    }

def mean_abs(rows,model,target):
    items=[(r["predictions"][target][model],r["actual"][target])
           for r in rows if r["predictions"][target][model] is not None]
    if not items:return None
    errors=[p-y for p,y in items]
    return {
      "n":len(errors),
      "MAE_pp":round(statistics.mean(map(abs,errors)),5),
      "RMSE_pp":round(math.sqrt(statistics.mean(e*e for e in errors)),5),
      "within_0_05pp":sum(abs(e)<0.05 for e in errors),
      "within_0_10pp":sum(abs(e)<0.10 for e in errors),
    }

def replay(client,event_rows):
    cases,skipped=[],[]
    accepted=set()
    for row in sorted(event_rows,key=lambda r:r["release"]):
        try:
            if row["target"] in accepted:raise ValueError("Duplicate CPI month")
            raw=event(client,row)
            train=[r for r in cases if r["release"]<raw["cutoff"]]
            pr={}
            for target in ("cpi","core"):
                baseline=raw["baseline"][target]
                pr[target]={"baseline":baseline,
                             **forecast_one(train,raw["features"],target,baseline)}
            raw["predictions"]=pr
            raw["trainingN"]=len(train)
            raw["lastKnownTrainingRelease"]=max((r["release"] for r in train),default=None)
            cases.append(raw)
            accepted.add(row["target"])
            print("Macro CPI vintage audited",raw["target"],
                  "train",len(train),flush=True)
        except (ValueError,TypeError,KeyError) as exc:
            skipped.append({"month":row["target"],"release":row["release"],
                            "reason":str(exc)})
    train_set=[r for r in cases if r["target"]<HOLDOUT_START]
    holdout=[r for r in cases if r["target"]>=HOLDOUT_START]
    methods=("baseline","macro_only","regime_adjusted")
    return {
       "schemaVersion":1,
       "status":"unvalidated_macro_factor_research",
       "sources":SOURCE,
       "macroFeatures":list(FEATURES),
       "originalInputs":"ALFRED as-of first-release indexed observations; commodity weekly/daily moving relative changes",
       "forecastLeadDays":7,
       "trainingPeriod":"Before 2026, with sequential training-only fit",
       "holdoutPeriod":"2026 separate from earlier months",
       "methods":{"baseline":"trailing 3 CPI months (BENCHMARK ONLY)",
                  "macro_only":"regularized regression on upstream market variables",
                  "regime_adjusted":"macroeconomic similarity and recency conditioned residual model"},
       "trainingN":len(train_set),"holdoutN":len(holdout),
       "scores":{target:{"before2026":{m:mean_abs(train_set,m,target) for m in methods},
                         "heldout2026":{m:mean_abs(holdout,m,target) for m in methods}}
                 for target in ("cpi","core")},
       "evaluated":len(cases),"skipped":skipped,"cases":cases,
       "limitations":[
          "External market signals do not determine the published CPI exactly",
          "Macro-only predictors are strictly as-of cutoff; 3m CPI is retained only for baseline and residual shrinkage",
          "No missing source is filled with later or currently revised data",
          "Only released first-vintage seasonally adjusted index changes; verify BLS published one-decimal text separately",
          "No professional consensus comparable as-of dates yet",
          "A small 2026 holdout cannot establish forecast quality in new macro regimes",
          "Regime weights and shrinkage were fixed prior to holdout and must not be tuned after seeing validation",
          "No revised/assumed unofficial leading rents are included here",
       ]
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--events",default="data/shelter-hotel-streak-holdout.json")
    p.add_argument("--cache",default=".cache/econintel-alfred")
    p.add_argument("--output",default="data/cpi-macro-dynamic-replay.json")
    p.add_argument("--max-events",type=int,default=0)
    args=p.parse_args()
    e=json.loads(Path(args.events).read_text(encoding="utf8"))
    if e["status"]!="evaluated_holdout":raise SystemExit("Event roster not verified")
    rows=e["cases"][:args.max_events] if args.max_events else e["cases"]
    study=replay(Fred(os.getenv("FRED_API_KEY"),args.cache),rows)
    out=Path(args.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(study,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print(json.dumps({"used":study["evaluated"],"training":study["trainingN"],
                      "holdout":study["holdoutN"],"scores":study["scores"],
                      "exclusions":study["skipped"]},indent=2),flush=True)
    if study["holdoutN"]<5:
        raise SystemExit("Insufficient untouched 2026 CPI actual cases")
if __name__=="__main__":main()
