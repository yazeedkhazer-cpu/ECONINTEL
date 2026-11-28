/* ECONINTEL CPI component model v2 — research candidate, NOT a validated nowcast.
   October 2026 BLS CPI release / September 2026 published relative importance.
   https://www.bls.gov/news.release/archives/cpi_11102026.htm
   Composite contributions are an approximation; BLS indexes are not additive
   in exactly this way due index arithmetic and seasonal adjustment.
   Re-estimate subcomponent weights and residuals for each PIT evaluation. */
(function(root){
"use strict";
const ok=Number.isFinite, BLS_URL="https://www.bls.gov/news.release/archives/cpi_11102026.htm";
const W=Object.freeze({
  food:13.447, energy:7.649, goods:18.807, shelter:35.238, otherServices:24.860,
  rent:7.707, oer:25.853, apparel:2.489, newCars:3.729, usedCars:2.670,
  medical:6.813, transportation:6.256, insurance:2.510, airfare:1.055
});
function weights(){
 const w={...W};
 w.otherShelter=+(w.shelter-w.rent-w.oer).toFixed(3);
 w.otherGoods=+(w.goods-w.apparel-w.newCars-w.usedCars).toFixed(3);
 w.otherTransportation=+(w.transportation-w.insurance-w.airfare).toFixed(3);
 w.otherServicesRemainder=+(w.otherServices-w.medical-w.transportation).toFixed(3);
 return w;
}
const split=weights();
const required=["cpi","corecpi","cpishelter","cpirent","cpioer","cpigoods",
"cpiservices","cpiapparel","cpinewvehicles","cpiusedcars",
"cpimedicalservices","cpitransportservices","cpiinsurance","cpiairfares"];
function monthKey(idx){return String(Math.floor(idx/12)).padStart(4,"0")+"-"+String(idx%12+1).padStart(2,"0");}
function monthNumber(s){return /^\d{4}-(0[1-9]|1[0-2])$/.test(s)?+s.slice(0,4)*12+(+s.slice(5))-1:null;}
function lastMonth(d,id){
 const s=d.series?.[id],a=s?.history;
 return a?.length?a[a.length-1][0]:null;
}
function rate(d,id,m){
 const s=d.series?.[id],a=s?.history;
 if(!a||!["connected","stale"].includes(s.status))return null;
 const previous=monthKey(monthNumber(m)-1);
 const row=a.find(p=>p[0]===m),prev=a.find(p=>p[0]===previous);
 return row&&prev&&ok(row[1])&&ok(prev[1])&&prev[1]>0?(row[1]/prev[1]-1)*100:null;
}
function smooth(d,id,last,volatile=false){
 const j=monthNumber(last);
 if(j===null)return null;
 const r=[0,1,2].map(i=>rate(d,id,monthKey(j-i)));
 if(!r.every(ok))return null;
 const avg=(r[0]+r[1]+r[2])/3;
 // Fixed, unoptimised research weights. Monthly latest is deliberately damped.
 return volatile?.25*r[0]+.75*avg:.4*r[0]+.6*avg;
}
function historicalResidual(d,last,weight,series){
 const j=monthNumber(last);if(j===null)return null;
 const residual=[];
 for(let lag=0;lag<3;lag++){
  const m=monthKey(j-lag);
  let num=weight.total*rate(d,weight.totalId,m);
  if(!ok(num))return null;
  for(const item of series){
   const r=rate(d,item.id,m);
   if(!ok(r))return null;
   num-=item.weight*r;
  }
  if(!(weight.remainder>0))return null;
  residual.push(num/weight.remainder);
 }
 const avg=residual.reduce((a,b)=>a+b,0)/residual.length;
 return {rate:avg, monthly:residual, note:"Derived residual of published parent CPI series, not a separately reported series"};
}
function buildPart(id,name,weight,projected,source,method){
 return {id,name,weight,rate:projected,contribution:ok(projected)?weight*projected/100:null,
 source,method};
}
function makeGroup(name,children,totalWeight){
 if(children.some(x=>!ok(x.contribution)))return null;
 const contributed=children.reduce((s,p)=>s+p.contribution,0);
 const rate=100*contributed/totalWeight;
 return {name,weight:totalWeight,rate,contribution:contributed,children};
}
function assess(data, {requireFresh=true}={}){
 if(!data?.series)throw Error("No CPI source series");
 const baseline=root.ECON_INFLATION_STRUCTURAL?.compute(data);
 const base=lastMonth(data,"cpi");
 if(!base||monthNumber(base)===null)return {status:"insufficient",reason:"لا توجد قراءة CPI تاريخية شهرية",required};
 const target=monthKey(monthNumber(base)+1);
 const missing=required.filter(id=>{
  const s=data.series[id];
  return !s||!["connected","stale"].includes(s.status)||
   !s.history?.length||(requireFresh&&lastMonth(data,id)!==base);
 });
 const baseResult={version:"2.0-research",status:"insufficient",base,target,
  missing,weights:split,blsReferenceMonth:"2026-09",blsPublished:"2026-11-10",
  source:BLS_URL,notValidated:true,baseline:baseline?.forecasts||null};
 const rent=smooth(data,"cpirent",base),oer=smooth(data,"cpioer",base);
 const shelterResidual=historicalResidual(data,base,
  {total:split.shelter,totalId:"cpishelter",remainder:split.otherShelter},[
   {id:"cpirent",weight:split.rent},{id:"cpioer",weight:split.oer}]);
 if([rent,oer,shelterResidual?.rate].every(ok)){
  baseResult.shelterPreview=makeGroup("السكن",[
   buildPart("rent","الإيجار الفعلي",split.rent,rent,"cpirent","40% آخر شهر + 60% متوسط 3"),
   buildPart("oer","الإيجار المكافئ للمالكين",split.oer,oer,"cpioer","40% آخر شهر + 60% متوسط 3"),
   buildPart("otherShelter","باقي السكن",split.otherShelter,shelterResidual.rate,
       "cpishelter residual","متوسط مكون متبقٍ مستنتج، وليس سلسلة مستقلة")],split.shelter);
 }
 if(missing.length){
  return {...baseResult,status:"awaiting_component_data",
    reason:"السلاسل التفصيلية لم تُحمّل كلها بعد: "+missing.join(" · ")};
 }
 const apparel=smooth(data,"cpiapparel",base,true),
       newCars=smooth(data,"cpinewvehicles",base,true),
       usedCars=smooth(data,"cpiusedcars",base,true),
       medical=smooth(data,"cpimedicalservices",base),
       insurance=smooth(data,"cpiinsurance",base),
       airfare=smooth(data,"cpiairfares",base,true);
 const goodsOther=historicalResidual(data,base,
   {total:split.goods,totalId:"cpigoods",remainder:split.otherGoods},[
    {id:"cpiapparel",weight:split.apparel},
    {id:"cpinewvehicles",weight:split.newCars},
    {id:"cpiusedcars",weight:split.usedCars}]);
 const transportationOther=historicalResidual(data,base,
  {total:split.transportation,totalId:"cpitransportservices",remainder:split.otherTransportation},[
   {id:"cpiinsurance",weight:split.insurance},
   {id:"cpiairfares",weight:split.airfare}]);
 const serviceOther=historicalResidualServices(data,base);
 const transport=makeGroup("خدمات النقل",[
   buildPart("insurance","تأمين السيارات",split.insurance,insurance,"cpiinsurance","زخم مخفف"),
   buildPart("airfare","تذاكر الطيران",split.airfare,airfare,"cpiairfares","زخم مخفف للتقلب"),
   buildPart("otherTransport","خدمات النقل المتبقية",split.otherTransportation,transportationOther?.rate,
       "cpitransportservices residual","مكون متبقٍ مستنتج")],split.transportation);
 const goods=makeGroup("السلع الأساسية",[
   buildPart("apparel","الملابس",split.apparel,apparel,"cpiapparel","زخم مخفف للتقلب"),
   buildPart("newCars","السيارات الجديدة",split.newCars,newCars,"cpinewvehicles","زخم مخفف للتقلب"),
   buildPart("usedCars","السيارات المستعملة",split.usedCars,usedCars,"cpiusedcars","زخم مخفف للتقلب"),
   buildPart("otherGoods","السلع الأساسية الأخرى",split.otherGoods,goodsOther?.rate,
       "cpigoods residual","مكون متبقٍ مستنتج")],split.goods);
 const services=makeGroup("الخدمات خارج السكن",[
   buildPart("medical","الخدمات الطبية",split.medical,medical,"cpimedicalservices","زخم مخفف"),
   buildPart("transport","خدمات النقل",split.transportation,transport?.rate,
       "cpitransportservices","مجموع مكونات النقل"),
   buildPart("otherServices","الخدمات الأخرى",split.otherServicesRemainder,serviceOther?.rate,
       "cpiservices residual","مكون متبقٍ مستنتج")],split.otherServices);
 if(!baseResult.shelterPreview||!goods||!services||
    !ok(baseline?.energy?.rate)||!ok(root.ECON_INFLATION_STRUCTURAL?.trend(data,"cpifood",base))){
  return {...baseResult,status:"insufficient",
    reason:"فجوة أو انقطاع في سجل واحد من مكونات CPI المطلوبة"};
 }
 const foodRate=root.ECON_INFLATION_STRUCTURAL.trend(data,"cpifood",base);
 const energyRate=baseline.energy.rate;
 const headlineContributions=[
  buildPart("food","الغذاء",split.food,foodRate,"cpifood","زخم 3 أشهر"),
  buildPart("energy","الطاقة",split.energy,energyRate,"gasoline→cpienergy","نموذج الطاقة v1"),
  buildPart("goods","السلع الأساسية",split.goods,goods.rate,"components","تفكيك فرعي"),
  buildPart("shelter","السكن",split.shelter,baseResult.shelterPreview.rate,"components","تفكيك الإيجارات"),
  buildPart("coreServices","الخدمات خارج السكن",split.otherServices,services.rate,"components","تفكيك الخدمات")
 ];
 const cpi=headlineContributions.reduce((a,p)=>a+p.contribution,0)/
  (split.food+split.energy+split.goods+split.shelter+split.otherServices)*100;
 const core=(goods.contribution+baseResult.shelterPreview.contribution+services.contribution)/
  (split.goods+split.shelter+split.otherServices)*100;
 return {...baseResult,status:"experimental_unvalidated",cpi,core,groups:{
   goods,shelter:baseResult.shelterPreview,transport,services
  },contributions:headlineContributions,
  inputsGeneratedAt:data.generatedAt||null,
  limitations:[
   "BLS Sep 2026 weights only; historical backtest requires event-date weights",
   "Fixed heuristic momentum and inferred residuals; no historical calibration or consensus comparison yet",
   "Seasonally adjusted CPI component indices and rounded relative importance are not exactly additive",
   "Monthly gasoline proxy may be partial; energy uses previous experimental v1 rule"
  ]};
}
function historicalResidualServices(data,last){
 const j=monthNumber(last),vals=[];
 if(j===null)return null;
 const w=split;
 for(let lag=0;lag<3;lag++){
  const period=monthKey(j-lag);
  const sv=rate(data,"cpiservices",period);
  const sh=rate(data,"cpishelter",period);
  const md=rate(data,"cpimedicalservices",period);
  const tr=rate(data,"cpitransportservices",period);
  if(![sv,sh,md,tr].every(ok))return null;
  vals.push((60.098*sv-w.shelter*sh-w.medical*md-w.transportation*tr)/w.otherServicesRemainder);
 }
 return {rate:vals.reduce((a,b)=>a+b,0)/3,monthly:vals};
}
root.ECON_CPI_COMPONENTS_V2={assess,weights,rate,smooth,historicalResidual,historicalResidualServices};
})(typeof window!=="undefined"?window:globalThis);
