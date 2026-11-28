'use strict';
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'..','assets','inflation.js'),'utf8');
const elements=new Map();
function el(id){if(!elements.has(id))elements.set(id,{id,innerHTML:'',textContent:'',hidden:false,onclick:null,oninput:null});return elements.get(id)}
const months=[];
for(let i=0;i<15;i++)months.push([`${2025+Math.floor(i/12)}-${String(i%12+1).padStart(2,'0')}`,100+i*.3]);
const catalog=['cpi','corecpi','pce','corepce'].map(id=>({id,label:id,frequency:'monthly',kind:'price',group:'A',provider:'mock',url:'https://fred.stlouisfed.org/series/'+id}));
const series=Object.fromEntries(catalog.map(x=>[x.id,{status:'connected',history:months,value:months.at(-1)[1],period:months.at(-1)[0]}]));
const sample={schemaVersion:1,generatedAt:'2026-03-01T00:00:00Z',catalog,series,unconnected:[]};
const context={document:{getElementById:el,querySelectorAll:()=>[]},fetch:async()=>({ok:true,json:async()=>sample}),Date,Intl,console,Number,Math,String,Object,Set,Array,Promise};
vm.runInNewContext(source,context);setTimeout(()=>{
 try{
 assert.match(el('coverage').textContent,/4\/4/);
 assert.match(el('stats').innerHTML,/Core PCE/);
 assert.match(el('stats').innerHTML,/آخر 12 شهر · YoY/);
 assert.match(el('stats').innerHTML,/شهري · MoM/);
 assert.match(el('stats').innerHTML,/زخم 3 أشهر · SAAR/);
 assert.match(el('stats').innerHTML,/زخم 6 أشهر · SAAR/);
 const expectedYoY=((months.at(-1)[1]/months.at(-13)[1]-1)*100).toFixed(2)+'%';
 const expected3m=((Math.pow(months.at(-1)[1]/months.at(-4)[1],4)-1)*100).toFixed(2)+'%';
 assert.ok(el('stats').innerHTML.includes(expectedYoY),'YoY must use exactly 12 months');
 assert.ok(el('stats').innerHTML.includes(expected3m),'3M SAAR must annualize 3-month growth');
 assert.match(el('forecast').innerHTML,/خط أساس/);
 assert.match(el('indicators').innerHTML,/المؤشر/);
 console.log('Inflation UI smoke test passed');
 }catch(e){console.error(e);process.exitCode=1;}
},15);
