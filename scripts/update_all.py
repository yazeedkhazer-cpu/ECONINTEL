#!/usr/bin/env python3
"""ECONINTEL v1.2 - validate all data BEFORE atomic publication.

The updater fetches BLS and optionally FRED. A failure never changes the
published file. Prior FRED observations are retained if credentials are absent
or the optional FRED provider temporarily fails, but identified as old data.
"""
from __future__ import annotations
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import sys
import update_bls as bls
import update_fred as fred
import update_diffusion as diffusion

ROOT=Path(__file__).resolve().parents[1]

def output_payload(bls_payload: dict, fetched_at: str, fred_data: dict | None = None,
                   previous: dict | None = None, fred_error: str | None = None,
                   diffusion_data: dict | None = None, diffusion_error: str | None = None) -> dict:
    fresh=bls.construct(bls.parse_payload(bls_payload),fetched_at)
    result={key:value for key,value in fresh['metrics'].items() if key not in ('isman','isserv')}
    oldmetrics=(previous or {}).get('metrics',{})
    # Keep dated last-known FRED values if optional source unavailable, not the seed as "live".
    for mid, old in oldmetrics.items():
        if isinstance(old,dict) and (
                str(old.get('seriesId','')).startswith('derived:ICSA') or
                old.get('seriesId') in fred.SERIES or
                (old.get('status')=='api' and old.get('seriesId') in (
                    'BLS:CES:SUMMARY_B:DIFFUSION:PRIVATE:1M', bls.DIFFUSION_SERIES_ID))):
            result.setdefault(mid,old)
    if fred_data:
        for item in fred_data.values():
            item['observedAt']=fetched_at
        result.update(fred_data)
    if diffusion_data:
        diffusion_data['observedAt']=fetched_at
        # Extend historical window across refreshes; newer official BLS revisions win.
        older=result.get('diffusion',{}).get('history',[])
        now=diffusion_data.get('history',[])
        diffusion_data['history']=[[m,v] for m,v in sorted({**dict(older),**dict(now)}.items())]
        result['diffusion']=diffusion_data
    result.pop('isman',None);result.pop('isserv',None)
    fresh['metrics']=result
    fresh['sources']={
      'BLS_DIFFUSION':{'status':'updated' if diffusion_data else 'unavailable',
                       'fetchedAt':fetched_at if diffusion_data else None,
                       'note':diffusion_error or 'BLS Table B: no validated fresh observation'},
      'BLS':{'status':'updated','fetchedAt':fetched_at,'endpoint':fresh['apiUrl']},
      'FRED':{'status':'updated' if fred_data else ('not-configured' if not os.environ.get('FRED_API_KEY') else 'unavailable'),
              'fetchedAt':fetched_at if fred_data else None,
              'note':fred_error or 'Optional provider; set FRED_API_KEY in GitHub secrets'}
    }
    fresh['coverage']={'automatic':len(set(result).intersection({
     'nfp','private','unrate','u6','part','emratio','wage','wage_mom','wage_level','hours','diffusion','temp','jolts','hire','layoff','claims','longterm','parttime','primeage','quits','claims4wk','continuing','beveridge','sahm','adp','eci','eciy','productivity','ulc','nfp3','nfp12','longshare'})), 'total':32}
    return fresh

def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--bls-fixture',type=Path)
    parser.add_argument('--fred-fixture',type=Path)
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args(argv)
    payload=json.loads(args.bls_fixture.read_text(encoding='utf8')) if args.bls_fixture else bls.fetch()
    stamp=datetime.now(timezone.utc).isoformat(timespec='seconds')
    prior_path=ROOT/'data/official-latest.json'
    previous=json.loads(prior_path.read_text(encoding='utf8')) if prior_path.exists() else None
    fred_data={};error=None
    if args.fred_fixture:
        fixture=json.loads(args.fred_fixture.read_text(encoding='utf8'))
        fred_data=fred.build({key:fred.parse_observations(val) for key,val in fixture.items()})
    elif os.environ.get('FRED_API_KEY'):
        try:
            fred_data=fred.fetch()
        except Exception as exc:
            error=str(exc)
            print('FRED unavailable; retaining last known FRED metrics:',error,file=sys.stderr)
    diffusion_data=None;diffusion_error=None
    # Test fixture runs are offline by design; keep external enrichment disabled.
    if not args.bls_fixture:
        try:
            checked=bls.construct(bls.parse_payload(payload),stamp)
            diffusion_data=(checked['metrics'].get('diffusion') or
                            diffusion.fetch(checked['metrics']['nfp']['date']))
        except Exception as exc:
            diffusion_error=str(exc)
            print('Diffusion unavailable; retaining previously verified data:',diffusion_error,file=sys.stderr)
    result=output_payload(payload,stamp,fred_data,previous,error,diffusion_data,diffusion_error)
    print(f"Validated {len(result['metrics'])}/32 indicators; BLS required, FRED and BLS diffusion optional")
    print('References: '+', '.join(f'{k}={v["date"]}' for k,v in result['metrics'].items()))
    if args.dry_run:
        return
    # BLS required values already validated by construct. These are published atomically.
    compact=json.dumps(result,ensure_ascii=False,separators=(',',':'))
    bls.atomic_write(ROOT/'data/official-latest.json',json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    bls.atomic_write(ROOT/'assets/official-data.js','/* Auto-generated; DO NOT manually edit. */\nwindow.ECON_OFFICIAL_DATA = '+compact+';\n')
    # Snapshot is a first-seen-by-this-updater timestamp, not a BLS release timestamp.
    # Preserve only when contents differ from previous snapshot, not on each polling run.
    def normalized(x):
        return {k:{key:v.get(key) for key in ('date','value','history')} for k,v in x.get('metrics',{}).items()}
    if not previous or normalized(previous)!=normalized(result):
        name=stamp[:19].replace('-','').replace(':','').replace('T','-')+'Z.json'
        bls.atomic_write(ROOT/'data/snapshots'/name,json.dumps({
            'capturedAt':stamp,'warning':'Capture time is not necessarily official release time; do not treat as historical release vintage',
            'metrics':result['metrics']},ensure_ascii=False,indent=2)+'\n')
    print('Saved official-latest.json, official-data.js and optional changed-data snapshot')

if __name__=='__main__':
    try: main()
    except Exception as e:
        print('Update aborted; existing files preserved:',e,file=sys.stderr)
        sys.exit(1)
