'use strict';
const assert=require('node:assert/strict');
const H=require('./assets/labor-health-engine.js');
const now=new Date('2026-11-24T12:00:00Z');
const months=Array.from({length:18},(_,i)=>{const y=2025+Math.floor((i+1)/12);const m=(i+1)%12+1;return `${y}-${String(m).padStart(2,'0')}`;});
const dates=Array.from({length:24},(_,i)=>new Date(Date.UTC(2026,5,6+i*7)).toISOString().slice(0,10));
function monthly(id,fn){const h=months.map((d,i)=>[d,fn(i)]);return {id,live:true,custom:false,value:h.at(-1)[1],date:h.at(-1)[0],history:h};}
function weekly(id,fn){const h=dates.map((d,i)=>[d,fn(i)]);return {id,live:true,custom:false,value:h.at(-1)[1],date:h.at(-1)[0],history:h};}
const stable=()=>[
 monthly('nfp3',i=>150),monthly('nfp12',i=>155),monthly('unrate',i=>4.2-.02*i),monthly('u6',i=>7.8-.02*i),
 monthly('emratio',i=>59+.05*i),monthly('primeage',i=>82+.05*i),monthly('jolts',i=>7+i*.04),monthly('hire',i=>3.3+i*.02),
 weekly('claims4wk',i=>250-i*3),weekly('continuing',i=>2.05-i*.01),monthly('diffusion',i=>55),monthly('hours',i=>34.2+i*.015)
];
const weak=()=>[
 monthly('nfp3',i=>150-7*i),monthly('nfp12',i=>150),monthly('unrate',i=>3.5+.075*i),monthly('u6',i=>7+.09*i),
 monthly('emratio',i=>60.2-.10*i),monthly('primeage',i=>84-.10*i),monthly('jolts',i=>9-i*.18),monthly('hire',i=>3.8-i*.07),
 weekly('claims4wk',i=>210+i*7),weekly('continuing',i=>1.5+i*.035),monthly('diffusion',i=>45),monthly('hours',i=>34.5-i*.07)
];
// sanity time window is fresh and data generated is months 2025-02 ... 2026-07? should reach recent 2026-11
assert.equal(months.at(-1),'2026-07');
// correct month series for as-of Nov 2026
function shiftMonth(m){return m.map(x=>{const h=x.history.map(p=>{const old=H.monthKey(p[0]);if(old===null)return p;const n=old+3;return [`${Math.floor((n-1)/12)}-${String((n-1)%12+1).padStart(2,'0')}`,p[1]];});return h===x.history?x:{...x,history:h,date:h.at(-1)[0],value:h.at(-1)[1]};})}
let s=H.evaluate(shiftMonth(stable()),now);assert.equal(s.coverage.analyzed,6);assert.ok(['resilient','stable'].includes(s.kind),JSON.stringify(s.coverage));
let w=H.evaluate(shiftMonth(weak()),now);assert.equal(w.kind,'weak',JSON.stringify(w.coverage));
// Synthetic seed/custom indicators must be rejected, not silently used as official live.
let bad=shiftMonth(stable());bad.find(x=>x.id==='unrate').live=false;bad.find(x=>x.id==='nfp3').custom=true;
let b=H.evaluate(bad,now);assert.equal(b.pillars.find(x=>x.id==='unemployment').result,'missing');assert.equal(b.pillars.find(x=>x.id==='employment').result,'missing');
// Stale payload blocks status even when positive.
let stale=H.evaluate(shiftMonth(stable()),new Date('2028-11-24T12:00:00Z'));assert.equal(stale.kind,'insufficient');
// Expect month gaps not to be filled or approximated
let gap=shiftMonth(stable());let u=gap.find(x=>x.id==='unrate');u.history=u.history.filter((_,i)=>i!==14); // i 14 corresponds 3 months before last (17)
assert.equal(H.change(u,3),null);
// All 32 registered weight indicators are NOT auto-counted, only independent pillars.
let extra=shiftMonth(stable());for(let i=0;i<20;i++)extra.push(monthly('unused'+i,()=>1));
assert.equal(H.evaluate(extra,now).coverage.analyzed,6);
console.log('PASS: research classification, source validation, missing history, staleness, no duplicate counting');
