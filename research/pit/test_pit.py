import unittest
from fetch_pit import parse_observations,payroll_averages,normalize

class Tests(unittest.TestCase):
 def test_realtime_and_future(self):
  body={'observations':[
      {'date':'2024-08-01','value':'4.2','realtime_start':'2024-08-01','realtime_end':'2024-09-30'},
      {'date':'2024-07-01','value':'4.1','realtime_start':'2024-09-01','realtime_end':'9999-12-31'},
      {'date':'2024-10-01','value':'4.3','realtime_start':'2024-08-01','realtime_end':'9999-12-31'},
      {'date':'2024-06-01','value':'.','realtime_start':'2024-01-01','realtime_end':'9999-12-31'}]}
  self.assertEqual(parse_observations(body,'2024-08-31'),[['2024-08',4.2]])
 def test_rolling_gaps(self):
  payems=[['2024-01',100],['2024-02',110],['2024-03',130],['2024-04',160]]
  self.assertEqual(payroll_averages(payems,3),[['2024-04',20.0]])
  self.assertEqual(payroll_averages([['2024-01',100],['2024-02',110],['2024-04',130],['2024-05',140]],2),[])
 def test_unit_conversion_and_missing(self):
  b={'IC4WSA':{'observations':[{'date':'2024-08-24','value':'198750','realtime_start':'2024-08-30','realtime_end':'2024-09-30'}]},
     'CES0500000021':{'error':'Unavailable'}}
  metrics,trace,error=normalize(b,'2024-08-31')
  self.assertEqual(metrics['claims4wk']['value'],198.75)
  self.assertNotIn('diffusion',metrics)
  self.assertIn('CES0500000021',error)

if __name__=='__main__':unittest.main()
