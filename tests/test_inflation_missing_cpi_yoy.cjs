'use strict';
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'..','assets','inflation.js'),'utf8');
const elements=new Map();
function element(id){if(!elements.has(id))elements.set(id,{innerHTML:'',textContent:'',hidden:false,onclick:null,oninput:null});return elements.get(id)}
const complete=[];
for(let year=2025;year<=2026;year++)for(let month=1;month<=12;month++){
 if(year===2026&&month>10)continue;
 complete.push([year+'-'+String(month).padStart(2,'0'),100+(year-2025)*12+month]);
}
const withGap=complete.filter(([date])=>date!=='2025-10');
const catalog=['cpi','corecpi','pce','corepce'].map(id=>({id,kind:'price',frequency:'monthly',group:'x',provider:'test',url:'https://fred.stlouisfed.org'}));
const series=Object.fromEntries(catalog.map(({id})=>[id,{status:'connected',period:'2026-10',history:id==='cpi'||id==='corecpi'?withGap:complete,value:132}]));
for(const id of ['cpi','corecpi'])series[id].value=withGap.at(-1)[1];
for(const id of ['pce','corepce'])series[id].value=complete.at(-1)[1];
const sample={schemaVersion:1,generatedAt:'2026-11-28T00:00:00Z',catalog,series,unconnected:[]};
const context={document:{getElementById:element,querySelectorAll:()=>[]},fetch:async()=>({ok:true,json:async()=>sample}),Date,Intl,console,Number,Math,String,Object,Set,Array,Promise};
vm.runInNewContext(source,context);
setTimeout(()=>{
 try {
  const html=element('stats').innerHTML;
  assert.equal((html.match(/أكتوبر 2026: السنوي غير منشور رسميًا/g)||[]).length,2);
  assert.match(html,/3\.7%/);
  assert.match(html,/2\.6%/);
  assert.equal((html.match(/آخر قراءة سنوية رسمية/g)||[]).length,2);
  assert.equal((html.match(/class="inflation-missing-note"/g)||[]).length,2);
  assert.match(html,/زخم 3 أشهر · SAAR/);
  assert.match(html,/زخم 6 أشهر · SAAR/);
  const expected=((complete.at(-1)[1]/complete.find(x=>x[0]==='2025-10')[1]-1)*100).toFixed(2)+'%';
  assert.match(html,new RegExp(expected.replace('.','\\.')),'PCE YoY correctly uses October 2025 baseline');
  console.log('Missing October 2025 official CPI: no false YoY and contextual September BLS reading');
 } catch(err){console.error(err);process.exitCode=1;}
},15);
