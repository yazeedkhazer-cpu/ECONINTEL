#!/usr/bin/env python3
"""Numerical-first inflation forecast audit, first ALFRED vintage.

Inputs are frozen individual releases from the 2023-2024 historical
structural pilot. Outcome labels are index-derived first ALFRED vintage,
NOT audited literal BLS/BEA published one-decimal releases.

This audit explicitly measures exact one-decimal hits (nearest 0.1 pp),
continuous errors, and a walk-forward model-combination experiment that
only chooses weights from earlier ALREADY RELEASED observations. It is not
a promise of future predictability.
"""
from __future__ import annotations
import argparse
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
import json
import math
from pathlib import Path
import statistics
from datetime import datetime,timezone

FAMILY_TARGETS={"cpi":("headline","core"),
                "pce":("headline","core"),
                "ppi":("headline",)}
WEIGHTS=(0,0.25,0.5,0.75,1)
MIN_PRIOR=6

def round_one(x):
    if not isinstance(x,(int,float)) or not math.isfinite(x):
        raise ValueError("Invalid inflation data for rounded comparison")
    return float(Decimal(str(x)).quantize(Decimal("0.1"),rounding=ROUND_HALF_UP))

def is_finite(x):
    return isinstance(x,(int,float)) and math.isfinite(x)

def validate(report):
    family=report.get("family")
    if family not in FAMILY_TARGETS:raise ValueError("Unrecognized report family "+str(family))
    if report.get("status")!="complete":raise ValueError("Pilot incomplete: "+family)
    prior=set()
    ordered=sorted(report.get("results") or [],key=lambda r:r["release_date"])
    if not ordered:raise ValueError("No first-vintage release cases")
    for r in ordered:
        key=(r["release_date"],r["target_period"])
        if key in prior:raise ValueError("Duplicate release and target month")
        prior.add(key)
        if not r["as_of"]<r["release_date"]:raise ValueError("Forecast cutoff on or after announcement")
        if r["actual_vintage"]!=r["release_date"]:
            raise ValueError("Target not first-release vintage")
        for target in FAMILY_TARGETS[family]:
            vals=[r["actual"].get(target),r["predictions"][target]["structural"],
                  r["predictions"][target]["baseline"]]
            if not all(is_finite(v) for v in vals):
                raise ValueError("Incomplete or nonfinite initial release")
    return family,ordered

def quote_score(rows,method,target):
    if not rows:return None
    y=[r["actual"][target] for r in rows]
    z=[r["predictions"][target][method] for r in rows]
    errors=[p-a for p,a in zip(z,y)]
    n=len(rows)
    return {
      "n":n,
      "mae_pp":round(statistics.mean(abs(e) for e in errors),5),
      "rmse_pp":round(math.sqrt(statistics.mean(e*e for e in errors)),5),
      "signed_bias_pp":round(statistics.mean(errors),5),
      "exact_1_decimal_hits":sum(round_one(p)==round_one(a) for p,a in zip(z,y)),
      "exact_1_decimal_rate":round(sum(round_one(p)==round_one(a) for p,a in zip(z,y))/n,5),
      "within_0_05pp_hits":sum(abs(e)<=0.05 for e in errors),
      "within_0_10pp_hits":sum(abs(e)<=0.10 for e in errors),
    }

def mix(row,target,weight):
    src=row["predictions"][target]
    return (1-weight)*src["baseline"]+weight*src["structural"]

def online_winner(row,previous,target):
    """EX-ANTE weight selection: prior releases MUST precede target cutoff."""
    eligible=[e for e in previous if e["release_date"]<row["as_of"]]
    if len(eligible)<MIN_PRIOR:return None
    ranked=[]
    for w in WEIGHTS:
        e=statistics.mean(abs(mix(r,target,w)-r["actual"][target]) for r in eligible)
        # Favor simpler baseline in ties.
        ranked.append((e,w))
    _,weight=min(ranked)
    return {"weight":weight,"forecast":mix(row,target,weight),
            "trainingN":len(eligible),
            "latestTrainingRelease":max(e["release_date"] for e in eligible)}

