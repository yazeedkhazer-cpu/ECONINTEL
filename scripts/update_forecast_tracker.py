#!/usr/bin/env python3
"""ECONINTEL: official publication calendar + opt-in licensed consensus archive.

No market forecast values are created without a sourced record. Updates append
first-observed snapshots; provider LastUpdate is not treated as observation time.
Standard library only. No secret is ever persisted to the public JSON output.
"""
from __future__ import annotations
import argparse
import json
import math
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'data' / 'forecast-tracker.json'
ET = ZoneInfo('America/New_York')
UTC = timezone.utc
BLS_ICS = 'https://www.bls.gov/schedule/news_release/bls.ics'
DOL_SCHEDULE = 'https://oui.doleta.gov/unemploy/archive.asp'
TE_BASE = 'https://api.tradingeconomics.com/calendar/country/united%20states'
INDICATORS = ('nfp','private','unrate','wage_mom','wage','jolts','claims','adp','eci','productivity','ulc')
GROUPS = {
 'nfp':('nfp','private','unrate','wage_mom','wage'),
 'jolts':('jolts',), 'claims':('claims',), 'adp':('adp',),
 'eci':('eci',), 'productivity':('productivity','ulc')
}
SOURCE = {'nfp':'https://www.bls.gov/schedule/news_release/empsit.htm',
 'jolts':'https://www.bls.gov/schedule/news_release/jolts.htm',
 'eci':'https://www.bls.gov/schedule/news_release/eci.htm',
 'productivity':'https://www.bls.gov/schedule/news_release/prod2.htm',
 'claims':DOL_SCHEDULE, 'adp':'https://adpemploymentreport.com/'}


def iso(dt:datetime)->str:
 return dt.astimezone(UTC).isoformat(timespec='seconds').replace('+00:00','Z')


def parse_dt(x:str)->datetime:
 if not isinstance(x,str): raise ValueError('Invalid ISO datetime')
 d=datetime.fromisoformat(x.replace('Z','+00:00'))
 if d.tzinfo is None: raise ValueError('Missing timezone')
 return d.astimezone(UTC)


def http_text(url:str)->str:
 request=urllib.request.Request(url,headers={'User-Agent':'ECONINTEL Research Data / calendar verification (public release dates)','Accept':'text/calendar,text/plain,application/json,*/*'})
 with urllib.request.urlopen(request,timeout=35) as resp: return resp.read(2_000_000).decode('utf-8','replace')


def parse_ics(raw:str)->list[dict]:
 """Parse published calendar VEVENTS. ICS timestamps MUST be explicit."""
 if 'BEGIN:VEVENT' not in raw: raise ValueError('No VEVENT in BLS calendar')
 lines=[]
 for line in raw.replace('\r\n','\n').split('\n'):
  if line.startswith((' ','\t')) and lines: lines[-1]+=line[1:]
  else: lines.append(line)
 out=[]; cur=None
 for line in lines:
  if line=='BEGIN:VEVENT':cur={};continue
  if line=='END:VEVENT':
   if cur:
    title=cur.get('SUMMARY','').replace('\\,',',').strip()
    typ=release_type(title)
    rawdt=cur.get('DTSTART')
    if typ and rawdt:
     try:when=ics_timestamp(rawdt)
     except (ValueError,TypeError):continue
     out.append({'group':typ,'releaseAt':iso(when),'reference':'','status':'official_calendar','source':SOURCE[typ]})
   cur=None;continue
  if cur is not None and ':' in line:
   key,val=line.split(':',1)
   # Retain the TZID attribute for DTSTART.
   if key.startswith('DTSTART'):cur['DTSTART']=(key,val)
   elif key.startswith('SUMMARY'):cur['SUMMARY']=val
 return sorted({(x['group'],x['releaseAt']):x for x in out}.values(),key=lambda x:x['releaseAt'])


def release_type(title:str)->str|None:
 s=title.lower()
 if 'job openings and labor turnover' in s:return 'jolts'
 if 'employment cost index' in s:return 'eci'
 if 'employment situation' in s:return 'nfp'
 if re.search(r'\bproductivity and costs\b',s):return 'productivity'
 return None


