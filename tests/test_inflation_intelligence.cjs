'use strict';
const assert=require('node:assert/strict');
require('../assets/inflation-intelligence.js');
const engine=globalThis.ECON_INFLATION_INTELLIGENCE;
assert.ok(engine&&typeof engine.evaluate==='function');
const ids=['corepce','corecpi','cpi','pce'];
function makeData(){
 const catalog=ids.map(id=>({id,kind:'price',frequency:'monthly'}));
 const series=Object.fromEntries(ids.map(id=>[id,{status:'connected',period:'2025-06',history:Array.from({length:18},(_,i)=>{
  const y=2024+Math.floor(i/12),m=String(i%12+1).padStart(2,'0');
  return [y+'-'+m,100*Math.pow(1.003,i)];})}]));
 return {catalog,series};
}
const d=makeData(), result=engine.evaluate(d);
assert.equal(result.axes.length,7);
assert.equal(result.strength,'مرتفع');
assert.equal(result.missing,6);
assert.ok(engine.annual(d,'corepce',3)>3.5);
const broken=makeData();
broken.series.corepce.history.splice(-2,1);
assert.equal(engine.annual(broken,'corepce',3),null);
const absent=makeData();
delete absent.series.corepce;
assert.equal(engine.evaluate(absent).strength,'غير متاح');
console.log('Inflation seven-axis research tests passed');
