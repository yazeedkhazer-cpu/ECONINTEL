"""Deterministic synthetic fixtures: no actual market forecasts in these tests."""
import sys
import unittest
import json
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import update_forecast_tracker as f

SEED={'catalog':{id:grp for grp,ids in f.GROUPS.items() for id in ids},
      'calendar':[{'group':'nfp','releaseAt':'2026-12-04T13:30:00Z','reference':'2026-11','status':'official_verified','source':f.SOURCE['nfp']},
                  {'group':'claims','releaseAt':'2026-11-25T13:30:00Z','reference':'','status':'official_exception','source':f.DOL_SCHEDULE}],
      'snapshots':[]}
NOW=datetime(2026,11,23,12,0,tzinfo=timezone.utc)
ICS='''BEGIN:VCALENDAR\r
BEGIN:VEVENT\r
DTSTART;TZID=America/New_York:20261204T083000\r
SUMMARY:Employment Situation for November 2026\r
END:VEVENT\r
BEGIN:VEVENT\r
DTSTART:20261201T150000Z\r
SUMMARY:Job Openings and Labor Turnover Survey\r
END:VEVENT\r
END:VCALENDAR\r
'''

class ForecastTests(unittest.TestCase):
 def test_ics_dates_and_indicators(self):
  got=f.parse_ics(ICS)
  self.assertEqual(got[0]['releaseAt'],'2026-12-01T15:00:00Z')
  self.assertEqual(got[1]['releaseAt'],'2026-12-04T13:30:00Z')
 def test_ics_ignores_too_vague_date(self):
  self.assertEqual(f.parse_ics(ICS.replace('20261204T083000','20261204').replace('20261201T150000Z','20261201')) , [])
 def test_claims_thanksgiving_exception_not_thursday(self):
  dates=[x['releaseAt'] for x in f.claims_calendar(NOW)]
  self.assertIn('2026-11-25T13:30:00Z', dates)
  self.assertNotIn('2026-11-26T13:30:00Z', dates)
  self.assertIn('2026-12-03T13:30:00Z',dates)
 def test_consensus_units(self):
  self.assertEqual(f.normalized_forecast('175K','nfp'),175)
  self.assertEqual(f.normalized_forecast('0.2M','nfp'),200)
  self.assertEqual(f.normalized_forecast('7,400K','jolts'),7.4)
  self.assertEqual(f.normalized_forecast('4.1%','unrate'),4.1)
  self.assertIsNone(f.normalized_forecast('N/A','nfp'))
 def test_fuzzy_events_rejected(self):
  self.assertEqual(f.classify_event('Average Hourly Earnings MoM'),'wage_mom')
  self.assertEqual(f.classify_event('Average Hourly Earnings YoY'),'wage')
  self.assertIsNone(f.classify_event('Random US Employment Index'))
 def test_only_pre_release_snapshots(self):
  data=json.loads(json.dumps(SEED))
  row={'Country':'United States','Event':'Non Farm Payrolls','Date':'2026-12-04T13:30:00','Forecast':'180K','TEForecast':'195K','CalendarId':'123','LastUpdate':'2026-11-23T10:00:00'}
  self.assertEqual(f.consensus_snapshots(data,[row],NOW),1)
  self.assertEqual(data['snapshots'][0]['value'],180)
  self.assertEqual(f.consensus_snapshots(data,[row],NOW),0)
  row['Forecast']='184K'
  self.assertEqual(f.consensus_snapshots(data,[row],NOW),1)
  self.assertEqual(len(data['snapshots']),2)
  self.assertEqual(f.consensus_snapshots(data,[row],datetime(2026,12,5,tzinfo=timezone.utc)),0)
 def test_unknown_release_rejected(self):
  data=json.loads(json.dumps(SEED))
  row={'Country':'United States','Event':'Non Farm Payrolls','Date':'2026-12-14T13:30:00','Forecast':'180K','CalendarId':'123'}
  self.assertEqual(f.consensus_snapshots(data,[row],NOW),0)
 def test_ics_preserves_when_unavailable(self):
  data=json.loads(json.dumps(SEED))
  after,_=f.update(data,NOW,None,None)
  self.assertTrue(any(e['group']=='nfp' for e in after['calendar']))
 def test_provider_calendar_is_not_official(self):
  d=json.loads(json.dumps(SEED))
  row={'Country':'United States','Event':'ADP Employment Change','Date':'2026-12-02T13:15:00','Forecast':'98K','CalendarId':'456','DateSpan':'0'}
  got=f.provider_calendar_rows(d,[row],NOW)
  self.assertEqual(got[0]['group'],'adp')
  self.assertEqual(got[0]['status'],'provider_calendar_unverified')
  self.assertEqual(got[0]['releaseAt'],'2026-12-02T13:15:00Z')
 def test_fallback_does_not_replace_official(self):
  d=json.loads(json.dumps(SEED))
  row={'Country':'United States','Event':'Non Farm Payrolls','Date':'2026-12-04T13:30:00','Forecast':'100K','CalendarId':'455'}
  self.assertEqual(f.provider_calendar_rows(d,[row],NOW),[])
 def test_all_eleven_unique(self):
  self.assertEqual(len(SEED['catalog']),11)
  self.assertEqual(set(SEED['catalog']),set(f.INDICATORS))

if __name__=='__main__':unittest.main()