def ics_timestamp(t:tuple[str,str])->datetime:
 key,value=t
 if re.fullmatch(r'\d{8}',value): raise ValueError('Date only; no scheduled time')
 if not re.fullmatch(r'\d{8}T\d{6}Z?',value):raise ValueError('Unsupported ICS timestamp')
 utc=value.endswith('Z')
 dt=datetime.strptime(value.rstrip('Z'),'%Y%m%dT%H%M%S')
 if utc:return dt.replace(tzinfo=UTC)
 match=re.search(r'TZID=([^;:]+)',key)
 tz=ZoneInfo(match.group(1)) if match else ET
 return dt.replace(tzinfo=tz).astimezone(UTC)


def claims_calendar(now:datetime)->list[dict]:
 """DOL's public weekly rule with explicitly announced holiday exceptions."""
 special={date(2026,11,25),date(2027,11,10),date(2027,11,24)}
 result=[]; start=now.astimezone(ET).date()-timedelta(days=1)
 for i in range(100):
  day=start+timedelta(days=i)
  if day.weekday()!=3 and day not in special:continue
  if day in (date(2026,11,26),date(2027,11,11),date(2027,11,25)):continue
  moment=datetime(day.year,day.month,day.day,8,30,tzinfo=ET).astimezone(UTC)
  if moment<now-timedelta(hours=1):continue
  result.append({'group':'claims','releaseAt':iso(moment),'reference':'',
                 'status':'official_exception' if day in special else 'official_weekly_rule',
                 'source':DOL_SCHEDULE})
  if len(result)>=16:break
 return result


def merge_calendar(existing:list[dict],new:list[dict],now:datetime)->list[dict]:
 combined={}
 # Retain official future events and recent past events (historical linking).
 for e in existing+new:
  try:dt=parse_dt(e['releaseAt']);kind=e['group']
  except (ValueError,KeyError,TypeError):continue
  if kind not in GROUPS:continue
  if dt<now-timedelta(days=120) or dt>now+timedelta(days=600):continue
  key=(kind,e['releaseAt'])
  old=combined.get(key)
  if old is None or e.get('status')=='official_calendar':combined[key]=e
 return sorted(combined.values(),key=lambda e:(e['releaseAt'],e['group']))


def classify_event(label:str)->str|None:
 """Only high-confidence one-to-one matches; no overlap or fuzzy guessing."""
 name=re.sub(r'\s+',' ',str(label).strip().lower().replace('–','-').replace('—','-'))
 exact={
 'non farm payrolls':'nfp', 'nonfarm payrolls':'nfp','non-farm payrolls':'nfp',
 'private nonfarm payrolls':'private','private non-farm payrolls':'private',
 'unemployment rate':'unrate',
 'average hourly earnings mom':'wage_mom', 'average hourly earnings (mom)':'wage_mom',
 'average hourly earnings yoy':'wage','average hourly earnings (yoy)':'wage',
 'jolts job openings':'jolts','jolts job openings (monthly)':'jolts',
 'initial jobless claims':'claims',
 'adp employment change':'adp','adp employment change (monthly)':'adp',
 'employment cost index qoq':'eci','employment cost index (qoq)':'eci',
 'nonfarm productivity qoq':'productivity','nonfarm productivity (qoq)':'productivity',
 'unit labor costs qoq':'ulc','unit labor costs (qoq)':'ulc'
 }
 return exact.get(name)


def normalized_forecast(raw:str,indicator:str)->float|None:
 """Match website units: K jobs/claims, M openings, % other rates."""
 if raw is None:return None
 v=str(raw).strip().replace(' ','')
 if not v:return None
 match=re.fullmatch(r'([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)([KMB]?)(%?)',v,re.I)
 if not match:return None
 x=float(match.group(1).replace(',',''))
 suffix=match.group(2).upper()
 if indicator in ('nfp','private','claims','adp'):
  x*= {'':1,'K':1,'M':1000,'B':1_000_000}.get(suffix,0)
  if suffix not in ('','K','M','B') or match.group(3):return None
 elif indicator=='jolts':
  x*= {'':1,'K':0.001,'M':1,'B':1000}.get(suffix,0)
  if match.group(3):return None
 else:
  if suffix:return None
 if not math.isfinite(x) or abs(x)>1_000_000:return None
 return round(x,6)


