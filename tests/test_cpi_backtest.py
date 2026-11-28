"""Deterministic offline regression tests for ECONINTEL CPI vintage backtesting."""
import sys
import unittest
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
import cpi_backtest as c


def series(start_year, start_month, values):
    result = {}
    for i, value in enumerate(values):
        month_index = start_year * 12 + start_month - 1 + i
        year, month = divmod(month_index, 12)
        result[f"{year:04d}-{month+1:02d}-01"] = value
    return result


class FakeFred:
    """Revised future observations are revealed ONLY on/after release day."""
    def __init__(self):
        self.calls = []
        self.old_head = series(2022, 1, [100 * 1.002**i for i in range(25)])
        self.old_core = series(2022, 1, [105 * 1.003**i for i in range(25)])

    def release_days(self, start, end):
        return ["2024-03-12"]

    def observations(self, series_id, as_of, start):
        self.calls.append((series_id, as_of))
        if series_id == "CPIAUCSL":
            observations = self.old_head.copy()
        elif series_id == "CPILFESL":
            observations = self.old_core.copy()
        else:
            return {}
        if as_of >= "2024-03-12":
            prior = observations["2024-01-01"]
            observations["2024-02-01"] = prior * (
                1.004 if series_id == "CPIAUCSL" else 1.005
            )
        # Earlier periods do not know the new February data.
        return observations


class TestPointInTime(unittest.TestCase):
    def test_monthly_gap_is_not_filled(self):
        self.assertIsNone(c.monthly_changes({
            "2025-09-01": 100, "2025-11-01": 101,
            "2025-12-01": 102}, 2))

    def test_consecutive_three_month_baseline(self):
        a = series(2024, 1, [100, 101, 102.01, 103.0301])
        self.assertAlmostEqual(c.average(c.monthly_changes(a, 3)), 1.0)

    def test_stale_energy_is_excluded(self):
        prices = {"2024-01-01": 80, "2024-01-03": 81,
                  "2024-01-05": 82, "2024-01-07": 83}
        self.assertIsNone(c.market_change(prices, 2, "2024-03-01"))

    def test_first_release_kept_separate_from_history(self):
        fake = FakeFred()
        before = c.snapshot(fake, "2024-03-05")
        self.assertEqual(max(before["headline"]), "2024-01-01")
        actual, vintage = c.first_outcome(fake, "2024-03-12", "2024-02-01")
        self.assertEqual(vintage, "2024-03-12")
        self.assertAlmostEqual(actual["headline"], 0.4)
        self.assertAlmostEqual(actual["core"], 0.5)
        self.assertEqual(max(before["headline"]), "2024-01-01")

    def test_walk_forward_never_sees_future_release(self):
        fake = FakeFred()
        output = c.backtest(fake, "2024-03-01", "2024-03-31", 7, 6)
        self.assertEqual(output["warmupCases"], 1)
        self.assertEqual(output["evaluatedCases"], 0)  # Do NOT claim measured accuracy.
        row = output["results"][0]
        self.assertEqual(row["as_of"], "2024-03-05")
        self.assertEqual(row["target_period"], "2024-02")
        self.assertAlmostEqual(row["actual"]["headline"], 0.4)
        self.assertAlmostEqual(row["predictions"]["headline"]["baseline"], 0.2)
        self.assertIsNone(row["predictions"]["headline"]["ridge"])
        self.assertEqual(output["status"], "insufficient")

    def test_train_only_ridge(self):
        # Constant features are safe; intercept handles the training mean.
        x = {"lag1": 0.3, "lag3": 0.3}
        fitted = [(x, y) for y in (0.2, 0.3, 0.4, 0.3, 0.3, 0.3)]
        self.assertAlmostEqual(c.ridge_forecast(fitted, x), 0.3, places=7)

    def test_scoring_uses_identical_evaluation_set(self):
        records = [{
            "actual": {"headline": 0.4},
            "previous": {"headline": 0.2},
            "predictions": {"headline": {"baseline": 0.3, "ridge": 0.4}}
        }]
        self.assertEqual(c.score(records,"headline","ridge")["mae"],0.0)
        self.assertEqual(c.score(records,"headline","baseline")["n"],1)

    def test_month_transition(self):
        self.assertEqual(c.next_month("2024-12-01"), "2025-01-01")


if __name__ == "__main__":
    unittest.main()
