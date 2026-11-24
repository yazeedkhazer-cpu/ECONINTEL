'use strict';
/* Run after update_all.py, commit the generated dated labor-monitor.json with official data. */
const fs=require('node:fs');const path=require('node:path');
const {advance}=require('./labor_monitor_core.cjs');
const root=path.resolve(__dirname,'..');
const official=JSON.parse(fs.readFileSync(path.join(root,'data/official-latest.json'),'utf8'));
const out=path.join(root,'data/labor-monitor.json');
let previous=null;
if(fs.existsSync(out))previous=JSON.parse(fs.readFileSync(out,'utf8'));
const result=advance(previous,official,new Date());
if(result.changed){
 fs.mkdirSync(path.dirname(out),{recursive:true});
 const temp=out+'.tmp-'+process.pid;
 fs.writeFileSync(temp,JSON.stringify(result.value,null,2)+'\n',{encoding:'utf8',mode:0o644});
 fs.renameSync(temp,out);
}
console.log(result.changed?`Labor research snapshot saved; ${result.value.events.length} cumulative alerts.`:'Labor observations unchanged: no duplicate snapshot or alert.');
