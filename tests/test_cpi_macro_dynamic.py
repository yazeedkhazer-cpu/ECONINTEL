"""PIT macro CPI prototype: no-leakage and dynamic-vs-baseline contract."""
import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"research"))
import cpi_macro_dynamic as m

def features(x):
    return {name: ((x+.2*i)**2 if i%2 else (x+.3*i))
            for i,name in enumerate(m.FEATURES)}
def case(i):
    release=f"2025-{i%12+1:02d}-13"
    cutoff=f"2025-{i%12+1:02d}-06"
    return {"release":release,"cutoff":cutoff,"target":f"2025-{i%12+1:02d}",
            "features":features(i), "actual":{"cpi":.2+.03*i,"core":.3+.02*i},
            "baseline":{"cpi":.25,"core":.25}}

class FakeFred:
    def __init__(self):self.calls=[]
    def observations(self,id,when,start):
        self.calls.append((id,when))
        return {"2024-01-01":100.,"2024-02-01":100.4}

class Tests(unittest.TestCase):
    def test_no_current_actual_label_in_macro_features(self):
        x={key:{"2025-01-01":100,"2025-01-08":101} for key in m.SOURCE}
        for name in ("ppi","commodities","wages"):
            x[name]={"2024-10-01":100,"2024-11-01":101}
        with self.assertRaisesRegex(ValueError,"Missing or stale"):
            m.extract(x,"2025-02-05")

    def test_model_prediction_depends_on_macro_factors_not_just_last_cpi(self):
        rows=[case(i) for i in range(12)]
        a=features(.4);b=features(5.0)
        p=m.forecast_one(rows,a,"cpi",.25)
        q=m.forecast_one(rows,b,"cpi",.25)
        self.assertTrue(m.is_number(p["macro_only"]))
        self.assertTrue(m.is_number(p["regime_adjusted"]))
        self.assertNotAlmostEqual(p["macro_only"],q["macro_only"],places=6)
        self.assertNotAlmostEqual(p["regime_adjusted"],q["regime_adjusted"],places=6)

    def test_training_data_only_no_final_candidate_labels(self):
        rows=[case(i) for i in range(12)]
        present=features(7)
        current=m.forecast_one(rows,present,"core",.31)
        self.assertEqual(current,m.forecast_one(rows,present,"core",.31))
        self.assertNotEqual(current,m.forecast_one(rows+[case(11)],present,"core",.31))
        self.assertEqual(m.forecast_one(rows[:9],present,"core",.31),
                         {"macro_only":None,"regime_adjusted":None})

    def test_first_release_must_be_that_day_and_same_month(self):
        with self.assertRaisesRegex(ValueError,"not first released"):
            m.first_release(FakeFred(),"2025-03-13","2025-02-01","2025-03-06")

    def test_no_ex_post_training_in_replay(self):
        records=[{"target":f"2024-{i+1:02d}",
                  "release":f"2024-{i+2:02d}-13",
                  "cutoff":f"2024-{i+2:02d}-06"} for i in range(7)]
        def fake(_,row):
            i=int(row["target"][-2:])
            return {"release":row["release"],"cutoff":row["cutoff"],
                    "target":row["target"],"features":features(i),
                    "baseline":{"cpi":.2,"core":.2},
                    "actual":{"cpi":.21,"core":.22},
                    "marketSourceLatest":{}}
        with patch.object(m,"event",side_effect=fake):
            result=m.replay(None,records)
        self.assertEqual(result["evaluated"],7)
        self.assertEqual([c["trainingN"] for c in result["cases"]],list(range(7)))
        self.assertTrue(all(c["lastKnownTrainingRelease"] is None or
                            c["lastKnownTrainingRelease"]<c["cutoff"] for c in result["cases"]))
        self.assertIsNone(result["cases"][0]["predictions"]["cpi"]["regime_adjusted"])

    def test_weighted_ridge_does_not_reuse_future_scaling(self):
        r=[case(i) for i in range(12)]
        current=features(.2)
        a=m.weighted_ridge(r,current,"cpi",True,True)
        b=m.weighted_ridge(r,current,"cpi",True,True)
        self.assertAlmostEqual(a,b)
        self.assertTrue(m.is_number(a))
if __name__=="__main__":unittest.main()
