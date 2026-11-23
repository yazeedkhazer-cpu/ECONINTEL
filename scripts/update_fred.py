#!/usr/bin/env python3
"""Optional FRED official observations overlay, with quarterly and weekly frequency kept separate.

A free FRED_API_KEY is required. FRED series values are revised; the fetched
history is a *current vintage*, NOT an as-released historical backtest dataset.
"""
from __future__ import annotations
import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime

API = 'https://api.stlouisfed.org/fred/series/observations'
SERIES = ('ICSA', 'CCSA', 'ECIALLCIV', 'OPHNFB', 'ULCNFB', 'SAHMREALTIME', 'ADPMNUSNERSA')

def fetch_series(sid: str, key: str) -> dict:
    args = {'series_id':sid, 'api_key':key, 'file_type':'json',
            'observation_start':f'{date.today().year-7}-01-01', 'sort_order':'asc'}
    req = urllib.request.Request(API+'?'+urllib.parse.urlencode(args),
                                 headers={'User-Agent':'ECONINTEL/1.2 research'})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise RuntimeError(f'FRED {sid} failed: {exc}') from exc

def parse_observations(payload: dict) -> list[list]:
    if not isinstance(payload.get('observations'), list):
        raise ValueError('FRED missing observations')
    obs = {}
    for row in payload['observations']:
        try:
            day = date.fromisoformat(row['date'])
            val = float(row['value'])
            if not math.isfinite(val) or day > date.today():
                continue
            obs[day.isoformat()] = val
        except (ValueError, TypeError, KeyError):
            continue
    return [[d,v] for d,v in sorted(obs.items())]

def mentry(series_id: str, history: list[list], unit: str, transform=1.0, source=None, period='weekly') -> dict | None:
    if not history:
        return None
    vals = [[d, round(v*transform, 5)] for d,v in history]
    return {'date':vals[-1][0], 'value':vals[-1][1], 'history':vals,
            'source':source or f'FRED · {series_id}', 'seriesId':series_id,
            'status':'api', 'frequency':period, 'unit':unit}

def quarter_key(d: str) -> str:
    yr, mo = map(int,d[:7].split('-'))
    return f'{yr}-Q{(mo-1)//3+1}'

def quarter_history(rows: list[list], span: int, annualized=False) -> list[list]:
    d = {int(k[:4])*4 + (int(k[5:7])-1)//3: v for k,v in rows}
    out=[]
    for q in sorted(d):
        old=d.get(q-span)
        if old is None or old<=0:
            continue
        growth=(pow(d[q]/old,4)-1)*100 if annualized else (d[q]/old-1)*100
        yr, part = divmod(q,4)
        # chart history uses end-of-quarter months; data date uses quarter label
        out.append([f'{yr:04d}-{(part+1)*3:02d}',round(growth,4)])
    return out

def build(observations: dict[str,list[list]]) -> dict:
    """Pure conversion: returns only series whose frequency & source are verified."""
    result={}
    claims=observations.get('ICSA',[])
    if x:=mentry('ICSA',claims,'K',.001,source='U.S. DOL · FRED (ICSA)'):
        result['claims']=x
    # Exactly consecutive weekly dates: no imputation around holiday or missing weeks.
    moving=[]
    by_week={date.fromisoformat(d):v for d,v in claims}
    from datetime import timedelta
    for d in sorted(by_week):
        dates=[d-timedelta(days=7*i) for i in range(4)]
        if all(t in by_week for t in dates):
            moving.append([d.isoformat(),round(sum(by_week[t] for t in dates)/4,4)])
    if x:=mentry('derived:ICSA:4wk',moving,'K',.001,source='U.S. DOL · FRED · متوسط 4 أسابيع'):
        result['claims4wk']=x
    if x:=mentry('CCSA',observations.get('CCSA',[]),'M',.000001,source='U.S. DOL · FRED (CCSA)'):
        result['continuing']=x
    for sid, specs in [('ECIALLCIV',[('eci',1,False),('eciy',4,False)]),
                       ('OPHNFB',[('productivity',1,True)]),
                       ('ULCNFB',[('ulc',1,True)])]:
        for id,span,annual in specs:
            hist=quarter_history(observations.get(sid,[]),span,annualized=annual)
            if x:=mentry(sid,hist,'%',source=f'BLS via FRED · {sid} · calculated',period='quarterly'):
                x['date']=quarter_key(hist[-1][0]); result[id]=x
    # ADP publishes the monthly level (persons) in FRED. ECONINTEL's ADP card is
    # monthly CHANGE in thousands, so compute it only for consecutive months.
    adp_levels=observations.get('ADPMNUSNERSA',[])
    adp_months={int(d[:4])*12+int(d[5:7]):v for d,v in adp_levels}
    adp_changes=[]
    for k in sorted(adp_months):
        if k-1 in adp_months:
            year, month=divmod(k-1,12)
            adp_changes.append([f'{year:04d}-{month+1:02d}',round((adp_months[k]-adp_months[k-1])/1000,4)])
    if x:=mentry('ADPMNUSNERSA',adp_changes,'K',source='ADP · National Employment Report via FRED · calculated',period='monthly'):
        result['adp']=x
    if x:=mentry('SAHMREALTIME',observations.get('SAHMREALTIME',[]),'pp',source='FRED · Sahm rule',period='monthly'):
        x['history']=[[d[:7],v] for d,v in x['history']]
        x['date']=x['date'][:7]
        result['sahm']=x
    return result

def fetch() -> dict:
    key = os.environ.get('FRED_API_KEY','').strip()
    if not key:
        return {}
    return build({sid:parse_observations(fetch_series(sid,key)) for sid in SERIES})
