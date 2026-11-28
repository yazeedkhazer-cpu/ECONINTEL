/* ECONINTEL Inflation component-proxy nowcast v0.1.
 * EXPERIMENTAL: not validated PIT, no probability/calibrated confidence claimed.
 * Official headline CPI-U Sept 2026 relative-importance weights published with
 * the Oct 2026 BLS CPI report:
 * food 13.447, energy 7.648, core goods 18.807, shelter 35.238,
 * services less energy/shelter 24.860 = 100.000.
 * Source: https://www.bls.gov/news.release/cpi.htm (Oct 2026, table 1)
 * Linear contribution approximation ≠ exact seasonal Laspeyres aggregation.
 */
(function(root){
"use strict";
const W=Object.freeze({food:13.447,energy:7.648,goods:18.807,shelter:35.238,other:24.860});
const FIN=Number.isFinite;
function month(s){return /^\d{4}-(0[1-9]|1[0-2])$/.test(s)?+s.slice(0,4)*12+ +s.slice(5)-1:null;}
function key(n){return String(Math.floor(n/12)).padStart(4,"0")+"-"+String(n%12+1).padStart(2,"0");}
function values(data,id){
 const s=data?.series?.[id];
 return Object.fromEntries((s?.history||[]).filter(x=>Array.isArray(x)&&month(x[0])!==null&&FIN(x[1])&&x[1]>0));
}
function mom(data,id,m){
 const s=values(data,id),n=month(m);
 if(n===null||!FIN(s[m])||!FIN(s[key(n-1)]))return null;
 return (s[m]/s[key(n-1)]-1)*100;
}
function trend(data,id,finish,n=3){
 const end=month(finish);if(end===null)return null;
 const rates=Array.from({length:n},(_,i)=>mom(data,id,key(end-i)));
 return rates.every(FIN)?rates.reduce((a,b)=>a+b,0)/n:null;
}
function latest(data,id){const s=Object.keys(values(data,id)).sort();return s.length?s[s.length-1]:null;}
function average(xs){return xs.reduce((a,b)=>a+b,0)/xs.length;}
function fitProxy(data, target, proxy, finish, minPairs=15){
 const n=month(finish);if(n===null)return null;
 const samples=[];
 for(let i=n-42;i<=n;i++){
  const t=key(i),x=mom(data,proxy,t),y=mom(data,target,t);
  if(FIN(x)&&FIN(y))samples.push([x,y]);
 }
 if(samples.length<minPairs)return null;
 const xm=average(samples.map(x=>x[0])),ym=average(samples.map(x=>x[1]));
 const covariance=samples.reduce((s,p)=>s+(p[0]-xm)*(p[1]-ym),0);
 const variance=samples.reduce((s,p)=>s+(p[0]-xm)**2,0);
 // Penalised univariate slope: stable under small or near-constant proxy variance.
 const beta=Math.max(-1.5,Math.min(1.5,covariance/(variance+10)));
 return {alpha:ym-beta*xm,beta,n:samples.length,proxy};
}
function projectProxy(data,target,proxy,finish,next){
 const fit=fitProxy(data,target,proxy,finish),x=mom(data,proxy,next);
 if(!fit||!FIN(x))return null;
 const rate=fit.alpha+fit.beta*x;
 return {rate:Math.max(-12,Math.min(12,rate)),proxyMove:x,beta:fit.beta,n:fit.n,
  partial:!!data.series?.[proxy]?.partialPeriod,proxy};
}
function otherServices(data,m){
 const sv=mom(data,"cpiservices",m),shelter=mom(data,"cpishelter",m);
 if(!FIN(sv)||!FIN(shelter))return null;
 return (60.098*sv-W.shelter*shelter)/W.other;
}
function otherTrend(data,finish){
 const n=month(finish);if(n===null)return null;
 const a=Array.from({length:3},(_,i)=>otherServices(data,key(n-i)));
 return a.every(FIN)?average(a):null;
}
function yr(data,id,lastIndex,nextMoM,nextPeriod){
 const v=values(data,id),last=lastIndex,reference=v[key(month(nextPeriod)-12)];
 return FIN(last)&&FIN(reference)&&reference>0?(((last*(1+nextMoM/100))/reference)-1)*100:null;
}
function lastLevel(data,id,at){return values(data,id)[at]??null;}
function solve(A,b){
 const n=b.length, M=A.map((r,i)=>r.concat(b[i]));
 for(let k=0;k<n;k++){
  let p=k;for(let i=k+1;i<n;i++)if(Math.abs(M[i][k])>Math.abs(M[p][k]))p=i;
  if(Math.abs(M[p][k])<1e-9)return null;
  [M[k],M[p]]=[M[p],M[k]];
  const den=M[k][k];for(let j=k;j<=n;j++)M[k][j]/=den;
  for(let i=0;i<n;i++){if(i===k)continue;
   const f=M[i][k];for(let j=k;j<=n;j++)M[i][j]-=f*M[k][j];}
 }
 return M.map(row=>row[n]);
}
function ridge(samples,features){
 if(samples.length<24)return null;
 const k=features.length,mean=[],sd=[];
 for(let j=0;j<k;j++){
  const vals=samples.map(s=>s.x[j]);mean[j]=average(vals);
  const v=average(vals.map(x=>(x-mean[j])**2));
  sd[j]=Math.max(Math.sqrt(v),1e-6);
 }
 const transformed=x=>[1,...x.map((v,i)=>(v-mean[i])/sd[i])];
 const X=samples.map(r=>transformed(r.x)), y=samples.map(r=>r.y);
 const size=k+1, matrix=Array.from({length:size},()=>Array(size).fill(0));
 const vec=Array(size).fill(0);
 for(let i=0;i<X.length;i++)for(let j=0;j<size;j++){
  vec[j]+=X[i][j]*y[i];for(let h=0;h<size;h++)matrix[j][h]+=X[i][j]*X[i][h];
 }
 for(let j=1;j<size;j++)matrix[j][j]+=16; // ridge penalty
 const coeff=solve(matrix,vec);if(!coeff)return null;
 return {rate:coeff.reduce((s,c,i)=>s+c*transformed(features)[i],0),
  trainingN:samples.length};
}
function fitPce(data,id,finish,targetRates){
 const upto=month(finish);
 const getfeatures=(m,overrides)=>{
  const f=[
   overrides?.cpi??mom(data,"cpi",m),overrides?.corecpi??mom(data,"corecpi",m),
   overrides?.ppi??mom(data,"ppi",m),
   mom(data,"pce",key(month(m)-1)),mom(data,"corepce",key(month(m)-1))
  ];
  return f.every(FIN)?f:null;
 };
 const samples=[];
 for(let k=upto-78;k<=upto;k++){
  const m=key(k),f=getfeatures(m),y=mom(data,id,m);
  if(f&&FIN(y))samples.push({x:f,y});
 }
 const future=getfeatures(key(upto+1),targetRates);
 if(!future)return null;
 const v=ridge(samples,future);
 return v?{rate:Math.max(-3,Math.min(3,v.rate)),trainingN:v.trainingN,
  note:"Ridge on historical CPI, Core CPI, PPI and lagged PCE; initial current-revised training"}:null;
}
function compute(data){
 if(!data?.series)throw Error("Missing inflation series");
 const base=latest(data,"cpi");if(!base)throw Error("No CPI reference period");
 const next=key(month(base)+1);
 const ids=["corecpi","cpishelter","cpigoods","cpiservices","cpifood","cpienergy","ppi","pce","corepce"];
 if(ids.some(id=>latest(data,id)!==base))
  return {status:"insufficient",reason:"سلاسل بيانات التضخم الأساسية لا تغطي نفس آخر شهر؛ توقف الحساب لمنع خلط الفترات",base,next,forecasts:{}};
 const food=trend(data,"cpifood",base),shelter=trend(data,"cpishelter",base),
       goods=trend(data,"cpigoods",base),other=otherTrend(data,base);
 const energy=projectProxy(data,"cpienergy","gasoline",base,next);
 const ppiProxy=projectProxy(data,"ppi","brent",base,next);
 if(![food,shelter,goods,other].every(FIN)||!energy||!ppiProxy)
  return {status:"insufficient",reason:"بيانات مكونات CPI أو مؤشرات الطاقة غير كافية لنموذج أولي",base,next,forecasts:{}};
 const parts=[
  {name:"الغذاء",weight:W.food,rate:food,source:"cpifood"},
  {name:"الطاقة",weight:W.energy,rate:energy.rate,source:"gasoline→cpienergy",proxy:energy},
  {name:"السلع الأساسية",weight:W.goods,rate:goods,source:"cpigoods"},
  {name:"السكن",weight:W.shelter,rate:shelter,source:"cpishelter"},
  {name:"الخدمات الأساسية خارج السكن",weight:W.other,rate:other,source:"cpiservices − shelter"}
 ].map(p=>({...p,contribution:p.weight*p.rate/100}));
 const headline=parts.reduce((s,p)=>s+p.contribution,0);
 const core=(parts[2].contribution+parts[3].contribution+parts[4].contribution)/(W.goods+W.shelter+W.other)*100;
 const ppiTrend=trend(data,"ppi",base);
 // Blend historical PPI persistence with current Brent-based estimate; fixed
 // 50/50 blending is a research assumption, not official PPI component weights.
 if(!FIN(ppiTrend))return {status:"insufficient",reason:"فجوة في بيانات PPI",base,next,forecasts:{}};
 const ppiRate=(ppiTrend+ppiProxy.rate)/2;
 const pce=fitPce(data,"pce",base,{cpi:headline,corecpi:core,ppi:ppiRate});
 const corepce=fitPce(data,"corepce",base,{cpi:headline,corecpi:core,ppi:ppiRate});
 const rates={cpi:headline,corecpi:core,ppi:ppiRate,pce:pce?.rate??null,corepce:corepce?.rate??null};
 const forecasts=Object.fromEntries(Object.entries(rates).map(([id,m])=>[id,
  {mom:FIN(m)?m:null,yoy:FIN(m)?yr(data,id,lastLevel(data,id,base),m,next):null,
   source:id==="cpi"||id==="corecpi"?"BLS weighted component proxy":
          id==="ppi"?"PPI trend + Brent historical fit":"Historical CPI/PPI to PCE ridge proxy",
   trainingN:id==="ppi"?ppiProxy.n:id==="pce"?pce?.trainingN:id==="corepce"?corepce?.trainingN:null,
   status:FIN(m)?"experimental_unvalidated":"insufficient"}]));
 return {status:Object.values(forecasts).every(f=>f.status==="experimental_unvalidated")?"experimental":"partial",
  base,next,weights:W,parts,energy,ppiProxy,forecasts,
  assumptions:[
   "BLS September 2026 relative importances; weighted contribution is a first-order approximation, not exact official CPI",
   "Oil and pump prices use incomplete November monthly averages as of snapshot; CPI energy forecast uses regression trained on currently revised data",
   "PPI 50/50 blend is experimental, not component-weighted; PCE fits are not historically PIT-validated",
   "No dated professional consensus or calibrated probability ranges have been linked",
  ]};
}
root.ECON_INFLATION_STRUCTURAL={compute,mom,trend,fitProxy,otherServices,weights:W};
})(typeof window!=="undefined"?window:globalThis);
