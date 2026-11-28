"""Deterministic tests of shelter V2 ex-post error attribution."""
import sys, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"research"))
import shelter_error_forensics as f

W={"reference":"2022-12","publishedOn":"2023-01-12",
   "shelter":34.413,"rent":7.528,"oer":25.424,"residual":1.461}
CASE={"target":"2023-09","release":"2023-10-12","cutoff":"2023-10-05",
      "weightRef":"2022-12","actual":0.6471048,
      "prediction":{"baseline":0.364926,"v2":0.34986691614246807,
        "rent_projected":0.46750387445762875,
        "oer_projected":0.4146462412348795,
        "residual_projected":-1.3835489519930537}}

class TestErrorForensics(unittest.TestCase):
    def test_exact_accounting_identity_with_known_v2_prediction(self):
        d=f.attribute(CASE,{"rent":0.5,"oer":0.6,"lodging":3.7},W)
        self.assertAlmostEqual(d["attributed_error_sum_pp"],CASE["actual"]-CASE["prediction"]["v2"],places=9)
        self.assertEqual(d["largest_absolute_component"],"remaining_shelter_implied")
        self.assertGreater(d["attributed_error_pp"]["oer"],0)
        self.assertEqual(d["actual_lodging_mom"],3.7)

    def test_keep_as_of_predictors_separate_from_release_date_observations(self):
        seen=[]
        def labels(_,release,target):
            seen.append(("label",release,target))
            return {"shelter":0.6471048,"rent":0.5,"oer":0.6,"lodging":3.7},[]
        def earlier(_,cutoff,target):
            seen.append(("prior",cutoff,target))
            return {"available":True,"lodging_volatility_std":2.0,
                    "last_lodging_mom":-1.0,"three_month_lodging_rates":[-1.0,-2.0,-3.0],
                    "lodging_trailing_range":2.0}
        with patch.object(f,"first_release_rates",side_effect=labels):
            with patch.object(f,"prior_lodging_volatility",side_effect=earlier):
                report=f.study({"cases":[CASE]},None,[W])
        self.assertEqual(report["decomposed_cases"],1)
        self.assertEqual(seen,[("label","2023-10-12","2023-09-01"),
                               ("prior","2023-10-05","2023-09-01")])
        self.assertEqual(report["status"],"descriptive_not_predictive_validation")

    def test_missing_actual_rent_or_oer_is_excluded(self):
        with patch.object(f,"first_release_rates",return_value=({"shelter":0.65},["rent","oer"])):
            report=f.study({"cases":[CASE]},None,[W])
        self.assertEqual(report["decomposed_cases"],0)
        self.assertEqual(report["skipped"][0]["month"],"2023-09")

    def test_future_weights_are_rejected(self):
        w=dict(W,publishedOn="2023-10-06")
        with patch.object(f,"first_release_rates",return_value=({"rent":0.5,"oer":0.6,"lodging":3.7},[])):
            with self.assertRaisesRegex(ValueError,"future-dated"):
                f.study({"cases":[CASE]},None,[w])

if __name__=="__main__":unittest.main()
