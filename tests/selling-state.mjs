import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {setImmediate} from 'node:timers/promises';

// Mount the actual card with a delayed initial HTTP response, then deliver newer
// state through its normal render entry point. Neither stale data nor a stale
// error may replace that state/message.
for(const failure of [false,true]) {
  let card,resolve,reject;
  const response=new Promise((yes,no)=>{resolve=yes;reject=no;});
  const message={textContent:''},node={innerHTML:'',disabled:false};
  const form={elements:{namedItem:()=>null},querySelector:()=>node};
  const el={innerHTML:'',querySelector:s=>s==='form'?form:s==='[data-sale-message]'?message:node,
    addEventListener:()=>{}};
  const Lab={util:{esc:String,fmt:String,ls:{get:()=>({})}},card:c=>card=c,api:()=>response};
  vm.runInNewContext(fs.readFileSync(new URL('../modules/selling/web/card.js',import.meta.url),'utf8'),
    {Lab,setTimeout,clearTimeout});
  card.mount(el);
  const current={job:{status:'complete'},context:{goods:[]}};
  card.render(el,{selling:current});
  message.textContent='Current results';
  if(failure)reject(Error('stale failure'));else resolve({job:null,context:{goods:[]}});
  await setImmediate();
  assert.equal(el._selling.data,current,'Old HTTP response overwrote live state');
  assert.equal(message.textContent,'Current results','Old HTTP error overwrote current message');
  card.unmount(el);
}
console.log('Cargo panel preserves live state across delayed HTTP success/failure.');
