/* ECONINTEL inflation-family nowcast workbench — diagnostic preview, not calibrated CPI/PCE forecast. */
(function(root){
"use strict";
const N=Number.isFinite;
const TARGETS=[
 {id:"cpi",name:"Headline CPI",ar:"التضخم العام للمستهلك",group:"CPI",agency:"BLS",release:"2026-12-10",unit:"CPI"},
 {id:"corecpi",name:"Core CPI",ar:"التضخم الأساسي للمستهلك",group:"CPI",agency:"BLS",release:"2026-12-10",unit:"CPI"},
 {id:"pce",name:"Headline PCE",ar:"مؤشر نفقات الاستهلاك العام",group:"PCE",agency:"BEA",release:"2026-12-23",unit:"PCE"},
 {id:"corepce",name:"Core PCE",ar:"مؤشر نفقات الاستهلاك الأساسي",group:"PCE",agency:"BEA",release:"2026-12-23",unit:"PCE"},
 {id:"ppi",name:"Headline PPI",ar:"أسعار المنتجين — الطلب النهائي",group:"PPI",agency:"BLS",release:"2026-12-15",unit:"PPI"},
];
function monthIndex(s){return /^\d{4}-(0[1-9]|1[0-2])$/.test(s)?Number(s.slice(0,4))*12+Number(s.slice(5))-1:null;}
function monthLabel(n){return String(Math.floor(n/12)).padStart(4,"0")+"-"+String((n%12)+1).padStart(2,"0");}
function monthSeries(series){
 const a=series&&series.history;
 return a&&Array.isArray(a)?a.filter(p=>Array.isArray(p)&&monthIndex(p[0])!==null&&N(p[1])&&p[1]>0)
  .slice().sort((x,y)=>monthIndex(x[0])-monthIndex(y[0])):[];
}
function forecastBase(series){
 const a=monthSeries(series);if(a.length<4)return {status:"insufficient",why:"أقل من 4 مشاهدات شهرية"};
 const last=a.slice(-4);
 const gap=last.some((x,i)=>i>0&&monthIndex(x[0])!==monthIndex(last[i-1][0])+1);
 if(gap)return {status:"insufficient",why:"فجوة في الأشهر الأخيرة — لا نملأ بيانات مفقودة"};
 const growth=last.slice(1).map((p,i)=>(p[1]/last[i][1]-1)*100);
 const mom=growth.reduce((a,b)=>a+b,0)/3;
 const target=monthLabel(monthIndex(last[3][0])+1);
 const prevYear=monthLabel(monthIndex(target)-12);
 const reference=a.find(p=>p[0]===prevYear);
 const projectedIndex=last[3][1]*(1+mom/100);
 const yoy=reference&&reference[1]>0?(projectedIndex/reference[1]-1)*100:null;
 return {status:"baseline",mom,yoy,period:target,lastPeriod:last[3][0],history:growth,
         prevYear:reference?.[0]??null,why:"متوسط MoM لآخر 3 أشهر متصلة؛ ليس توقع ECONINTEL المعتمد"};
}
function monthlyChange(d,id){
 const a=monthSeries(d.series?.[id]);if(a.length<2)return null;
 const x=a.at(-1),y=a.at(-2);
 if(monthIndex(x[0])!==monthIndex(y[0])+1)return null;
 return {value:(x[1]/y[1]-1)*100,period:x[0],partial:!!d.series[id].partialPeriod};
}
function sources(d){
 const ids=[
  ["energy","الطاقة","brent","Brent"],
  ["energy","الطاقة","gasoline","البنزين"],
  ["energy","الطاقة","cpienergy","CPI الطاقة"],
  ["housing","السكن والإيجارات","cpishelter","Shelter"],
  ["housing","السكن والإيجارات","cpirent","Rent"],
  ["housing","السكن والإيجارات","cpioer","OER"],
  ["prices","السلع والخدمات","cpigoods","Core Goods"],
  ["prices","السلع والخدمات","cpiservices","Services"],
  ["supply","المنتجون والواردات","ppi","PPI"],
  ["supply","المنتجون والواردات","ppicomm","PPI Commodities"],
  ["supply","المنتجون والواردات","import","Import Prices"],
  ["labour","الأجور والطلب","wages","Wages"],
  ["labour","الأجور والطلب","retail","Retail Sales"],
  ["labour","الأجور والطلب","realpce","Real PCE"],
  ["persistent","التضخم المستمر","sticky","Sticky CPI"],
  ["persistent","التضخم المستمر","median","Median CPI"],
  ["persistent","التضخم المستمر","trimcpi","Trimmed CPI"],
  ["persistent","التضخم المستمر","trimpce","Trimmed PCE"],
 ];
 return ids.map(([group,groupLabel,id,label])=>({
  group,groupLabel,id,label,metric:monthlyChange(d,id),
  last:d.series?.[id]?.history?.at(-1)??null,
  kind:d.catalog?.find(s=>s.id===id)?.kind??null,
  caveat:!!d.series?.[id]?.partialPeriod,
 }));
}
function evaluate(d){
 if(d?.schemaVersion!==1||!d.series||!Array.isArray(d.catalog))throw Error("Unexpected inflation data schema");
 return {generatedAt:d.generatedAt??null,
  forecasts:TARGETS.map(x=>({...x,baseline:forecastBase(d.series[x.id]),
    econintel:null,marketConsensus:null,
    state:"ECONINTEL forecast uncalibrated — number intentionally withheld"})),
  inputs:sources(d),seriesCount:Object.values(d.series).filter(s=>s.status==="connected").length,
  catalogCount:d.catalog.length};
}
const e=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt=(v,n=2)=>N(v)?(v>=0?"+":"")+v.toFixed(n)+"%":"—";
const difference=(v,c)=>N(v)&&N(c)?(v-c).toFixed(3)+" pp":"—";
function draw(view){
 const node=document.getElementById("nowcastTargets");
 if(!node)return;
 node.innerHTML=view.forecasts.map(t=>{
 const b=t.baseline;
 return '<article class="target"><div class="top"><div><div class="eyebrow">'+e(t.name)+'</div><h3>'+e(t.ar)+'</h3></div><span>'+e(t.agency)+'</span></div>'+
 '<div class="small">الفترة المستهدفة: '+e(b.period||"غير متاحة")+
 ' · تاريخ الإصدار المخطط: '+e(t.release)+'</div>'+
 '<div class="grid3"><div class="metric"><small>ECONINTEL Nowcast</small><strong>—</strong><span>غير معاير بعد</span></div>'+
 '<div class="metric"><small>خط أساس تجريبي MoM</small><strong>'+fmt(b.mom,3)+'</strong><span>'+e(b.status==="baseline"?"متوسط 3 أشهر":b.why)+'</span></div>'+
 '<div class="metric"><small>خط أساس YoY تقريبي</small><strong>'+fmt(b.yoy,2)+'</strong><span>مشتق من مؤشر SA وليس القراءة الرسمية NSA</span></div></div>'+
 '<div class="comparison"><label>توقع السوق MoM (%) <input type="number" class="consensus" step="0.01" data-id="'+e(t.id)+'" placeholder="أدخل إجماعًا موثقًا"></label>'+
 '<span>فارق الخط الأساسي: <b class="diff" data-id="'+e(t.id)+'">—</b></span></div>'+
 '<p class="small">لا نعرض ECONINTEL = خط الأساس؛ المحرك الرقمي متعدد المكونات قيد المعايرة التاريخية.</p></article>';
 }).join("");
 node.querySelectorAll(".consensus").forEach(inp=>inp.addEventListener("input",()=>{
  const parent=inp.closest(".target");
  const id=inp.dataset.id;
  const t=view.forecasts.find(x=>x.id===id);
  const value=inp.value.trim()===""?null:Number(inp.value);
  parent.querySelector(".diff").textContent=difference(t.baseline.mom,value);
 }));
 const groups=[...new Set(view.inputs.map(x=>x.groupLabel))];
 const drivers=document.getElementById("drivers");
 drivers.innerHTML=groups.map(label=>{
 const inputs=view.inputs.filter(x=>x.groupLabel===label);
 return '<div class="driver"><h3>'+e(label)+'</h3>'+inputs.map(x=>
 '<div class="driverline"><span>'+e(x.label)+'</span><span class="mono">'+
 (x.metric?fmt(x.metric.value,2):"—")+'</span></div>'+
 '<div class="small">'+e(x.metric?.period??x.last?.[0]??"غير متاح")+
 (x.caveat?' · شهر جزئي':'')+(x.kind!=="price"?' · يختلف نوع القياس':'')+'</div>').join("")+'</div>'
 }).join("");
 document.getElementById("updated").textContent=view.generatedAt?new Date(view.generatedAt).toLocaleString("ar-JO",{timeZone:"Asia/Amman"}):"غير متاح";
 document.getElementById("coverage").textContent=view.seriesCount+"/"+view.catalogCount;
}
function mount(){
 const status=document.getElementById("status");
 fetch("data/inflation-latest.json?t="+Date.now(),{cache:"no-store"})
  .then(r=>{if(!r.ok)throw Error("HTTP "+r.status);return r.json()})
  .then(data=>{const v=evaluate(data);draw(v);status.textContent="البيانات متاحة. الأرقام الحالية خطوط أساس تجريبية وليست توقعات ECONINTEL المعتمدة.";})
  .catch(err=>status.textContent="تعذر جلب البيانات: "+err.message);
}
if(typeof document!=="undefined"){if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",mount,{once:true});else mount();}
root.ECON_INFLATION_NOWCAST={monthSeries,forecastBase,monthlyChange,sources,evaluate};
})(typeof window!=="undefined"?window:globalThis);
