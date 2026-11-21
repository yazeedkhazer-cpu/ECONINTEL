"""Deterministic, synthetic test data: NOT official market observations."""
from datetime import date, timedelta
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import update_fred as f
import update_bls as b
import update_all as u
from test_update import synthetic_payload

class FredLiveTests(unittest.TestCase):
    def sample(self):
        w=date(2026,9,5)
        weeks=[[(w+timedelta(weeks=i)).isoformat(),200000+i*1000] for i in range(8)]
        quarters=[[f'{y}-{m:02d}-01',100+i*2] for i,(y,m) in enumerate([(2025,1),(2025,4),(2025,7),(2025,10),(2026,1),(2026,4),(2026,7)])]
        return {'ICSA':weeks, 'CCSA':[[d,1800000] for d,v in weeks],
                'ECIALLCIV':quarters,'OPHNFB':quarters,'ULCNFB':quarters,
                'SAHMREALTIME':[['2026-08-01',.15],['2026-09-01',.23]]}

    def test_all_supported_fred_metrics(self):
        result=f.build(self.sample())
        self.assertEqual(set(result),{'claims','claims4wk','continuing','eci','eciy','productivity','ulc','sahm'})
        self.assertEqual(result['claims']['date'],'2026-10-24')
        self.assertEqual(result['claims']['value'],207.)
        self.assertEqual(result['claims4wk']['value'],205.5)
        self.assertEqual(result['eciy']['date'],'2026-Q3')
        self.assertAlmostEqual(result['eciy']['value'],100*(112/104-1),places=3)
        self.assertAlmostEqual(result['productivity']['value'],100*((112/110)**4-1),places=3)
        self.assertEqual(result['sahm']['date'],'2026-09')

    def test_no_gap_filling_weekly(self):
        rows=self.sample()
        rows['ICSA'].pop(2)
        out=f.build(rows)
        self.assertEqual(len(out['claims4wk']['history']),2)

    def test_no_weekly_values_in_future(self):
        payload={'observations':[{'date':'2026-10-02','value':'225000'},
                                 {'date':'2099-01-01','value':'123'}]}
        self.assertEqual(f.parse_observations(payload),[['2026-10-02',225000.]])

    def test_bls_and_fred_merge(self):
        res=u.output_payload(synthetic_payload(), '2026-11-21T15:00:00+00:00',f.build(self.sample()))
        self.assertEqual(res['coverage']['automatic'],30)
        self.assertEqual(res['metrics']['nfp3']['value'],120)
        self.assertEqual(res['metrics']['longshare']['date'],'2026-10')
        self.assertEqual(res['metrics']['claims']['unit'],'K')

    def test_missing_fred_preserves_old_version(self):
        old={'metrics':{'claims':{'value':200,'date':'2026-10-01','history':[['2026-10-01',200]],
                                  'seriesId':'ICSA','observedAt':'2026-10-01'}}}
        r=u.output_payload(synthetic_payload(),'2026-11-21T15:00:00+00:00',previous=old)
        self.assertEqual(r['metrics']['claims']['observedAt'],'2026-10-01')

if __name__=='__main__':unittest.main()
