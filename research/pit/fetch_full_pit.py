#!/usr/bin/env python3
"""ECONINTEL: full 2022-present monthly ALFRED vintages, research-only.

Optimizes vintage retrieval using FRED API output_type=1 (observations by
real-time period) and validates the reconstructed snapshots against direct
ALFRED as-of calls at selected dates. All output stays in pit_full_output/.
No synthetic values, secret prints, or writes to the production dashboard.
"""
from __future__ import annotations
import calendar
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from collections import Counter
from fetch_pit import SOURCES, normalize, parse_observations, ROOT, URL

OUT = ROOT / 'pit_full_output'
START = '2022-04'
FIRST = '2022-04-30'
# Series not on FRED/ALFRED: there is no valid vintage returned by this endpoint.
# The real source is BLS CES0500000021; NEVER substitute current revised history.
UNAVAILABLE = {'CES0500000021': 'Official BLS diffusion CES0500000021 is not in ALFRED (pilot returned HTTP 400). Historical release-vintages not yet obtained.'}
API_SERIES = tuple(s for s in SOURCES if s not in UNAVAILABLE)
LIMIT = 100000


def cutoffs(today: date, start: str = START, include_partial: bool = True):
    y, m = map(int, start.split('-'))
    out = []
    while True:
        last = date(y, m, calendar.monthrange(y, m)[1])
        if last > today: break
        out.append({'asOf': last.isoformat(), 'month': f'{y:04d}-{m:02d}', 'completeMonth': True})
        m += 1
        if m == 13: y, m = y + 1, 1
    if include_partial and today.isoformat() > (out[-1]['asOf'] if out else FIRST):
        out.append({'asOf': today.isoformat(), 'month': today.strftime('%Y-%m'), 'completeMonth': False})
    return out


def _get_page(key, sid, rt_start, rt_end, offset=0, limit=LIMIT, retries=4):
    params = {
        'series_id': sid, 'api_key': key, 'file_type': 'json',
        'observation_start': '2020-01-01', 'observation_end': rt_end,
        'realtime_start': rt_start, 'realtime_end': rt_end,
        'output_type': 1, 'limit': limit, 'offset': offset, 'sort_order':'asc'
    }
    req = urllib.request.Request(URL + '?' + urllib.parse.urlencode(params), headers={'User-Agent': 'ECONINTEL-PIT-full-research/1.0'})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=50) as resp:
                body = json.load(resp)
            if 'error_code' in body or not isinstance(body.get('observations'), list):
                raise RuntimeError('ALFRED returned malformed or error response')
            return body
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or attempt == retries-1:
                raise RuntimeError(f'ALFRED HTTP {e.code} for {sid}') from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            if attempt == retries-1:
                raise RuntimeError(f'ALFRED connection/JSON failure for {sid}') from None
        time.sleep(min(2 ** (attempt+1), 15))
    raise RuntimeError('ALFRED retry limit reached')


def _all_pages(key, sid, rt_start, rt_end):
    offset = 0
    records = []
    for _ in range(30):
        obj = _get_page(key, sid, rt_start, rt_end, offset)
        chunk = obj['observations']
        records.extend(chunk)
        count = int(obj.get('count', len(records)))
        if len(chunk) == 0 and len(records) < count:
            raise RuntimeError(f'ALFRED missing pagination records for {sid}')
        if len(records) >= count:
            return records
        offset += len(chunk)
    raise RuntimeError(f'ALFRED pagination safety cap exceeded for {sid}')


def asof_rows(rows, cutoff, sid):
    """Return one row per observation date as of cutoff; fail on conflicting vintages."""
    out = {}
    for row in rows:
        observed = str(row.get('date', ''))
        if observed > cutoff or len(observed) != 10: continue
        rt_start, rt_end = str(row.get('realtime_start','')), str(row.get('realtime_end',''))
        if not (rt_start <= cutoff <= rt_end): continue
        try: v = float(row.get('value','.'))
        except (ValueError,TypeError): continue
        if not math.isfinite(v): continue
        if observed in out and out[observed] != v:
            raise ValueError(f'Ambiguous overlapping ALFRED vintages for {sid} {observed} {cutoff}')
        out[observed] = v
    return [{'date':p, 'value':str(v), 'realtime_start':cutoff, 'realtime_end':cutoff}
            for p,v in sorted(out.items())]


def comparable_rows(rows, cutoff, sid):
    """FRED's direct query and reconstructed vintage must have identical history."""
    return parse_observations({'observations':asof_rows(rows,cutoff,sid)},cutoff)


def live_asof(key,sid,cutoff):
    return _all_pages(key,sid,cutoff,cutoff)


