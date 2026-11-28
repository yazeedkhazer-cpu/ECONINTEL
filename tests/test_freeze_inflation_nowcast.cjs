const assert=require("node:assert/strict");
const fs=require("node:fs");
const {snapshot,hash}=require("../research/freeze_next_inflation_nowcast.cjs");
const data=JSON.parse(fs.readFileSync("data/inflation-latest.json","utf8"));
const calendar=JSON.parse(fs.readFileSync("research/data/verified_inflation_calendar_2026_11.json","utf8"));
const models=[
 "assets/inflation-structural.js","assets/cpi-components-v2.js",
 "assets/inflation-nowcast.js"].map(s=>fs.readFileSync(s,"utf8"));
const now=Date.parse(data.generatedAt)+3600000;
const s=snapshot(data,calendar,models,now);
assert.equal(s.targetMonth,"2026-11");
assert.equal(s.sourceConnected,50);
assert.equal(Object.keys(s.forecasts).length,5);
assert.deepEqual(new Set(Object.keys(s.forecasts)),
 new Set(["cpi","corecpi","pce","corepce","ppi"]));
assert(Number.isFinite(s.forecasts.cpi.researchForecastMoM));
assert(Number.isFinite(s.forecasts.corecpi.researchForecastMoM));
assert.equal(s.forecasts.cpi.forecastStatus,"UNVALIDATED_NOT_FOR_TRADING");
assert.equal(s.forecasts.cpi.sourcedConsensusMoM,null);
assert.equal(s.uncertainty.calibrated,false);
assert.equal(s.forecasts.cpi.targetPeriod,"2026-11");
assert.equal(s.sourceSnapshotSha256,hash(JSON.stringify(data)));
assert(s.cpiComponentGroups.shelter.children.length>=3);
assert(s.frozenAtUtc < calendar.entries.cpi.releaseAtUtc);
assert.throws(()=>snapshot(data,calendar,models,Date.parse(calendar.entries.cpi.releaseAtUtc)),
 /Do not freeze after/);
assert.throws(()=>snapshot(data,calendar,models,Date.parse(data.generatedAt)+73*3600000),
 /stale/);
const badData=structuredClone(data);
badData.series.cpiinsurance.status="missing";
assert.throws(()=>snapshot(badData,calendar,models,now),/Granular V2/);
const badCalendar=structuredClone(calendar);
badCalendar.targetPeriod="2026-12";
assert.throws(()=>snapshot(data,badCalendar,models,now),/Forecast target period/);
console.log("Pre-release CPI PCE PPI immutable forecast snapshot protocol: OK");
