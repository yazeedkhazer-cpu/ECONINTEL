#!/usr/bin/env python3
"""Research-only multi-release PIT backtest: CPI, PCE and headline PPI.

As-of ALFRED observations, expanding-window regressions and first-vintage
outcomes. Not the calibrated ECONINTEL expenditure-weighted final nowcast.
"""
import argparse
from datetime import date, datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import statistics
import sys

from cpi_backtest import Fred, change, day, market_change, monthly_changes, next_month, solve, score

SPECS = {
    "cpi": {"release_id": 10, "targets": {"headline": "CPIAUCSL", "core": "CPILFESL"}},
    "pce": {"release_id": 54, "targets": {"headline": "PCEPI", "core": "PCEPILFE"}},
    "ppi": {"release_id": 46, "targets": {"headline": "PPIFIS"}},
}
# The predictor families are shared but target models and training are independent.
PREDICTORS = {
    "cpi": "CPIAUCSL", "corecpi": "CPILFESL",
    "pce": "PCEPI", "corepce": "PCEPILFE",
    "ppi": "PPIFIS", "rent": "CUSR0000SEHA",
    "oer": "CUSR0000SEHC", "wages": "CES0500000003",
    "brent": "DCOILBRENTEU", "gasoline": "GASREGW",
}
COLUMNS = (
    "lag1", "lag3", "lag12", "cpi_same", "corecpi_same", "ppi_same",
    "rent_last", "oer_last", "wages_last", "brent_latest", "gasoline_latest",
)


def mean_or_none(values):
    numbers = [x for x in values if x is not None and math.isfinite(x)]
    return statistics.mean(numbers) if numbers else None


def month_growth(snapshot, name, month=None):
    rows = snapshot.get(name, {})
    if len(rows) < 2:
        return None
    periods = sorted(rows)
    if month is None:
        month = periods[-1]
    if month not in rows:
        return None
    expected_prev = date.fromisoformat(month).replace(day=1)
    if expected_prev.month == 1:
        prior = f"{expected_prev.year-1}-12-01"
    else:
        prior = f"{expected_prev.year}-{expected_prev.month-1:02d}-01"
    if prior not in rows:
        return None
    return change(rows[month], rows[prior])


def x_features(snapshot, target, target_period, cutoff=None):
    history = snapshot[target]
    lag3 = monthly_changes(history, 3)
    if lag3 is None:
        return None
    lag12 = monthly_changes(history, 12)
    return {
        "lag1": lag3[-1], "lag3": statistics.mean(lag3),
        "lag12": statistics.mean(lag12) if lag12 else None,
        # These same-month values become available for PCE after CPI/PPI publication.
        # ALFRED's cutoff vintage controls whether any reading can be used.
        "cpi_same": month_growth(snapshot, "cpi", target_period),
        "corecpi_same": month_growth(snapshot, "corecpi", target_period),
        "ppi_same": month_growth(snapshot, "ppi", target_period),
        "rent_last": month_growth(snapshot, "rent"),
        "oer_last": month_growth(snapshot, "oer"),
        "wages_last": month_growth(snapshot, "wages"),
        "brent_latest": market_change(snapshot.get("brent", {}), 20, cutoff) if cutoff else None,
        "gasoline_latest": market_change(snapshot.get("gasoline", {}), 4, cutoff) if cutoff else None,
    }


def ridge(train, x, alpha=16.0):
    if not train:
        return None
    means = [mean_or_none([a.get(c) for a, y in train]) or 0.0 for c in COLUMNS]
    stds = []
    for c in COLUMNS:
        values = [a.get(c) for a, _ in train]
        values = [v for v in values if v is not None and math.isfinite(v)]
        stds.append(max(statistics.pstdev(values), 1e-8) if len(values) > 1 else 1.0)

    def transform(a):
        return [1.0] + [((a[c]-means[i])/stds[i]
                         if a.get(c) is not None and math.isfinite(a[c]) else 0.0)
                        for i, c in enumerate(COLUMNS)]

    matrix = [transform(a) for a, _ in train]
    labels = [y for _, y in train]
    n = len(COLUMNS)+1
    lhs = [[sum(r[i]*r[j] for r in matrix) +
            (alpha if i == j and i > 0 else 0.0)
            for j in range(n)] for i in range(n)]
    rhs = [sum(r[i]*y for r, y in zip(matrix, labels)) for i in range(n)]
    beta = solve(lhs, rhs)
    return sum(a*b for a, b in zip(transform(x), beta)) if beta else None


def release_calendar(client, release_id, start, end):
    raw = client.get("/release/dates", release_id=release_id,
                     include_release_dates_with_no_data="false", sort_order="desc", limit=1000)
    return sorted({r["date"] for r in raw.get("release_dates", [])
                   if start <= r.get("date", "") <= end})


def series_asof(client, when):
    begin = f"{day(when).year-3:04d}-01-01"
    return {name: client.observations(code, when, begin)
            for name, code in PREDICTORS.items()}


def target_month(snapshot, series_ids):
    latest = [max(snapshot.get(s, {}), default="") for s in series_ids]
    if any(not item for item in latest) or len(set(latest)) != 1:
        return None
    if any(monthly_changes(snapshot[s], 3) is None for s in series_ids):
        return None
    return next_month(latest[0])


