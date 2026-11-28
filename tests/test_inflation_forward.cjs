'use strict';
const assert=require('node:assert/strict');
require('../assets/inflation-forward.js');
const m=globalThis.ECON_INFLATION_FORWARD;
assert.equal(typeof m.evaluate,'function');
function make(values,partial=false){
 const months=Array.from({length:5},(_,i)=>'2026-'+String(i+7).padStart(2,'0'));
 return {catalog:[{id:'brent',kind:'commodity',frequency:'daily'}],series:{brent:{status:'connected',partialPeriod:partial,period:months.at(-1),history:values.map((v,i)=>[months[i],v])}},unconnected:[]};
}
assert.equal(m.recent(make([10,11,12,13,14]),'brent',2).period,'2026-11');
assert.equal(m.mom(make([10,11,12,13,14]),'brent'),(14/13-1)*100);
let missing=make([10,11,12,13,14]);
missing.series.brent.history.splice(3,1);
assert.equal(m.mom(missing,'brent'),null,'No silent comparison across missing observation months');
const easing=make([100,105,108,100,85],true),e=m.evaluate(easing);
assert.equal(e.groups.length,6);
assert.equal(e.groups[0].dir,'down');
assert.equal(e.groups[0].partial,true);
assert.equal(e.headline.state,'insufficient','Do not infer economy-wide direction from oil alone');
const empty={series:{},catalog:[],unconnected:[]};
assert.equal(m.evaluate(empty).core.state,'insufficient');
console.log('Forward inflation research: continuity, partial periods and coverage tests passed');