def download(today=None, key=None, out_folder=None):
    today = today or datetime.now(timezone.utc).date()
    key = key or os.environ.get('FRED_API_KEY','').strip()
    if not key: raise RuntimeError('FRED_API_KEY missing from GitHub Secrets; no key needed in chat')
    dates = cutoffs(today)
    if not dates: raise RuntimeError('No completed month to test')
    start, end = dates[0]['asOf'], dates[-1]['asOf']
    # Three as-of checks protect against accidental misuse of bulk vintage intervals.
    checks = sorted({start, dates[min(len(dates)-1,len(dates)//2)]['asOf'], end})
    snapshots = {d['asOf']: {} for d in dates}
    failures = {}
    modes = {}
    for sid in API_SERIES:
        print('Retrieving historical ALFRED revisions:', sid, flush=True)
        try:
            bulk = _all_pages(key,sid,start,end)
            valid = True
            for chk in checks:
                direct = live_asof(key,sid,chk)
                if comparable_rows(bulk,chk,sid) != comparable_rows(direct,chk,sid):
                    valid = False
                    print('  Bulk intervals differ from direct as-of; using direct monthly snapshots:',sid,flush=True)
                    break
            if valid:
                modes[sid] = {'mode':'bulk-validated', 'rows':len(bulk), 'checked':checks}
                for d in dates:
                    cut = d['asOf']
                    snapshots[cut][sid] = {'observations':asof_rows(bulk,cut,sid)}
            else:
                modes[sid]={'mode':'direct-monthly-fallback','checked':checks}
                for d in dates:
                    cut=d['asOf']
                    try: snapshots[cut][sid]={'observations':asof_rows(live_asof(key,sid,cut),cut,sid)}
                    except Exception as e: snapshots[cut][sid]={'error':str(e)}
        except Exception as e:
            # Some ALFRED series reject a broad vintage-window query.
            # Complete the research with exact monthly as-of requests instead.
            print('  Bulk request unavailable; using direct monthly as-of:',sid,flush=True)
            successes=0
            per_date_errors=0
            for d in dates:
                cut=d['asOf']
                try:
                    snapshots[cut][sid]={'observations':asof_rows(live_asof(key,sid,cut),cut,sid)}
                    successes+=1
                except Exception as per_err:
                    snapshots[cut][sid]={'error':str(per_err)}
                    per_date_errors+=1
            modes[sid]={'mode':'direct-monthly-after-bulk-error', 'availableDates':successes,
                        'missingDates':per_date_errors,'bulkError':str(e)}
            if not successes: failures[sid]=str(e)
    frames=[]
    for d in dates:
        raw={**snapshots[d['asOf']], **{s:{'error':e} for s,e in UNAVAILABLE.items()}}
        metrics,trace,errors=normalize(raw,d['asOf'])
        # Assert no fabricated future data, and no current-vintage or seed values.
        for metric in metrics.values():
            if metric['date'][:10] > d['asOf']:
                raise RuntimeError(f'Future observation leaked into {d["asOf"]}')
            if not str(metric.get('source','')).startswith('ALFRED '):
                raise RuntimeError('Non-ALFRED data leaked into research frame')
        frames.append({**d,'metrics':metrics,'trace':trace,'unavailable':errors,
                       'anchorCount':len(metrics),'anchorTotal':12})
        print(f"  {d['asOf']}: {len(metrics)}/12 official anchors",flush=True)
    output={'schemaVersion':2,'mode':'ALFRED as-of month-end, plus clearly marked current partial month',
            'asOfGeneratedAt':datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'limitations':[
              'Historical vintages by end-of-day; does not reconstruct exact release-minute information.',
              'ALFRED historical availability can differ from BLS first publication.',
              'Diffusion (BLS CES0500000021) is deliberately MISSING until verified source vintages exist.',
              'No forecasting, calibration, evidence of causal prediction, or guaranteed economic truth.',
              'Research output only. Production data, weights and classification logic unchanged.'],
            'seriesModes':modes,'sourceErrors':{**failures, **UNAVAILABLE},
            'cutoffs':dates,'frames':frames}
    output_dir = Path(out_folder) if out_folder else OUT
    output_dir.mkdir(parents=True,exist_ok=True)
    target=output_dir/'pit_full_frames.json'
    target.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Saved',target,'frames',len(frames),'series failures',len(failures),'explicitly missing diffusion',flush=True)
    # Do not pretend to have validated a run where ALFRED sources largely failed.
    adequate=sum(f['anchorCount']>=9 for f in frames)
    if adequate < max(1,int(len(frames)*0.8)):
        raise RuntimeError(f'Insufficient PIT source coverage: {adequate}/{len(frames)} frames with 9+ anchors')
    return output


if __name__=='__main__':
    try: download()
    except Exception as e:
        print('PIT research failed safely (production unchanged):',str(e),file=sys.stderr)
        sys.exit(1)
