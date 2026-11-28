#!/usr/bin/env python3
"""CPI Rent/OER/Lodging genuine vintage walk-forward experiment.

No future training labels: as-of inputs 7 calendar days before CPI;
first-release outcomes must appear on the SAME release date.
All predictions are numeric monthly % changes (SA index); no BLS rounded
press-release claim. Event roster: independently checked CPI shelter dates.
CPI V2 is NOT changed or promoted by this experiment.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json, math, os, statistics
from pathlib import Path
from cpi_backtest import Fred, solve
from shelter_v2_pit import month, ix, rate

SOURCES={"rent":"CUSR0000SEHA","oer":"CUSR0000SEHC",
         "lodging":"CUSR0000SEHB"}
FEATURE_NAMES=("lag1","mean3","momentum","seasonal_y1")
MIN_TRAIN=10
RIDGE=20.0
ROOT=Path(__file__).resolve().parents[1]

def finite(x):
    return isinstance(x,(int,float)) and math.isfinite(x)

def input_features(data,target):
    previous=month(ix(target)-1)
    p=[rate(data,month(ix(previous)-i)) for i in range(3)]
    s=rate(data,month(ix(target)-12))
    if not all(finite(v) for v in p) or not finite(s):
        return None
    return {"lag1":p[0],"mean3":statistics.mean(p),
            "momentum":p[0]-p[1],"seasonal_y1":s}

def regularized(train,features,alpha=RIDGE):
    """Standardize each feature on TRAINING examples ONLY.
    Always fall back to simple baseline if there are too few episodes.
    """
    if len(train)<MIN_TRAIN:
        return None
    names=FEATURE_NAMES
    means={k:statistics.mean(t["features"][k] for t in train) for k in names}
    std={k:max(statistics.pstdev(t["features"][k] for t in train),1e-5)
         for k in names}
    def x(f):
        return [1.0]+[(f[k]-means[k])/std[k] for k in names]
    xmat=[x(row["features"]) for row in train]
    y=[row["actual"] for row in train]
    n=len(names)+1
    lhs=[[sum(row[i]*row[j] for row in xmat)+(alpha if i==j and i>0 else 0)
          for j in range(n)] for i in range(n)]
    rhs=[sum(row[i]*target for row,target in zip(xmat,y)) for i in range(n)]
    coeff=solve(lhs,rhs)
    if coeff is None:
        return None
    return sum(a*b for a,b in zip(x(features),coeff))

def predictions(features,training):
    old=features["mean3"]
    fitted=regularized(training,features)
    return {
        "baseline3":old,
        "last_month":features["lag1"],
        "seasonal_prior_year":features["seasonal_y1"],
        "fixed_seasonal_blend":old*.7+features["seasonal_y1"]*.3,
        "ridge_train_only":fitted,
    }

def fetch_episode(client,row):
    target=row["target"]+"-01"
    cutoff=row["cutoff"]
    release=row["release"]
    begin=f"{int(cutoff[:4])-4}-01-01"
    result={"month":row["target"],"asOf":cutoff,"release":release,"categories":{}}
    for name,series in SOURCES.items():
        before=client.observations(series,cutoff,begin)
        if max(before,default="")!=month(ix(target)-1):
            raise ValueError(name+" as-of history not aligned with shelter release")
        f=input_features(before,target)
        if f is None:
            raise ValueError(name+" as-of seasonal + 3m history incomplete")
        after=client.observations(series,release,begin)
        if max(after,default="")!=target:
            raise ValueError(name+" ALFRED index not first-released on calendar day")
        actual=rate(after,target)
        if not finite(actual):
            raise ValueError(name+" first-release monthly value unavailable")
        result["categories"][name]={"features":f,"actual":actual}
    return result

def score(rows,which):
    out=[r for r in rows if finite(r["predictions"].get(which))]
    if not out:
        return {"n":0,"maePp":None,"exactOneDecimal":None}
    errs=[r["predictions"][which]-r["actual"] for r in out]
    # Exact-tenth comparisons use Decimal half-up in the separate audit; here
    # none are official rounded BLS press figures; no exact-rate claim.
    return {"n":len(out),"maePp":round(statistics.mean(abs(e) for e in errs),5),
            "rmsePp":round(math.sqrt(statistics.mean(e*e for e in errs)),5),
            "biasPp":round(statistics.mean(errs),5)}

def replay(client,source_events):
    by_category={name:[] for name in SOURCES}
    excluded=[]
    accepted=set()
    ordered=sorted(source_events,key=lambda x:x["release"])
    for row in ordered:
        if row["target"] in accepted:
            excluded.append({"month":row["target"],"reason":"duplicate target"})
            continue
        try:
            fetched=fetch_episode(client,row)
        except (ValueError,KeyError) as ex:
            excluded.append({"month":row.get("target"),"reason":str(ex)})
            continue
        accepted.add(row["target"])
        for name in SOURCES:
            item=fetched["categories"][name]
            earlier=[t for t in by_category[name] if t["release"]<row["cutoff"]]
            preds=predictions(item["features"],earlier)
            by_category[name].append({
                "month":row["target"],"release":row["release"],"cutoff":row["cutoff"],
                "features":item["features"],"predictionTrainingN":len(earlier),
                "lastKnownLabelRelease":max((x["release"] for x in earlier),default=None),
                "predictions":preds,"actual":item["actual"]})
        print("CPI first-vintage components checked:",row["target"],flush=True)
    results={}
    for name,rows in by_category.items():
        # Disjoint, STRICT holdout for the future-facing validity score. We
        # selected methods before evaluating any current 2026 outcome.
        period1=[r for r in rows if r["month"]<"2026-01"]
        holdout=[r for r in rows if r["month"]>="2026-01"]
        # The earlier cases are also informative but NOT a held-out test.
        methods=("baseline3","last_month","seasonal_prior_year",
                 "fixed_seasonal_blend","ridge_train_only")
        results[name]={
          "allValid":len(rows),"priorStudy":len(period1),"heldout2026":len(holdout),
          "pre2026Metrics":{k:score(period1,k) for k in methods},
          "heldout2026Metrics":{k:score(holdout,k) for k in methods},
          "cases":rows}
    return {
     "schemaVersion":1,"status":"real_time_category_replay",
     "generatedAt":datetime.now(timezone.utc).isoformat(),
     "source":"ALFRED point-in-time CPI-U seasonally adjusted Rent, OER and Lodging indices",
     "lastPreReleaseDays":7,
     "method":"Fixed baselines and training-only expanding-window ridge; min 10 earlier published event labels",
     "selectedMethodBefore2026":None,
     "warnings":[
      "No category method may be promoted if it fails to beat equal-weight 3m baseline on separate 2026 cases",
      "2026 small holdout is not definitive; compare same matched monthly releases and extend to other regimes",
      "Do not infer CPI/Core CPI accuracy from three component-only tests",
      "First ALFRED vintage SA index MoM values may differ from rounded official CPI press release text",
      "Historical relative-importance and true contemporaneous source dates must be verified for any aggregate CPI model",
      "A model with 100% retrospective accuracy on its tuning dates can still have zero genuine forecasting ability",
     ],
     "sourceCandidates":len(source_events),"accepted":len(accepted),
     "excluded":excluded,"categories":results,
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--events",default="data/shelter-hotel-streak-holdout.json")
    p.add_argument("--cache",default=".cache/econintel-alfred")
    p.add_argument("--output",default="data/cpi-category-walkforward.json")
    p.add_argument("--max-events",type=int,default=0)
    args=p.parse_args()
    event_report=json.loads(Path(args.events).read_text(encoding="utf8"))
    assert event_report["status"]=="evaluated_holdout"
    cases=event_report["cases"]
    if args.max_events:cases=cases[:args.max_events]
    report=replay(Fred(os.getenv("FRED_API_KEY"),args.cache),cases)
    out=Path(args.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print(json.dumps({
      "accepted":report["accepted"],"excluded":len(report["excluded"]),
      "holdout":{k:v["heldout2026Metrics"] for k,v in report["categories"].items()},
    },indent=2),flush=True)
    if report["accepted"]<10:raise SystemExit("Insufficient release-vintage samples")

if __name__=="__main__":main()
