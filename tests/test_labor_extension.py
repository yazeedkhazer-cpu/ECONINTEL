"""Synthetic fixtures only: these are not official economic observations."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import update_diffusion as d
import update_fred as f
import update_all as u
from test_update import synthetic_payload


HTML = '''<html><body><table><thead><tr><th>Category</th>
<th>Aug.<br>2026</th><th>Sept.<br>2026</th><th>Oct.<br>2026 (p)</th>
</tr></thead><tbody>
<tr><th>EMPLOYMENT BY SELECTED INDUSTRY</th></tr>
<tr><td>Total private</td><td>50</td><td>50</td><td>50</td></tr>
<tr><th>DIFFUSION INDEXES (5)</th></tr>
<tr><th>Total Private</th></tr>
<tr><td>Over 1-month span</td><td>59.4</td><td>54.2</td><td>57.6</td></tr>
<tr><td>Over 3-month span</td><td>59</td><td>60</td><td>61</td></tr>
<tr><th>Manufacturing</th></tr>
<tr><td>Over 1-month span</td><td>20</td><td>25</td><td>30</td></tr>
</tbody></table></body></html>'''


class LaborCompletionTests(unittest.TestCase):
    def test_official_bls_diffusion_not_manufacturing(self):
        got=d.parse_table(HTML,'2026-10')
        self.assertEqual(got['value'],57.6)
        self.assertEqual(got['date'],'2026-10')
        self.assertEqual(len(got['history']),3)
        self.assertEqual(got['seriesId'],'BLS:CES:SUMMARY_B:DIFFUSION:PRIVATE:1M')

    def test_bls_diffusion_wrong_month_rejected(self):
        with self.assertRaisesRegex(ValueError,'does not match'):
            d.parse_table(HTML,'2026-11')

    def test_bls_diffusion_malformed_row_rejected(self):
        with self.assertRaisesRegex(ValueError,'not recognized'):
            d.parse_table(HTML.replace('<td>57.6</td>',''),'2026-10')

    def test_adp_consecutive_months_in_thousands(self):
        r=f.build({'ADPMNUSNERSA':[['2026-07-01',132763000],
                                         ['2026-08-01',132799000],
                                         ['2026-09-01',132885000],
                                         ['2026-10-01',132971000]]})
        self.assertEqual(r['adp']['value'],86.0)
        self.assertEqual(r['adp']['history'],[['2026-08',36.0],['2026-09',86.0],['2026-10',86.0]])
        self.assertEqual(r['adp']['date'],'2026-10')

    def test_adp_missing_month_never_guessed(self):
        got=f.build({'ADPMNUSNERSA':[['2026-07-01',100000],['2026-09-01',120000]]})
        self.assertNotIn('adp',got)

    def test_32_metrics_possible_only_with_valid_enrichments(self):
        rows={'ADPMNUSNERSA':[['2026-09-01',1000000],['2026-10-01',1100000]]}
        # Synthetic 8 FRED values from existing test fixture.
        from test_live import FredLiveTests
        rows.update(FredLiveTests().sample())
        fred=f.build(rows)
        diff=d.parse_table(HTML,'2026-10')
        result=u.output_payload(synthetic_payload(),'2026-11-21T16:00:00+00:00',fred,
                                diffusion_data=diff)
        self.assertEqual(len(result['metrics']),32)
        self.assertEqual(result['coverage']['automatic'],32)
        self.assertNotIn('isman',result['metrics'])
        self.assertNotIn('isserv',result['metrics'])

    def test_failed_diffusion_fetch_keeps_verified_old_not_seed(self):
        old=d.parse_table(HTML,'2026-10')
        old['observedAt']='2026-11-06T00:00:00Z'
        r=u.output_payload(synthetic_payload(),'2026-11-21T17:00:00Z',previous={'metrics':{'diffusion':old}})
        self.assertEqual(r['metrics']['diffusion']['observedAt'],old['observedAt'])

if __name__=='__main__':unittest.main()
