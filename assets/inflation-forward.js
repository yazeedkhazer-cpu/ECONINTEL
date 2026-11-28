/* ECONINTEL Forward Inflation Pressure v0.1 — directional research, not a calibrated nowcast.
 Do not interpret as exact CPI/PCE predictions. Last-revised FRED snapshot, not point-in-time.
 Families are treated separately; market/commodity monthly averages may be partial. */
(function(root){
'use strict';
const ok=x=>typeof x==='number'&&Number.isFinite(x);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','\'':'&#39;'}[c]));
const mon=s=>/^\d{4}-(0[1-9]|1[0-2])$/.test(s)?12*Number(s.slice(0,4))+Number(s.slice(5)):null;
const fmt=(n,s='%')=>ok(n)?(n>=0?'+':'')+n.toFixed(2)+s:'—';
function recent(d,id,k=2) {
 const x=d?.series?.[id],meta=d?.catalog?.find(c=>c.id===id);
 if(!x||x.status!=='connected'||!Array.isArray(x.history)||x.history.length<k||meta?.frequency==='quarterly')return null;
 const a=x.history.slice(-k);
 if(a.some((p,i)=>!Array.isArray(p)||mon(p[0])===null||!ok(p[1])||(i&&mon(p[0])!==mon(a[i-1][0])+1)))return null;
 return {v:a.map(p=>p[1]),period:a.at(-1)[0],partial:!!x.partialPeriod,freq:meta.frequency};
}
function mom(d,id,lag=0){
 const h=recent(d,id,lag+2);if(!h)return null;const end=h.v[h.v.length-1-lag],prev=h.v[h.v.length-2-lag];
 return prev>0?(end/prev-1)*100:null;
}
function momentum(d,id){
 const x=mom(d,id),p=mom(d,id,1);
 return x===null||p===null?null:{now:x,previous:p,diff:x-p,period:d.series[id].period,partial:!!d.series[id].partialPeriod};
}
function percent(d,id){
 const h=recent(d,id,2);return h&&h.v[0]>0?{value:(h.v[1]/h.v[0]-1)*100,partial:h.partial,period:h.period}:null;
}
function pointChange(d,id){
 const h=recent(d,id,2);return h?{value:h.v[1]-h.v[0],partial:h.partial,period:h.period}:null;
}
function indicator(id,label,data,kind,threshold=0.15){
 if(!data)return {id,label,signal:0,available:false,reason:'السلسلة غير متاحة أو الفترة غير متصلة'};
 let v=kind==='momchange'?data.diff:data.value;
 let signal=v<=-threshold?-1:v>=threshold?1:0;
 return {id,label,signal,available:true,value:v,period:data.period,
   partial:!!data.partial,unit:kind==='points'?' نقطة مئوية':'%',reason:''};
}
function family(id,label,indicators,note){
 const usable=indicators.filter(x=>x.available),up=usable.filter(x=>x.signal>0).length,down=usable.filter(x=>x.signal<0).length;
 const dir=!usable.length?'missing':down>up?'down':up>down?'up':'mixed';
 return {id,label,dir,usable:usable.length,total:indicators.length,indicators,note,
   partial:usable.some(x=>x.partial)};
}
function evaluate(d){
 const groups=[
 family('energy','الطاقة والوقود',[
  indicator('brent','Brent · تغير متوسط السعر الشهري',percent(d,'brent'),'change',3),
  indicator('gasoline','بنزين التجزئة · تغير متوسط السعر الشهري',percent(d,'gasoline'),'change',2),
  indicator('wti','WTI · تغير متوسط السعر الشهري',percent(d,'wti'),'change',3)
 ],'الطاقة تؤثر غالبًا أولًا على التضخم العام. متوسط الشهر الجاري جزئي وليس قراءة نهائية.'),
 family('producers','أسعار المنتجين وتكاليف المدخلات',[
  indicator('ppi','PPI الطلب النهائي · تغير الزخم الشهري',momentum(d,'ppi'),'momchange',0.15),
  indicator('ppicomm','PPI السلع · تغير الزخم الشهري',momentum(d,'ppicomm'),'momchange',0.25),
  indicator('import','أسعار الواردات · تغير الزخم الشهري',momentum(d,'import'),'momchange',0.15)
 ],'تغير PPI لا ينتقل بالكامل أو مباشرة إلى CPI وPCE؛ لا نتعامل معه كمساهمة سعرية.'),
 family('housing','السكن الرسمي',[
  indicator('cpishelter','Shelter CPI · تغير الزخم الشهري',momentum(d,'cpishelter'),'momchange',0.08),
  indicator('cpioer','OER · تغير الزخم الشهري',momentum(d,'cpioer'),'momchange',0.08),
  indicator('cpirent','Rent CPI · تغير الزخم الشهري',momentum(d,'cpirent'),'momchange',0.08)
 ],'سكن CPI مؤشر متأخر؛ غياب الإيجارات الجديدة Zillow/BLS يمنع اعتباره إشارة قيادة مستقلة.'),
 family('demand','طلب الأسر وتكاليف الأجور',[
  indicator('realpce','الإنفاق الحقيقي · تغير الزخم الشهري',momentum(d,'realpce'),'momchange',0.12),
  indicator('retail','التجزئة · تغير الزخم الشهري',momentum(d,'retail'),'momchange',0.25),
  indicator('wages','الأجر الاسمي · تغير الزخم الشهري',momentum(d,'wages'),'momchange',0.08)
 ],'إشارات غير مباشرة قد تعكس تباطؤ الطلب، دون إثبات انتقاله للتضخم.'),
 family('expectations','توقعات التضخم وتسعير السندات',[
  indicator('breakeven5','تعادل تضخم 5 سنوات · تغير بالنقاط',pointChange(d,'breakeven5'),'points',0.10),
  indicator('breakeven10','تعادل تضخم 10 سنوات · تغير بالنقاط',pointChange(d,'breakeven10'),'points',0.10),
  indicator('mich','توقع ميشيغان لسنة · تغير بالنقاط',pointChange(d,'mich'),'points',0.20)
 ],'TIPS يتأثر بمخاطر التضخم والسيولة؛ ليس توقعًا صافيًا أو احتمال قرار فائدة.'),
 family('underlying','استمرارية التضخم الأساسي',[
  indicator('corepce','Core PCE · تغير الزخم الشهري',momentum(d,'corepce'),'momchange',0.08),
  indicator('corecpi','Core CPI · تغير الزخم الشهري',momentum(d,'corecpi'),'momchange',0.08),
  indicator('sticky','Sticky CPI 12m · تغير بالنقاط',pointChange(d,'sticky'),'points',0.15)
 ],'هذه مؤشرات استمرارية متأخرة، وتُستخدم كاختبار مضاد لا كإنذار مبكر.'),
 ];
 const pick=ids=>groups.filter(x=>ids.includes(x.id));
 function outlook(ids,required){
  const subset=pick(ids).filter(x=>x.dir!=='missing'),up=subset.filter(x=>x.dir==='up').length,down=subset.filter(x=>x.dir==='down').length,mixed=subset.filter(x=>x.dir==='mixed').length;
  const active=subset.length;
  const state=active<required?'insufficient':down>=2&&down>up?'easing':up>=2&&up>down?'rising':'mixed';
  return {state,up,down,mixed,active,required,partial:subset.some(x=>x.partial)};
 }
 const headline=outlook(['energy','producers','housing','demand','expectations'],3);
 const core=outlook(['producers','housing','demand','expectations','underlying'],4);
 const labels={easing:'إشارات تميل لانحسار الضغوط',rising:'إشارات تميل لزيادة الضغوط',mixed:'إشارات متعارضة — لا اتجاه محسوم',insufficient:'أدلة غير كافية'};
 const period=d?.series?.corepce?.period||null;
 const external=d?.unconnected||[];
 const waiting=['zori','ism_man_prices','ism_services_prices','sp_flash_input','gscpi','sce_1y','cleveland_nowcast']
  .filter(id=>external.some(x=>x.id===id));
 return {headline:{...headline,label:labels[headline.state]},core:{...core,label:labels[core.state]},
  groups,referencePeriod:period,asOf:d?.generatedAt||null,
  connected:Object.values(d?.series||{}).filter(x=>x.status==='connected').length,
  waiting,calibrated:false,limitations:'هذه قراءة اتجاهية مشروطة لا تتنبأ برقم CPI أو PCE، ولا تثبت أنها تسبق السوق. البيانات مراجعة وقد تتأخر عن تاريخ النشر، وبيانات شهر الطاقة الحالي جزئية، وPMI/Zillow غير متصلين. لا توجد نسب نجاح أو احتمالات مُعايرة.'};
}
function mount(){
 const stats=document.getElementById('stats');if(!stats)return;
 const box=document.createElement('section');box.className='panel';box.id='forward-inflation-outlook';
 box.style.margin='20px 0';box.style.padding='20px';
 const hero=document.querySelector('.hero');
 if(hero)hero.insertAdjacentElement('beforebegin',box);
 else stats.insertAdjacentElement('afterend',box);
 box.textContent='جاري حساب مؤشرات اتجاه التضخم...';
 const label={down:'تخفيف الضغوط',up:'زيادة الضغوط',mixed:'إشارات متباينة',missing:'غير متاح'};
 const fill=d=>{
  const r=evaluate(d),h=r.headline,c=r.core;
  const readableDate=r.asOf?new Intl.DateTimeFormat('ar-JO',{day:'numeric',month:'long',year:'numeric',timeZone:'Asia/Amman'}).format(new Date(r.asOf)):'غير متاح';
  const headlineLabel=h.state==='easing'?'ضغوط تميل للانحسار':h.label;
  const coreLabel=c.state==='easing'?'إشارات هدوء مع مخاطر مستمرة':c.label;
  const energy=r.groups.find(x=>x.id==='energy');
  const production=r.groups.find(x=>x.id==='producers');
  const underlying=r.groups.find(x=>x.id==='underlying');
  const find=(group,id)=>group?.indicators.find(x=>x.id===id);
  const brent=find(energy,'brent'),gasoline=find(energy,'gasoline'),ppi=find(production,'ppi'),sticky=find(underlying,'sticky');
  const causes=[];
  const periodMonth=d?.series?.brent?.period||'';
  const monthText=/^\d{4}-\d{2}$/.test(periodMonth)?
    new Intl.DateTimeFormat('ar-JO',{month:'long',year:'numeric',timeZone:'UTC'}).format(new Date(periodMonth+'-01T00:00:00Z')):'الفترة الأخيرة';
  if(brent?.available && Math.abs(brent.value)>=2)
    causes.push('متوسط Brent في '+monthText+(brent.value<0?' أقل':' أعلى')+' بنحو '+Math.abs(brent.value).toFixed(1)+'% من الشهر السابق');
  if(gasoline?.available && Math.abs(gasoline.value)>=2)
    causes.push('البنزين '+(gasoline.value<0?'أقل':'أعلى')+' بنحو '+Math.abs(gasoline.value).toFixed(1)+'%');
  if(ppi?.available && Math.abs(ppi.value)>=0.15)
    causes.push('زخم PPI '+(ppi.value<0?'انخفض':'ارتفع')+' عن الشهر السابق');
  if(sticky?.available && sticky.signal>0)
    causes.push('بعض مؤشرات التضخم المستمر ارتفعت');
  if(!causes.length)causes.push('الإشارات القيادية متباينة أو لا تتوافر بيانات كافية لتحديد السبب');
  const label={down:'تخفيف الضغوط',up:'زيادة الضغوط',mixed:'إشارات متباينة',missing:'غير متاح'};
  box.innerHTML='<div style="font-size:12px;color:#9ab9d8;font-weight:600">الملخص التنفيذي · قراءة استشرافية أولية — '+esc(readableDate)+'</div>'+
   '<h2 style="margin:10px 0 8px">إلى أين يتجه التضخم الأمريكي؟</h2>'+
   '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin:16px 0">'+
   [['التضخم العام','الأشهر القريبة',headlineLabel],['التضخم الأساسي','الأشهر القادمة',coreLabel]].map(([title,horizon,reading])=>
    '<div style="border:1px solid #38516b;border-radius:12px;padding:16px"><small>'+esc(title)+'</small>'+
    '<h3 style="margin:8px 0 4px">'+esc(reading)+'</h3><small style="color:#a2b6ce">'+esc(horizon)+'</small></div>').join('')+
   '</div><p><strong>ليش؟</strong> '+esc(causes.join('، '))+'. '+(c.state==='easing'?'لكن التضخم الأساسي ما زال يحتاج تأكيدًا قبل اعتبار الهدوء مستدامًا.':'اتجاه التضخم الأساسي لم يُحسم بعد.')+'</p>'+
   '<p style="font-size:12px;color:#c3af80;margin-top:9px">'+
    (h.partial||c.partial?'بعض المقارنات تعتمد على شهر أسعار جزئي وغير مكتمل. ':'')+
    'هذه فرضيات اتجاهية أولية وليست توقعات مثبتة الدقة. تاريخ العرض هو تاريخ تحديث البيانات وليس موعد صدور CPI/PCE.</p>'+
   '<details style="margin-top:14px;border-top:1px solid #38516b;padding-top:12px"><summary style="cursor:pointer;font-weight:600">عرض الأدلة المؤيدة والمعارضة بالتفصيل</summary>'+
   '<p style="font-size:12px;color:#b7c6d7">محاور التضخم العام: '+h.down+' تهدأ · '+h.up+' ترتفع · '+h.mixed+' مختلطة. المحاور الأساسية: '+c.down+' تهدأ · '+c.up+' ترتفع · '+c.mixed+' مختلطة.</p>'+
   '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px">'+
    r.groups.map(g=>'<details style="border:1px solid #2c4159;border-radius:10px;padding:12px"><summary style="cursor:pointer"><b>'+
    esc(g.label)+'</b> · '+esc(label[g.dir])+'</summary><p style="font-size:12px">'+esc(g.note)+'</p>'+
    g.indicators.map(i=>'<div style="font-size:13px;margin:6px 0">'+esc(i.label)+': '+(i.available?fmt(i.value,i.unit):'غير متاح')+
       (i.partial?' (شهر جزئي)':'')+'</div>').join('')+'</details>').join('')+'</div>'+
   '<p style="font-size:12px;color:#a8b8cd;margin-top:14px">مصادر لم تُربط بعد: '+esc(r.waiting.join(' · ')||'لا يوجد')+
   '<br>'+esc(r.limitations)+'</p></details>';
 };
 fetch('data/inflation-latest.json?t='+Date.now(),{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(fill)
 .catch(e=>box.textContent='تعذّر قراءة بيانات التوقع الاتجاهي: '+e.message);
}
if(typeof document!=='undefined'){
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});else mount();
}
root.ECON_INFLATION_FORWARD={evaluate,recent,mom,momentum};
})(typeof window!=='undefined'?window:globalThis);
