'use strict';
/* Read-only PILOT: replay the EXACT existing six-pillar rules with ALFRED as-of data.
   Does not change official-latest, live weight tables, status, or GitHub content. */
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'../..');
const health=require(path.join(root,'assets','labor-health-engine.js'));
const folder=path.join(root,'pit_research_output');
const input=JSON.parse(fs.readFileSync(path.join(folder,'pit_month_end_frames.json'),'utf8'));
const rows=[];
const report={schemaVersion:1,method:'ALFRED month-end as-of pilot, not release-time point-in-time validation',
  limitations:input.limitations,checkpoints:[]};
for(const frame of input.frames){
 const r=health.evaluate(frame.metrics,new Date(frame.cutoff+'T23:59:59Z'));
 const item={cutoff:frame.cutoff,kind:r.kind,label:r.label,coverage:r.coverage,
   pillars:r.pillars.map(({id,result,why,extra,periods})=>({id,result,why,extra,periods})),
   missing:frame.unavailable,sourceTrace:frame.trace};
 report.checkpoints.push(item);
 rows.push([frame.cutoff,r.kind,r.label,r.coverage.analyzed,r.coverage.officialAnchors,
            ...r.pillars.map(p=>p.result)]);
}
fs.writeFileSync(path.join(folder,'pit_classifications.json'),JSON.stringify(report,null,2)+'\n');
const esc=x=>'"'+String(x??'').replaceAll('"','""')+'"';
const headings=['cutoff','kind','label','analyzedPillars','validAnchors',
                'employment','unemployment','participation','demand','layoffs','breadth'];
fs.writeFileSync(path.join(folder,'pit_classifications.csv'),[headings,...rows].map(r=>r.map(esc).join(',')).join('\r\n')+'\r\n');
const lines=['# ECONINTEL — Point-in-Time Pilot (Month-End As-Of)',
  '', '**ليس اعتمادًا نهائيًا.** المواعيد هي نهاية اليوم وليس ساعة الإعلان الفعلية؛ والتغطية محدودة بحسب أرشيف ALFRED.',
  '', '| تاريخ الفحص | التصنيف | المحاور الصالحة | المؤشرات المحورية المتاحة |',
  '|---|---|---:|---:|',
  ...report.checkpoints.map(x=>`| ${x.cutoff} | ${x.label} (${x.kind}) | ${x.coverage.analyzed}/6 | ${x.coverage.officialAnchors}/12 |`),
  '', '## مصادر لم تتوفر لكل تاريخ',
  ...report.checkpoints.map(x=>`- ${x.cutoff}: ${Object.keys(x.missing).length?JSON.stringify(x.missing):'لا توجد أخطاء API؛ اكتمال سلسلة التاريخ قد يختلف'}`),
  '', '## ملاحظات علمية',
  '- استخدمت قواعد المحرك نفسه، دون إعادة معايرتها.',
  '- فقدان أحد المحاور لا يُحوَّل إلى تقييم إيجابي، ولا يتم تعويضه من بيانات معاد مراجعتها.',
  '- المرحلة التالية: تغطية شهرية كاملة مع أرشيفات النشر الأصلية وتقويم الإصدار الفعلي، ثم مقارنة خارج العينة.',
  '- لا ترفع هذه البيانات إلى صفحة ECONINTEL الحية ولا تغيّر الأوزان حتى تتضح التغطية.',
];
fs.writeFileSync(path.join(folder,'PIT_SUMMARY_AR.md'),lines.join('\n')+'\n');
console.log('Saved pilot classifications and Arabic report in pit_research_output/');
