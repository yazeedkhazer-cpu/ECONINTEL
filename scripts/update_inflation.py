#!/usr/bin/env python3
"""ECONINTEL Inflation Observatory: read-only external FRED series retrieval.
Writes only data/inflation-latest.json. No model fit, no prediction claims, no CPI weights assumptions.
"""
import json, os, math, time, urllib.parse, urllib.request, urllib.error
from pathlib import Path
from datetime import datetime, timezone
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data'/'inflation-latest.json'
KEY=os.getenv('FRED_API_KEY','').strip()
API='https://api.stlouisfed.org/fred/series/observations'
# Verified and research-candidate FRED IDs; nonexistent/unavailable are explicitly missing, never fabricated.
# tag: price = price-index level, yoyrate = percent from source, level = raw level, pmi = diffusion, commodity = physical input price.
RAW=[
 ('cpi','CPIAUCSL','CPI العام','أسعار المستهلك','price','monthly','BLS/FRED','headline'),
 ('corecpi','CPILFESL','Core CPI','أسعار المستهلك','price','monthly','BLS/FRED','core'),
 ('pce','PCEPI','PCE العام','نفقات الاستهلاك','price','monthly','BEA/FRED','headline'),
 ('corepce','PCEPILFE','Core PCE','نفقات الاستهلاك','price','monthly','BEA/FRED','core'),
 ('cpishelter','CUSR0000SAH1','CPI السكن','السكن والإيجارات','price','monthly','BLS/FRED','shelter'),
 ('cpirent','CUSR0000SEHA','الإيجار الفعلي CPI','السكن والإيجارات','price','monthly','BLS/FRED','shelter'),
 ('cpioer','CUSR0000SEHC','الإيجار المكافئ للمالكين OER','السكن والإيجارات','price','monthly','BLS/FRED','shelter'),
 ('cpienergy','CPIENGSL','CPI الطاقة','الطاقة والمواد الأولية','price','monthly','BLS/FRED','energy'),
 ('cpifood','CPIUFDSL','CPI الغذاء','الغذاء','price','monthly','BLS/FRED','food'),
 ('cpigoods','CUSR0000SACL1E','CPI السلع باستثناء الغذاء والطاقة','السلع والخدمات','price','monthly','BLS/FRED','goods'),
 ('cpiservices','CUSR0000SASLE','CPI الخدمات باستثناء الطاقة','السلع والخدمات','price','monthly','BLS/FRED','services'),
 ('cpilodging','CUSR0000SEHB','الإقامة الفندقية CPI','السكن والإيجارات','price','monthly','BLS/FRED','shelter_detail'),
 ('cpiapparel','CPIAPPSL','الملابس CPI','السلع والخدمات','price','monthly','BLS/FRED','core_goods_detail'),
 ('cpinewvehicles','CUSR0000SETA01','السيارات الجديدة CPI','السلع والخدمات','price','monthly','BLS/FRED','core_goods_detail'),
 ('cpiusedcars','CUSR0000SETA02','السيارات المستعملة CPI','السلع والخدمات','price','monthly','BLS/FRED','core_goods_detail'),
 ('cpimedicalservices','CUSR0000SAM2','الخدمات الطبية CPI','السلع والخدمات','price','monthly','BLS/FRED','core_services_detail'),
 ('cpitransportservices','CUSR0000SAS4','خدمات النقل CPI','السلع والخدمات','price','monthly','BLS/FRED','core_services_detail'),
 ('cpiinsurance','CUSR0000SETE','تأمين السيارات CPI','السلع والخدمات','price','monthly','BLS/FRED','core_services_detail'),
 ('cpiairfares','CUSR0000SETG01','أسعار تذاكر الطيران CPI','السلع والخدمات','price','monthly','BLS/FRED','core_services_detail'),
 ('ppi','PPIFIS','PPI الطلب النهائي','أسعار المنتجين','price','monthly','BLS/FRED','ppi'),
 ('ppicomm','PPIACO','PPI السلع الأساسية للمنتجين','أسعار المنتجين','price','monthly','BLS/FRED','ppi'),
 ('import','IR','أسعار الواردات الأمريكية','الاستيراد والتوريد','price','monthly','BLS/FRED','import_nsa'),
 ('gdpdef','GDPDEF','مُعامل انكماش GDP','الأسعار الأوسع','price','quarterly','BEA/FRED','gdp'),
 ('sticky','STICKCPIM159SFRBATL','Sticky CPI 12m','التضخم الأساسي المستمر','yoyrate','monthly','Atlanta Fed/FRED','persistence'),
 ('median','MEDCPIM158SFRBCLE','Median CPI الشهري السنوي','التضخم الأساسي المستمر','annualizedrate','monthly','Cleveland Fed/FRED','persistence'),
 ('trimcpi','TRMMEANCPIM158SFRBCLE','Trimmed Mean CPI الشهري السنوي','التضخم الأساسي المستمر','annualizedrate','monthly','Cleveland Fed/FRED','persistence'),
 ('trimpce','PCETRIM12M159SFRBDAL','Trimmed Mean PCE 12m','التضخم الأساسي المستمر','yoyrate','monthly','Dallas Fed/FRED','persistence'),
 ('wti','DCOILWTICO','نفط WTI','الطاقة والمواد الأولية','commodity','daily','EIA/FRED','energy'),
 ('brent','DCOILBRENTEU','نفط Brent','الطاقة والمواد الأولية','commodity','daily','EIA/FRED','energy'),
 ('gasoline','GASREGW','سعر البنزين التجزئة','الطاقة والمواد الأولية','commodity','weekly','EIA/FRED','energy'),
 ('natgas','DHHNGSP','الغاز الطبيعي','الطاقة والمواد الأولية','commodity','daily','EIA/FRED','energy'),
 ('wages','CES0500000003','متوسط الأجر في القطاع الخاص','الطلب والأجور','level','monthly','BLS/FRED','wage'),
 ('eci','ECIALLCIV','مؤشر تكلفة التوظيف ECI','الطلب والأجور','price','quarterly','BLS/FRED','wage'),
 ('ulc','ULCNFB','تكلفة العمل لوحدة الإنتاج','الطلب والأجور','price','quarterly','BLS/FRED','wage'),
 ('retail','RSAFS','مبيعات التجزئة','الطلب والأجور','level','monthly','Census/FRED','demand'),
 ('realpce','PCEC96','الاستهلاك الحقيقي','الطلب والأجور','level','monthly','BEA/FRED','demand'),
 ('savings','PSAVERT','معدل الادخار الشخصي','ائتمان وثقة المستهلك','level','monthly','BEA/FRED','demand'),
 ('credit','TOTALSL','ائتمان المستهلك القائم','ائتمان وثقة المستهلك','level','monthly','Fed/FRED','credit'),
 ('debtservice','TDSP','عبء خدمة ديون الأسر','ائتمان وثقة المستهلك','level','quarterly','Fed/FRED','credit'),
 ('delinq','DRCCLACBS','تأخر سداد البطاقات الائتمانية','ائتمان وثقة المستهلك','level','quarterly','Fed/FRED','credit'),
 ('sentiment','UMCSENT','ثقة المستهلك — ميشيغان','ائتمان وثقة المستهلك','level','monthly','Michigan/FRED','confidence'),
 ('mich','MICH','توقع التضخم سنة — ميشيغان','التوقعات والتسعير','level','monthly','Michigan/FRED','expectations'),
 ('breakeven5','T5YIE','تعادل تضخم TIPS خمس سنوات','التوقعات والتسعير','level','daily','Fed/FRED','market'),
 ('breakeven10','T10YIE','تعادل تضخم TIPS عشر سنوات','التوقعات والتسعير','level','daily','Fed/FRED','market'),
 ('forwardinfl','T5YIFR','تعادل تضخم 5y5y','التوقعات والتسعير','level','daily','Fed/FRED','market'),
 ('case','CSUSHPINSA','Case-Shiller أسعار المنازل','السكن والإيجارات','price','monthly','S&P/FRED','houseprice'),
 ('starts','HOUST','بدء إنشاء المساكن','السكن والإيجارات','level','monthly','Census/FRED','housing_supply'),
 ('permits','PERMIT','تصاريح البناء','السكن والإيجارات','level','monthly','Census/FRED','housing_supply'),
 ('mortgage','MORTGAGE30US','فائدة الرهن العقاري 30 سنة','السكن والإيجارات','level','weekly','Freddie Mac/FRED','housing_supply'),
 ('vacancy','RRVRUSQ156N','معدل شغور المساكن المؤجرة','السكن والإيجارات','level','quarterly','Census/FRED','housing_supply'),
]
SOURCES=[{'id':a,'fredId':b,'label':c,'group':d,'kind':e,'frequency':f,'provider':g,'role':h,'url':'https://fred.stlouisfed.org/series/'+b} for a,b,c,d,e,f,g,h in RAW]
MANUAL=[
 {'id':'ism_man_prices','label':'ISM Manufacturing Prices Paid','group':'PMI / ضغوط الأسعار','provider':'ISM','status':'not_connected','url':'https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/'},
 {'id':'ism_services_prices','label':'ISM Services Prices Paid','group':'PMI / ضغوط الأسعار','provider':'ISM','status':'not_connected','url':'https://www.ismworld.org/'},
 {'id':'sp_flash_input','label':'S&P Flash PMI Input Prices','group':'PMI / ضغوط الأسعار','provider':'S&P Global','status':'not_connected','url':'https://www.spglobal.com/marketintelligence/'},
 {'id':'sp_flash_charged','label':'S&P Flash PMI Prices Charged','group':'PMI / ضغوط الأسعار','provider':'S&P Global','status':'not_connected','url':'https://www.spglobal.com/marketintelligence/'},
 {'id':'zori','label':'Zillow Observed Rent Index — USA','group':'السكن والإيجارات','provider':'Zillow','status':'not_connected','url':'https://www.zillow.com/research/data/'},
 {'id':'gscpi','label':'Global Supply Chain Pressure Index','group':'الاستيراد والتوريد','provider':'NY Fed','status':'not_connected','url':'https://www.newyorkfed.org/research/policy/gscpi'},
 {'id':'sce_1y','label':'NY Fed Survey of Consumer Expectations 1y','group':'التوقعات والتسعير','provider':'NY Fed','status':'not_connected','url':'https://www.newyorkfed.org/microeconomics/databank.html'},
 {'id':'cleveland_nowcast','label':'Cleveland Fed Inflation Nowcast','group':'التنبؤ والمتابعة','provider':'Cleveland Fed','status':'not_connected','url':'https://www.clevelandfed.org/our-research/indicators-and-data/inflation-nowcasting'},
 {'id':'freight','label':'Freight / shipping cost index','group':'الاستيراد والتوريد','provider':'provider needed','status':'not_connected','url':'https://www.newyorkfed.org/research/policy/gscpi'},
]

