#!/usr/bin/env python3
"""Read-only month-end FRED/ALFRED as-of pilot for ECONINTEL. No writes to production.

Requires FRED_API_KEY in environment (never stored). Every as-of date queries ALFRED's
real-time historical view. An observation/reference date is NOT a publication date.
"""
from __future__ import annotations
import json, os, sys, time, urllib.parse, urllib.request, urllib.error
from collections import OrderedDict
from datetime import date
from pathlib import Path

# FRED IDs manually selected to align with existing 12 core ECONINTEL input anchors.
# PAYEMS payroll level => nfp3/nfp12 rolling averages of period-to-period changes.
SOURCES = OrderedDict([
    ('PAYEMS', ('nfp3','nfp12')),
    ('UNRATE', ('unrate',)),
    ('U6RATE', ('u6',)),
    ('EMRATIO', ('emratio',)),
    ('LNS11300060', ('primeage',)),
    ('JTSJOL', ('jolts',)),
    ('JTSHIR', ('hire',)),
    ('IC4WSA', ('claims4wk',)),
    ('CCSA', ('continuing',)),
    ('CES0500000021', ('diffusion',)),
    ('AWHAETP', ('hours',)),
])
# Actual units checked against FRED series metadata (raw payroll and job openings
# in thousands; IC4WSA & CCSA in persons, site displays claims as thousands or millions).
SCALES = {'JTSJOL':1/1000, 'IC4WSA':1/1000, 'CCSA':1/1_000_000}
WEEKLY = {'IC4WSA','CCSA'}
CHECKPOINTS = ['2022-06-30','2022-07-31','2023-12-31','2024-08-31','2024-09-30','2025-11-30','2026-10-31']
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT / 'pit_research_output'
URL='https://api.stlouisfed.org/fred/series/observations'

def parse_observations(payload, cutoff, weekly=False):
    # Realtime must cover actual as-of; duplicate rows must not override silently.
    rows={}
    for r in payload.get('observations',[]):
        p=str(r.get('date',''))
        if len(p)!=10 or p>cutoff: continue
        if not (r.get('realtime_start','0000-01-01')<=cutoff<=r.get('realtime_end','9999-12-31')):
            continue
        v=r.get('value','.')
        try: value=float(v)
        except (TypeError, ValueError): continue
        key=p if weekly else p[:7]
        if key in rows and rows[key]!=value:
            raise ValueError('Conflicting observations for a real-time period: '+key)
        rows[key]=value
    return [[p,rows[p]] for p in sorted(rows)]

def month_seq_equal(a,b):
    y,m=map(int,a.split('-'));y2,m2=map(int,b.split('-'))
    return y2*12+m2 == y*12+m+1

def payroll_averages(payems,window):
    changes=[]
    for (prev,v0),(cur,v1) in zip(payems,payems[1:]):
        if month_seq_equal(prev,cur): changes.append([cur,round(v1-v0,5)])
    result=[]
    for idx in range(window-1,len(changes)):
        chunk=changes[idx-window+1:idx+1]
        if len(chunk)!=window or any(not month_seq_equal(chunk[i-1][0],chunk[i][0]) for i in range(1,window)):
            continue
        result.append([chunk[-1][0],round(sum(val for _,val in chunk)/window,5)])
    return result

