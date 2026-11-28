"""Deterministic CPI V2 Rent/OER PIT tests, no network required."""
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"research"))
import shelter_v2_pit as m

W={"reference":"2022-12","publishedOn":"2023-01-12","shelter":34.413,
   "rent":7.528,"oer":25.424,"residual":1.461}
W2={"reference":"2023-12","publishedOn":"2024-01-11","shelter":36.191,
    "rent":7.671,"oer":26.769,"residual":1.751}

def h(rate,start="2022-01-01",count=36):
    beginning=m.ix(start)
    return {m.month(beginning+i):100*(1+rate/100)**i for i in range(count)}

class MockFred:
    def __init__(self):
        self.calls=[]
    def observations(self,code,asof,begin):
        self.calls.append((code,asof))
        z=h({"CUSR0000SAH1":.25,"CUSR0000SEHA":.2,
             "CUSR0000SEHC":.27}[code],count=23)
        if asof<"2023-12-12":return {k:v for k,v in z.items() if k<="2023-10-01"}
        return {k:v for k,v in z.items() if k<="2023-11-01"}

class TestCpiShelterPit(unittest.TestCase):
    def test_weight_vintage_boundary_and_residual(self):
        self.assertIsNone(m.weights_asof([W,W2],"2023-01-11"))
        self.assertEqual(m.weights_asof([W,W2],"2023-12-31")["reference"],"2022-12")
        self.assertEqual(m.weights_asof([W,W2],"2024-01-11")["reference"],"2023-12")
        self.assertAlmostEqual(W["rent"]+W["oer"]+W["residual"],W["shelter"])

    def test_no_target_month_in_features(self):
        data={"shelter":h(.25,count=22),"rent":h(.2,count=22),"oer":h(.27,count=22)}
        p=m.predict(data,W)
        self.assertEqual(p["last"],"2023-10-01")
        self.assertEqual(p["target"],"2023-11-01")
        self.assertAlmostEqual(p["baseline"],.25,places=6)
        # The model recomposes the historically consistent parent index.
        self.assertAlmostEqual(p["v2"],.25,places=5)

    def test_missing_month_blocks_forward_fill(self):
        data={"shelter":h(.25,count=22),"rent":h(.2,count=22),"oer":h(.27,count=22)}
        del data["rent"]["2023-09-01"]
        self.assertIsNone(m.predict(data,W))

    def test_actual_observation_requires_same_day_vintage(self):
        client=MockFred()
        self.assertIsNone(m.label_on_first_release(client,"2023-11-14","2023-11-01"))
        actual=m.label_on_first_release(client,"2023-12-12","2023-11-01")
        self.assertAlmostEqual(actual,.25,places=5)

    def test_metrics_only_same_month_and_never_conflate_models(self):
        rows=[{"prediction":{"baseline":.4,"v2":.2},"actual":.15},
              {"prediction":{"baseline":.3,"v2":.5},"actual":.35}]
        self.assertEqual(m.metrics(rows,"v2")["n"],2)
        self.assertEqual(m.metrics(rows,"v2")["monthly_wins"],1)
        self.assertEqual(m.metrics(rows,"baseline")["monthly_wins"],1)

if __name__=="__main__":
    unittest.main()
