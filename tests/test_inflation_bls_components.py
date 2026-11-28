"""Offline tests for the official BLS v2 CPI auto-insurance fallback."""
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("econintel_inflation_update", ROOT/"scripts"/"update_inflation.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class FakeReply:
    def __init__(self,object_):
        self.payload=json.dumps(object_).encode("utf-8")
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self):return self.payload

class TestBlsSeriesFallback(unittest.TestCase):
    def test_registered_motor_insurance_series_is_official_bls(self):
        s=next(s for s in m.SOURCES if s["id"]=="cpiinsurance")
        self.assertEqual(s["fredId"],"CUSR0000SETE")
        self.assertIn("data.bls.gov",s["url"])
        self.assertEqual(s["provider"],"BLS Public API")

    def test_bls_calendar_validation_skips_annual_m13_and_preserves_gap(self):
        s=next(s for s in m.SOURCES if s["id"]=="cpiinsurance")
        payload={"status":"REQUEST_SUCCEEDED","Results":{"series":[{"data":[
           {"year":"2026","period":"M10","value":"842.132"},
           {"year":"2026","period":"M13","value":"899"},
           {"year":"2026","period":"M08","value":"831.447"},
           {"year":"2026","period":"M09","value":"837.289"}]}]}}
        def respond(req,timeout=30):
            self.assertEqual(req.get_method(),"POST")
            sent=json.loads(req.data.decode("utf-8"))
            self.assertEqual(sent["seriesid"],["CUSR0000SETE"])
            return FakeReply(payload)
        with patch.object(m.urllib.request,"urlopen",side_effect=respond):
            key,result=m.get_source(s)
        self.assertEqual(key,"cpiinsurance")
        self.assertEqual(result["status"],"connected")
        self.assertEqual([x[0] for x in result["history"]],["2026-08","2026-09","2026-10"])
        self.assertEqual(result["value"],842.132)
        self.assertFalse(result["partialPeriod"])

    def test_invalid_bls_response_is_missing_not_fabricated(self):
        s=next(s for s in m.SOURCES if s["id"]=="cpiinsurance")
        with patch.object(m.urllib.request,"urlopen",return_value=FakeReply(
                {"status":"REQUEST_FAILED","Results":{}})):
            with patch.object(m.time,"sleep",return_value=None):
                id_,result=m.get_source(s)
        self.assertEqual(id_,"cpiinsurance")
        self.assertEqual(result["status"],"missing")
        self.assertNotIn("history",result)

if __name__=="__main__":unittest.main()
