'use strict';
const assert=require('node:assert/strict');
const M=require('./scripts/labor_monitor_core.cjs');
function make(now='2026-11-24T12:00:00Z'){
 const source={generatedAt:now,metrics:{}};
 const ids=['nfp','private','nfp3','nfp12','unrate','u6','longterm','parttime','longshare','part','emratio','primeage','wage','wage_mom','wage_level','hours','eci','eciy','jolts','hire','layoff','quits','beveridge','claims','claims4wk','continuing','diffusion','temp','sahm','productivity','ulc','adp'];
 for(const id of ids)source.metrics[id]={date:'2026-10',value:1,status:'api',source:'TEST ONLY',seriesId:'TEST:'+id,history:[['2026-09',1],['2026-10',1]]};
 return source;
}
const now=new Date('2026-11-24T12:00:00Z');
let d=make();let first=M.advance(null,d,now);
assert.equal(first.changed,true);assert.equal(first.value.events.length,0);assert.equal(first.value.snapshots.length,1);
assert.equal(M.advance(first.value,d,new Date('2026-11-24T13:00:00Z')).changed,false);
// New release is detected, without inventing an analyst forecast.
d=make();d.metrics.unrate={...d.metrics.unrate,date:'2026-11',value:1.3,history:[...d.metrics.unrate.history,['2026-11',1.3]]};
let next=M.advance(first.value,d,new Date('2026-11-24T14:00:00Z'));
assert.equal(next.changed,true);assert.ok(next.value.events.some(e=>e.metricId==='unrate'&&e.level==='warning'&&e.type==='release'));
// Revisions are labeled as revisions, not new months.
const d2=structuredClone(d);d2.metrics.unrate.value=1.6;d2.metrics.unrate.history.at(-1)[1]=1.6;
const revised=M.advance(next.value,d2,new Date('2026-11-24T15:00:00Z'));
assert.ok(revised.value.events.some(e=>e.metricId==='unrate'&&e.type==='revision'));
// Subthreshold variation does not send repeated alerts.
const d3=structuredClone(d2);d3.metrics.unrate.value=1.65;d3.metrics.unrate.history.at(-1)[1]=1.65;
const small=M.advance(revised.value,d3,new Date('2026-11-24T16:00:00Z'));
assert.equal(small.value.events.length,revised.value.events.length);
// Missing or seed-based datasets must never be treated as verified official coverage.
const bad=make();delete bad.metrics.adp;assert.throws(()=>M.advance(null,bad,now),/Expected all 32/);
const notApi=make();notApi.metrics.adp.status='seed';assert.throws(()=>M.advance(null,notApi,now),/Expected all 32/);
console.log('PASS: new official periods, revisions, thresholds, no duplicates, 32-source validation');
