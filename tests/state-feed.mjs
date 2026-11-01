import fs from 'node:fs';
import assert from 'node:assert/strict';
const source=fs.readFileSync(new URL('../web/state-feed.js',import.meta.url),'utf8');
const {StateFeed}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const tick=()=>new Promise(r=>setTimeout(r,0));
function harness(options={}) {
  let state={};const requests=[];
  const feed=new StateFeed({retryMs:5,...options,
    fetchSnapshot:()=>new Promise((resolve,reject)=>requests.push({resolve,reject})),
    snapshot:s=>{state={...s}},change:m=>{state[m.key]=m.value;}});
  return {feed,requests,get state(){return state}};
}
const event=(v,key,value)=>({v,ns:'party',key,value});
// The initial snapshot already covers older queued messages.
{
  const h=harness();h.feed.reset({_version:10,pickup:52});
  h.feed.receive(event(9,'pickup',1200));
  assert.equal(h.state.pickup,52);assert.equal(h.feed.version,10);assert.equal(h.requests.length,0);
  h.feed.stop();
}
// Out-of-order messages for different fields are both retained, in order.
{
  const h=harness();h.feed.reset({_version:10,pickup:52});
  h.feed.receive(event(12,'pickup',0));h.feed.receive(event(11,'delivered',52));
  assert.equal(h.state.delivered,52);assert.equal(h.state.pickup,0);
  h.requests[0].resolve({_version:11,pickup:52,delivered:52});await tick();
  assert.equal(h.state.pickup,0);assert.equal(h.feed.version,12);h.feed.stop();
}
// Snapshot fills a missing update, then later buffered updates are replayed.
{
  const h=harness();h.feed.reset({_version:10});h.feed.receive(event(13,'pickup',200));
  h.requests[0].resolve({_version:12,delivered:1000,pickup:1200});await tick();
  assert.equal(h.state.delivered,1000);assert.equal(h.state.pickup,200);assert.equal(h.feed.version,13);h.feed.stop();
}
// Reconnect to a restarted server: an old HTTP response cannot overwrite it.
{
  const h=harness();h.feed.reset({_version:10});h.feed.receive(event(12,'pickup',1200));
  h.feed.reset({_version:1,pickup:52});h.requests[0].resolve({_version:20,pickup:1200});await tick();
  assert.equal(h.state.pickup,52);assert.equal(h.feed.version,1);h.feed.stop();
}
// Failed repairs retry without needing another event; pending storage is bounded.
{
  const h=harness({maxPending:2});h.feed.reset({_version:1});
  for(let v=5;v<=8;v++)h.feed.receive(event(v,'pickup',v));
  assert.ok(h.feed.pending.size<=2);h.requests[0].reject(new Error('offline'));
  for(let i=0;i<30 && h.requests.length<2;i++)await new Promise(r=>setTimeout(r,5));
  assert.equal(h.requests.length,2);h.requests[1].resolve({_version:8,pickup:52});await tick();
  assert.equal(h.state.pickup,52);assert.equal(h.feed.version,8);h.feed.stop();
}
console.log('State feed ordering and recovery passed.');
