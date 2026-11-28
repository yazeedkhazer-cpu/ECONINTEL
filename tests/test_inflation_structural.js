const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const ctx=vm.createContext({console});
vm.runInContext(fs.readFileSync("assets/inflation-structural.js","utf8"),ctx);
vm.runInContext(fs.readFileSync("assets/inflation-nowcast.js","utf8"),ctx);
const model=ctx.ECON_INFLATION_STRUCTURAL;
const input=JSON.parse(fs.readFileSync("data/inflation-latest.json","utf8"));
const result=model.compute(input);
assert.equal(result.status,"experimental",JSON.stringify({status:result.status,reason:result.reason}));
assert.equal(result.base,"2026-10");
assert.equal(result.next,"2026-11");
assert.equal(result.parts.length,5);
assert(Math.abs(Object.values(result.weights).reduce((a,b)=>a+b,0)-100)<1e-9);
for(const [name,reading] of Object.entries(result.forecasts)){
 assert(Number.isFinite(reading.mom),name+" missing MoM");
 assert(Number.isFinite(reading.yoy),name+" missing YoY");
 assert.equal(reading.status,"experimental_unvalidated");
}
assert(Math.abs(result.parts.reduce((a,b)=>a+b.contribution,0)-result.forecasts.cpi.mom)<1e-10);
const expectedCore=result.parts.slice(2).reduce((a,b)=>a+b.contribution,0)/(100-result.weights.food-result.weights.energy)*100;
assert(Math.abs(expectedCore-result.forecasts.corecpi.mom)<1e-10);
const integrated=ctx.ECON_INFLATION_NOWCAST.evaluate(input);
assert.equal(integrated.structural.status,"experimental");
assert.equal(integrated.forecasts.length,5);
assert(integrated.forecasts.every(x=>Number.isFinite(x.econintel.mom)));
assert(integrated.forecasts.every(x=>Number.isFinite(x.baseline.mom)));
const changed=structuredClone(input);
changed.series.gasoline.history.at(-1)[1]*=.8;
const energyImpact=model.compute(changed);
assert(Math.abs(energyImpact.forecasts.cpi.mom-result.forecasts.cpi.mom)>0.01,
 "Current energy price proxy should materially affect headline CPI");
assert(Math.abs(energyImpact.forecasts.corecpi.mom-result.forecasts.corecpi.mom)<1e-9,
 "Core CPI excludes energy");
const missing=structuredClone(input);
missing.series.cpishelter.history.pop();
assert.equal(model.compute(missing).status,"insufficient");
console.log("ECONINTEL structural inflation model tests: OK");
console.log("Model preview experimental: ",Object.fromEntries(Object.entries(result.forecasts).map(([id,r])=>[id,{mom:r.mom.toFixed(3),yoy:r.yoy.toFixed(3)}])));