def candidate_event(event_at:datetime,group:str,calendar:list[dict])->dict|None:
 matches=[]
 for item in calendar:
  if item.get('group')!=group:continue
  try:delta=abs((parse_dt(item['releaseAt'])-event_at).total_seconds())
  except (ValueError,KeyError):continue
  if delta<=86400:matches.append((delta,item))
 matches.sort(key=lambda x:x[0]);return matches[0][1] if matches else None


def provider_calendar_rows(data:dict,rows:list[dict],now:datetime)->list[dict]:
 """Provider fallback ONLY when no nearby official event; explicitly unverified."""
 proposed={}
 for row in rows:
  if row.get('Country') not in ('United States','USA'):continue
  ind=classify_event(row.get('Event',''))
  if not ind:continue
  group=data['catalog'][ind]
  try:
   value=str(row['Date'])
   when=parse_dt(value+'Z' if not value.endswith('Z') and '+' not in value else value)
  except (ValueError,KeyError,TypeError):continue
  if not (now-timedelta(hours=1)<when<now+timedelta(days=540)):continue
  if candidate_event(when,group,data.get('calendar',[])):continue
  source='https://tradingeconomics.com/calendar'
  rowurl=str(row.get('URL') or '')
  if rowurl.startswith('/united-states/') and re.fullmatch(r'/[a-z0-9/-]+',rowurl):source='https://tradingeconomics.com'+rowurl
  ev={'group':group,'releaseAt':iso(when),'reference':'',
      'status':'provider_calendar_unverified','source':source}
  proposed[(group,ev['releaseAt'])]=ev
 return list(proposed.values())


def consensus_snapshots(data:dict,rows:list[dict],now:datetime)->int:
 """Only sample *before* official release; never retroactively invent consensus."""
 added=0; snapshots=data.setdefault('snapshots',[])
 for item in rows:
  if item.get('Country') not in ('United States','USA'):continue
  ind=classify_event(item.get('Event',''))
  if ind is None:continue
  val=normalized_forecast(item.get('Forecast'),ind)
  if val is None:continue
  try:
   event_at=parse_dt(str(item['Date'])+'Z' if 'Z' not in str(item['Date']) and '+' not in str(item['Date']) else str(item['Date']))
  except (ValueError,TypeError):continue
  scheduled=candidate_event(event_at,data['catalog'][ind],data.get('calendar',[]))
  if not scheduled:continue
  # Protect point-in-time correctness. Values obtained after release are not "known before".
  release=parse_dt(scheduled['releaseAt'])
  if now>=release:continue
  if item.get('DateSpan') not in (None,'0',0,'1',1):continue
  eid=str(item.get('CalendarId') or '').strip()
  if not eid:continue
  prior=[s for s in snapshots if s.get('id')==ind and s.get('releaseAt')==scheduled['releaseAt'] and s.get('sourceId')==eid]
  if prior and abs(float(prior[-1]['value'])-val)<1e-9:continue
  snapshots.append({'id':ind,'releaseAt':scheduled['releaseAt'],'reference':scheduled.get('reference',''),
    'value':val,'unit':'M' if ind=='jolts' else 'K' if ind in ('nfp','private','claims','adp') else '%',
    'observedAt':iso(now),'source':'Trading Economics · survey consensus (Forecast field)',
    'sourceId':eid,'providerUpdatedAt':str(item.get('LastUpdate') or ''),
    'providerEvent':str(item.get('Event') or '')[:130]})
  added+=1
 data['snapshots']=sorted(snapshots,key=lambda x:x['observedAt'])[-4000:]
 return added


def update(data:dict,now:datetime,ics:str|None=None,te_rows:list[dict]|None=None)->tuple[dict,int]:
 if set(data.get('catalog',{}))!=set(INDICATORS):raise ValueError('Wrong 11-indicator catalog')
 incoming=[]
 if ics:incoming=parse_ics(ics)
 incoming.extend(claims_calendar(now))
 data['calendar']=merge_calendar(data.get('calendar',[]),incoming,now)
 added=consensus_snapshots(data,te_rows or [],now)
 data['lastRun']=iso(now)
 return data,added