def get(api_key,series,cutoff,attempts=3):
    params={
        'series_id':series,'api_key':api_key,'file_type':'json',
        'observation_start':'2020-01-01','observation_end':cutoff,
        'realtime_start':cutoff,'realtime_end':cutoff,'limit':'100000'
    }
    query=urllib.parse.urlencode(params)
    req=urllib.request.Request(URL+'?'+query,headers={'User-Agent':'ECONINTEL-PIT-Research/0.1'})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req,timeout=30) as response:
                obj=json.loads(response.read().decode('utf-8'))
            if 'error_code' in obj: raise RuntimeError(f'FRED returned error code {obj["error_code"]}')
            if int(obj.get('count',len(obj.get('observations',[])))) > len(obj.get('observations',[])):
                raise RuntimeError('FRED pagination needed; refusing partial series')
            return obj
        except urllib.error.HTTPError as err:
            # Never print full request URL or contents which can carry a credential.
            if err.code not in (429,500,502,503,504) or attempt==attempts-1:
                raise RuntimeError('FRED HTTP status '+str(err.code)) from None
        except (urllib.error.URLError,TimeoutError) as err:
            if attempt==attempts-1: raise RuntimeError('FRED connection failed') from None
        time.sleep(min(2+attempt*3,8))
    raise RuntimeError('Unknown query failure')

def normalize(raw, cutoff):
    """Convert historical FRED series to the exact six-pillar input units.
    Missing sources remain missing: NEVER fill by recent, revised, or seed data.
    """
    metrics={};errors={};trace={}
    for sid,resp in raw.items():
        if 'error' in resp:
            errors[sid]=resp['error'];continue
        h=parse_observations(resp,cutoff,sid in WEEKLY)
        if sid=='PAYEMS':
            for window,metric in ((3,'nfp3'),(12,'nfp12')):
                series=payroll_averages(h,window)
                if series:
                    metrics[metric]={'id':metric,'live':True,'custom':False,'date':series[-1][0],
                         'value':series[-1][1],'history':series,'source':'ALFRED PAYEMS derived as-of '+cutoff}
            trace[sid]={'lastObservedDate':h[-1][0] if h else None,'numObservations':len(h)}
        else:
            metric=SOURCES[sid][0]
            k=SCALES.get(sid,1.0)
            scaled=[[x,round(v*k,5)] for x,v in h]
            if scaled:
                metrics[metric]={'id':metric,'live':True,'custom':False,'date':scaled[-1][0],
                          'value':scaled[-1][1],'history':scaled,'source':'ALFRED '+sid+' as-of '+cutoff}
            trace[sid]={'lastObservedDate':h[-1][0] if h else None,'numObservations':len(h)}
    return metrics,trace,errors

def main():
    key=os.getenv('FRED_API_KEY','').strip()
    if not key:
        print('ERROR: FRED_API_KEY is unavailable (no key requested or printed).',file=sys.stderr)
        sys.exit(2)
    OUT.mkdir(exist_ok=True)
    assembled=[]
    failed=0
    for cutoff in CHECKPOINTS:
        print('As-of',cutoff,flush=True)
        raw={}
        for sid in SOURCES:
            try:
                raw[sid]=get(key,sid,cutoff)
                print('  '+sid+': retrieved',flush=True)
            except Exception as exc:
                raw[sid]={'error':str(exc)};failed+=1
                print('  '+sid+': unavailable ('+str(exc)+')',flush=True)
        metrics,trace,errors=normalize(raw,cutoff)
        assembled.append({'cutoff':cutoff,'metrics':metrics,'trace':trace,'unavailable':errors,
                          'anchorCount':len(metrics),'anchorTotal':12})
    result={
        'schemaVersion':1,'mode':'ALFRED month-end real-time as-of — RESEARCH ONLY',
        'limitations':['Not exact release-hour, revision-event or vintage-publication backtest.',
                       'FRED availability and revisions may differ from initial BLS release.',
                       'Never silently backfills missing indicators or time periods.',
                       'No weights, forecasts, live data or files in production were changed.'],
        'pilotCutoffs':CHECKPOINTS,'frames':assembled,'sourceUrl':'https://fred.stlouisfed.org/docs/api/fred/series_observations.html'}
    target=OUT/'pit_month_end_frames.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Saved',target,'Unavailable requests:',failed,flush=True)
    if all(x['anchorCount']==0 for x in assembled):
        print('ERROR: no valid PIT observations. Not proceeding to classification.',file=sys.stderr)
        sys.exit(1)

if __name__=='__main__': main()
