"""Offline accuracy-gate tests: actual public release rounding and no future labels."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"research"))
import inflation_numeric_accuracy as m

def item(i,actual=None):
    month=f"2023-{i+1:02d}"
    release=f"2023-{i+2:02d}-12"
    cutoff=f"2023-{i+2:02d}-05"
    val=.1+i*.025 if actual is None else actual
    return {"release_date":release,"as_of":cutoff,"target_period":month,
        "actual_vintage":release,
        "actual":{"headline":val},
        "predictions":{"headline":{"baseline":.15+i*.01,"structural":val+.03}}}

class TestNumericAccuracy(unittest.TestCase):
    def test_correct_rounding_and_tolerance_not_same(self):
        self.assertEqual(m.round_one(.25),.3)
        self.assertEqual(m.round_one(-.25),-.3)
        self.assertEqual(m.round_one(.35),.4)
        self.assertNotEqual(m.round_one(.249),m.round_one(.251))
        self.assertEqual(m.round_one(.21),m.round_one(.24))

    def test_model_has_no_future_target_label_in_online_tuning(self):
        rows=[item(i) for i in range(10)]
        # All ten events have month-later release dates before next month's cutoffs.
        chosen=m.online_winner(rows[6],rows[:6], "headline")
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen["trainingN"],6)
        self.assertLess(chosen["latestTrainingRelease"],rows[6]["as_of"])
        # Adding future target-month items is filtered by release date.
        fake=item(7,actual=9)
        still=m.online_winner(rows[6],rows[:6]+[fake],"headline")
        self.assertEqual(still["forecast"],chosen["forecast"])
        self.assertEqual(still["trainingN"],6)

    def test_no_training_before_six_prior_known_releases(self):
        rows=[item(i) for i in range(8)]
        self.assertIsNone(m.online_winner(rows[5],rows[:5],"headline"))
        self.assertEqual(m.online_report(rows,"headline")["n"],2)

    def test_nonfirst_vintage_or_future_asof_fails(self):
        report={"family":"ppi","status":"complete","results":[item(0)]}
        report["results"][0]["actual_vintage"]="2023-02-13"
        with self.assertRaises(ValueError):
            m.validate(report)
        report["results"][0]["actual_vintage"]=report["results"][0]["release_date"]
        report["results"][0]["as_of"]=report["results"][0]["release_date"]
        with self.assertRaises(ValueError):
            m.validate(report)

    def test_score_hit_is_discrete_not_smuggled_accuracy(self):
        rows=[item(0,actual=.13),item(1,actual=.29)]
        outcome=m.quote_score(rows,"structural","headline")
        self.assertEqual(outcome["n"],2)
        self.assertEqual(outcome["exact_1_decimal_hits"],1)
        self.assertEqual(outcome["within_0_05pp_hits"],2)
        self.assertEqual(outcome["within_0_10pp_hits"],2)

if __name__=="__main__":unittest.main()
