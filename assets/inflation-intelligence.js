/* ECONINTEL seven-axis inflation intelligence v1.0.
 Research diagnostics, NOT a validated CPI/PCE nowcast or official component weights.
 Uses latest-revised FRED data; unconnected leading sources are explicitly excluded. */
(function(root){
'use strict';
const finite=x=>typeof x==='number'&&Number.isFinite(x);
const fmt=(x,unit='%')=>finite(x)?x.toFixed(2)+unit:'—';
const get=(d,id)=>{const x=d?.series?.[id];return x?.status==='connected'&&Array.isArray(x.history)&&x.history.length?x:null;};
const month=s=>/^\d{4}-(0[1-9]|1[0-2])$/.test(s)?Number(s.slice(0,4))*12+Number(s.slice(5)):null;
const quarter=s=>/^\d{4}-Q[1-4]$/.test(s)?Number(s.slice(0,4))*4+Number(s.slice(-1)):null;
function val(d,id,n=0){
 const s=get(d,id),h=s?.history;if(!h||h.length<=n)return null;
 const a=h[h.length-1],b=h[h.length-1-n],idx=/Q[1-4]$/.test(a[0])?quarter:month;
 if(idx(a[0])===null||idx(b[0])===null||idx(a[0])-idx(b[0])!==n)return null;
 return finite(b[1])?b[1]:null;
}
function annual(d,id,n=3){
 const meta=d?.catalog?.find(x=>x.id===id);if(!meta||meta.kind!=='price')return null;
 const a=val(d,id),b=val(d,id,n);if(a===null||b===null||a<=0||b<=0)return null;
 return ((a/b)**(meta.frequency==='quarterly'?4:12/n)-1)*100;
}
function change(d,id,n=3){
 const a=val(d,id),b=val(d,id,n);return a===null||b===null?null:a-b;
}
function growth(d,id,n=3){
 const a=val(d,id),b=val(d,id,n);return a===null||b===null||a<=0||b<=0?null:(a/b-1)*100;
}
function axis(label,status,explain,details){return {label,status,explain,details};}
function score(v,low,high){return !finite(v)?'missing':v>=high?'high':v>=low?'medium':'low';}
function evaluate(d){
 const pce3=annual(d,'corepce',3),pce6=annual(d,'corepce',6);
 const cpi3=annual(d,'corecpi',3),serv=annual(d,'cpiservices',3),goods=annual(d,'cpigoods',3);
 const shelter=annual(d,'cpishelter',3),oer=annual(d,'cpioer',3),rent=annual(d,'cpirent',3);
 const ppi=annual(d,'ppi',3),pc=annual(d,'ppicomm',3),im=annual(d,'import',12);
 const energy=annual(d,'cpienergy',3),food=annual(d,'cpifood',3),oil=growth(d,'wti',1);
 const spend=growth(d,'realpce',3),wages=growth(d,'wages',3),ulc=annual(d,'ulc',1);
 const mich=val(d,'mich'),mex=change(d,'mich',3),tips=val(d,'breakeven5'),tipsChange=change(d,'breakeven5',3);
 const breadth=[cpi3,serv,goods].filter(finite),up=breadth.filter(x=>x>=3).length;
 const hmax=Math.max(...[shelter,oer].filter(finite));
 const pmax=Math.max(...[ppi,pc].filter(finite));
 const demand=[spend!==null&&spend>1.5,wages!==null&&wages>1.5,ulc!==null&&ulc>3].filter(Boolean).length;
 const axes=[
 axis('1 · زخم التضخم الأساسي',score(pce3,2.5,3.5),
 'Core PCE هو أساس تصنيف شدة التضخم، بمقارنة 3 أشهر مع 6 أشهر.',
 ['Core PCE 3m SAAR: '+fmt(pce3),'Core PCE 6m SAAR: '+fmt(pce6)]),
 axis('2 · انتشار الأسعار',breadth.length<2?'missing':up>=2?'high':up===1?'medium':'low',
 'عدد مقاييس السلع والخدمات المرتفعة، وليس نسبة انتشار بنود CPI الرسمية.',
 ['Core CPI 3m: '+fmt(cpi3),'خدمات CPI 3m: '+fmt(serv),'سلع CPI 3m: '+fmt(goods)]),
 axis('3 · السكن والإيجارات',score(hmax,2.7,4),
 'القراءات الرسمية متأخرة عن إيجارات السوق الجديدة؛ Zillow غير متصل بعد.',
 ['Shelter CPI 3m: '+fmt(shelter),'OER 3m: '+fmt(oer),'Rent CPI 3m: '+fmt(rent)]),
 axis('4 · المنتجون والتوريد',score(pmax,2,4),
 'PPI وأسعار الواردات تقيسان الضغوط الأولية، ولا تنتقل تلقائيًا إلى CPI.',
 ['PPI 3m: '+fmt(ppi),'PPI سلع 3m: '+fmt(pc),'أسعار الواردات 12m: '+fmt(im),'PMI Prices وGSCPI: غير متصلين']),
 axis('5 · الطاقة والغذاء',score(energy,4,10),
 'صدمة الطاقة قد ترفع المؤشر العام دون ارتفاع متزامن في التضخم الأساسي.',
 ['طاقة CPI 3m: '+fmt(energy),'غذاء CPI 3m: '+fmt(food),'تغير WTI آخر شهر: '+fmt(oil)]),
 axis('6 · الطلب والأجور',![spend,wages,ulc].some(finite)?'missing':demand>=2?'high':demand===1?'medium':'low',
 'تقييم مساعد لاستمرار الضغوط، لا قياس مباشر للتضخم.',
 ['الإنفاق الحقيقي 3m: '+fmt(spend),'الأجور 3m: '+fmt(wages),'ULC ربع سنوي سنويًا: '+fmt(ulc)]),
 axis('7 · التوقعات والأسواق',!finite(mex)&&!finite(tipsChange)?'missing':(mex??0)>0.5||(tipsChange??0)>0.25?'high':(mex??0)>0.15||(tipsChange??0)>0.1?'medium':'low',
 'تعادل TIPS يشمل علاوات مخاطر وسيولة، وليس توقع تضخم خالصًا.',
 ['توقع ميشيغان سنة: '+fmt(mich),'تغير ميشيغان 3m: '+fmt(mex,' نقطة'),'TIPS 5Y: '+fmt(tips),'تغير TIPS 3m: '+fmt(tipsChange,' نقطة')])
 ];
 let strength='غير متاح',phase='غير متاح',driver='غير محسوم';
 if(finite(pce3)&&finite(pce6)){
   strength=pce3>=3.5?'مرتفع':pce3>=2.5?'متوسط':'محدود نسبيًا';
   phase=pce3>pce6+0.4?'يتسارع':pce3<pce6-0.4?'يتباطأ':'مستقر نسبيًا';
 }
 if(finite(serv)&&finite(goods)&&serv>=3&&goods>=3)driver='ضغوط واسعة في السلع والخدمات';
 else if(finite(energy)&&energy>10&&finite(cpi3)&&cpi3<3)driver='ضغط طاقة بارز';
 else if(finite(shelter)&&finite(pce3)&&shelter>pce3+1)driver='ضغط سكن بارز';
 else if(finite(pce3))driver='مختلط أو غير محسوم';
 return {strength,phase,driver,axes,corePce3:pce3,corePce6:pce6,period:get(d,'corepce')?.period||null,
    connected:Object.values(d?.series||{}).filter(x=>x.status==='connected').length,
    total:d?.catalog?.length||0,missing:axes.filter(x=>x.status==='missing').length,
    caveat:'قواعد أولية غير مُعايرة تاريخيًا. البيانات مُراجعة وليست نسخ لحظة النشر. لا تستخدم أوزان CPI/PCE الرسمية، ولا تتنبأ بالقراءة القادمة. مؤشرات PMI وZillow وNY Fed غير المتصلة لا تدخل الأحكام.'};
}
function mount(){
 const anchor=document.getElementById('stats');if(!anchor)return;
 const holder=document.createElement('section');holder.className='panel';holder.id='inflation-intelligence-seven';
 holder.style.margin='20px 0';holder.style.padding='20px';anchor.insertAdjacentElement('afterend',holder);
 const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
 function draw(r){
 const status={high:'ضغوط مرتفعة',medium:'ضغوط متوسطة',low:'ضغوط محدودة',missing:'بيانات غير كافية'};
 holder.innerHTML='<div style="font-size:12px;color:#98b4c9">INFLATION INTELLIGENCE · RESEARCH</div><h2>محرك التضخم متعدد المحاور</h2>'
 +'<p>7 محاور مستقلة · '+(7-r.missing)+'/7 متاحة · '+r.connected+'/'+r.total+' مصادر متصلة</p>'
 +'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:18px 0">'
 +[['شدة التضخم',r.strength],['المرحلة',r.phase],['مصدر الضغط المحتمل',r.driver]].map(([a,b])=>'<div style="border:1px solid #32465e;border-radius:10px;padding:13px"><small>'+esc(a)+'</small><h3>'+esc(b)+'</h3></div>').join('')+'</div>'
 +'<p>آخر فترة Core PCE: '+esc(r.period||'—')+' · زخم 3 أشهر '+fmt(r.corePce3)+' / 6 أشهر '+fmt(r.corePce6)+'</p>'
 +'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(245px,1fr));gap:12px">'
 +r.axes.map(a=>'<details style="border:1px solid #32465e;border-radius:10px;padding:13px"><summary style="cursor:pointer"><b>'+esc(a.label)+'</b> · '+esc(status[a.status])+'</summary><p>'+esc(a.explain)+'</p>'+a.details.map(x=>'<div style="margin:5px 0;color:#acbfd0;font-size:13px">'+esc(x)+'</div>').join('')+'</details>').join('')+'</div>'
 +'<p style="color:#a8b5ca;font-size:12px;margin-top:15px">'+esc(r.caveat)+'</p>';
 }
 holder.textContent='جاري تحميل تحليل التضخم...';
 fetch('data/inflation-latest.json?t='+Date.now(),{cache:'no-store'}).then(x=>{if(!x.ok)throw Error('HTTP '+x.status);return x.json()})
 .then(x=>draw(evaluate(x))).catch(e=>holder.textContent='تعذّر تحميل البيانات: '+e.message);
}
if(typeof document!=='undefined'){
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});else mount();
}
root.ECON_INFLATION_INTELLIGENCE={evaluate,annual,val,growth};
})(typeof window!=='undefined'?window:globalThis);
