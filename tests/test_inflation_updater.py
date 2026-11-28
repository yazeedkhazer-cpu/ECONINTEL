import importlib.util,json,pathlib,unittest,unittest.mock,sys
HERE=pathlib.Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('infupdate',HERE/'scripts/update_inflation.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class FakeResponse:
 def __init__(self,body):self.body=body
 def __enter__(self):return self
 def __exit__(self,*a):return False
 def read(self):return json.dumps(self.body).encode()
class Tests(unittest.TestCase):
 def test_no_invented_api_key(self):
  old=m.KEY
  try:
   m.KEY=''
   spec=m.SOURCES[0]
   name,res=m.get_source(spec)
   self.assertEqual(res['status'],'missing')
   self.assertEqual(name,'cpi')
  finally:m.KEY=old
 def test_normalize_monthly(self):
  body={'observations':[{'date':x,'value':str(v)} for x,v in [('2026-06-01',312.0),('2026-07-01',313),('2026-08-01',314)]]}
  with unittest.mock.patch.object(m,'KEY','FAKE'),unittest.mock.patch.object(m.urllib.request,'urlopen',return_value=FakeResponse(body)):
   name,res=m.get_source(m.SOURCES[0])
  self.assertEqual(name,'cpi');self.assertEqual(res['history'],[['2026-06',312.0],['2026-07',313.0],['2026-08',314.0]])
  self.assertEqual(res['status'],'connected')
 def test_daily_aggregation_and_no_future(self):
  body={'observations':[{'date':x,'value':str(v)} for x,v in [('2026-09-02',60),('2026-09-05',70),('2026-10-02',80)]]}
  spec=next(s for s in m.SOURCES if s['id']=='wti')
  with unittest.mock.patch.object(m,'KEY','FAKE'),unittest.mock.patch.object(m.urllib.request,'urlopen',return_value=FakeResponse(body)):
   name,res=m.get_source(spec)
  self.assertEqual(res['history'],[['2026-09',65.0],['2026-10',80.0]])
 def test_catalog_types_unique(self):
  ids=[x['id'] for x in m.SOURCES];self.assertEqual(len(ids),len(set(ids)))
  self.assertEqual(len(m.SOURCES),42)
  self.assertEqual(len(m.MANUAL),9)
  self.assertTrue(all(x['kind'] in {'price','commodity','level','annualizedrate','yoyrate'} for x in m.SOURCES))
if __name__=='__main__':unittest.main()