def online_report(rows,target):
    cases=[]
    for index,r in enumerate(rows):
        chosen=online_winner(r,rows[:index],target)
        if not chosen:continue
        cases.append({
          "release":r["release_date"],"cutoff":r["as_of"],"month":r["target_period"],
          "actual":r["actual"][target],
          "online":chosen["forecast"],
          "baseline":r["predictions"][target]["baseline"],
          "structural":r["predictions"][target]["structural"],
          "selectedStructuralWeight":chosen["weight"],
          "trainingN":chosen["trainingN"],
          "lastKnownLabelRelease":chosen["latestTrainingRelease"],
        })
    def metrics(field):
        if not cases:return None
        errors=[c[field]-c["actual"] for c in cases]
        return {
          "n":len(cases),
          "mae_pp":round(statistics.mean(abs(e) for e in errors),5),
          "exact_1_decimal_hits":sum(round_one(c[field])==round_one(c["actual"]) for c in cases),
          "within_0_05pp_hits":sum(abs(e)<=0.05 for e in errors),
        }
    return {
      "n":len(cases),"warmup_event_count":MIN_PRIOR,
      "testScores":{name:metrics(name) for name in ("online","structural","baseline")},
      "cases":cases,
      "note":"As-of sequential weight selection; weight grid predeclared and forecast issued only after six earlier distinct releases.",
    }

def audit(report):
    family,rows=validate(report)
    targets={}
    for target in FAMILY_TARGETS[family]:
        targets[target]={
          "structural":quote_score(rows,"structural",target),
          "baseline":quote_score(rows,"baseline",target),
          "online":online_report(rows,target),
          "releases":[{"release":r["release_date"],"asOf":r["as_of"],
            "target":r["target_period"],"actual":r["actual"][target],
            "structural":r["predictions"][target]["structural"],
            "baseline":r["predictions"][target]["baseline"],
            "structuralOneDecimal":round_one(r["predictions"][target]["structural"]),
            "firstVintageActualOneDecimal":round_one(r["actual"][target]),
            "match":round_one(r["predictions"][target]["structural"])==round_one(r["actual"][target])}
            for r in rows],
        }
    return {"family":family,"evaluated":len(rows),"targets":targets}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir",required=True)
    parser.add_argument("--output",default="data/inflation-numeric-accuracy-audit.json")
    args=parser.parse_args()
    files=list(Path(args.input_dir).rglob("*-structural-pit.json"))
    if not files:raise SystemExit("Missing original 2023-24 structural PIT files")
    reports={}
    for file in files:
        d=json.loads(file.read_text(encoding="utf8"))
        if d.get("family") in FAMILY_TARGETS:
            family=d["family"]
            if family in reports:raise SystemExit("Duplicate pilot for "+family)
            reports[family]=d
    if set(reports)!=set(FAMILY_TARGETS):
        raise SystemExit("Need all three independently tested families: CPI, PCE, PPI")
    scored={family:audit(reports[family]) for family in FAMILY_TARGETS}
    result={
      "schemaVersion":1,
      "status":"historical_accuracy_audit",
      "generatedAt":datetime.now(timezone.utc).isoformat(),
      "referenceRun":"https://github.com/yazeedkhazer-cpu/ECONINTEL/actions/runs/46163855962",
      "source":"Historical first ALFRED index-vintage PIT cases from previous experiment",
      "publishedNumberAudit":"NOT YET VERIFIED against rounded initial BLS/BEA release text",
      "rounding":"Decimal ROUND_HALF_UP to 0.1 percentage point",
      "accuracyDefinition":"Match to 1 decimal of monthly inflation percentage change, AND separate continuous tolerance checks",
      "onlineRule":"Predeclared convex grid weights {0,.25,.50,.75,1}, smallest previous MAE using only release labels prior to each forecast cutoff, 6 earlier cases required.",
      "reports":scored,
      "limitations":[
        "Do not claim near-100% accuracy; these are historical index-derived release results, not official printed news readings",
        "Tiny 14/16 monthly sample; online evaluation only has 8/10 cases after six warmup events",
        "Model mixture grid not tested on 2024-2026 holdout, so cannot claim forward improvement",
        "No contemporaneous professional market consensus",
        "Do not tune component weights or accuracy thresholds on the evaluation cases",
      ],
    }
    output=Path(args.output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf8")
    print(json.dumps({family:{key:{name:res["targets"][key][name]
             if name in ("structural","baseline") else res["targets"][key]["online"]["testScores"]}
         for name in ("structural","baseline","online")}
         for key in res["targets"]} for family,res in scored.items()},ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
