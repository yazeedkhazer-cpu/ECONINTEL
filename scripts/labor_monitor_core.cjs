'use strict';
/* Official release-change monitor. No analyst consensus, forecast, or financial signal.
   Rules and thresholds are provisional research assumptions, not Fed weights.
   Use source periods and preserve vintage snapshots first seen by ECONINTEL. */
const H=require('../assets/labor-health-engine.js');
const WATCH=Object.freeze({
 nfp:{min:40,unfavorable:-1,label:'NFP — الوظائف غير الزراعية',unit:' ألف'},
 unrate:{min:0.2,unfavorable:1,label:'معدل البطالة U-3',unit:' نقطة مئوية'},
 u6:{min:0.3,unfavorable:1,label:'البطالة الموسّعة U-6',unit:' نقطة مئوية'},
 emratio:{min:0.2,unfavorable:-1,label:'نسبة العاملين إلى السكان',unit:' نقطة مئوية'},
 primeage:{min:0.2,unfavorable:-1,label:'مشاركة عمر العمل الأساسي',unit:' نقطة مئوية'},
 jolts:{min:0.3,unfavorable:-1,label:'الوظائف الشاغرة JOLTS',unit:' مليون'},
 hire:{min:0.2,unfavorable:-1,label:'معدل التعيينات',unit:' نقطة مئوية'},
 claims4wk:{min:15,unfavorable:1,label:'متوسط طلبات الإعانة الجديدة',unit:' ألف'},
 continuing:{min:0.1,unfavorable:1,label:'طلبات الإعانة المستمرة',unit:' مليون'},
 diffusion:{min:5,unfavorable:-1,label:'انتشار نمو التوظيف',unit:' نقطة'},
 hours:{min:0.2,unfavorable:-1,label:'متوسط ساعات العمل',unit:' ساعة'},
 wage_mom:{min:0.15,unfavorable:0,label:'نمو الأجور الشهري',unit:' نقطة مئوية'},
 eci:{min:0.2,unfavorable:0,label:'تكلفة التوظيف ECI',unit:' نقطة مئوية'}
});
const EVENTS_MAX=200,SNAPSHOTS_MAX=120;
const round=x=>Math.round((x+Number.EPSILON)*1000)/1000;
const comparable=x=>x&&typeof x.date==='string'&&Number.isFinite(Number(x.value));
function snapshotCurrent(source,now=new Date()){
 if(!source||!source.metrics||typeof source.metrics!=='object'||!source.generatedAt)throw Error('Official data unavailable');
 const entries=Object.entries(source.metrics).filter(([id,m])=>m?.status==='api'&&comparable(m));
 if(entries.length!==32)throw Error(`Expected all 32 official indicators, got ${entries.length}`);
 const rows=Object.fromEntries(entries.map(([id,m])=>[id,{id,live:true,custom:false,value:Number(m.value),date:m.date,history:m.history,source:m.source,seriesId:m.seriesId}]));
 const r=H.evaluate(rows,now);
 const metrics=Object.fromEntries(entries.map(([id,m])=>[id,{date:m.date,value:Number(m.value),seriesId:String(m.seriesId||''),source:String(m.source||'')} ]));
 return {capturedAt:now.toISOString(),officialFetchedAt:source.generatedAt,
  label:r.label,kind:r.kind,coverage:r.coverage,
  pillars:r.pillars.map(p=>({id:p.id,result:p.result,why:p.why,extra:p.extra,periods:p.periods})),
  supportEvidence:r.supportEvidence,riskEvidence:r.riskEvidence,other:r.other,missing:r.missing,metrics};
}
function sameObservations(a,b){
 if(!a||!b||!a.metrics||!b.metrics)return false;
 return Object.keys(b.metrics).every(id=>a.metrics[id]?.date===b.metrics[id].date&&a.metrics[id]?.value===b.metrics[id].value)
 && Object.keys(a.metrics).length===Object.keys(b.metrics).length;
}
function eventsBetween(prev,next){
 if(!prev)return [];
 const events=[];
 if(prev.kind!==next.kind){
  const worsening=['weak','softening'].includes(next.kind);
  events.push({type:'state',level:worsening?'warning':'info',detectedAt:next.capturedAt,
   title:`تغير تقييم سوق العمل: ${next.label}`,detail:`التصنيف السابق: ${prev.label}. الحالة الجديدة مبنية على ${next.coverage.analyzed} محاور صالحة؛ راجع الأدلة المعارضة والناقصة.`,referenceDate:'المحاور الستة'});
 }
 for(const [id,settings] of Object.entries(WATCH)){
  const old=prev.metrics?.[id],newM=next.metrics?.[id];
  if(!comparable(old)||!comparable(newM))continue;
  const diff=round(newM.value-old.value);
  if(Math.abs(diff)+1e-6<settings.min)continue;
  const isRevision=newM.date===old.date;
  const bad=settings.unfavorable&&Math.sign(diff)===settings.unfavorable;
  const detail=`${isRevision?'مراجعة للفترة نفسها':'تغيّر بين فترتين منشورتين'}: ${old.value} (${old.date}) إلى ${newM.value} (${newM.date})؛ الفارق ${diff>0?'+':''}${diff}${settings.unit}. `+
    (settings.unfavorable===0?'له أكثر من تفسير ويحتاج سياق الأجور/التضخم.':'الإشارة منفردة ليست حكمًا على سوق العمل بأكمله.');
  events.push({type:isRevision?'revision':'release',level:bad?'warning':'info',metricId:id,
   detectedAt:next.capturedAt,referenceDate:newM.date,
   title:`${settings.label}: ${bad?'تحرك يستحق فحص الضعف':'تغير بارز في القراءة'}`,
   detail});
 }
 return events;
}
function advance(previous,source,now=new Date()){
 const current=snapshotCurrent(source,now);
 const historic=previous&&previous.schemaVersion===1?previous:{schemaVersion:1,events:[],snapshots:[]};
 const prev=historic.snapshots.at(-1);
 if(sameObservations(prev,current))return {changed:false,value:historic};
 const alerts=eventsBetween(prev,current);
 const snap={...current,initialBaseline:!prev};
 return {changed:true,value:{schemaVersion:1,about:'First-observed official data snapshots, not proof of original release vintages. No analyst consensus or price forecast.',
  latest:snap,events:[...(historic.events||[]),...alerts].slice(-EVENTS_MAX),snapshots:[...(historic.snapshots||[]),snap].slice(-SNAPSHOTS_MAX)}};
}
module.exports={WATCH,snapshotCurrent,sameObservations,eventsBetween,advance};
