/* Exercise the real CLI, journal watcher, API and SSE in Chrome. Node 22+. */
import {spawn} from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'elitelab-mining-browser-'));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const listener=http.createServer();
await new Promise(r=>listener.listen(0,'127.0.0.1',r));
const port=listener.address().port;
await new Promise(r=>listener.close(r));
const base=`http://127.0.0.1:${port}`;
const journals=path.join(temporary,'journals');fs.mkdirSync(journals);
const journal=path.join(journals,'Journal.20261022100000.01.log');
fs.writeFileSync(journal,JSON.stringify({event:'LoadGame',timestamp:'2026-10-22T10:00:00Z',Commander:'Test Miner',FID:'F2'})+'\n');
const env={...process.env,ELITELAB_SETTINGS:path.join(temporary,'settings.json'),ELITELAB_HOST:'127.0.0.1',ELITELAB_PORT:String(port),
  ELITELAB_OFFLINE:'1',ELITELAB_JOURNAL_DIR:journals,ELITELAB_DATA_DIR:path.join(temporary,'data'),
  ELITELAB_INSTANCE_DIR:path.join(temporary,'instance'),ELITELAB_AUTH_TOKEN:''};
let server,chrome,ws,serverLog='';
const append=events=>fs.appendFileSync(journal,events.map(e=>JSON.stringify(e)).join('\n')+'\n');
try {
  server=spawn(process.env.PYTHON||'python',['-u',path.join(root,'tests/mining_desk_server.py')],{cwd:root,env,windowsHide:true});
  server.stdout.on('data',d=>serverLog+=d);server.stderr.on('data',d=>serverLog+=d);
  let ready=false;
  for(let i=0;i<200;i++) {
    try{ready=(await (await fetch(base+'/api/health',{signal:AbortSignal.timeout(500)})).json()).ready;}catch{}
    if(ready)break;await sleep(100);
  }
  assert.ok(ready,serverLog);
  const profile=path.join(temporary,'chrome');
  chrome=spawn(process.env.CHROME_BIN||(process.platform==='win32'?'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe':'google-chrome'),
    ['--headless=new','--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'],
    {windowsHide:true,stdio:'ignore'});
  const debugFile=path.join(profile,'DevToolsActivePort');
  for(let i=0;i<200&&!fs.existsSync(debugFile);i++)await sleep(100);
  assert.ok(fs.existsSync(debugFile),'Chrome did not start');
  const debugPort=Number(fs.readFileSync(debugFile,'utf8').split('\n')[0]);
  const tabs=await (await fetch(`http://127.0.0.1:${debugPort}/json`)).json();
  ws=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);
  await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j;});
  let sequence=0;const pending=new Map(),errors=[];
  ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(m.error):p.resolve(m.result);}else if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails);};
  const send=(method,params={})=>new Promise((resolve,reject)=>{
    const id=++sequence,timer=setTimeout(()=>reject(new Error('CDP timeout '+method)),10000);
    pending.set(id,{resolve:r=>{clearTimeout(timer);resolve(r);},reject:e=>{clearTimeout(timer);reject(e);}});
    ws.send(JSON.stringify({id,method,params}));
  });
  const evaluate=async expression=>{const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(JSON.stringify(r.exceptionDetails));return r.result.value;};
  const waitFor=async expression=>{for(let i=0;i<450;i++){if(await evaluate(expression))return;await sleep(100);}assert.fail('Timed out: '+expression+'\n'+serverLog);};
  await send('Runtime.enable');await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url:base});
  await waitFor("!!document.querySelector('#card-mining [data-mining-total]')");
  assert.match(await evaluate("document.querySelector('#card-mining').textContent"),/No refinery output recorded/);
  await evaluate("[...document.querySelectorAll('[data-preset]')].find(b=>b.dataset.preset==='Mining & trade').click();true");
  assert.equal(await evaluate("document.querySelector('#grid > .card').dataset.id"),'mining');
  // Put the card first through the supported layout controls, retaining a companion cargo card.
  await evaluate("[...document.querySelectorAll('#layout-menu input[data-id]')].filter(c=>c.checked&&!['mining','cargo'].includes(c.dataset.id)).map(c=>c.dataset.id).forEach(id=>document.querySelector('#layout-menu input[data-id='+id+']').click());true");
  const events=fs.readFileSync(path.join(root,'tests/fixtures/mining/Journal.20261022100000.01.log'),'utf8').trim().split('\n').map(JSON.parse);
  append(events.slice(4));
  await waitFor("document.querySelector('[data-mining-total]').textContent==='3 t'");
  await waitFor("document.querySelector('#card-mining').textContent.includes('Last game session ended.')");
  assert.match(await evaluate("document.querySelector('#card-mining').textContent"),/6 t\/h/);
  assert.match(await evaluate("document.querySelector('#card-mining').textContent"),/Alexandrite/);
  const api=await (await fetch(base+'/api/mining')).json();
  assert.equal(api.refined_tons,3);assert.equal(api.ended,true);
  const demo=[{event:'LoadGame',timestamp:'2026-10-22T14:00:00Z',Commander:'Test Miner',FID:'F2'},
    {event:'Location',timestamp:'2026-10-22T14:00:01Z',StarSystem:'Delkar',StarPos:[67.8125,32.65625,35.25]},
    {event:'Cargo',timestamp:'2026-10-22T14:00:02Z',Vessel:'Ship',Inventory:[]},
    {event:'BuyDrones',timestamp:'2026-10-22T14:01:00Z',TotalCost:20000},
    {event:'ProspectedAsteroid',timestamp:'2026-10-22T14:05:00Z',Materials:[{Name:'Platinum',Proportion:51.67},{Name:'Palladium',Proportion:12.5}],Content_Localised:'Material Content: High',Remaining:82.4}];
  for(let i=0;i<48;i++)demo.push({event:'MiningRefined',timestamp:'2026-10-22T14:20:00Z',Type:'Platinum'});
  for(let i=0;i<6;i++)demo.push({event:'MiningRefined',timestamp:'2026-10-22T14:25:00Z',Type:'Painite'});
  demo.push({event:'MarketSell',timestamp:'2026-10-22T15:00:00Z',Type:'Platinum',Count:8,TotalSale:2224000},
    {event:'RefuelAll',timestamp:'2026-10-22T15:01:00Z',Cost:2400},{event:'RepairAll',timestamp:'2026-10-22T15:02:00Z',Cost:5800},
    {event:'BuyAmmo',timestamp:'2026-10-22T15:03:00Z',Cost:1200},{event:'Shutdown',timestamp:'2026-10-22T15:05:00Z'});
  append(demo);
  await waitFor("Lab.state.mining?.summary?.profit?.net_profit===2194600 && Lab.state.mining.summary.ended");
  await evaluate("document.querySelector('[data-form=spots] [name=ref]').value='Delkar';document.querySelector('[data-form=spots]').requestSubmit();true");
  await waitFor("document.querySelectorAll('[data-results=spots] [data-pin]').length>0");
  assert.match(await evaluate("document.querySelector('[data-results=spots]').textContent"),/Delkar 7 A Ring/);
  await evaluate("document.querySelector('[data-pin]').click();true");
  assert.equal(await evaluate("Lab.state.mining.selected.ring"),'Delkar 7 A Ring');
  assert.equal(await evaluate("document.querySelector('[data-form=buyers] [name=ref]').value"),'Delkar');
  await evaluate("document.querySelector('[data-tab=buyers]').click();document.querySelector('[data-load]').click();document.querySelector('[data-form=buyers]').requestSubmit();true");
  await waitFor("document.querySelectorAll('[data-results=buyers] [data-quote]').length>0");
  assert.equal(await evaluate("document.querySelector('[data-form=buyers] [name=quantity]').value"),'40');
  await evaluate("document.querySelector('[data-quote]').click();true");
  assert.match(await evaluate("document.querySelector('[data-valuation]').textContent"),/Unsold estimate/);
  if(process.env.ELITELAB_MINING_LIVE!=='1')assert.match(await evaluate("document.querySelector('[data-valuation]').textContent"),/11,660,000/);
  const planned=(await (await fetch(base+'/api/mining')).json()).profit;
  assert.equal(planned.net_profit,2194600,'A quote must never become realized profit');
  const outputDir=process.env.ELITELAB_SCREENSHOT_DIR||path.join(temporary,'screenshots');fs.mkdirSync(outputDir,{recursive:true});
  await evaluate("document.querySelector('[data-tab=spots]').click();true");
  for(const [name,width,height] of [['desktop',1440,1000],['mobile',390,844]]) {
    await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<500});await sleep(200);
    await evaluate("scrollTo(0,0);true");
    assert.ok(await evaluate('document.body.scrollWidth')<=width,'Horizontal page overflow');
    assert.ok(await evaluate("document.querySelector('#card-mining').scrollWidth<=document.querySelector('#card-mining').clientWidth+2"),'Mining card overflow');
    const shot=await send('Page.captureScreenshot',{format:'png'});
    fs.writeFileSync(path.join(outputDir,`mining-${name}.png`),Buffer.from(shot.data,'base64'));
  }
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});
  await evaluate("document.querySelector('[data-tab=buyers]').click();scrollTo(0,0);true");await sleep(100);
  const buyerShot=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(outputDir,'mining-buyers.png'),Buffer.from(buyerShot.data,'base64'));
  // A provider error clears results, and retrying works through the actual backend.
  await evaluate("document.querySelector('[data-form=spots] [name=ref]').value='Unavailable test';document.querySelector('[data-form=spots]').requestSubmit();true");
  await waitFor("document.querySelector('[data-search-status=spots]').textContent.includes('unavailable')");
  assert.equal(await evaluate("document.querySelectorAll('[data-results=spots] [data-pin]').length"),0);
  await evaluate("document.querySelector('[data-form=spots] [name=ref]').value='Delkar';document.querySelector('[data-form=spots]').requestSubmit();true");
  await waitFor("document.querySelectorAll('[data-results=spots] [data-pin]').length>0");
  // Simulate reversed network completion and provider-controlled HTML at the UI boundary.
  await evaluate("window.miningApi=Lab.api;window.miningResolvers=[];Lab.api=(p,q)=>p==='/api/mining/spots'?new Promise(r=>window.miningResolvers.push(r)):window.miningApi(p,q);document.querySelector('[data-form=spots]').requestSubmit();document.querySelector('[data-form=spots]').requestSubmit();true");
  await evaluate("window.miningResolvers[1]({results:[],note:'Newest result',bodies_checked:0,ref:'Delkar'});true");
  await waitFor("document.querySelector('[data-results=spots]').textContent.includes('Newest result')");
  await evaluate("window.miningResolvers[0]({results:[],note:'Old result',bodies_checked:0,ref:'Delkar'});true");await sleep(100);
  assert.equal(await evaluate("document.querySelector('[data-results=spots]').textContent.includes('Old result')"),false);
  await evaluate(`document.querySelector('[data-form=spots]').requestSubmit();window.miningResolvers[2]({results:[{ring:'<img src=x onerror="window.providerInjected=true">',system:'<img src=x>',ring_type:'Metallic',reserve:'Pristine',distance:1,signals:[{name:'<svg onload=alert(1)>',count:2}],updated_at:'bad',signals_updated_at:'bad',power_state:'Unknown'}],note:'<img src=x>',bodies_checked:1,ref:'Delkar'});true`);
  await waitFor("document.querySelector('[data-results=spots]').textContent.includes('<img')");
  assert.equal(await evaluate("document.querySelectorAll('[data-results=spots] img,[data-results=spots] svg').length"),0);
  assert.equal(await evaluate('!!window.providerInjected'),false);
  await evaluate("Lab.api=window.miningApi;document.querySelector('[data-form=spots] [name=hotspot]').value='Keep this filter';document.querySelector('[data-form=spots] [name=hotspot]').dispatchEvent(new Event('input',{bubbles:true}));true");
  const hostile='<img src=x onerror="window.miningInjected=true">';
  append([{event:'LoadGame',timestamp:'2026-10-22T14:00:00Z',Commander:'Test Miner',FID:'F2'},
    {event:'ProspectedAsteroid',timestamp:'2026-10-22T14:01:00Z',Content_Localised:hostile,MotherlodeMaterial:hostile,Remaining:100,Materials:[{Name:hostile,Proportion:25}]},
    {event:'MiningRefined',timestamp:'2026-10-22T14:02:00Z',Type:'Gold',Type_Localised:hostile}]);
  await waitFor("document.querySelector('[data-mining-total]').textContent==='1 t'");
  assert.equal(await evaluate("document.querySelectorAll('#card-mining img').length"),0);
  assert.equal(await evaluate('!!window.miningInjected'),false);
  assert.ok(await evaluate("document.querySelector('#card-mining').textContent.includes('<img')"));
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await sleep(150);
  assert.ok(await evaluate('document.body.scrollWidth')<=390);
  assert.equal(await evaluate("document.querySelector('[data-form=spots] [name=hotspot]').value"),'Keep this filter');
  await send('Page.reload');
  await waitFor("document.querySelector('#card-mining [data-mining-total]')?.textContent==='1 t'");
  assert.equal(await evaluate("!!document.querySelector('#card-cargo') && !document.querySelector('#card-ship')"),true);
  assert.equal(await evaluate("document.querySelector('[data-form=spots] [name=hotspot]').value"),'Keep this filter');
  assert.deepEqual(await evaluate("[...document.querySelectorAll('.render-error')].map(e=>e.textContent)"),[]);
  assert.deepEqual(errors,[]);
  assert.doesNotMatch(serverLog,/Traceback|handler failed/);
  console.log('Mining CLI, API, journal/SSE, profit ledger, ring search, buyers, quote valuation, retry, response ordering, saved filters/layout, desktop/mobile and HTML escaping passed. Provider: '+(process.env.ELITELAB_MINING_LIVE==='1'?'live Spansh':'synthetic fixture')+'. Screenshots: '+outputDir);
  await send('Browser.close').catch(()=>{});
} finally {
  ws?.close();chrome?.kill();
  if(server && server.exitCode===null) {
    try{await fetch(base+'/api/shutdown',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',signal:AbortSignal.timeout(1000)});}catch{}
    for(let i=0;i<50&&server.exitCode===null;i++)await sleep(100);
    if(server.exitCode===null)server.kill();
  }
}
