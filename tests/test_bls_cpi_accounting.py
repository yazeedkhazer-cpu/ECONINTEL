"""Reproduce published BLS aggregation example; enforce source date gates."""
import sys,math,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"research"))
import bls_cpi_accounting as b

class TestBlsMethodology(unittest.TestCase):
    def test_official_bls_beverages_example_rounds_to_17pct(self):
        result=b.benchmark_bls_beverages()
        self.assertAlmostEqual(result["monthlyPercentChange"],1.6534,delta=.01)
        self.assertEqual(round(result["monthlyPercentChange"],1),1.7)
        self.assertAlmostEqual(sum(x["contributionPp"] for x in result["contributions"]),
                               result["monthlyPercentChange"])
        self.assertTrue(result["notOfficialSaCpi"])

    def test_geometric_prices_and_arithmetic_quantities_differ(self):
        p=[100,100];q=[120,90]
        geo=b.weighted_geometric_relative(p,q,[1,1])
        las=b.weighted_laspeyres_relative(p,q,[1,1])
        self.assertAlmostEqual(geo,math.sqrt(1.08),places=8)
        self.assertAlmostEqual(las,1.05)
        self.assertNotAlmostEqual(geo,las)

    def test_housing_monthly_sixth_root_not_a_simple_divide_by_six(self):
        prev=250;relative=1.06
        self.assertAlmostEqual(b.six_month_housing_index(prev,relative),
                               prev*1.06**(1/6),places=10)
        self.assertNotAlmostEqual(b.six_month_housing_index(prev,relative),
                                  prev*(1+.06/6),places=5)

    def test_any_duplicate_or_future_weight_rejected(self):
        base={"id":"x","baseMonth":"2024-12","baseCostWeight":100.,
              "weightPublishedOn":"2025-01-01",
              "baseIndex":100,"priorIndex":103,"targetIndex":105}
        with self.assertRaisesRegex(ValueError,"Double-counted"):
            b.aggregate_cost_weight_change([base,base],
              "2024-12","2025-05","2025-06",as_of="2025-07-01")
        with self.assertRaisesRegex(ValueError,"Future dated"):
            b.aggregate_cost_weight_change([{**base,"weightPublishedOn":"2025-07-01"}],
              "2024-12","2025-05","2025-06",as_of="2025-06-30")

    def test_forecast_uses_only_pre_cutoff_market_sources(self):
        c={"id":"energy","weightPublishedOn":"2025-01-12",
           "baseCostWeight":7.0,"baseIndex":100.,"priorIndex":103.,
           "forecastPriceRelative":1.04,
           "inputDataPublishedAt":"2025-07-08T11:00:00Z"}
        result=b.projection_from_price_relatives([c],
          "2024-12","2025-06","2025-07","2025-07-09T00:00:00Z")
        self.assertAlmostEqual(result["monthlyPercentChange"],4.0)
        with self.assertRaisesRegex(ValueError,"Future source"):
            b.projection_from_price_relatives([{**c,"inputDataPublishedAt":"2025-07-11T00:00:00Z"}],
             "2024-12","2025-06","2025-07","2025-07-09T00:00:00Z")
        self.assertEqual(result["status"],"MODEL_COMPONENT_FORECAST_UNVALIDATED")

    def test_reject_missing_prices_and_nonpositive_weights(self):
        with self.assertRaises(ValueError):
            b.weighted_geometric_relative([100,101],[110],[1,1])
        with self.assertRaises(ValueError):
            b.weighted_laspeyres_relative([100],[110],[0])
        with self.assertRaises(ValueError):
            b.six_month_housing_index(250,0)

if __name__=="__main__":unittest.main()
