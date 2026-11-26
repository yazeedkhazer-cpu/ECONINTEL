'use strict';
/* Research-only. Replays exactly the deployed six-pillar engine, unchanged.
   Does not infer truth/accuracy from agreement with a revised-data backtest. */
const fs=require('node:fs'), path=require('node:path');
const ROOT=path.resolve(__dirname,'../..');
const H=require(path.join(ROOT,'assets/labor-health-engine.js'));
const OUT=path.join(ROOT,'pit_full_output');
const CSV_BASE=path.join(ROOT,'research/pit/baseline/replay_revised_20261124.csv');
const COLS=['employment','unemployment','participation','demand','layoffs','breadth'];
function csvString(values){return values.map(v=>'"'+String(v??'').replaceAll('"','""')+'"').join(',');}
function parseCSV(s){
 const rows=[];let row=[],cell='',quoted=false;
 for(let i=0;i<s.length;i++){
   const c=s[i];
   if(c==='"'){if(quoted&&s[i+1]==='"'){cell+='"';i++;}else quoted=!quoted;}
   else if(!quoted&&c===','){row.push(cell);cell='';}
   else if(!quoted&&(c==='\n'||c==='\r')){if(c==='\r'&&s[i+1]==='\n')i++;row.push(cell);if(row.some(v=>v!==''))rows.push(row);row=[];cell='';}
   else cell+=c;
 }
 if(cell||row.length){row.push(cell);rows.push(row);}
 const h=rows.shift();return rows.map(row=>Object.fromEntries(h.map((k,i)=>[k,row[i]??''])));
}
function analyze(input,baseline=[]){
 const byMonth=new Map(baseline.map(x=>[x.asOfMonth,x]));
 const result=[];
 for(const frame of input.frames){
   const r=H.evaluate(frame.metrics,new Date(frame.asOf+'T23:59:59Z'));
   const old=byMonth.get(frame.month);
   const kinds=r.pillars.map(x=>[x.id,x.result]);
   const d={cutoff:frame.asOf,month:frame.month,completeMonth:frame.completeMonth,
     kind:r.kind,label:r.label,coverage:r.coverage,validAnchors:r.coverage.officialAnchors,
     fullAnchorCoverage:r.coverage.officialAnchors===12,
     allSixPillars:r.coverage.analyzed===6,
     oldRevisedKind:old?.kind??null,
     agreedWithRevised:old&&frame.completeMonth?r.kind===old.kind:null,
     differencesFromRevised:old&&frame.completeMonth&&old.kind!==r.kind?{revised:old.kind,asof:r.kind}:null,
     missingSourceIds:Object.keys(frame.unavailable||{}),
     pillars:r.pillars.map(p=>({id:p.id,result:p.result,why:p.why,extra:p.extra,
       anchorDates:p.periods,primaryAvailability:p.available+'/'+p.needed.length})),
     support:r.supportEvidence,risks:r.riskEvidence,neutral:r.other,
     quality:r.coverage.officialAnchors===12?'all-12-anchors':
       r.coverage.officialAnchors>=10?'partial-10-plus':
       r.coverage.officialAnchors>=9?'limited-9':'insufficient'};
   result.push(d);
 }
 const historic=result.filter(x=>x.completeMonth),provisional=result.filter(x=>!x.completeMonth);
 const types={};result.forEach(x=>types[x.kind]=(types[x.kind]||0)+1);
 const transitions=historic.slice(1).filter((x,i)=>x.kind!==historic[i].kind);
 const agreed=historic.filter(x=>x.agreedWithRevised===true);
 const differed=historic.filter(x=>x.agreedWithRevised===false);
 const summary={schemaVersion:2,mode:'RESEARCH ONLY — ALFRED end-of-day vintage, not intraday original release',
   fullHistoricalMonths:historic.length,partialMonths:provisional.length,cutoffs:result.length,
   earliest:historic[0]?.cutoff??null,latest:result.at(-1)?.cutoff??null,
   classificationCounts:types,transitions:transitions.length,
   fullyCovered:historic.filter(x=>x.fullAnchorCoverage).length,
   withAtLeast10Anchors:historic.filter(x=>x.validAnchors>=10).length,
   missingDiffusionMonths:historic.filter(x=>x.missingSourceIds.includes('CES0500000021')).length,
   agreementWithRevised:agreed.length,differenceFromRevised:differed.length,
   nonComparable:historic.length-agreed.length-differed.length,
   validAsPrediction:false,whyNotValidated:[
     'The historical comparison baseline uses revised values and assumed publication delays.',
     'A high agreement count does not prove accurate forecasting or economic causation.',
     'BLS Employment Diffusion vintages are missing from ALFRED and are not imputed.',
     'No independent economic regime/outcome labels or release-hour backtesting.',
     'Current classification thresholds have not been calibrated out-of-sample.'
   ]};
 return {summary,rows:result,transitions,differed};
}
function write(input, baseline){
 const out=analyze(input,baseline);
 fs.mkdirSync(OUT,{recursive:true});
 fs.writeFileSync(path.join(OUT,'pit_full_classifications.json'),JSON.stringify({summary:out.summary,rows:out.rows},null,2)+'\n');
 fs.writeFileSync(path.join(OUT,'pit_full_summary.json'),JSON.stringify(out.summary,null,2)+'\n');
 let headers=['asOf','referenceMonth','completeMonth','pitKind','revisedKind','sameClassification','validAnchors','analyzedPillars',...COLS];
 const csv=[csvString(headers),...out.rows.map(x=>csvString([x.cutoff,x.month,x.completeMonth,x.kind,x.oldRevisedKind,
   x.agreedWithRevised,x.validAnchors,x.coverage.analyzed,...COLS.map(k=>x.pillars.find(p=>p.id===k)?.result)]))].join('\r\n')+'\r\n';
 fs.writeFileSync(path.join(OUT,'pit_full_comparison.csv'),csv);
 fs.writeFileSync(path.join(OUT,'pit_disagreements.csv'),[csvString(['asOf','PIT','revisedData','anchors']),
   ...out.differed.map(x=>csvString([x.cutoff,x.kind,x.oldRevisedKind,x.validAnchors]))].join('\r\n')+'\r\n');
 const s=out.summary;
 const lines=[
   '# ECONINTEL — التقرير التاريخي الشامل لسوق العمل (ALFRED)', '',
   '**بحث تشخيصي، وليس شهادة دقة نهائية أو اختبارًا وقت صدور الأخبار بالساعة.**','',
   `- الفترة: ${s.earliest} إلى ${s.latest}.`,
   `- الأشهر الكاملة: ${s.fullHistoricalMonths}، والشهر الجاري الجزئي: ${s.partialMonths}.`,
   `- انتقالات تصنيف نهاية الأشهر الكاملة: ${s.transitions}.`,
   `- تواريخ تغطي 12/12 محورًا مرجعيًا: ${s.fullyCovered}/${s.fullHistoricalMonths}.`,
   `- تواريخ تغطي 10+ مؤشرات محورية: ${s.withAtLeast10Anchors}/${s.fullHistoricalMonths}.`,
   `- تواريخ تفتقد Diffusion BLS التاريخي: ${s.missingDiffusionMonths}.`,
   `- اتفاق التصنيف مع الاختبار السابق المعدّل: ${s.agreementWithRevised}؛ اختلاف: ${s.differenceFromRevised}؛ دون مقارنة: ${s.nonComparable}.`,
   '', '## توزيع التصنيفات',
   ...Object.entries(s.classificationCounts).map(([k,n])=>`- ${k}: ${n}`),
   '', '## جميع الأشهر — نتائج ALFRED',
   '| نهاية الفترة | حالة السوق وفق المحرك | التغطية | النسخة المعدلة |',
   '|---|---|---:|---|',
   ...out.rows.map(x=>`| ${x.cutoff}${x.completeMonth?'':' (جزئي)'} | ${x.label} | ${x.validAnchors}/12 | ${x.oldRevisedKind??'—'} |`),
   '', '## أشهر اختلف فيها تصنيف ALFRED عن الاختبار القديم',
   ...(out.differed.length?out.differed.map(x=>`- ${x.cutoff}: PIT = ${x.kind}، revised = ${x.oldRevisedKind} (تغطية ${x.validAnchors}/12)`):['- لا يوجد اختلاف في الأشهر القابلة للمقارنة.']),
   '', '## الحدود غير المكتملة',
   '- **Diffusion**: السلسلة الرسمية BLS CES0500000021 غير موجودة في ALFRED بحسب اختبارنا؛ تُعرض مفقودة ولا نستبدلها بنسخة مُراجَعة.',
   '- **نهاية اليوم**: البيانات تعكس ما كان متاحًا عند نهاية التاريخ، لا لحظة إصدار كل رقم.',
   '- **الاختبار السابق**: مبني على بيانات مراجَعة ومواعيد إصدار تقريبية، لذا الاختلاف بينهما ليس قياس دقة.',
   '- **الحكم الاقتصادي**: هذا يختبر استقرار تفسير المحرك ومتانة مصادره، وليس القدرة على التنبؤ بركود أو إثبات صحة موضوعية للتصنيفات.',
   '- **قبل اعتبار المحرك صالحًا بحثيًا نهائيًا**: توثيق بيانات نشر BLS الأصلية، تعريف مرجع خارجي للمقارنة، ومعايرة أي تعديل على فترة منفصلة.',
   '', '## حماية المشروع',
   '- هذا الاختبار للقراءة فقط. لم يغيّر الموقع أو بياناته أو الأوزان أو قواعد المحرك، ولم ينشئ Commit.',
   '- جميع النتائج موجودة داخل GitHub Actions Artifact منفصل.',
 ];
 fs.writeFileSync(path.join(OUT,'PIT_FULL_REPORT_AR.md'),lines.join('\n')+'\n');
 console.log(`PIT full research report created: ${s.fullHistoricalMonths} historical months, ${s.partialMonths} partial, ${s.differenceFromRevised} differences, ${s.missingDiffusionMonths} diffusion gaps.`);
 return out;
}
if(require.main===module){
 const input=JSON.parse(fs.readFileSync(path.join(OUT,'pit_full_frames.json'),'utf8'));
 const old=parseCSV(fs.readFileSync(CSV_BASE,'utf8'));
 write(input,old);
}
module.exports={analyze,write,parseCSV};
