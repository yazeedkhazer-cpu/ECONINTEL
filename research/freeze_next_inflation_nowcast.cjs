#!/usr/bin/env node
/* ECONINTEL pre-release inflation prediction seal.
   This deliberately freezes real browser-model output BEFORE the official
   timestamp. Current FRED revision snapshots are allowed for prospective
   use, NEVER silently backdated to simulate historical prediction.
   The user-facing headline is an UNVALIDATED model expectation.
*/
"use strict";
const fs=require("node:fs"),path=require("node:path"),vm=require("node:vm"),crypto=require("node:crypto");
const ROOT=path.resolve(__dirname,"..");
const MODEL_FILES=["assets/inflation-structural.js","assets/cpi-components-v2.js","assets/inflation-nowcast.js"];
const CALENDAR="research/data/verified_inflation_calendar_2026_11.json";
const MINUTES=60*1000;
function assert(cond,why){if(!cond)throw Error(why)}
function hash(s){return crypto.createHash("sha256").update(s).digest("hex")}
function utcTime(s){
 const ms=Date.parse(s);
 assert(Number.isFinite(ms)&&/([zZ]|[+-]\d{2}:\d{2})$/.test(s),"Invalid timezone-qualified timestamp");
 return ms;
}
function snapshot(data,calendar,modelSources,now=Date.now()){
 assert(data?.schemaVersion===1&&Array.isArray(data.catalog),"Inflation snapshot not recognized");
 assert(calendar?.schemaVersion===1&&calendar.entries&&calendar.targetPeriod,"Release calendar missing");
 const nowMs=typeof now==="number"?now:utcTime(now);
 const calendarIds=["cpi","corecpi","ppi","pce","corepce"];
 assert(calendarIds.every(id=>calendar.entries[id]),"Missing official release schedule for one target");
 assert(calendarIds.every(id=>utcTime(calendar.entries[id].releaseAtUtc)>nowMs),
        "Do not freeze after any scheduled November 2026 release has occurred");
 const dataAt=utcTime(data.generatedAt);
 assert(nowMs>=dataAt,"Cannot freeze using a future-dated data snapshot");
 assert(nowMs-dataAt<=72*60*MINUTES,"Inflation data >72h stale; refresh before freezing");
 const ctx=vm.createContext({console});
 for(const s of modelSources)vm.runInContext(s,ctx);
 const results=ctx.ECON_INFLATION_NOWCAST.evaluate(data);
 const v2=ctx.ECON_CPI_COMPONENTS_V2.assess(data);
 assert(results.forecasts.length===5,"Missing one inflation forecast");
 assert(results.structural.status==="experimental","V1 source model is incomplete");
 assert(v2.status==="experimental_unvalidated","Granular V2 source model is incomplete");
 assert(results.structural.next===calendar.targetPeriod&&v2.target===calendar.targetPeriod,
       "Forecast target period not identical to verified release calendar");
 const targets={};
 for(const item of results.forecasts){
  const calendarEntry=calendar.entries[item.id];
  assert(Number.isFinite(item.econintel?.mom),"Missing baseline structural estimate: "+item.id);
  const mom= item.id==="cpi"?v2.cpi:item.id==="corecpi"?v2.core:item.econintel.mom;
  targets[item.id]={
   releaseAtUtc:calendarEntry.releaseAtUtc,
   releaseAgency:calendarEntry.agency,
   officialSchedule:calendarEntry.original,
   targetPeriod:calendar.targetPeriod,
   researchForecastMoM:mom,
   v1ReferenceMoM:item.econintel.mom,
   simple3mBaselineMoM:item.baseline.mom,
   officialNsaYoy:null,
   sourcedConsensusMoM:null,
   forecastStatus:"UNVALIDATED_NOT_FOR_TRADING",
   methodology:item.id==="cpi"||item.id==="corecpi"?
        "Unvalidated nested BLS CPI component proxy V2":"Unvalidated structural statistical proxy V1",
  };
 }
 const nowIso=new Date(nowMs).toISOString();
 return {
   schemaVersion:1,
   id:"ECONINTEL-"+calendar.targetPeriod+"-"+nowIso,
   study:"PRE-RELEASE LIVE-INFORMATION SNAPSHOT; never backdated as historical simulation",
   frozenAtUtc:nowIso,
   sourceSnapshotGeneratedAtUtc:data.generatedAt,
   sourceSnapshotSha256:hash(JSON.stringify(data)),
   implementationSha256:hash(modelSources.join("\n")),
   releaseScheduleSha256:hash(JSON.stringify(calendar)),
   sourceConnected:Object.values(data.series).filter(v=>v.status==="connected").length,
   sourceTotal:data.catalog.length,
   targetMonth:calendar.targetPeriod,
   forecasts:targets,
   cpiComponentContributions:v2.contributions,
   cpiComponentGroups:v2.groups,
   uncertainty:{interval:null,calibrated:false,why:"Pending independent PIT error quantile calibration"},
   performance:{pastExactOneDecimalHitRate:null,reason:"No validated Core CPI V2 full-model holdout"},
   limitations:[
    "Models v1/v2 are uncalibrated and must not be labeled reliable or near 100%",
    "Model calculations use the source snapshot as collected today, not historically reconstructed CPI BLS first-release vintages",
    "November gasoline and Brent monthly means may be partial",
    "No dated pre-release market consensus linked yet",
    "Official NSA annual rate requires its own first-release-source construction",
    "Scheduled official release timestamps need reverification if agencies reschedule",
   ]
 };
}
function main(){
 const dataPath=path.join(ROOT,"data","inflation-latest.json");
 const calPath=path.join(ROOT,CALENDAR);
 const data=JSON.parse(fs.readFileSync(dataPath,"utf8"));
 const cal=JSON.parse(fs.readFileSync(calPath,"utf8"));
 const models=MODEL_FILES.map(file=>fs.readFileSync(path.join(ROOT,file),"utf8"));
 const item=snapshot(data,cal,models,Date.now());
 const folder=path.join(ROOT,"research","forecasts");
 fs.mkdirSync(folder,{recursive:true});
 const output=path.join(folder,item.frozenAtUtc.replace(/[:.]/g,"-")+"_2026-11.json");
 // Deliberately refuse accidental overwrite or silent retroactive editing.
 fs.writeFileSync(output,JSON.stringify(item,null,2)+"\n",{flag:"wx"});
 console.log(JSON.stringify({saved:path.relative(ROOT,output),frozenAtUtc:item.frozenAtUtc,
  sourceCount:item.sourceConnected,
  forecasts:Object.fromEntries(Object.entries(item.forecasts).map(([k,x])=>[k,x.researchForecastMoM]))},null,2));
}
if(require.main===module)main();
module.exports={snapshot,utcTime,hash};
