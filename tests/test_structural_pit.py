"""Offline deterministic no-lookahead and data-gap tests for real structural CPI/PCE/PPI replay."""
import sys
import unittest
from pathlib import Path
from datetime import date
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"research"))
import structural_pit as m

def monthly(start=2016,count=106,rate=.2,base=100):
    startyear,startmonth=start,1
    result={}
    for i in range(count):
        y,mo=divmod(startyear*12+startmonth-1+i,12)
        result[f"{y:04d}-{mo+1:02d}-01"]=base*(1+rate/100)**i
    return result

def monthly_until(hist,period):
    return {k:v for k,v in hist.items() if k<=period}

def fixture(latest="2024-10-01",gas_target="2024-11-01"):
    histories={
     "cpi":monthly(count=120,rate=.31),
     "corecpi":monthly(count=120,rate=.28),
     "cpifood":monthly(count=120,rate=.24),
     "cpienergy":monthly(count=120,rate=.4),
     "cpigoods":monthly(count=120,rate=.18),
     "cpishelter":monthly(count=120,rate=.32),
     "cpiservices":monthly(count=120,rate=.29),
     "ppi":monthly(count=120,rate=.35),
     "pce":monthly(count=120,rate=.27),
     "corepce":monthly(count=120,rate=.25),
    }
    out={k:monthly_until(v,latest) for k,v in histories.items()}
    out["gasoline"]=monthly_until(monthly(count=120,rate=.9),gas_target)
    out["brent"]=monthly_until(monthly(count=120,rate=.7),gas_target)
    return out

WEIGHTS=[
 {"referenceMonth":"2022-12","publishedOn":"2023-01-12",
  "food":13.531,"energy":6.921,"goods":21.361,"shelter":34.413,"other":23.774},
 {"referenceMonth":"2023-12","publishedOn":"2024-01-11",
  "food":13.555,"energy":6.655,"goods":18.891,"shelter":36.191,"other":24.708},
]

class FakeClient:
    def __init__(self):
        self.calls=[]
        self.data=fixture()
        self.codes=dict((v,k) for k,v in m.INPUTS.items())

    def observations(self,series_id,as_of,start):
        self.calls.append((series_id,as_of))
        key=self.codes[series_id]
        h=self.data[key].copy()
        if as_of>="2024-12-11" and key in ("cpi","corecpi"):
            previous=h["2024-10-01"]
            h["2024-11-01"]=previous*(1.002 if key=="cpi" else 1.003)
        if key in ("gasoline","brent"):
            # EIA frequency is weekly/daily, not CPI frequency.
            def month_days(s,v):
                y,mo=s.split("-")[:2]
                return {f"{y}-{mo}-{d:02d}":v for d in (2,9,16,23)}
            expanded={}
            for p,v in h.items():
                expanded.update(month_days(p,v))
            return {k:v for k,v in expanded.items() if k<=as_of and k>=start}
        return {k:v for k,v in h.items() if k<=as_of and k>=start}

def event_days(client,release_id,start,end):
    return ["2024-12-11","2024-12-12"]

class TestStructural(unittest.TestCase):
    def test_historical_weights_not_from_future(self):
        self.assertEqual(m.get_weights(WEIGHTS,"2023-12-25")["referenceMonth"],"2022-12")
        self.assertEqual(m.get_weights(WEIGHTS,"2024-01-10")["referenceMonth"],"2022-12")
        self.assertEqual(m.get_weights(WEIGHTS,"2024-01-11")["referenceMonth"],"2023-12")
        self.assertIsNone(m.get_weights(WEIGHTS,"2022-12-05"))

    def test_five_components_sum_and_energy_exclusion(self):
        data=fixture()
        w=WEIGHTS[1]
        a=m.components(data,w,"2024-11-01")
        self.assertIsNotNone(a)
        self.assertEqual(set(a["contributions"]),{"food","energy","goods","shelter","other"})
        self.assertAlmostEqual(sum(a["contributions"].values()),a["headline"])
        other=m.monthly_aggregate({"2024-11-05":10,"2024-11-12":20})
        self.assertEqual(other["2024-11-01"],15)
        changed=fixture()
        changed["gasoline"]["2024-11-01"]*=0.8
        b=m.components(changed,w,"2024-11-01")
        self.assertNotAlmostEqual(a["headline"],b["headline"],places=4)
        self.assertAlmostEqual(a["core"],b["core"],places=9)

    def test_absent_current_month_gas_data_blocks_cpi(self):
        data=fixture()
        del data["gasoline"]["2024-11-01"]
        self.assertIsNone(m.components(data,WEIGHTS[1],"2024-11-01"))

    def test_pce_can_use_known_same_month_cpi(self):
        data=fixture(latest="2024-10-01")
        # CPI November is released before November PCE report; PCE itself is not.
        for name in ("cpi","corecpi","ppi"):
            old=data[name]["2024-10-01"]
            data[name]["2024-11-01"]=old*1.004
        result=m.pce_models(data,"2024-11-01",WEIGHTS[1])
        self.assertIsNotNone(result)
        self.assertTrue(all(result["same_month_actual_published_at_cutoff"].values()))
        self.assertAlmostEqual(result["inputs"]["cpi"],.4)
        self.assertTrue(m.is_number(result["headline"]))
        self.assertTrue(m.is_number(result["core"]))

    def test_replay_is_not_target_leaky(self):
        old=m.release_calendar
        try:
            m.release_calendar=event_days
            client=FakeClient()
            rep=m.evaluate(client,"cpi","2024-12-01","2024-12-20",WEIGHTS,7,0)
            self.assertEqual(rep["calendar_candidates"],2)
            self.assertEqual(rep["evaluated_cases"],1)
            self.assertEqual(rep["results"][0]["release_date"],"2024-12-11")
            self.assertEqual(rep["results"][0]["as_of"],"2024-12-04")
            self.assertAlmostEqual(rep["results"][0]["actual"]["headline"],.2)
            self.assertEqual(rep["results"][0]["official_weights_reference"],"2023-12")
            self.assertEqual(rep["skipped"][0]["reason"],"Duplicate target month")
            self.assertAlmostEqual(rep["results"][0]["predictions"]["headline"]["baseline"],.31,places=3)
            # The prediction and the outcome must come from distinct vintage dates.
            self.assertTrue(any(a=="2024-12-04" for s,a in client.calls))
            self.assertTrue(any(a=="2024-12-11" for s,a in client.calls))
        finally:
            m.release_calendar=old

    def test_core_weight_partition(self):
        for w in WEIGHTS:
            self.assertAlmostEqual(sum(w[k] for k in ("food","energy","goods","shelter","other")),100)

if __name__=="__main__":
    unittest.main()
