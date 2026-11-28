#!/usr/bin/env python3
"""Point-in-time first test of ECONINTEL CPI V2 shelter submodel only.

BLS annual December shelter/rent/OER weights as published by cutoff,
three latest months of ALFRED as-of data and first release-vintage shelter
outcome. The test does NOT establish full CPI or Core CPI predictive accuracy.
"""
import argparse
from datetime import date,datetime,timedelta,timezone
import json
import math
from pathlib import Path
import statistics
import os
from cpi_backtest import Fred,change,day
from inflation_releases import release_calendar

ROOT=Path(__file__).resolve().parents[1]
WEIGHTS_FILE=Path(__file__).parent/"data"/"cpi_shelter_weights_pit.json"
SOURCES={"shelter":"CUSR0000SAH1","rent":"CUSR0000SEHA","oer":"CUSR0000SEHC"}

def month(i):
    return f"{i//12:04d}-{(i%12)+1:02d}-01"

def ix(t):
    d=day(t)
    return d.year*12+d.month-1

def rate(a,period):
    j=ix(period)
    return change(a.get(period),a.get(month(j-1)))

def growth3(a,last):
    vals=[rate(a,month(ix(last)-i)) for i in range(3)]
    return vals if all(v is not None and math.isfinite(v) for v in vals) else None

def weights_asof(weights,cutoff):
    candidates=[w for w in weights if w["publishedOn"]<=cutoff]
    if not candidates:return None
    w=sorted(candidates,key=lambda x:x["publishedOn"])[-1]
    if min(w[k] for k in ("shelter","rent","oer","residual"))<=0:
        return None
    if abs(w["shelter"]-w["rent"]-w["oer"]-w["residual"])>0.001:
        raise ValueError("BLS shelter weight partition invalid")
    return w

def predict(snapshot,w):
    latest=[max(snapshot[k],default=None) for k in SOURCES]
    if any(x is None for x in latest) or len(set(latest))!=1:
        return None
    last=latest[0]
    shelter=growth3(snapshot["shelter"],last)
    rent=growth3(snapshot["rent"],last)
    oer=growth3(snapshot["oer"],last)
    if not (shelter and rent and oer):return None
    # Exact V2 shelter decomposition: 40% latest + 60% trailing 3m for
    # Rent and OER, implied residual = 3m average of parent-reconciled rates.
    rent_pred=.4*rent[0]+.6*statistics.mean(rent)
    oer_pred=.4*oer[0]+.6*statistics.mean(oer)
    remaining=[(w["shelter"]*s-w["rent"]*r-w["oer"]*o)/w["residual"]
               for s,r,o in zip(shelter,rent,oer)]
    residual_pred=statistics.mean(remaining)
    model=(w["rent"]*rent_pred+w["oer"]*oer_pred+w["residual"]*residual_pred)/w["shelter"]
    return {"last":last,"target":month(ix(last)+1),
            "baseline":statistics.mean(shelter),"v2":model,
            "rent_projected":rent_pred,"oer_projected":oer_pred,
            "residual_projected":residual_pred}

def label_on_first_release(client,release_date,target):
    # Accept only a same-day ALFRED vintage that contains the new target,
    # not a subsequently revised value from years later.
    vintage=client.observations(SOURCES["shelter"],release_date,
        f"{day(release_date).year-3:04d}-01-01")
    if max(vintage,default=None)!=target:return None
    return rate(vintage,target)

def metrics(rows,method):
    if not rows:return {"n":0,"mae":None,"rmse":None}
    errs=[r["prediction"][method]-r["actual"] for r in rows]
    return {"n":len(errs),
            "mae":round(statistics.mean(abs(e) for e in errs),5),
            "rmse":round(math.sqrt(statistics.mean(e*e for e in errs)),5),
            "monthly_wins":sum(abs(r["prediction"][method]-r["actual"]) <
                    abs(r["prediction"]["baseline" if method=="v2" else "v2"]-r["actual"])
                    for r in rows)}

def replay(client,start,end,horizon=7,max_events=16):
    w=json.loads(WEIGHTS_FILE.read_text(encoding="utf-8"))["rows"]
    release_dates=release_calendar(client,10,start,end)
    if max_events:release_dates=release_dates[:max_events]
    cases,excluded,seen=[],[],set()
    for release in release_dates:
        cutoff=(day(release)-timedelta(days=horizon)).isoformat()
        weight=weights_asof(w,cutoff)
        if not weight:
            excluded.append({"release":release,"reason":"No previously published weights"})
            continue
        begin=f"{day(cutoff).year-4:04d}-01-01"
        vintages={key:client.observations(code,cutoff,begin) for key,code in SOURCES.items()}
        forecast=predict(vintages,weight)
        if not forecast:
            excluded.append({"release":release,"reason":"Three consecutive same-vintage histories unavailable"})
            continue
        if forecast["target"] in seen:
            excluded.append({"release":release,"reason":"Duplicate CPI target month"})
            continue
        actual=label_on_first_release(client,release,forecast["target"])
        if actual is None:
            excluded.append({"release":release,"reason":"Missing same-day ALFRED first shelter index"})
            continue
        seen.add(forecast["target"])
        cases.append({"release":release,"cutoff":cutoff,
             "target":forecast["target"][:7],"weightRef":weight["reference"],
             "weightPublished":weight["publishedOn"],
             "prediction":{k:forecast[k] for k in
                ("baseline","v2","rent_projected","oer_projected","residual_projected")},
             "actual":actual})
        print("evaluated shelter",forecast["target"][:7],flush=True)
    return {"schemaVersion":1,"status":"complete" if cases else "insufficient",
        "model":"ECONINTEL CPI V2 shelter only",
        "cutoffDays":horizon,"generatedAt":datetime.now(timezone.utc).isoformat(),
        "candidates":len(release_dates),"valid":len(cases),
        "metrics":{"v2":metrics(cases,"v2"),"baseline":metrics(cases,"baseline")},
        "cases":cases,"excluded":excluded,
        "warnings":["This does not validate the full CPI/Core CPI V2 model",
        "Historic weight reference tables may have changed since original publication",
        "First ALFRED seasonally adjusted index may not match rounded BLS text",
        "Only tested 2023 onward with available weight vintages",
        "Parameters fixed before inspecting test outcomes; independent holdout still needed"]}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start",default="2023-02-01")
    parser.add_argument("--end",default="2024-06-30")
    parser.add_argument("--max-events",type=int,default=16)
    parser.add_argument("--horizon",type=int,default=7)
    parser.add_argument("--cache",default=".cache/econintel-alfred")
    parser.add_argument("--output",default="data/shelter-v2-pit.json")
    args=parser.parse_args()
    if args.start>args.end or args.horizon<1 or args.max_events<0 or day(args.end)>date.today():
        parser.error("Invalid test range")
    client=Fred(os.getenv("FRED_API_KEY"),args.cache)
    result=replay(client,args.start,args.end,args.horizon,args.max_events)
    path=Path(args.output)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:result[k] for k in ("status","valid","candidates","metrics")},
                     indent=2),flush=True)
    if not result["valid"]:
        raise SystemExit("No historical shelter cases: no accuracy claim")

if __name__=="__main__":
    main()
