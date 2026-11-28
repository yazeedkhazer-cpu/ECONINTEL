const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync("assets/inflation-nowcast.js", "utf8");
const context = vm.createContext({console});
vm.runInContext(source, context);
const api = context.ECON_INFLATION_NOWCAST;

function months(year, firstMonth, count, start, monthlyRate){
  const out = [];
  for(let i=0;i<count;i++){
    const n=year*12 + firstMonth-1 + i;
    out.push([Math.floor(n/12)+"-"+String(n%12+1).padStart(2,"0"),
      start*Math.pow(1+monthlyRate/100,i)]);
  }
  return out;
}
const input=months(2025,1,23,100,.2); // Jan 2025–Nov 2026, 0.2% MoM
const forecast=api.forecastBase({history:input});
assert.equal(forecast.status,"baseline");
assert.equal(forecast.period,"2026-12");
assert(Math.abs(forecast.mom-.2)<1e-9);
assert(Math.abs(forecast.yoy-(Math.pow(1.002,12)-1)*100)<1e-9);
assert.equal(forecast.prevYear,"2025-12");

const gap=input.filter(x=>x[0]!=="2026-10");
assert.equal(api.forecastBase({history:gap}).status,"insufficient");
assert.equal(api.forecastBase({history:[]}).status,"insufficient");

const catalog=["cpi","corecpi","pce","corepce","ppi"].map(id=>({id,kind:"price"}));
const series=Object.fromEntries(catalog.map(x=>[x.id,{history:input,status:"connected"}]));
const evaluated=api.evaluate({schemaVersion:1,catalog,series,generatedAt:"2026-11-28T13:00:00Z"});
assert.equal(evaluated.forecasts.length,5);
assert(evaluated.forecasts.every(x=>x.baseline.status==="baseline"));
assert(evaluated.forecasts.every(x=>x.econintel===null));
assert.equal(evaluated.seriesCount,5);
assert.throws(()=>api.evaluate({schemaVersion:2,catalog,series}),/schema/);
console.log("ECONINTEL inflation-family nowcast tests: OK");
