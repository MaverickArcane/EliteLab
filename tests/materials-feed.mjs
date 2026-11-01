import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const source=fs.readFileSync(process.env.MATERIALS_CARD_SOURCE || new URL('../modules/materials/web/card.js',import.meta.url),'utf8');
const tick=()=>new Promise(r=>setTimeout(r,0));
const row=(count,gained=3)=>({name:'Iron',key:'iron',count,gained,category:'Raw',grade:1,cap:300});
function harness() {
  let card;const requests=[];
  vm.runInNewContext(source,{Lab:{util:{esc:String,fmt:String},card:c=>{card=c},
    api:()=>new Promise((resolve,reject)=>requests.push({resolve,reject}))},Date});
  const nodes=new Map();
  const el={querySelector:key=>{if(!nodes.has(key))nodes.set(key,{value:'',innerHTML:'',textContent:''});return nodes.get(key)}};
  card.mount(el);
  return {card,el,requests,list:()=>el.querySelector('.mat-list').innerHTML,
    render:version=>card.render(el,{materials:{inventory_version:version,totals:{Raw:25},inventory_count:1}})};
}
// An older HTTP response cannot put old counts back after a newer inventory event.
{
  const h=harness();h.render(1);h.render(2);
  if(h.requests.length>1){h.requests[1].resolve({materials:[row(25)]});await tick();}
  h.requests[0].resolve({materials:[row(5)]});await tick();
  h.requests[1].resolve({materials:[row(25)]});await tick();
  assert.match(h.list(),/>25</,'stale inventory response overwrote the latest count');
  assert.doesNotMatch(h.list(),/>5</);
}
// Filter edits made while loading apply to the returned rows, including category.
{
  const h=harness();h.render(1);
  h.el.querySelector('#mat-cat').value='Encoded';h.el.querySelector('#mat-cat').onchange();
  h.requests[0].resolve({materials:[row(25)]});await tick();
  assert.doesNotMatch(h.list(),/Iron/);
}
// Failure remains visible and a manual refresh retries without another journal event.
{
  const h=harness();h.render(1);h.requests[0].reject(new Error('offline'));await tick();
  assert.match(h.el.querySelector('.mat-status').textContent,/offline/);
  h.el.querySelector('#mat-refresh').onclick();h.requests[1].resolve({materials:[row(0,3)]});await tick();
  h.el.querySelector('#mat-view').value='gained';h.el.querySelector('#mat-view').onchange();
  assert.match(h.list(),/Iron/);assert.match(h.list(),/\+3/);
}
console.log('Materials inventory ordering, filters and retry passed.');
