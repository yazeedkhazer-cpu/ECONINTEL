import unittest
from datetime import date
from fetch_full_pit import cutoffs,asof_rows
from fetch_pit import normalize

class PITFullTests(unittest.TestCase):
    def test_historical_range_month_ends_only_and_partial_current(self):
        cs=cutoffs(date(2026,11,26))
        self.assertEqual(len(cs),56)
        self.assertEqual(cs[0]['asOf'],'2022-04-30')
        self.assertEqual(cs[-2]['asOf'],'2026-10-31')
        self.assertEqual(cs[-1]['asOf'],'2026-11-26')
        self.assertFalse(cs[-1]['completeMonth'])
    def test_no_future_and_historical_revisions(self):
        rows=[
          {'date':'2024-07-01','value':'4.1','realtime_start':'2024-08-01','realtime_end':'2024-08-16'},
          {'date':'2024-07-01','value':'4.3','realtime_start':'2024-08-17','realtime_end':'2024-09-30'},
          {'date':'2024-07-01','value':'4.4','realtime_start':'2024-10-01','realtime_end':'9999-12-31'},
          {'date':'2024-09-01','value':'5.1','realtime_start':'2024-08-01','realtime_end':'9999-12-31'}]
        a=asof_rows(rows,'2024-08-10','UNRATE');b=asof_rows(rows,'2024-08-31','UNRATE')
        self.assertEqual([(x['date'],x['value']) for x in a],[('2024-07-01','4.1')])
        self.assertEqual([(x['date'],x['value']) for x in b],[('2024-07-01','4.3')])
        self.assertEqual(asof_rows(rows,'2024-10-31','UNRATE')[0]['value'],'4.4')
    def test_overlap_conflict_is_rejected(self):
        rows=[{'date':'2024-07-01','value':str(x),'realtime_start':'2024-08-01','realtime_end':'2024-10-01'} for x in (4.1,4.2)]
        with self.assertRaisesRegex(ValueError,'Ambiguous'):asof_rows(rows,'2024-08-31','UNRATE')
    def test_missing_diffusion_is_not_faked(self):
        m,tr,errors=normalize({'CES0500000021':{'error':'Not available'}},'2024-08-31')
        self.assertNotIn('diffusion',m)
        self.assertIn('CES0500000021',errors)
    def test_no_end_of_month_in_future(self):
        cs=cutoffs(date(2026,11,1))
        self.assertEqual(cs[-2]['asOf'],'2026-10-31')
        self.assertEqual(cs[-1]['asOf'],'2026-11-01')
        self.assertTrue(all(x['asOf']<='2026-11-01' for x in cs))
if __name__=='__main__':unittest.main()