def initial_vintage(client, released, period, targets):
    begin = f"{day(released).year-2:04d}-01-01"
    for k in range(5):
        vintage = (day(released) + timedelta(days=k)).isoformat()
        obs = {target: client.observations(code, vintage, begin)
               for target, code in targets.items()}
        if any(max(series, default="") != period for series in obs.values()):
            continue
        mom = {target: month_growth(obs, target) for target in targets}
        if all(x is not None and math.isfinite(x) for x in mom.values()):
            return mom, vintage
    return None, None


def replay(client, family, start, end, horizon=7, min_train=18, max_events=0):
    spec = SPECS[family]
    targets = spec["targets"]
    source_keys = {name: next(k for k, code in PREDICTORS.items() if code == value)
                   for name, value in targets.items()}
    dates = release_calendar(client, spec["release_id"], start, end)
    if max_events:
        dates = dates[:max_events]
    train = {name: [] for name in targets}
    accepted = set()
    records, rejected = [], []
    for released in dates:
        asof = (day(released)-timedelta(days=horizon)).isoformat()
        snap = series_asof(client, asof)
        period = target_month(snap, source_keys.values())
        if not period:
            rejected.append({"date": released, "reason": "no aligned consecutive target history"})
            continue
        if period in accepted:
            rejected.append({"date": released, "reason": "duplicate target month"})
            continue
        actual, vintage = initial_vintage(client, released, period, targets)
        if actual is None:
            rejected.append({"date": released, "reason": "unmatched initial vintage"})
            continue
        if vintage != released:
            rejected.append({"date": released, "reason": "calendar precedes initial ALFRED publication"})
            continue
        feats = {name: x_features(snap, key, period, asof)
                 for name, key in source_keys.items()}
        if any(x is None for x in feats.values()):
            rejected.append({"date": released, "reason": "feature history incomplete"})
            continue
        preds = {}
        for name in targets:
            fitted = ridge(train[name], feats[name]) if len(train[name]) >= min_train else None
            preds[name] = {"baseline": round(feats[name]["lag3"], 5),
                           "ridge": round(fitted, 5) if fitted is not None else None}
        rec = {"release_date": released, "forecast_date": asof,
               "target_period": period[:7], "outcome_vintage": vintage,
               "predictions": preds,
               "previous": {name: round(month_growth(snap, key), 5)
                            for name, key in source_keys.items()},
               "actual": {name: round(value, 5) for name, value in actual.items()},
               "features": feats}
        records.append(rec)
        accepted.add(period)
        for name in targets:
            train[name].append((feats[name], actual[name]))
    scored = [r for r in records if all(r["predictions"][name]["ridge"] is not None
                                       for name in targets)]
    return {
        "schemaVersion": 1, "family": family,
        "status": "complete" if scored else "insufficient",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "release_id": spec["release_id"], "horizon_days": horizon,
        "calendar_candidates": len(dates), "unique_months": len(records),
        "evaluated_cases": len(scored), "warmup_cases": len(records)-len(scored),
        "metrics": {name: {method: score(scored, name, method)
                           for method in ("baseline", "ridge")} for name in targets},
        "results": records, "skipped": rejected,
        "methodology": "ALFRED real-time observations fixed at forecast-date; "
                       "outcomes fixed at first same-day available vintage. "
                       "Ridge trained only on previous release outcomes; no current revisions.",
        "limitations": [
            "Not the final ECONINTEL seven-axis or BLS/BEA expenditure-weighted model.",
            "No first-published press-release one-decimal validation yet.",
            "Strict ALFRED same-day condition can exclude legitimate releases with FRED delays.",
            "Daily ALFRED vintages cannot establish intraday source availability.",
            "No point-in-time economist consensus or Cleveland Fed benchmark yet.",
        ],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--family", choices=list(SPECS), required=True)
    p.add_argument("--start", default="2018-01-01")
    p.add_argument("--end", default="2026-11-28")
    p.add_argument("--horizon", type=int, default=7)
    p.add_argument("--min-train", type=int, default=18)
    p.add_argument("--max-events", type=int, default=0)
    p.add_argument("--cache", default=".cache/econintel-alfred")
    p.add_argument("--output")
    args = p.parse_args()
    if args.horizon < 1 or args.min_train < 6 or args.max_events < 0:
        p.error("Invalid horizon/min-train/max-events")
    if date.fromisoformat(args.end) > date.today():
        p.error("End date cannot be in the future")
    client = Fred(os.getenv("FRED_API_KEY"), args.cache)
    result = replay(client, args.family, args.start, args.end,
                    args.horizon, args.min_train, args.max_events)
    outfile = Path(args.output or f"data/{args.family}-pit-evaluation.json")
    outfile.parent.mkdir(parents=True, exist_ok=True)
    outfile.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"family": args.family, "status": result["status"],
                      "evaluated": result["evaluated_cases"],
                      "metrics": result["metrics"]}, ensure_ascii=False, indent=2))
    if not result["evaluated_cases"]:
        sys.exit("No out-of-sample cases; results cannot establish accuracy")


if __name__ == "__main__":
    main()
