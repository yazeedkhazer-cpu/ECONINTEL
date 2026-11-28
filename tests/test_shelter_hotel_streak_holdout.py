"""No-leakage and pre-registered hotel-streak warning holdout tests."""
import sys
import unittest
from datetime import date
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"research"))
import shelter_hotel_streak_holdout as m

def series(last="2024-03-01",grow=.3,rate_window=None):
    start=2023*12
    out={}
    for i in range(18):
        t=m.month(start+i)
        out[t]=100*(1+grow/100)**i
    return {k:v for k,v in out.items() if k<=last}
class Fake:
    def __init__(self):
        self.calls=[]
    def observations(self,code,as_of,start):
        self.calls.append((code,as_of))
        # CPI March first shows up on April 10 (not one week before).
        vals=series(last="2024-02-01")
        if as_of>="2024-04-10":
            vals["2024-03-01"]=vals["2024-02-01"]*1.006
        return vals

class TestStreakRisk(unittest.TestCase):
    def test_strict_nonzero_equal_sign(self):
        self.assertTrue(m.same_direction([1,.2,3]))
        self.assertTrue(m.same_direction([-.1,-3,-.7]))
        self.assertFalse(m.same_direction([1,-.2,3]))
        self.assertFalse(m.same_direction([1,0,1]))
        self.assertFalse(m.same_direction([]))

    def test_baseline_exante_without_future_actual(self):
        c=Fake()
        r=m.evaluate_episode(c,"2024-04-10",7)
        self.assertEqual(r["cutoff"],"2024-04-03")
        self.assertEqual(r["target"],"2024-03")
        self.assertAlmostEqual(r["first_released_actual_shelter_mom"],.6)
        self.assertAlmostEqual(r["predicted_shelter_mom_3m_baseline"],.3)
        self.assertTrue(r["lodging_streak_flag"])
        self.assertTrue(r["large_miss_0_15pp"])
        self.assertIn(("CUSR0000SAH1","2024-04-03"),c.calls)
        self.assertIn(("CUSR0000SAH1","2024-04-10"),c.calls)

    def test_holdout_violating_discovery_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"AFTER"):
            m.evaluate(Fake(),"2023-01-01","2024-04-30")

    def test_group_scoring_and_exclusion_dates(self):
        old=m.release_calendar
        try:
            m.release_calendar=lambda *args:["2024-04-10","2024-04-10"]
            r=m.evaluate(Fake(),"2024-04-01","2024-04-30",7)
            self.assertEqual(r["validCases"],1)
            self.assertEqual(r["groups"]["flag"]["n"],1)
            self.assertEqual(r["groups"]["no_flag"]["n"],0)
            self.assertEqual(len(r["skipped"]),1)
            self.assertIsNone(r["flaggedMinusUnflaggedMaePp"])
        finally:
            m.release_calendar=old
if __name__=="__main__":
    unittest.main()
