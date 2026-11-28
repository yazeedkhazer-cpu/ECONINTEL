"""Category forecast PIT integrity: no future outcomes in regressions."""
import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"research"))
import cpi_category_walkforward as m

def trajectory(last,rate_pct,n=36):
    idx=m.ix(last)
    return {m.month(idx-n+1+i):100*(1+rate_pct/100)**i for i in range(n)}

class FakeFred:
    def __init__(self):self.calls=[]
    def observations(self,series,when,begin):
        self.calls.append((series,when))
        # target 2024-03; before release 2024-04-03 only through Feb.
        a=trajectory("2024-02-01",.35)
        if when=="2024-04-10":
            a["2024-03-01"]=a["2024-02-01"]*(1+.005)
        return a

class TestForecast(unittest.TestCase):
    def test_only_prior_known_releases_train(self):
        training=[{"release":"2024-01-15","features":{"lag1":.2,"mean3":.2,"momentum":0,"seasonal_y1":.2},"actual":.3}]
        f={"lag1":.2,"mean3":.3,"momentum":.1,"seasonal_y1":.4}
        self.assertIsNone(m.regularized(training,f))
        self.assertEqual(m.predictions(f,training)["baseline3"],.3)
        self.assertAlmostEqual(m.predictions(f,training)["fixed_seasonal_blend"],.33)

    def test_ridge_stable_and_train_only(self):
        f={"lag1":.3,"mean3":.3,"momentum":0,"seasonal_y1":.3}
        train=[{"features":{"lag1":.1+i*.01,"mean3":.15+i*.008,
                "momentum":.01,"seasonal_y1":.2+i*.006},
                "actual":.3+i*.01} for i in range(12)]
        pred=m.regularized(train,f)
        self.assertTrue(m.finite(pred))
        self.assertAlmostEqual(pred,m.regularized(train,f))
        self.assertGreater(abs(m.regularized(train+[{"features":f,"actual":10}],f)-pred),.01)

    def test_categories_pit_outcome_after_release_only(self):
        c=FakeFred()
        row={"target":"2024-03","cutoff":"2024-04-03","release":"2024-04-10"}
        r=m.fetch_episode(c,row)
        self.assertEqual(r["month"],"2024-03")
        for name in m.SOURCES:
            self.assertAlmostEqual(r["categories"][name]["actual"],.5)
            self.assertAlmostEqual(r["categories"][name]["features"]["mean3"],.35)
        self.assertIn(("CUSR0000SEHC","2024-04-03"),c.calls)
        self.assertIn(("CUSR0000SEHC","2024-04-10"),c.calls)

    def test_missing_first_release_must_fail_closed(self):
        c=FakeFred()
        def before_only(s,when,begin):
            return trajectory("2024-02-01",.3)
        c.observations=before_only
        with self.assertRaisesRegex(ValueError,"not first-released"):
            m.fetch_episode(c,{"target":"2024-03","cutoff":"2024-04-03",
                                "release":"2024-04-10"})

    def test_walkforward_training_labels_end_before_cutoff(self):
        c=FakeFred()
        a=[{"target":"2024-03","cutoff":"2024-04-03","release":"2024-04-10"},
           {"target":"2024-03","cutoff":"2024-04-03","release":"2024-04-10"}]
        result=m.replay(c,a)
        self.assertEqual(result["accepted"],1)
        self.assertEqual(len(result["excluded"]),1)
        for category in result["categories"].values():
            self.assertEqual(category["cases"][0]["predictionTrainingN"],0)
            self.assertIsNone(category["cases"][0]["predictions"]["ridge_train_only"])

if __name__=="__main__":unittest.main()
