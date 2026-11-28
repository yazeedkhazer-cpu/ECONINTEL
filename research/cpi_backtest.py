#!/usr/bin/env python3
"""ECONINTEL CPI point-in-time backtest. Requires FRED_API_KEY.
Inputs are exact ALFRED vintages at cutoff. Results use the earliest matching
post-release CPI vintage, not today's revised readings. No current-value leakage.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.stlouisfed.org/fred"
CPI_RELEASE_ID = 10
SOURCES = {
    "headline": "CPIAUCSL",
    "core": "CPILFESL",
    "ppi": "PPIFIS",
    "rent": "CUSR0000SEHA",
    "oer": "CUSR0000SEHC",
    "wages": "CES0500000003",
    "brent": "DCOILBRENTEU",
    "gasoline": "GASREGW",
}
FEATURES = ("lag1", "lag3", "lag12", "ppi", "rent", "oer", "wages", "brent", "gasoline")
TARGETS = ("headline", "core")


def day(value):
    return date.fromisoformat(str(value))


def month_id(value):
    d = day(value)
    return d.year * 12 + d.month


def next_month(value):
    d = day(value)
    year = d.year + (d.month == 12)
    month = 1 if d.month == 12 else d.month + 1
    return f"{year:04d}-{month:02d}-01"


def change(current, prior):
    if current is None or prior is None or prior == 0:
        return None
    return (current / prior - 1) * 100


def numeric(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def average(vals):
    usable = [v for v in vals if numeric(v)]
    return statistics.mean(usable) if usable else None


def monthly_changes(history, count):
    keys = sorted(history)
    if len(keys) < count + 1:
        return None
    keys = keys[-count-1:]
    if any(month_id(b) != month_id(a) + 1 for a, b in zip(keys, keys[1:])):
        return None
    rates = [change(history[b], history[a]) for a, b in zip(keys, keys[1:])]
    return rates if all(numeric(v) for v in rates) else None


def latest_monthly(history):
    changes = monthly_changes(history, 1)
    return changes[0] if changes else None


def market_change(history, count, as_of, max_age=32):
    # Daily Brent, weekly gasoline. Only observations available by cutoff;
    # reject stale feeds instead of carrying old energy prices forward.
    keys = sorted(history)
    if len(keys) < count * 2 or (day(as_of) - day(keys[-1])).days > max_age:
        return None
    before = average([history[k] for k in keys[-2*count:-count]])
    after = average([history[k] for k in keys[-count:]])
    return change(after, before)


def build_features(snapshot, target, cutoff):
    lag3 = monthly_changes(snapshot[target], 3)
    if lag3 is None:
        return None
    lag12 = monthly_changes(snapshot[target], 12)
    return {
        "lag1": lag3[-1],
        "lag3": average(lag3),
        "lag12": average(lag12) if lag12 else None,
        "ppi": latest_monthly(snapshot.get("ppi", {})),
        "rent": latest_monthly(snapshot.get("rent", {})),
        "oer": latest_monthly(snapshot.get("oer", {})),
        "wages": latest_monthly(snapshot.get("wages", {})),
        "brent": market_change(snapshot.get("brent", {}), 20, cutoff),
        "gasoline": market_change(snapshot.get("gasoline", {}), 4, cutoff),
    }


class Fred:
    def __init__(self, api_key, cache):
        if not api_key:
            raise ValueError("FRED_API_KEY is required (keep it in GitHub Actions secrets)")
        self.key = api_key
        self.cache = Path(cache)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.last_request_at = 0.0

    def get(self, endpoint, **params):
        # Cache file names and contents never include the API key.
        canonical = endpoint + "?" + urllib.parse.urlencode(sorted(params.items()))
        path = self.cache / (hashlib.sha256(canonical.encode()).hexdigest() + ".json")
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        query = urllib.parse.urlencode({**params, "api_key": self.key, "file_type": "json"})
        url = API + endpoint + "?" + query
        for attempt in range(7):
            # Official FRED v1 limit is 120 requests/min. Stay below 70/min
            # to leave headroom for other workflows using the same key.
            gap = time.monotonic() - self.last_request_at
            if gap < 0.90:
                time.sleep(0.90 - gap)
            self.last_request_at = time.monotonic()
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "ECONINTEL-PIT-1.0"})
                with urllib.request.urlopen(req, timeout=35) as response:
                    result = json.load(response)
                if "error_code" in result:
                    raise RuntimeError("FRED error: " + str(result.get("error_message", "unknown")))
                path.write_text(json.dumps(result), encoding="utf-8")
                return result
            except urllib.error.HTTPError as err:
                if err.code == 429 and attempt < 6:
                    retry_after = err.headers.get("Retry-After", "")
                    try:
                        suggested = float(retry_after)
                    except (TypeError, ValueError):
                        suggested = 65.0
                    delay = max(65.0, min(suggested, 180.0))
                    print("FRED rate limit hit; waiting before retry (no data substituted).",
                          file=sys.stderr)
                    time.sleep(delay)
                    continue
                if err.code in (500, 502, 503, 504) and attempt < 6:
                    time.sleep(min(2**attempt, 60))
                    continue
                raise RuntimeError(f"FRED HTTP {err.code}; check API key or quota") from None
            except (urllib.error.URLError, TimeoutError):
                if attempt == 6:
                    raise
                time.sleep(min(2**attempt, 60))
        raise RuntimeError("FRED API unavailable after retries")

    def release_days(self, start, end):
        response = self.get("/release/dates", release_id=CPI_RELEASE_ID,
                            include_release_dates_with_no_data="false",
                            sort_order="desc", limit=1000)
        return sorted({x["date"] for x in response.get("release_dates", [])
                       if start <= x.get("date", "") <= end})

    def observations(self, series_id, as_of, start):
        result = self.get("/series/observations", series_id=series_id,
                          realtime_start=as_of, realtime_end=as_of,
                          observation_start=start, observation_end=as_of,
                          sort_order="asc", limit=10000)
        history = {}
        for row in result.get("observations", []):
            value, period = row.get("value"), row.get("date", "")
            if value in (None, ".") or period > as_of:
                continue
            if not (row["realtime_start"] <= as_of <= row["realtime_end"]):
                raise ValueError(f"Invalid vintage for {series_id}: {as_of}")
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if numeric(number):
                history[period] = number
        return history


def start_window(as_of):
    # Sufficient coverage for 12-month feature with seasonally adjusted revisions.
    return f"{day(as_of).year-3:04d}-01-01"


def snapshot(client, as_of):
    return {key: client.observations(series, as_of, start_window(as_of))
            for key, series in SOURCES.items()}


def target_month_before(inputs):
    headline, core = inputs["headline"], inputs["core"]
    if not headline or not core or max(headline) != max(core):
        return None
    if monthly_changes(headline, 3) is None or monthly_changes(core, 3) is None:
        return None
    return next_month(max(headline))


def first_outcome(client, release_date, expected_period):
    """Read first date that both headline and core appear; never a later revision."""
    for lag in range(5):
        vintage = (day(release_date) + timedelta(days=lag)).isoformat()
        observed = {key: client.observations(SOURCES[key], vintage,
                                            start_window(release_date))
                    for key in TARGETS}
        if any(max(observed[key], default="") != expected_period for key in TARGETS):
            continue
        rates = {key: latest_monthly(observed[key]) for key in TARGETS}
        if all(numeric(value) for value in rates.values()):
            return rates, vintage
    return None, None


def solve(matrix, vector):
    n = len(vector)
    a = [list(row) + [vector[i]] for i, row in enumerate(matrix)]
    for k in range(n):
        pivot = max(range(k, n), key=lambda j: abs(a[j][k]))
        if abs(a[pivot][k]) < 1e-10:
            return None
        a[k], a[pivot] = a[pivot], a[k]
        scale = a[k][k]
        a[k] = [v / scale for v in a[k]]
        for i in range(n):
            if i != k:
                scale = a[i][k]
                a[i] = [v - scale * w for v, w in zip(a[i], a[k])]
    return [a[i][-1] for i in range(n)]


def ridge_forecast(history, current, alpha=16.0):
    """Train-only mean/std normalisation; missing variables imputed with train mean."""
    if not history:
        return None
    columns = [[x.get(field) for x, y in history] for field in FEATURES]
    means = [average(c) or 0.0 for c in columns]
    stdev = []
    for col in columns:
        valid = [v for v in col if numeric(v)]
        std = statistics.pstdev(valid) if len(valid) > 1 else 0.0
        stdev.append(std if std > 1e-10 else 1.0)

    def transform(x):
        return [1.0] + [
            (x[field] - means[j]) / stdev[j] if numeric(x.get(field)) else 0.0
            for j, field in enumerate(FEATURES)
        ]

    rows = [transform(x) for x, y in history]
    labels = [y for x, y in history]
    n = len(FEATURES) + 1
    lhs = [[sum(x[i] * x[j] for x in rows) +
            (alpha if i == j and i > 0 else 0.0)
            for j in range(n)] for i in range(n)]
    rhs = [sum(x[i] * y for x, y in zip(rows, labels)) for i in range(n)]
    beta = solve(lhs, rhs)
    if beta is None:
        return None
    return sum(v * b for v, b in zip(transform(current), beta))


def score(records, target, name):
    pairs = [(r["predictions"][target].get(name), r["actual"][target],
              r["previous"][target]) for r in records
             if r["predictions"][target].get(name) is not None]
    if not pairs:
        return {"n": 0, "mae": None, "rmse": None,
                "rounded_tenth_hit": None, "direction_accuracy": None}
    error = [pred - actual for pred, actual, _ in pairs]
    size = len(pairs)
    return {
        "n": size,
        "mae": round(average([abs(e) for e in error]), 4),
        "rmse": round(math.sqrt(average([e*e for e in error])), 4),
        "rounded_tenth_hit": round(sum(round(p, 1) == round(a, 1)
                                         for p, a, _ in pairs) / size, 4),
        "direction_accuracy": round(sum((p > prev) == (a > prev)
                                        for p, a, prev in pairs) / size, 4),
    }


def backtest(client, start, end, horizon=7, minimum_train=18, max_events=0):
    events = client.release_days(start, end)
    if max_events:
        events = events[:max_events]
    fitted = {name: [] for name in TARGETS}
    cases, skipped = [], []
    accepted_periods = set()
    for i, released in enumerate(events):
        as_of = (day(released) - timedelta(days=horizon)).isoformat()
        try:
            inputs = snapshot(client, as_of)
            expected_period = target_month_before(inputs)
            if expected_period is None:
                skipped.append({"release": released, "why": "Missing/gapped pre-release CPI data"})
                continue
            if expected_period in accepted_periods:
                skipped.append({"release": released, "why": "Duplicate CPI target month"})
                continue
            actual, actual_vintage = first_outcome(client, released, expected_period)
            if actual is None:
                skipped.append({"release": released, "why": "No matched first-release vintage"})
                continue
            # The FRED release calendar occasionally includes an earlier date for
            # the same CPI month (e.g. 2022-02-08 vs BLS CPI on 2022-02-10).
            # Require the first ALFRED publication to coincide with this date;
            # otherwise the seven-day cutoff is NOT seven days before CPI.
            if actual_vintage != released:
                skipped.append({"release": released,
                                "why": "Calendar candidate predates ALFRED first CPI vintage " + actual_vintage})
                continue
            features = {name: build_features(inputs, name, as_of) for name in TARGETS}
            if any(x is None for x in features.values()):
                skipped.append({"release": released, "why": "Insufficient feature history"})
                continue
            predictions = {}
            for name in TARGETS:
                predictions[name] = {
                    "baseline": round(features[name]["lag3"], 5),
                    "ridge": (round(ridge_forecast(fitted[name], features[name]), 5)
                              if len(fitted[name]) >= minimum_train else None),
                }
            case = {
                "release_date": released, "as_of": as_of,
                "target_period": expected_period[:7],
                "actual_vintage": actual_vintage,
                "actual": {n: round(actual[n], 5) for n in TARGETS},
                "previous": {n: round(latest_monthly(inputs[n]), 5) for n in TARGETS},
                "predictions": predictions,
                "features": {n: {k: round(v, 5) if numeric(v) else None
                                  for k, v in features[n].items()} for n in TARGETS},
            }
            cases.append(case)
            accepted_periods.add(expected_period)
            # The current first-release target becomes trainable AFTER this forecast.
            for name in TARGETS:
                fitted[name].append((features[name], actual[name]))
        except (ValueError, TypeError, KeyError) as err:
            skipped.append({"release": released, "why": str(err)[:140]})
        if (i + 1) % 10 == 0:
            print(f"{i+1}/{len(events)} release dates checked", file=sys.stderr)

    scored = [r for r in cases if all(r["predictions"][name]["ridge"] is not None
                                     for name in TARGETS)]
    return {
        "schemaVersion": 1,
        "status": "complete" if scored else "insufficient",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source": "FRED/ALFRED realtime vintages + FRED CPI release calendar (release_id=10)",
        "first_vintage_note": "Earliest available ALFRED index observation within 0–4 days of release",
        "calendar_candidates": len(events), "evaluatedCases": len(scored),
        "warmupCases": len(cases) - len(scored),
        "horizon_days": horizon, "min_training_cases": minimum_train,
        "metrics": {name: {method: score(scored, name, method)
                           for method in ("baseline", "ridge")} for name in TARGETS},
        "results": cases, "skipped": skipped,
        "caveats": [
            "No current-revised historical inputs or targets allowed.",
            "Release-date API gives calendar dates, not intraday publication times.",
            "MoM is computed from first-vintage seasonally adjusted index levels; "
            "BLS printed rounded percentage may differ due to index precision.",
            "No expectations consensus or Cleveland Fed external benchmark is included yet.",
            "Gaps and shutdown-related missing CPI months are excluded rather than filled.",
            "Duplicate CPI months and calendar dates preceding first ALFRED CPI publication are excluded.",
            "Only same-date ALFRED first-vintage CPI calendar candidates are currently accepted.",
            "Ridge is an experimental 9-feature benchmark, not an implemented "
            "CPI expenditure-weighted component model.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2018-01-01")
    parser.add_argument("--end", default="2026-11-28")
    parser.add_argument("--horizon", type=int, default=7)
    parser.add_argument("--min-train", type=int, default=18)
    parser.add_argument("--max-events", type=int, default=0)
    parser.add_argument("--cache", default=".cache/econintel-alfred")
    parser.add_argument("--output", default="data/cpi-backtest-results.json")
    args = parser.parse_args()
    if args.horizon < 1 or args.min_train < 6 or args.max_events < 0:
        parser.error("Require horizon >= 1 day, min-train >= 6 and max-events >= 0")
    if day(args.end) > date.today():
        parser.error("End cannot be in the future")
    if day(args.start) > day(args.end):
        parser.error("Start must precede end")
    client = Fred(os.environ.get("FRED_API_KEY"), args.cache)
    result = backtest(client, args.start, args.end, args.horizon,
                      args.min_train, args.max_events)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "evaluatedCases": result["evaluatedCases"],
                      "skipped": len(result["skipped"]),
                      "metrics": result["metrics"]}, ensure_ascii=False, indent=2))
    if not result["evaluatedCases"]:
        sys.exit("Not enough valid historical observations; no accuracy claim can be made")


if __name__ == "__main__":
    main()
