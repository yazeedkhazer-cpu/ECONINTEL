/* ECONINTEL Inflation Research 1.0; descriptive, rule-based, provisional thresholds.
   NO formal next-CPI nowcast, Fed weights, or trained probability is claimed. */
(()=>{'use strict';
const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct=(v,n=2)=>Number.isFinite(v)?(v>=0?'+':'')+v.toFixed(n)+'%':'—';
const num=(v,n=2)=>Number.isFinite(v)?v.toFixed(n):'—';
let DATA=null, GROUP='الكل',QUERY='';
const byid=id=>{let s=DATA?.catalog.find(s=>s.id===id);return s?{...s,...DATA.series[id]}:null};
const valid=s=>s && ['connected','stale'].includes(s.status)&&Array.isArray(s.history)&&s.history.length>0;
const last=s=>valid(s)?s.history.at(-1):null;
const histval=(s,back)=>valid(s)&&s.history.length>back?s.history.at(-(back+1))[1]:null;
const delta=(s,back,mode='pct')=>{if(!valid(s)||s.history.length<=back)return null;
 const x=histval(s,0),y=histval(s,back);if(!Number.isFinite(x)||!Number.isFinite(y)||y<=0)return null;
 return mode==='pp'?x-y:(x/y-1)*100;};
const freq=s=>s?.frequency==='quarterly'?'فصلي':'شهري';
const metrics=s=>{if(!valid(s))return {};
 const q=s.frequency==='quarterly',p=s.kind==='price'||s.kind==='commodity';
 return {change:delta(s,1),mom:!q&&p?delta(s,1):null,yoy:p?delta(s,q?4:12):null,
    m3:!q&&p&&s.history.length>3?((s.value/histval(s,3))**4-1)*100:null,
    m6:!q&&p&&s.history.length>6?((s.value/histval(s,6))**2-1)*100:null,
    qoq:q&&p?((s.value/histval(s,1))**4-1)*100:null};};
function periodContinuity(s,n){if(!valid(s)||s.history.length<n+1)return false;const a=s.history.slice(-(n+1));
 const idx=t=>/^\d{4}-Q[1-4]$/.test(t)?Number(t.slice(0,4))*4+Number(t.slice(-1)):Number(t.slice(0,4))*12+Number(t.slice(5,7));
 return a.every((v,i)=>i===0||idx(v[0])===idx(a[i-1][0])+1);
}
function m(s,n=2){const x=metrics(s);return x.m3!==null&&x.m3!==undefined&&Number.isFinite(x.m3)?x.m3:null;}
const showValue=s=>!valid(s)?'غير متاح':(s.kind==='price'?'مؤشر '+num(s.value,2):num(s.value,s.kind==='commodity'?2:2));
function graph(s){if(!valid(s)||s.history.length<2)return '';const points=s.history.slice(-24);let vs=points.map(p=>p[1]),min=Math.min(...vs),max=Math.max(...vs),spread=max-min||1;const xy=vs.map((v,i)=>`${8+i*314/(vs.length-1)},${62-(v-min)/spread*54}`).join(' ');return `<svg class="chart" viewBox="0 0 330 70" preserveAspectRatio="none" role="img" aria-label="مسار المؤشر خلال آخر 24 فترة"><polyline points="${xy}" fill="none" stroke="#6be2b3" stroke-width="2.4" vector-effect="non-scaling-stroke"/></svg>`;}
function diagnostic(){
 const cpce=byid('corepce'),ccpi=byid('corecpi'),pce=byid('pce'),sticky=byid('sticky'),trimpce=byid('trimpce'),oer=byid('cpioer'),ene=byid('cpienergy'),oil=byid('wti'),ppi=byid('ppi'),services=byid('cpiservices'),goods=byid('cpigoods'),wage=byid('eci'),mich=byid('mich');
 const a=metrics(cpce),c=metrics(ccpi),headline=metrics(pce),h=metrics(oer),en=metrics(ene),ps=metrics(ppi),s=metrics(services),g=metrics(goods);
 const complete=cpce&&valid(cpce)&&periodContinuity(cpce,6)&&Number.isFinite(a.m3)&&Number.isFinite(a.m6);
 let level='بيانات غير كافية',phase='بيانات غير كافية',driver='غير محسوم';
 if(complete){const rate=(a.m3+a.m6)/2;level=rate<2.5?'ضغط محدود نسبيًا':rate<3.5?'ضغط متوسط':'ضغط مرتفع';
   phase=a.m3>a.m6+0.35?'ضغوط تتسارع':a.m3<a.m6-0.35?'ضغوط تتباطأ':'زخم شبه مستقر';
 }
 const confirmedCore=complete&&valid(ccpi)&&Number.isFinite(c.m3);
 const headlineEnergy=Number.isFinite(en.m3)&&Number.isFinite(a.m3);
 const distributed=confirmedCore&&Number.isFinite(s.m3)&&Number.isFinite(g.m3)&&c.m3>=3&&s.m3>=3&&g.m3>=2.5;
 if(distributed)driver='ضغوط واسعة في السلع والخدمات';
 else if(headlineEnergy&&en.m3>=8&&(!confirmedCore||c.m3<3.5))driver='طاقة بارزة — انتقالها لباقي الأسعار غير محسوم';
 else if(Number.isFinite(h.m3)&&Number.isFinite(a.m3)&&h.m3>a.m3+1)driver='السكن من أبرز مصادر استمرار الضغط';
 else if(complete)driver='ضغوط مختلطة؛ لا يمكن حصر المصدر';
 const evidence=[
  ['Core PCE 3m SAAR',a.m3,'%', 'زخم الأسعار الأساسي دون الغذاء والطاقة'],
  ['Core PCE 6m SAAR',a.m6,'%', 'اتجاه نصف سنوي أقل تأثرًا بشهر واحد'],
  ['Core PCE 12m',a.yoy,'%', 'المعدل السنوي وليس الزخم الحالي'],
  ['Core CPI 3m SAAR',c.m3,'%', 'دليل مستقل لا يساوي PCE'],
  ['Shelter CPI 3m SAAR',metrics(byid('cpishelter')).m3,'%', 'الإيجارات المسجلة تتأخر عن السوق الجديد'],
  ['PPI 3m SAAR',ps.m3,'%', 'تكاليف المنتجين لا تنتقل تلقائيًا للمستهلك'],
  ['Energy CPI 3m SAAR',en.m3,'%', 'الطاقة قد ترفع Headline دون Core'],
  ['Trimmed Mean PCE 12m',valid(trimpce)?trimpce.value:null,'%', 'التضخم المستمر بعيدًا عن القيم المتطرفة']];
 $('diagnostics').innerHTML=[['شدة التضخم',level,'مقارنة بحثية لزخم Core PCE، ليست تصنيف الفيدرالي'],['مرحلة الدورة',phase,'تغير الزخم 3 أشهر مقابل 6 أشهر'],['مصدر الضغط',driver,'قراءة نوعية وليست مساهمة مرجحة بأوزان CPI']].map(t=>`<div class="diagnostic"><small>${t[0]}</small><b>${t[1]}</b><p>${t[2]}</p></div>`).join('');
 $('explanation').innerHTML=`<b>قراءة المحرك:</b> ${complete?'Core PCE على 3 أشهر = '+pct(a.m3,2)+'، وعلى 6 أشهر = '+pct(a.m6,2)+'.':'تغطية Core PCE غير كافية لاستنتاج مستوى/مرحلة التضخم.'}<br><br>
 <b>الأدلة القطاعية:</b> ${evidence.map(e=>`${esc(e[0])}: <span dir="ltr">${pct(e[1])}</span>`).join(' · ')}.<br><br>
 <b>تحذير منهجي:</b> هذه استدلالات قواعد أولية، لا تحتسب اتساع CPI الحقيقي عبر جميع بنود السلة أو مساهمات الأوزان الشهرية. أسعار النفط وPMI والسكن الأمامي لا تحدد بمفردها قراءة CPI القادمة.`;
}
function forecastBaseline(id){let s=byid(id);if(!valid(s)||!periodContinuity(s,12)||s.kind!=='price')return null;
 const h=s.history,rate=[];for(let k=1;k<=12;k++){const x=h.at(-k)[1],y=h.at(-k-1)[1];rate.push((x/y-1)*100)}
 const base=rate.slice(0,3).reduce((a,b)=>a+b)/3,lo=Math.min(...rate),hi=Math.max(...rate);
 return {base,low:lo,high:hi,period:s.period};}
function forecast(){const fields=[['cpi','CPI العام'],['corecpi','Core CPI'],['pce','PCE العام'],['corepce','Core PCE']];$('forecast').innerHTML=`<div class="forecast-grid">${fields.map(([id,label])=>{const f=forecastBaseline(id);return `<div class="forecast-tile"><small>${label} · خط أساس القراءة الشهرية القادمة</small><strong>${f?pct(f.base,3):'—'}</strong><div class="muted">${f?'نطاق القراءات الشهرية خلال 12 شهرًا: '+pct(f.low,2)+' إلى '+pct(f.high,2):'سجل متصل غير كافٍ'}</div><small>${f?'آخر شهر مرصود '+esc(f.period):'بيانات غير متاحة'}</small></div>`}).join('')}</div><p class="mute">المعادلة التجريبية = متوسط التغيرات الشهرية لآخر 3 أشهر؛ والنطاق هو أدنى/أعلى تغير خلال 12 شهرًا، <b>ليس</b> فاصل ثقة أو توقعًا قائمًا على نموذج اقتصادي. التنبؤ الفعلي يحتاج أوزان CPI/PCE ومكونات شهر الإصدار وبيانات Point-in-Time وتقييم الأخطاء.</p>`;}
function card(s){const st=DATA.series[s.id]||{status:'missing'};const x=metrics({...s,...st});let sub='';
 if(valid(st))sub=s.kind==='price' ? `MoM: ${pct(x.mom)} · 3m SAAR: ${pct(x.m3)} · YoY: ${pct(x.yoy)}` : s.kind==='commodity'?`تغير متوسط السعر الشهري: ${pct(x.change)} · 3m SAAR: ${pct(x.m3)}`:(s.kind==='yoyrate'||s.kind==='annualizedrate')?`التغير عن قراءة المؤشر السابقة: ${num(s.value-histval({...s,...st},1))} نقطة مئوية`:`التغير النسبي منذ الفترة السابقة: ${pct(x.change)} (ليس تغيرًا بالنقاط)`;
 else sub='لا توجد بيانات مؤكدة متاحة';
 return `<article class="indicator"><h3>${esc(s.label)}</h3><div class="value">${showValue({...s,...st})}</div><div class="sub">الفترة: ${esc(st.period||'—')} ${st.partialPeriod?'· شهر جزئي':''} · ${freq(s)}<br>${sub}</div>${valid(st)?graph(st):''}<div class="source"><span>${st.status==='connected'?'● متصل':st.status==='stale'?'◔ بيانات قديمة':'○ غير متصل'}</span><a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.provider)} ↗</a></div>${valid(st)?`<details><summary>بيانات وتفسير</summary><div>الدور: ${esc(s.role)} · رمز المصدر: ${esc(s.fredId)}<br>MoM يختلف عن YoY؛ بعض السلاسل لا تصح مقارنتها بطريقة موحّدة.<br>فترة الملاحظة ليست تاريخ إعلان المصدر.</div></details>`:`<small class="muted">${esc(st.error||'بانتظار التشغيل')}</small>`}</article>`;}
function indicators(){const cat=DATA?.catalog||[];const groups=['الكل',...new Set(cat.map(i=>i.group))];$('filters').innerHTML=groups.map(g=>`<button class="filter ${g===GROUP?'active':''}" data-group="${esc(g)}">${esc(g)}</button>`).join('');
 const q=QUERY.toLowerCase();const items=cat.filter(s=>(GROUP==='الكل'||s.group===GROUP)&&[s.label,s.fredId,s.provider,s.group].join(' ').toLowerCase().includes(q));
 $('indicators').innerHTML=items.length?items.map(card).join(''):'<div class="muted">لا توجد مؤشرات مطابقة.</div>';
 document.querySelectorAll('[data-group]').forEach(b=>b.onclick=()=>{GROUP=b.dataset.group;indicators()});}
function unconnected(){$('unconnected').innerHTML=(DATA?.unconnected||[]).map(x=>`<article class="indicator"><h3>${esc(x.label)}</h3><div class="muted">◌ غير متصل · ${esc(x.provider)}</div><div class="source"><span>خارج التقييم حتى توثيق الإصدار</span><a href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">المصدر ↗</a></div></article>`).join('');}
function snapshot(){const ids=[['cpi','CPI العام','m3'],['corecpi','Core CPI','m3'],['pce','PCE العام','m3'],['corepce','Core PCE','m3']];$('stats').innerHTML=ids.map(([id,label,k])=>{const s=byid(id),x=metrics(s);return `<div class="stat"><label>${label}</label><strong>${pct(x[k],2)}</strong><small>3 أشهر سنويًا (SAAR) · ${esc(s?.period||'—')}</small></div>`}).join('');
 const connected=Object.values(DATA.series||{}).filter(x=>x.status==='connected').length;const total=DATA.catalog.length;
 $('coverage').textContent=`متصل حاليًا: ${connected}/${total} سلسلة · ${DATA.unconnected.length} مصادر إضافية قيد الربط`;
 $('synced').textContent='آخر محاولة تحديث: '+(DATA.generatedAt?new Date(DATA.generatedAt).toLocaleString('ar-JO',{timeZone:'Asia/Amman'}):'لم يتم التشغيل');
 const lag=DATA.generatedAt?Date.now()-Date.parse(DATA.generatedAt):Infinity;
 $('warning').hidden=connected>0&&lag<7*864e5;if(!$('warning').hidden)$('warning').textContent='تنبيه: بيانات التضخم غير متصلة بعد أو آخر تحديث تجاوز 7 أيام. لا يُعتمد أي تصنيف دون فحص المصدر.';
 diagnostic();forecast();indicators();unconnected();}
async function load(){try{const r=await fetch('data/inflation-latest.json?t='+Date.now(),{cache:'no-store'});if(!r.ok)throw Error('HTTP '+r.status);const j=await r.json();if(j.schemaVersion!==1)throw Error('Invalid version');DATA=j;snapshot();}catch(e){$('warning').hidden=false;$('warning').textContent='لم نتمكن من قراءة ملف البيانات: '+String(e.message);}}
$('refresh').onclick=load;$('search').oninput=e=>{QUERY=e.target.value;indicators()};load();
})();