def te_url(now:datetime,api_key:str)->str:
 start=(now.date()-timedelta(days=3)).isoformat()
 end=(now.date()+timedelta(days=185)).isoformat()
 return f'{TE_BASE}/{start}/{end}?'+urllib.parse.urlencode({'c':api_key,'f':'json'})


def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('--offline',action='store_true',help='Do not access the network')
 ap.add_argument('--ics-fixture',type=Path)
 ap.add_argument('--te-fixture',type=Path)
 ap.add_argument('--now',help='UTC-aware ISO date-time (for tests)')
 ap.add_argument('--dry-run',action='store_true')
 args=ap.parse_args()
 now=parse_dt(args.now) if args.now else datetime.now(UTC)
 obj=json.loads(OUTPUT.read_text(encoding='utf-8'))
 before=json.loads(json.dumps(obj))
 ics=None
 if args.ics_fixture:ics=args.ics_fixture.read_text(encoding='utf-8')
 elif not args.offline:
  try:ics=http_text(BLS_ICS)
  except Exception as err:print('BLS ICS unavailable; preserving previously verified release calendar:',str(err),file=sys.stderr)
 rows=[]
 provider=obj.setdefault('provider',{})
 licensed=os.getenv('ECON_CONSENSUS_REPUBLICATION_OK','').lower() in ('true','yes','1')
 key=os.getenv('TE_API_KEY','').strip()
 if args.te_fixture:
  rows=json.loads(args.te_fixture.read_text(encoding='utf-8'))
  provider.update(status='test_fixture',note='Synthetic test data; not a real consensus feed')
 elif not key:provider.update(status='not_configured',note='No TE_API_KEY. Values must remain unavailable until a licensed provider is connected.')
 elif not licensed:provider.update(status='license_confirmation_required',note='Set ECON_CONSENSUS_REPUBLICATION_OK=true only if your provider agreement permits public display.')
 elif not args.offline:
  try:
   rows=json.loads(http_text(te_url(now,key)))
   if not isinstance(rows,list):raise ValueError('Provider response must be an array')
   provider.update(status='connected',note='Only original Forecast consensus field is accepted; TEForecast is not consensus.',lastSuccessfulFetch=iso(now))
  except Exception as err:
   provider.update(status='error',note='Provider query failed; prior snapshots retained')
   print('Consensus provider unavailable:',str(err).split('?',1)[0],file=sys.stderr)
 if not isinstance(rows,list):raise ValueError('Provider data invalid')
 # Provider-sourced times are NEVER presented as official confirmations.
 if rows:
  obj['calendar']=merge_calendar(obj.get('calendar',[]),provider_calendar_rows(obj,rows,now),now)
 result,n=update(obj,now,ics,rows)
 # Avoid hourly commits and deployments when only polling timestamps change.
 # This is a meaningful-change tracker, NOT a timer that rewrites JSON on every check.
 meaningful_before=json.loads(json.dumps(before))
 meaningful_after=json.loads(json.dumps(result))
 for x in (meaningful_before,meaningful_after):
  x.pop('lastRun',None)
  x.setdefault('provider',{}).pop('lastSuccessfulFetch',None)
 changed=meaningful_before!=meaningful_after
 if not changed:
  result['lastRun']=before.get('lastRun')
  result['provider']['lastSuccessfulFetch']=before.get('provider',{}).get('lastSuccessfulFetch')
 if not args.dry_run and changed:
  temp=OUTPUT.with_suffix('.json.tmp');temp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');temp.replace(OUTPUT)
 print('Tracked 11 indicators; calendar entries:',len(result['calendar']),'; new pre-release snapshots:',n,'; provider:',provider.get('status'),'; meaningful update:',changed)

if __name__=='__main__':
 try:main()
 except Exception as e:
  print('No forecast data were published:',str(e),file=sys.stderr);sys.exit(1)
