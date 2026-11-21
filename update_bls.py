#!/usr/bin/env python3
"""ECONINTEL / BLS monthly data updater.

Runs in CI or on a machine with internet. A successfully validated response
produces data/official-latest.json and assets/official-data.js atomically.
No Python dependencies beyond stdlib.

  python scripts/update_bls.py
  python scripts/update_bls.py --fixture tests/fixtures/bls_sample.json --dry-run

BLS reports may be revised, so generatedAt is a fetch time, not a release time.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import date, datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
API_V1 = 'https://api.bls.gov/publicAPI/v1/timeseries/data/'
API_V2 = 'https://api.bls.gov/publicAPI/v2/timeseries/data/'
API = API_V2
# Seasonally adjusted BLS IDs. Levels are in thousands unless noted.
SERIES = {
    'nfp_level': 'CES0000000001',
    'private_level': 'CES0500000001',
    'unrate': 'LNS14000000',
    'u6': 'LNS13327709',
    'part': 'LNS11300000',
    'emratio': 'LNS12300000',
    'primeage': 'LNS11300060',
    'unemployed_level': 'LNS13000000',
    'wage_level': 'CES0500000003',
    'hours': 'CES0500000002',
    'temp_level': 'CES6056132001',
    'jolts': 'JTS000000000000000JOL',
    'hire': 'JTS000000000000000HIR',
    'quits': 'JTS000000000000000QUR',
    'layoff': 'JTS000000000000000LDR',
    'longterm': 'LNS13008636',
    'parttime': 'LNS12032194',
}
SOURCES = {
    'nfp': 'BLS · CES', 'private': 'BLS · CES', 'wage_level': 'BLS · CES',
    'wage_mom': 'BLS · CES · حساب شهري', 'wage': 'BLS · CES · حساب سنوي',
    'temp': 'BLS · CES', 'hours': 'BLS · CES',
    'unrate': 'BLS · CPS', 'u6': 'BLS · CPS', 'part': 'BLS · CPS',
    'emratio': 'BLS · CPS', 'primeage': 'BLS · CPS',
    'longterm': 'BLS · CPS', 'parttime': 'BLS · CPS',
    'jolts': 'BLS · JOLTS', 'hire': 'BLS · JOLTS',
    'quits': 'BLS · JOLTS', 'layoff': 'BLS · JOLTS',
    'beveridge': 'BLS · JOLTS/CPS · محسوب',
    'nfp3': 'BLS · CES · متوسط 3 أشهر',
    'nfp12': 'BLS · CES · متوسط 12 شهرًا',
    'longshare': 'BLS · CPS · نسبة محسوبة',
}
MULTIPLIERS = {'jolts': 0.001, 'longterm': 0.001, 'parttime': 0.001}
MIN_KEYS = {'nfp', 'unrate', 'part', 'wage_level', 'hours', 'jolts'}


def monthnum(s: str) -> int:
    y, m = map(int, s.split('-'))
    if not (1900 <= y <= 2100 and 1 <= m <= 12):
        raise ValueError(f'Bad reference month: {s}')
    return y * 12 + m


def fetch() -> dict:
    now = date.today()
    # v2 requires free registration; the public unregistered endpoint is v1.
    key = os.environ.get('BLS_API_KEY', '').strip()
    endpoint = API_V2 if key else API_V1
    body = {'seriesid': list(SERIES.values()), 'startyear': str(now.year - 5), 'endyear': str(now.year)}
    if key:
        body['registrationkey'] = key
    req = urllib.request.Request(endpoint, data=json.dumps(body).encode('utf-8'),
                                 headers={'Content-Type': 'application/json',
                                          'User-Agent': 'ECONINTEL/1.1 (research data dashboard)'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            return json.load(resp)
    except (urllib.error.URLError, TimeoutError, ValueError) as err:
        raise RuntimeError(f'BLS request failed; existing data were preserved: {err}') from err


def parse_payload(payload: dict) -> dict[str, list[list]]:
    if payload.get('status') != 'REQUEST_SUCCEEDED':
        raise ValueError(f"BLS returned {payload.get('status')}: {payload.get('message')}")
    series = payload.get('Results', {}).get('series', [])
    by_id = {}
    allowed = set(SERIES.values())
    for item in series:
        sid = item.get('seriesID')
        if sid not in allowed:
            continue
        rows = {}
        for obs in item.get('data', []):
            period = obs.get('period', '')
            if len(period) != 3 or not period.startswith('M') or period == 'M13':
                continue
            try:
                month = f"{int(obs['year']):04d}-{int(period[1:]):02d}"
                monthnum(month)
                value = float(str(obs['value']).replace(',', ''))
                if not (-1e9 < value < 1e9):
                    continue
                rows[month] = value
            except (ValueError, TypeError, KeyError, OverflowError):
                continue
        if rows:
            by_id[sid] = [[k, rows[k]] for k in sorted(rows)]
    return by_id


def consecutive_change(rows: list, periods: int = 1, pct: bool = False) -> list[list]:
    by_month = {monthnum(k): v for k, v in rows}
    values = []
    for key, val in sorted(by_month.items()):
        old = by_month.get(key - periods)
        if old is None or (pct and old == 0):
            continue
        derived = (100 * (val / old - 1)) if pct else val - old
        y, m = divmod(key - 1, 12)
        values.append([f'{y:04d}-{m + 1:02d}', round(derived, 4)])
    return values


def construct(raw: dict, fetched_at: str) -> dict:
    def add(rows, source_id: str, output_id: str, mult=1.0):
        if not rows:
            return
        history = [[k, round(v * mult, 5)] for k, v in rows]
        out[output_id] = {'value': history[-1][1], 'date': history[-1][0],
                          'history': history, 'source': SOURCES[output_id],
                          'seriesId': source_id, 'status': 'api', 'observedAt': fetched_at}
    out = {}
    for key, sid in SERIES.items():
        rows = raw.get(sid, [])
        if not rows:
            continue
        if key in ('nfp_level', 'private_level', 'temp_level'):
            target = {'nfp_level': 'nfp', 'private_level': 'private', 'temp_level': 'temp'}[key]
            add(consecutive_change(rows), sid, target)
        elif key == 'wage_level':
            add(rows, sid, 'wage_level')
            add(consecutive_change(rows, 1, pct=True), sid, 'wage_mom')
            add(consecutive_change(rows, 12, pct=True), sid, 'wage')
        elif key == 'unemployed_level':
            continue
        else:
            add(rows, sid, key, MULTIPLIERS.get(key, 1.0))
    # Additional automatically derived metrics: preserve only consecutive windows.
    nfp = out.get('nfp', {}).get('history', [])
    for months in (3, 12):
        windows = []
        by_month = {monthnum(k): v for k, v in nfp}
        for k in sorted(by_month):
            if all(k - j in by_month for j in range(months)):
                y, m = divmod(k-1, 12)
                windows.append([f'{y:04d}-{m+1:02d}', round(sum(by_month[k-j] for j in range(months))/months, 4)])
        add(windows, f'derived:CES0000000001:{months}M', f'nfp{months}')
    # Long-term unemployed share uses aligned numerator and denominator.
    longterm = dict(raw.get(SERIES['longterm'], []))
    jobless_all = dict(raw.get(SERIES['unemployed_level'], []))
    longshare = [[d, round(100*longterm[d]/jobless_all[d], 4)]
                 for d in sorted(set(longterm)&set(jobless_all)) if jobless_all[d] > 0]
    add(longshare, 'derived:LNS13008636/LNS13000000', 'longshare')
    # Beveridge ratio must compare the SAME reference month, not latest of two disparate months.
    openings = dict(raw.get(SERIES['jolts'], []))
    jobless = dict(raw.get(SERIES['unemployed_level'], []))
    common = sorted(set(openings).intersection(jobless))
    ratio = [[d, round(openings[d] / jobless[d], 4)] for d in common if jobless[d] > 0]
    add(ratio, 'derived:JOLTS+LNS13000000', 'beveridge')
    if not MIN_KEYS.issubset(out):
        raise ValueError('BLS missing required indicator series: ' + ', '.join(sorted(MIN_KEYS - set(out))))
    # Prevent publishing a completely obsolete payload as if newly refreshed.
    current = date.fromisoformat(fetched_at[:10])
    observed = monthnum(out['nfp']['date'])
    current_month = monthnum(f'{current.year:04d}-{current.month:02d}')
    if observed > current_month:
        raise ValueError('Payroll reference month is in the future')
    if observed < current_month - 3:
        raise ValueError('Latest BLS payroll observation is over three months old')
    return {'generatedAt': fetched_at, 'provider': 'U.S. Bureau of Labor Statistics · Public Data API v2',
            'apiUrl': API_V2 if os.environ.get('BLS_API_KEY') else API_V1, 'metrics': out}


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                     prefix=path.name + '.', suffix='.tmp', delete=False) as tmp:
        tmp.write(content)
        tempname = tmp.name
    os.replace(tempname, path)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixture', type=Path, help='Use saved response, without network (testing)')
    parser.add_argument('--dry-run', action='store_true', help='Validate and print only; do not write')
    args = parser.parse_args(argv)
    payload = json.loads(args.fixture.read_text(encoding='utf-8')) if args.fixture else fetch()
    parsed = parse_payload(payload)
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    result = construct(parsed, now)
    print('Validated official indicators:', len(result['metrics']))
    print('Reference months:', ', '.join(f'{k}={v["date"]}' for k, v in result['metrics'].items()))
    if not args.dry_run:
        compact = json.dumps(result, ensure_ascii=False, separators=(',', ':'))
        atomic_write(ROOT / 'data' / 'official-latest.json', json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        atomic_write(ROOT / 'assets' / 'official-data.js',
                     '/* Generated from BLS data; see data/official-latest.json. */\nwindow.ECON_OFFICIAL_DATA = ' + compact + ';\n')
        print('Updated assets/official-data.js and data/official-latest.json')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print('Update cancelled — prior data remain intact:', str(exc), file=sys.stderr)
        sys.exit(1)
