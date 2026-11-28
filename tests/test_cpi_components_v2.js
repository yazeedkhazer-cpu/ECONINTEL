const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const ctx=vm.createContext({console});
vm.runInContext(fs.readFileSync("assets/inflation-structural.js","utf8"),ctx);
vm.runInContext(fs.readFileSync("assets/cpi-components-v2.js","utf8"),ctx);
const model=ctx.ECON_CPI_COMPONENTS_V2;
const real=JSON.parse(fs.readFileSync("data/inflation-latest.json","utf8"));
const preliminary=model.assess(real);
assert.equal(preliminary.status,"awaiting_component_data");
assert(preliminary.missing.includes("cpiinsurance"));
assert(preliminary.shelterPreview&&Number.isFinite(preliminary.shelterPreview.rate));
assert.equal(preliminary.cpi,undefined,"Must not invent a v2 all-items value on missing source data");
assert.equal(preliminary.core,undefined,"Must not invent a v2 core value on missing source data");
const w=model.weights();
assert(Math.abs((w.rent+w.oer+w.otherShelter)-w.shelter)<1e-8);
assert(Math.abs((w.apparel+w.newCars+w.usedCars+w.otherGoods)-w.goods)<1e-8);
assert(Math.abs((w.insurance+w.airfare+w.otherTransportation)-w.transportation)<1e-8);
assert(Math.abs((w.medical+w.transportation+w.otherServicesRemainder)-w.otherServices)<1e-8);
const full=structuredClone(real);
const aliases={
 cpilodging:"cpishelter",cpiapparel:"cpigoods",cpinewvehicles:"cpigoods",
 cpiusedcars:"cpigoods",cpimedicalservices:"cpiservices",
 cpitransportservices:"cpiservices",cpiinsurance:"cpiservices",
 cpiairfares:"cpiservices"
};
for(const [newId,oldId] of Object.entries(aliases)){
 const s=structuredClone(full.series[oldId]);
 assert(s.history.length>30);
 full.series[newId]={...s};
}
const a=model.assess(full);
assert.equal(a.status,"experimental_unvalidated",a.reason);
assert(Number.isFinite(a.cpi)&&Number.isFinite(a.core));
assert.equal(a.target,"2026-11");
assert.equal(a.groups.shelter.children.length,3);
assert.equal(a.groups.goods.children.length,4);
assert.equal(a.groups.services.children.length,3);
assert.equal(a.groups.transport.children.length,3);
assert(Math.abs(a.groups.goods.children.reduce((s,p)=>s+p.contribution,0)-a.groups.goods.contribution)<1e-9);
const coreContrib=a.groups.goods.contribution+a.groups.shelter.contribution+a.groups.services.contribution;
assert(Math.abs(a.core-coreContrib/(w.goods+w.shelter+w.otherServices)*100)<1e-10);
const sum=a.contributions.reduce((s,p)=>s+p.contribution,0);
const total=w.food+w.energy+w.goods+w.shelter+w.otherServices;
assert(Math.abs(a.cpi-sum*100/total)<1e-10);
const shock=structuredClone(full);
shock.series.gasoline.history.at(-1)[1]*=0.8;
const afterFuel=model.assess(shock);
assert(Math.abs(afterFuel.cpi-a.cpi)>0.01);
assert(Math.abs(afterFuel.core-a.core)<1e-10,"Core CPI excludes energy");
const insuranceShock=structuredClone(full);
insuranceShock.series.cpiinsurance.history.at(-1)[1]*=1.05;
const afterInsurance=model.assess(insuranceShock);
assert(Math.abs(afterInsurance.core-a.core)>1e-5);
const missing=structuredClone(full);
missing.series.cpiusedcars.history.pop();
assert.equal(model.assess(missing).status,"awaiting_component_data");
console.log("ECONINTEL detailed CPI decomposition v2: passed");
console.log("Proxy-only, NOT official or validated current forecast:",{
 headline:a.cpi.toFixed(3),core:a.core.toFixed(3),rent:a.groups.shelter.children[0].rate.toFixed(3),
 oer:a.groups.shelter.children[1].rate.toFixed(3)});
