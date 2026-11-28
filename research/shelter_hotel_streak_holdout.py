#!/usr/bin/env python3
"""Prospective-style held-out test of a pre-registered CPI shelter risk flag.

Discovery sample January 2023 - February 2024 is intentionally EXCLUDED.
Fixed hypothesis found in original sample: if last three published, seasonally
adjusted lodging MoM changes have the same strictly nonzero sign, the next
CPI shelter forecast (3-month mean) is at elevated risk of a >0.15 pp miss.

No fitting/tuning happens on holdout. Latest series vintages are frozen
at seven calendar days before each CPI release. Source: ALFRED.
"""
from __future__ import annotations
import argparse
from datetime import date,timedelta,datetime,timezone
import json
import math
import os
from pathlib import Path
import statistics

from cpi_backtest import Fred
from inflation_releases import release_calendar
from shelter_v2_pit import rate,month,ix

SHELTER_ID="CUSR0000SAH1"
LODGING_ID="CUSR0000SEHB"
THRESHOLD_PP=0.15
DISCOVERY_END="2024-02-29"

def lookback_three(vintage,last):
    vals=[rate(vintage,month(ix(last)-j)) for j in range(3)]
    return vals if all(x is not None and math.isfinite(x) for x in vals) else None

def same_direction(rates):
    return bool(rates and len(rates)==3 and
                (all(x>0 for x in rates) or all(x<0 for x in rates)))

def evaluate_episode(client,release,lead=7):
    cutoff=(date.fromisoformat(release)-timedelta(days=lead)).isoformat()
    begin=f"{int(cutoff[:4])-3}-01-01"
    shelter=client.observations(SHELTER_ID,cutoff,begin)
    lodging=client.observations(LODGING_ID,cutoff,begin)
    if not shelter or not lodging:
        raise ValueError("No frozen shelter or lodging series")
    last=max(shelter)
    target=month(ix(last)+1)
    if target in shelter:
        raise ValueError("CPI target month already published")
    prev=lookback_three(shelter,last)
    hotels=lookback_three(lodging,last)
    if prev is None or hotels is None:
        raise ValueError("Missing consecutive published months")
    baseline=statistics.mean(prev)
    outcome=client.observations(SHELTER_ID,release,begin)
    if max(outcome,default="")!=target:
        raise ValueError("No same-day ALFRED first shelter target")
    actual=rate(outcome,target)
    if actual is None or not math.isfinite(actual):
        raise ValueError("First shelter target incomplete")
    abs_err=abs(actual-baseline)
    return {
        "release":release,"cutoff":cutoff,"target":target[:7],
        "shelter_last_published":last[:7],
        "shelter_mom_prev_three":prev,
        "lodging_mom_prev_three":hotels,
        "lodging_streak_flag":same_direction(hotels),
        "predicted_shelter_mom_3m_baseline":baseline,
        "first_released_actual_shelter_mom":actual,
        "shelter_absolute_error_pp":abs_err,
        "large_miss_0_15pp":abs_err>THRESHOLD_PP,
    }

def evaluate(client,start,end,lead=7,max_events=0):
    if start<="2024-03-31":
        raise ValueError("Holdout must begin AFTER February 2024 discovery episodes")
    release_dates=release_calendar(client,10,start,end)
    if max_events:release_dates=release_dates[:max_events]
    cases,skipped,seen=[],[],set()
    for release in release_dates:
        try:
            r=evaluate_episode(client,release,lead)
            if r["target"] in seen:
                skipped.append({"release":release,"reason":"Duplicate target month"})
                continue
            cases.append(r)
            seen.add(r["target"])
            print("heldout:",r["target"],"warning:",r["lodging_streak_flag"],"abs_error:",round(r["shelter_absolute_error_pp"],4),flush=True)
        except (ValueError,KeyError,TypeError) as ex:
            skipped.append({"release":release,"reason":str(ex)})
    groups={}
    for name,pred in (("flag",True),("no_flag",False)):
        r=[x for x in cases if x["lodging_streak_flag"]==pred]
        groups[name]={
            "n":len(r),
            "mae_pp":round(statistics.mean(x["shelter_absolute_error_pp"] for x in r),5) if r else None,
            "large_miss_count":sum(x["large_miss_0_15pp"] for x in r),
            "large_miss_rate":round(sum(x["large_miss_0_15pp"] for x in r)/len(r),5) if r else None,
        }
    both=all(g["n"]>0 for g in groups.values())
    assoc=(groups["flag"]["mae_pp"]-groups["no_flag"]["mae_pp"]) if both else None
    return {
        "schemaVersion":1,
        "status":"evaluated_holdout" if cases else "no_eligible_cases",
        "generatedAt":datetime.now(timezone.utc).isoformat(),
        "study":"pre-registered 3 same-sign months of lodging index => elevated Shelter CPI nowcast error",
        "discoveryRange":"2023-01 through 2024-02, excluded",
        "heldoutReleaseRange":[start,end],
        "leadCalendarDays":lead,
        "forecast":"Simple three-month average of shelter MoM, not the v2 shelter composite; model-specific generalization not proven",
        "riskDefinition":"Three strictly positive or strictly negative as-of historical lodging MoM values",
        "largeMissThresholdPp":THRESHOLD_PP,
        "releaseCandidates":len(release_dates),
        "validCases":len(cases),
        "groups":groups,
        "flaggedMinusUnflaggedMaePp":round(assoc,5) if assoc is not None else None,
        "hypothesisDirectionSupported":bool(assoc is not None and assoc>0),
        "cases":cases,
        "skipped":skipped,
        "limitations":[
            "Discovery years were inspected before setting this rule; only holdout window is a valid independent check",
            "Risk flag predicts the magnitude of a 3m shelter BASELINE error; it is not a numerical CPI release nowcast",
            "Threshold 0.15 pp was selected after inspecting discovery years and must not be retuned on holdout",
            "Only ALFRED first-vintage index-derived seasonally adjusted monthly changes, not published rounded BLS text",
            "Does not prove causal influence of hotel prices or forecast the sign of upcoming hotel changes",
            "Small number of flagged events or episodes means very wide uncertainty on risk differences",
            "Even a positive sample would need another independent period before deployment"
        ]
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--start",default="2024-04-01")
    p.add_argument("--end",default="2026-11-28")
    p.add_argument("--horizon",type=int,default=7)
    p.add_argument("--max-events",type=int,default=0)
    p.add_argument("--cache",default=".cache/econintel-alfred")
    p.add_argument("--output",default="data/shelter-hotel-streak-holdout.json")
    args=p.parse_args()
    if args.end<args.start or args.horizon<1 or args.max_events<0 or date.fromisoformat(args.end)>date.today():
        p.error("Invalid range, horizon or event count")
    c=Fred(os.getenv("FRED_API_KEY"),args.cache)
    report=evaluate(c,args.start,args.end,args.horizon,args.max_events)
    out=Path(args.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:report[k] for k in
       ("status","validCases","groups","flaggedMinusUnflaggedMaePp","hypothesisDirectionSupported")},
       indent=2),flush=True)
    if report["validCases"]<6:
        raise SystemExit("Too few eligible holdout cases for a meaningful comparison")

if __name__=="__main__":
    main()
