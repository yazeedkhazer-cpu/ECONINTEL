"""Offline tests for PCE/PPI point-in-time inflation release studies."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
import inflation_releases as mod


def history(rate=0.2):
    rows={}
    for i in range(25):
        n=2022*12+i
        y,m=divmod(n,12)
        rows[f"{y:04d}-{m+1:02d}-01"]=100*(1+rate/100)**i
    return rows


class FakeProvider:
    def __init__(self):
        self.calls=[]
        self.prior=history()

    def get(self, endpoint, **params):
        if endpoint == "/release/dates":
            return {"release_dates": [{"date":x} for x in
                                     ("2024-03-26","2024-03-27","2024-03-28")]}
        raise ValueError(endpoint)

    def observations(self, code, as_of, start):
        self.calls.append((code, as_of))
        rows=self.prior.copy()
        if code in ("PCEPI","PCEPILFE"):
            # PCE February is not published before March 27.
            if as_of >= "2024-03-27":
                rows["2024-02-01"]=rows["2024-01-01"]*(1.004 if code=="PCEPI" else 1.003)
        else:
            # CPI and PPI for February were already available by March 20.
            if as_of >= "2024-03-14":
                rows["2024-02-01"]=rows["2024-01-01"]*1.005
        return rows


class TestInflationReleases(unittest.TestCase):
    def test_vintage_inputs_from_before_pce_event(self):
        client=FakeProvider()
        frozen=mod.series_asof(client,"2024-03-20")
        period=mod.target_month(frozen,["pce","corepce"])
        self.assertEqual(period,"2024-02-01")
        self.assertNotIn(period,frozen["pce"])
        self.assertIn(period,frozen["cpi"])
        self.assertIn(period,frozen["ppi"])
        x=mod.x_features(frozen,"pce",period)
        self.assertAlmostEqual(x["cpi_same"],0.5)
        self.assertAlmostEqual(x["ppi_same"],0.5)
        self.assertAlmostEqual(x["lag3"],0.2)

    def test_first_release_vintage_and_duplicate_exclusion(self):
        client=FakeProvider()
        output=mod.replay(client,"pce","2024-03-01","2024-03-31",7,6)
        self.assertEqual(output["calendar_candidates"],3)
        self.assertEqual(output["unique_months"],1)
        self.assertEqual(output["evaluated_cases"],0)
        self.assertEqual(output["status"],"insufficient")
        self.assertEqual(output["results"][0]["release_date"],"2024-03-27")
        self.assertEqual(output["results"][0]["forecast_date"],"2024-03-20")
        self.assertAlmostEqual(output["results"][0]["actual"]["headline"],0.4)
        self.assertEqual(len(output["skipped"]),2)

    def test_calendar_ids_for_inflation_families(self):
        self.assertEqual(mod.SPECS["cpi"]["release_id"],10)
        self.assertEqual(mod.SPECS["pce"]["release_id"],54)
        self.assertEqual(mod.SPECS["ppi"]["release_id"],46)

    def test_no_forward_fill_for_gap(self):
        rows={"2023-11-01":100,"2024-01-01":101}
        self.assertIsNone(mod.month_growth({"pce":rows},"pce"))

    def test_ridge_uses_only_given_training_cases(self):
        x={"lag1":.2,"lag3":.2}
        train=[(x,v) for v in [.1,.2,.3,.2,.2,.2]]
        self.assertAlmostEqual(mod.ridge(train,x),.2,places=6)


if __name__=="__main__":
    unittest.main()