def roundv(x):
    return round(x,5) if math.isfinite(x) else None

def get_source(spec):
    if not KEY:return spec['id'], {'status':'missing','error':'FRED_API_KEY not configured'}
    query=urllib.parse.urlencode({'api_key':KEY,'series_id':spec['fredId'],'file_type':'json','observation_start':'2018-01-01','limit':100000})
    req=urllib.request.Request(API+'?'+query,headers={'User-Agent':'ECONINTEL-Inflation-Research/1.0'})
    for n in range(3):
      try:
        with urllib.request.urlopen(req,timeout=30) as h: ob=json.loads(h.read().decode('utf8'))
        if 'error_code' in ob: raise ValueError('source HTTP error '+str(ob['error_code']))
        bydate={}
        for r in ob.get('observations',[]):
            try:
                val=float(r['value'])
                if math.isfinite(val):bydate[r['date']]=val
            except (ValueError,TypeError,KeyError):continue
        items=sorted(bydate.items())
        if not items: return spec['id'],{'status':'missing','error':'No valid observations'}
        # Commodity and market series: monthly mean for same-period comparisons; this is NOT publication-time replay.
        if spec['frequency'] in ('daily','weekly'):
            chunks=OrderedDict()
            for dt,v in items:chunks.setdefault(dt[:7],[]).append(v)
            monthly=[[m,roundv(sum(v)/len(v))] for m,v in chunks.items()]
        elif spec['frequency']=='quarterly':
            monthly=[[d[:4]+'-Q'+str((int(d[5:7])-1)//3+1),v] for d,v in items]
        else: monthly=[[d[:7],v] for d,v in items]
        return spec['id'],{'status':'connected','history':monthly[-120:],'value':monthly[-1][1],'period':monthly[-1][0], 'observations':len(monthly),'partialPeriod':spec['frequency'] in ('daily','weekly') and monthly[-1][0]==datetime.now(timezone.utc).strftime('%Y-%m')}
      except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,ValueError,json.JSONDecodeError) as ex:
        # Never include URL/query, which contains the key, in logs.
        err='HTTP status '+str(ex.code) if isinstance(ex,urllib.error.HTTPError) else type(ex).__name__
        if n==2 or (isinstance(ex,urllib.error.HTTPError) and ex.code not in (429,500,502,503,504)):
            return spec['id'],{'status':'missing','error':err}
        time.sleep(n+1)
    return spec['id'],{'status':'missing','error':'Unknown source error'}

def main():
  previous={}
  if OUT.exists():
    try:previous=json.loads(OUT.read_text(encoding='utf8')).get('series',{})
    except (OSError,ValueError):pass
  results={}
  with ThreadPoolExecutor(max_workers=5) as pool:
    futures=[pool.submit(get_source,s) for s in SOURCES]
    for f in as_completed(futures):
      k,r=f.result()
      if r['status']=='missing' and k in previous and previous[k].get('status') in ('connected','stale'):
        r={'status':'stale','error':r['error'],**{field:previous[k][field] for field in ('history','value','period','observations','partialPeriod') if field in previous[k]}}
      results[k]=r
  snap={'schemaVersion':1,'generatedAt':datetime.now(timezone.utc).isoformat(),'source':'FRED observations as currently revised (NOT as-published historical vintage)',
   'methodology':'Diagnostic monitoring; not calibrated CPI prediction; FRED period is NOT release date.',
   'catalog':SOURCES,'series':results,'unconnected':MANUAL}
  OUT.parent.mkdir(parents=True,exist_ok=True)
  p=OUT.with_suffix('.tmp');p.write_text(json.dumps(snap,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf8');p.replace(OUT)
  connected=sum(r['status']=='connected' for r in results.values())
  print(f'Inflation observations: {connected}/{len(SOURCES)} connected, {len(SOURCES)-connected} missing/stale. Key present: {bool(KEY)}')
  # Reject a silently empty refresh when key exists and no prior data; publish explicit unavailable metadata only.
  if connected==0:raise SystemExit('No current source connected; review API errors and secret')
if __name__=='__main__':main()
