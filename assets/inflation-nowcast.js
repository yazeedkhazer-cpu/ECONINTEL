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
 const structural=root.ECON_INFLATION_STRUCTURAL?.compute(d)||{status:"unavailable",reason:"الطبقة الاقتصادية غير متصلة",forecasts:{}};
 const detailed=root.ECON_CPI_COMPONENTS_V2?.assess(d)||{status:"not_loaded",missing:[],reason:"طبقة CPI التفصيلية غير متصلة"};
 return {generatedAt:d.generatedAt??null,structural,detailed,
  forecasts:TARGETS.map(x=>({...x,baseline:forecastBase(d.series[x.id]),
    econintel:structural.forecasts?.[x.id]??null,marketConsensus:null,
    state:structural.forecasts?.[x.id]?.status??"missing"})),
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
 const b=t.baseline,model=t.econintel,ready=N(model?.mom);
 return '<article class="target"><div class="top"><div><div class="eyebrow">'+e(t.name)+'</div><h3>'+e(t.ar)+'</h3></div><span>'+e(t.agency)+'</span></div>'+
 '<div class="small">الفترة المستهدفة: '+e(b.period||"غير متاحة")+
 ' · تاريخ الإصدار المخطط: '+e(t.release)+'</div>'+
 '<div class="grid3"><div class="metric"><small>ECONINTEL بحثي MoM</small><strong>'+fmt(model?.mom,3)+'</strong><span>'+e(ready?"نموذج أولي غير مختبر تاريخيًا":view.structural.reason||"غير متاح")+'</span></div>'+
 '<div class="metric"><small>ECONINTEL بحثي YoY</small><strong>'+fmt(model?.yoy,2)+'</strong><span>محسوب من سلسلة SA، وليس الرقم الرسمي NSA</span></div>'+
 '<div class="metric"><small>خط الأساس MoM</small><strong>'+fmt(b.mom,3)+'</strong><span>'+e(b.status==="baseline"?"متوسط آخر 3 أشهر":b.why)+'</span></div></div>'+
 '<div class="small">'+e(model?.source||"لا توجد منهجية مكتملة")+'</div>'+
 '<div class="comparison"><label>إجماع السوق الشهري (%) <input type="number" class="consensus" step="0.01" data-id="'+e(t.id)+'" placeholder="أدخل قراءة موثقة"></label>'+
 '<span>فارق ECONINTEL عن السوق: <b class="diff" data-id="'+e(t.id)+'">—</b></span></div>'+
 '<p class="small">توقع بحثي أولي: لا يُعامل على أنه مُثبت الدقة، ولا يساوي إجماع السوق. يلزم تاريخ ومصدر مستقل لرقم إجماع السوق قبل المقارنة الرسمية.</p></article>';
 }).join("");
 node.querySelectorAll(".consensus").forEach(inp=>inp.addEventListener("input",()=>{
  const parent=inp.closest(".target");
  const id=inp.dataset.id;
  const t=view.forecasts.find(x=>x.id===id);
  const value=inp.value.trim()===""?null:Number(inp.value);
  parent.querySelector(".diff").textContent=difference(t.econintel?.mom,value);
 }));
 const detailedBox=document.getElementById("cpiDetailed");
 if(detailedBox){
  const m=view.detailed;
  const fmtRate=(x)=>N(x)?(x>=0?"+":"")+x.toFixed(3)+"%":"—";
  const line=p=>'<div class="driverline"><span>'+e(p.name)+' · '+p.weight.toFixed(3)+'% سلة CPI</span><span class="mono">'+fmtRate(p.rate)+'</span></div>';
  let html='<p class="small">مرجع الأوزان: سبتمبر 2026، منشور 10 نوفمبر 2026. النموذج تفصيلي بحثي وغير مُعاير تاريخيًا.</p>';
  if(m.status==="experimental_unvalidated"){
   html+='<div class="grid3"><div class="metric"><small>V2 Headline CPI MoM</small><strong>'+fmtRate(m.cpi)+'</strong><span>تقدير تجريبي</span></div>'+
         '<div class="metric"><small>V2 Core CPI MoM</small><strong>'+fmtRate(m.core)+'</strong><span>تقدير تجريبي</span></div>'+
         '<div class="metric"><small>مقارنة V1 Core</small><strong>'+fmtRate(m.baseline?.corecpi?.mom)+'</strong><span>للمقارنة، وليس إثبات تحسن</span></div></div>';
  }else{
   html+='<p class="small">حالة المحرك التفصيلي: '+e(m.reason||m.status)+'</p>';
  }
  if(m.shelterPreview)html+='<h3>السكن · Rent + OER</h3>'+m.shelterPreview.children.map(line).join('');
  if(m.groups?.goods)html+='<h3>السلع الأساسية</h3>'+m.groups.goods.children.map(line).join('');
  if(m.groups?.transport)html+='<h3>النقل والتأمين والطيران</h3>'+m.groups.transport.children.map(line).join('');
  if(m.groups?.services)html+='<h3>الخدمات الأخرى</h3>'+m.groups.services.children.map(line).join('');
  if(m.missing?.length)html+='<p class="small">مصادر لم تصل بياناتها بعد: '+e(m.missing.join(" · "))+'</p>';
  html+='<p class="small">لا نعتمد أرقام V2 ولا نقارنها بالسوق قبل اختبارها تاريخيًا وبناء نطاق خطأ معاير.</p>';
  detailedBox.innerHTML=html;
 }
 const component=document.getElementById("componentBreakdown");
 if(component){
  const s=view.structural;
  if(!Array.isArray(s.parts)) component.textContent=s.reason||"بيانات المكونات غير كافية";
  else component.innerHTML=s.parts.map(p=>'<div class="driverline"><span>'+e(p.name)+' · '+p.weight.toFixed(3)+'% من السلة</span><b class="mono">'+fmt(p.rate,2)+' · '+p.contribution.toFixed(3)+' pp</b></div>').join("")+
   '<p class="small" style="margin-top:12px">نموذج خطي تقريبي بأوزان BLS لشهر سبتمبر 2026. الطاقة مبنية على متوسط أسعار البنزين الجزئي لشهر نوفمبر وارتباطه التاريخي بـCPI الطاقة، ولا تمثل الرقم الرسمي.</p>';
 }
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
  .then(data=>{const v=evaluate(data);draw(v);status.textContent=v.structural?.status==="experimental"?
   "القراءة الاستشرافية البحثية الأولية ظاهرة. نتائجها غير مُعايرة تاريخيًا بعد؛ لا تُقدَّم كاحتمال مؤكد أو إشارة تداول.":
   "بيانات متصلة، لكن نموذج المكونات غير مكتمل: "+(v.structural?.reason||"تعذر حساب الأرقام");})
  .catch(err=>status.textContent="تعذر جلب البيانات: "+err.message);
}
if(typeof document!=="undefined"){if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",mount,{once:true});else mount();}
root.ECON_INFLATION_NOWCAST={monthSeries,forecastBase,monthlyChange,sources,evaluate};
})(typeof window!=="undefined"?window:globalThis);
