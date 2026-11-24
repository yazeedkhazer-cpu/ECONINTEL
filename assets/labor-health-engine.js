/* ECONINTEL Labor Health Engine v1.8 — descriptive research rules, not Fed weights.
   Operates only on validated official historical observations. No forecast data.
   Heuristic thresholds are provisional until out-of-sample, point-in-time validation. */
(function(root,factory){
  'use strict';
  const api=factory();
  if(typeof module!=='undefined' && module.exports)module.exports=api;
  if(root)root.ECON_LABOR_HEALTH=api;
})(typeof window!=='undefined'?window:(typeof globalThis!=='undefined'?globalThis:null),function(){
'use strict';
const NAMES={
 employment:'نمو التوظيف',unemployment:'البطالة ونقص الاستخدام',
 participation:'المشاركة والتشغيل',demand:'الطلب على العمالة',
 layoffs:'التسريحات والإعانات',breadth:'اتساع التوظيف وساعات العمل'
};
const PRIMARY=['nfp3','nfp12','unrate','u6','emratio','primeage','jolts','hire','claims4wk','continuing','diffusion','hours'];
const TOOLS={
  employment:['nfp3','nfp12'],unemployment:['unrate','u6'],participation:['emratio','primeage'],
  demand:['jolts','hire'],layoffs:['claims4wk','continuing'],breadth:['diffusion','hours']
};
const AUXILIARY=['nfp','private','part','longterm','longshare','parttime','layoff','quits','beveridge','claims','temp','sahm','adp'];
const WAGE=['wage_mom','wage','eci','eciy','ulc','productivity'];
const STATUS={support:'داعمة',neutral:'مستقرة / غير حاسمة',weak:'تشير إلى ضعف',missing:'بيانات غير كافية'};
const monthKey=d=>/^\d{4}-(0[1-9]|1[0-2])$/.test(d||'')?Number(d.slice(0,4))*12+Number(d.slice(5)):null;
const weekDate=d=>/^\d{4}-\d{2}-\d{2}$/.test(d||'')?Date.parse(d+'T00:00:00Z'):NaN;
const finite=v=>v!==null&&v!==undefined&&Number.isFinite(Number(v));
const round=(v,n=2)=>Math.round((Number(v)+Number.EPSILON)*Math.pow(10,n))/Math.pow(10,n);
function series(m){if(!m||!Array.isArray(m.history))return [];
  return m.history.filter(x=>Array.isArray(x)&&typeof x[0]==='string'&&finite(x[1])).map(x=>[x[0],Number(x[1])]).sort((a,b)=>a[0].localeCompare(b[0]));
}
function historyValue(m,lag,unit='month'){
  const h=series(m);if(!h.length)return null;
  const last=h[h.length-1], target=unit==='week'?weekDate(last[0])-lag*7*864e5:monthKey(last[0])-lag;
  if(!Number.isFinite(target))return null;
  const at=h.find(x=>unit==='week'?weekDate(x[0])===target:monthKey(x[0])===target);
  return at?at[1]:null;
}
function observation(m){const h=series(m);return h.length?{value:h[h.length-1][1],date:h[h.length-1][0]}:null;}
function valid(m,now=new Date()){
  if(!m||m.live!==true||m.custom===true)return false;
  const p=observation(m);if(!p||!finite(m.value)||Math.abs(p.value-Number(m.value))>0.02)return false;
  if(monthKey(m.date)!==null&&monthKey(p.date)!==monthKey(m.date))return false;
  if(/^\d{4}-\d{2}-\d{2}$/.test(m.date)&&m.date!==p.date)return false;
  let stamp;
  if(/^\d{4}-Q[1-4]$/.test(p.date))stamp=Date.UTC(Number(p.date.slice(0,4)),Number(p.date.slice(-1))*3,0);
  else if(/^\d{4}-\d{2}-\d{2}$/.test(p.date))stamp=weekDate(p.date);
  else if(monthKey(p.date)!==null)stamp=Date.UTC(Number(p.date.slice(0,4)),Number(p.date.slice(5)),0);
  else return false;
  const age=(+now-stamp)/864e5;
  const limit=/^\d{4}-\d{2}-\d{2}$/.test(p.date)?35:/^\d{4}-Q/.test(p.date)?190:120;
  return age>=-10&&age<=limit;
}
function item(result,why,extra){return {result,why,extra:extra||''};}
function change(m,lag,kind='month'){if(!m)return null;const old=historyValue(m,lag,kind);return old===null?null:round(Number(m.value)-old,4);}
function percentage(m,lag,kind='month'){if(!m)return null;const old=historyValue(m,lag,kind);return old===null||old===0?null:round((Number(m.value)/old-1)*100,2);}
function showDelta(v,unit=''){return v===null?'غير متاح':`${v>0?'+':''}${round(v,2)}${unit}`;}
function gradeEmployment(d){const fast=d.nfp3,slow=d.nfp12;
 if(!fast||!slow)return item('missing','متوسطا 3 و12 شهرًا غير متاحين ببيانات كافية');
 const a=Number(fast.value),b=Number(slow.value),gap=round(a-b,1);
 if(a<0||a<60||(b>0&&a<.65*b))return item('weak',`متوسط 3 أشهر ${round(a,0)} ألف، مقابل ${round(b,0)} ألف خلال 12 شهرًا`,`فارق المتوسطين ${showDelta(gap,' ألف')}؛ القاعدة تجريبية`);
 if(a>=100&&a>=.85*b)return item('support',`نمو التوظيف ما زال قائمًا؛ متوسط 3 أشهر ${round(a,0)} ألف`, `المتوسط السنوي ${round(b,0)} ألف، والفارق ${showDelta(gap,' ألف')}`);
 return item('neutral',`المتوسط القصير ${round(a,0)} ألف مقابل ${round(b,0)} ألف سنويًا`,`لا اتجاه حاسم في معيار التوظيف`);
}
function gradeUnemployment(d){const u=d.unrate,wide=d.u6;
 if(!u)return item('missing','البطالة الرسمية غير متاحة');
 const ch3=change(u,3),ch6=change(u,6);
 if(ch3===null)return item('missing','يلزم تاريخ البطالة قبل ثلاثة أشهر دون فجوات');
 let result=ch3>=.3?'weak':ch3<=-.2?'support':'neutral';
 const u6=wide?change(wide,3):null;
 const hint=u6===null?'U-6 غير متاح لنفس المقارنة':`تغير U-6 في 3 أشهر ${showDelta(u6,' نقطة مئوية')}`;
 if(result==='support'&&u6!==null&&u6>=.3)result='neutral';
 return item(result,`البطالة ${round(u.value,2)}%؛ تغير 3 أشهر ${showDelta(ch3,' نقطة مئوية')}`,`${hint} • تغير 6 أشهر ${showDelta(ch6,' نقطة مئوية')}`);
}
function gradeParticipation(d){const e=d.emratio,p=d.primeage;
 if(!e&&!p)return item('missing','نسبة العاملين والمشاركة الأساسية غير متاحتين');
 const diffs=[e?change(e,3):null,p?change(p,3):null].filter(x=>x!==null);
 if(!diffs.length)return item('missing','لا تتوفر مقارنة ثلاثة أشهر للمشاركة والتشغيل');
 const ups=diffs.filter(x=>x>=.2).length,downs=diffs.filter(x=>x<=-.2).length;
 const result=downs>ups?'weak':ups>downs?'support':'neutral';
 return item(result,`تغير العاملين إلى السكان ${showDelta(e?change(e,3):null,' نقطة')}، ومشاركة 25–54 سنة ${showDelta(p?change(p,3):null,' نقطة')}`,`ثلاثة أشهر؛ لا نساوي بين المشاركة والتوظيف الفعلي`);
}
function gradeDemand(d){const j=d.jolts,h=d.hire;
 const dj=j?percentage(j,6):null,dh=h?change(h,3):null;
 if(dj===null&&dh===null)return item('missing','بيانات الطلب على العمالة غير كافية أو لا تتضمن فترة المقارنة');
 const w=(dj!==null&&dj<=-10?1:0)+(dh!==null&&dh<=-.2?1:0),s=(dj!==null&&dj>=6?1:0)+(dh!==null&&dh>=.2?1:0);
 return item(w>s?'weak':s>w?'support':'neutral',`تغير الشواغر خلال 6 أشهر ${showDelta(dj,'%')}، وتغير معدل التعيينات خلال 3 أشهر ${showDelta(dh,' نقطة')}`,`الشواغر تقيس الطلب المُعلن، والتعيينات تقيس التوظيف الفعلي`);
}
function gradeLayoffs(d){const c=d.claims4wk,cc=d.continuing;
 const dc=c?percentage(c,12,'week'):null,dcc=cc?percentage(cc,12,'week'):null;
 if(dc===null&&dcc===null)return item('missing','يلزم سجل أسبوعي متصل للمقارنة خلال 12 أسبوعًا');
 const w=(dc!==null&&dc>=12?1:0)+(dcc!==null&&dcc>=8?1:0),s=(dc!==null&&dc<=-12?1:0)+(dcc!==null&&dcc<=-8?1:0);
 return item(w>s?'weak':s>w?'support':'neutral',`متوسط الطلبات الجديدة: ${showDelta(dc,'%')}، والطلبات المستمرة: ${showDelta(dcc,'%')}`,`مقارنة 12 أسبوعًا، وليست قراءة أسبوع واحد`);
}
function gradeBreadth(d){const b=d.diffusion,h=d.hours;
 const db=b?Number(b.value):null,dh=h?change(h,3):null;
 if(db===null&&dh===null)return item('missing','مؤشر الانتشار وساعات العمل غير متاحين');
 const w=(db!==null&&db<48?1:0)+(dh!==null&&dh<=-.2?1:0),s=(db!==null&&db>=54?1:0)+(dh!==null&&dh>=.2?1:0);
 return item(w>s?'weak':s>w?'support':'neutral',`مؤشر الانتشار ${db===null?'—':db} (حد التعادل 50)، وتغير ساعات العمل 3 أشهر ${showDelta(dh,' ساعة')}`,`اتساع القطاع ومقدار الساعات يدعمان أو يعارضان قراءة NFP`);
}
const GRADERS={employment:gradeEmployment,unemployment:gradeUnemployment,participation:gradeParticipation,demand:gradeDemand,layoffs:gradeLayoffs,breadth:gradeBreadth};
function evaluate(metrics,now=new Date()){
 const raw=Array.isArray(metrics)?Object.fromEntries(metrics.map(m=>[m.id,m])):{...(metrics||{})};
 const usable=Object.fromEntries(Object.entries(raw).filter(([key,m])=>valid(m,now)));
 const pillars=Object.entries(GRADERS).map(([id,fn])=>{
   const needed=TOOLS[id];const used=needed.filter(x=>usable[x]);const grade=fn(usable);
   return {id,name:NAMES[id],...grade,desc:STATUS[grade.result],indicators:used,needed,available:used.length,periods:used.map(x=>({id:x,date:usable[x].date}))};
 });
 const analyzed=pillars.filter(x=>x.result!=='missing');
 const supports=analyzed.filter(x=>x.result==='support').length;
 const weak=analyzed.filter(x=>x.result==='weak').length;
 const neutral=analyzed.filter(x=>x.result==='neutral').length;
 const total=pillars.length;
 let label='أدلة غير كافية',kind='insufficient';
 if(analyzed.length>=4){
   if(weak>=4&&supports<=1){label='تدهور واسع في إشارات سوق العمل';kind='weak';}
   else if(supports>=4&&weak<=1){label='سوق عمل متماسك وفق الأدلة المتاحة';kind='resilient';}
   else if(weak>=2&&supports<=1){label='تباطؤ مع ارتفاع مؤشرات الضعف';kind='softening';}
   else if(weak>=2&&supports>=2){label='إشارات مختلطة ومتعارضة';kind='mixed';}
   else if(supports>=2&&weak===0){label='تماسك نسبي مع إشارات تحتاج متابعة';kind='stable';}
   else{label='سوق عمل في حالة مختلطة / انتقالية';kind='mixed';}
 }
 const supportEvidence=pillars.filter(x=>x.result==='support').map(x=>x.name+' — '+x.why);
 const riskEvidence=pillars.filter(x=>x.result==='weak').map(x=>x.name+' — '+x.why);
 const other=pillars.filter(x=>x.result==='neutral').map(x=>x.name+' — '+x.why);
 const missing=pillars.filter(x=>x.result==='missing').map(x=>x.name);
 const wage=Object.fromEntries(WAGE.map(id=>[id,usable[id]||null]));
 const primaryValid=PRIMARY.filter(id=>usable[id]).length;
 return {label,kind,pillars,coverage:{analyzed:analyzed.length,total,supports,weak,neutral,missing:missing.length,officialAnchors:primaryValid,anchorTotal:PRIMARY.length},supportEvidence,riskEvidence,other,missing,wages:wage,
      methodology:'تصنيف وصفي مبدئي؛ ستة محاور لتقليل ازدواجية المؤشرات. لا يمثل أوزانًا رسمية للفيدرالي أو احتمال ركود أو إشارة تداول. لا يدخل التقويم أو Consensus في تقييم التماسك.',
      asOf:now.toISOString(),
      dataDates:Object.fromEntries(Object.entries(usable).map(([id,m])=>[id,m.date]))};
}
return {evaluate,valid,series,change,percentage,PRIMARY,AUXILIARY,WAGE,STATUS,monthKey};
});
