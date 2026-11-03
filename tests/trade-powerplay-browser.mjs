/* Exercise the real CLI, journal watcher, API and SSE in Chrome. Node 22+. */
import {spawn} from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';

// These Node-side probes need no idle keep-alive pool. Closing explicitly avoids
// Windows aborting an unused probe socket while Chrome continues the scenario.
const fetch=(url,options={})=>globalThis.fetch(url,{...options,headers:{Connection:'close',...options.headers}});

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'elitelab-trade-powerplay-browser-'));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const listener=http.createServer();
await new Promise(r=>listener.listen(0,'127.0.0.1',r));
const port=listener.address().port;
await new Promise(r=>listener.close(r));
const base=`http://127.0.0.1:${port}`;
const journals=path.join(temporary,'journals');fs.mkdirSync(journals);
const journal=path.join(journals,'Journal.20261022100000.01.log');
fs.writeFileSync(journal,JSON.stringify({event:'LoadGame',timestamp:'2026-10-22T10:00:00Z',Commander:'Trade Tester',FID:'F2'})+'\n');
const env={...process.env,ELITELAB_SETTINGS:path.join(temporary,'settings.json'),ELITELAB_HOST:'127.0.0.1',ELITELAB_PORT:String(port),
  ELITELAB_OFFLINE:'1',ELITELAB_JOURNAL_DIR:journals,ELITELAB_DATA_DIR:path.join(temporary,'data'),
  ELITELAB_INSTANCE_DIR:path.join(temporary,'instance'),ELITELAB_AUTH_TOKEN:''};

fs.mkdirSync(env.ELITELAB_DATA_DIR,{recursive:true});
const stamp='2026-10-22T10:00:00Z';
const stop=(market_id,system,station,x,price)=>({market_id,system,station,pos:[x,0,0],price,volume:1000,pad:'L',arrival_ls:100,observed_at:stamp});
const buy=stop(1,'Sol','Port 1',0,100),sell=stop(2,'Alpha','Port 2',39,400);
const plan={id:'handoff-fixture',route_type:'round_trip',quantity:100,cmdr:'Trade Tester',selected_at:stamp,source:'Synthetic browser fixture',profit:40000,cost:30000,required_credits:10000,distance:39,total_distance:78,estimated_jumps:2,
 legs:[{commodity:'Gold',quantity:100,buy,sell,profit:30000,cost:10000,per_ton:300},
 {commodity:'Silver',quantity:100,buy:{...sell,price:200},sell:{...buy,price:300},profit:10000,cost:20000,per_ton:100}]};
fs.writeFileSync(path.join(env.ELITELAB_DATA_DIR,'personal.json'),JSON.stringify({plan}));

let server,chrome,ws,serverLog='';
const append=events=>fs.appendFileSync(journal,events.map(e=>JSON.stringify(e)).join('\n')+'\n');
try {
  server=spawn(process.env.PYTHON||'python',['-u',path.join(root,'tests/trade_powerplay_server.py')],{cwd:root,env,windowsHide:true});
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
  const waitFor=async expression=>{for(let i=0;i<150;i++){if(await evaluate(expression)){await evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(()=>r(true))))');return;}await sleep(100);}assert.fail('Timed out: '+expression+'\nStatuses: '+await evaluate("[...document.querySelectorAll('[data-search-status]')].map(e=>e.textContent).join(' | ')")+'\n'+serverLog);};
  await send('Runtime.enable');await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await send('Page.addScriptToEvaluateOnNewDocument',{source:"localStorage.setItem('workspace.v1',JSON.stringify('all'))"});
  await send('Page.navigate',{url:base});
  await waitFor("!!document.querySelector('[data-plan-powerplay]') && !!document.querySelector('[data-trade-powerplay-context]')");
  assert.equal(await evaluate("document.querySelector('[data-plan-powerplay]').disabled"),true);
  assert.equal((await (await fetch(base+'/api/personal/powerplay')).json()).status,'pledge_unknown');
  append([{event:'Powerplay',timestamp:'2026-10-22T10:01:00Z',Power:'Edmund Mahon',Merits:1200,Rank:1},
    {event:'Location',timestamp:'2026-10-22T10:01:01Z',StarSystem:'Sol',StarPos:[0,0,0],Docked:false}]);
  await waitFor("Lab.state.personal.powerplay_handoff.ready && !document.querySelector('[data-plan-powerplay]').disabled");
  // Keep only the actual source and destination panels using supported layout controls.
  await evaluate("[...document.querySelectorAll('#layout-menu input[data-id]')].filter(c=>c.checked&&!['personal','targets'].includes(c.dataset.id)).map(c=>c.dataset.id).forEach(id=>document.querySelector('#layout-menu input[data-id='+id+']').click());true");
  const input=(name)=>`document.querySelector('#card-targets [name=${name}],#t-${name}')`;
  const find=()=>evaluate("var b=document.querySelector('#t-go');if(b)b.click();else document.querySelector('[data-target-form]').requestSubmit();true");
  const status="document.querySelector('[data-target-status],#t-status').textContent";
  await evaluate(`${input('min')}.value='100';${input('max')}.value='180';${input('pad')}.value='M';document.querySelector('[data-personal-search] [name=destination]').value='Keep this filter';true`);
  const originalPlan=await (await fetch(base+'/api/personal/plan')).json();
  await evaluate("document.querySelector('[data-plan-powerplay=sell]').click();true");
  await waitFor("!document.querySelector('[data-trade-powerplay-context]').hidden");
  assert.equal(await evaluate(input('ref')+'.value'),'Alpha');
  assert.equal(await evaluate(input('power')+'.value'),'Edmund Mahon');
  assert.equal(await evaluate(input('min')+'.value'),'100');
  assert.equal(await evaluate(input('max')+'.value'),'180');
  assert.equal(await evaluate(input('pad')+'.value'),'M');
  assert.match(await evaluate("document.querySelector('[data-trade-powerplay-context]').textContent"),/100 t Gold planned/);
  assert.match(await evaluate("document.querySelector('[data-trade-powerplay-context]').textContent"),/Expected merits: unknown/);
  await find();
  await waitFor("document.querySelector('#card-targets').textContent.includes('Fixture Exchange')");
  assert.deepEqual((await (await fetch(base+'/api/personal/plan')).json()).plan,originalPlan.plan);
  assert.equal(await evaluate("Lab.state.powerplay.merits"),1200);
  const outputDir=process.env.ELITELAB_SCREENSHOT_DIR||path.join(temporary,'screenshots');fs.mkdirSync(outputDir,{recursive:true});
  const capture=async(name,width,height,target)=>{
    await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<500});
    await evaluate(`document.querySelector(${JSON.stringify(target)}).scrollIntoView({block:'start'});scrollBy(0,-130);true`);await sleep(250);
    assert.ok(await evaluate('document.body.scrollWidth')<=width,'Horizontal overflow at '+width);
    const shot=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(outputDir,name+'.png'),Buffer.from(shot.data,'base64'));
  };
  await capture('trade-powerplay-source-desktop',1440,1100,'[data-personal-plan]');
  await capture('trade-powerplay-finder-desktop',1440,1000,'#card-targets');
  await capture('trade-powerplay-finder-mobile',390,1000,'#card-targets');
  // Pinned origin survives a ship move; cargo-dependent results are cleared.
  append([{event:'FSDJump',timestamp:'2026-10-22T10:02:00Z',StarSystem:'Changed location',StarPos:[10,0,0]}]);
  await waitFor("Lab.state.journal.system==='Changed location'");
  assert.equal(await evaluate(input('ref')+'.value'),'Alpha');
  assert.equal(await evaluate("document.querySelector('#card-targets').textContent.includes('Fixture Exchange')"),false);
  // A request already in flight must not repopulate a changed route or the map.
  await evaluate("window.handoffApi=Lab.api;window.handoffResolve=null;Lab.api=(p,q)=>p==='/api/targets'?new Promise(r=>handoffResolve=r):window.handoffApi.call(Lab,p,q);true");
  await find();await waitFor('!!window.handoffResolve');
  append([{event:'Powerplay',timestamp:'2026-10-22T10:03:00Z',Power:'Felicia Winters',Merits:1200,Rank:1}]);
  await waitFor("document.querySelector('[data-trade-powerplay-context]').textContent.includes('refresh required')");
  await evaluate("handoffResolve({ref:'Alpha',power:'Edmund Mahon',count:1,results:[{system:'Old response',station:'Stale station',x:1,y:0,z:0}]});Lab.api=window.handoffApi;true");await sleep(150);
  assert.equal(await evaluate("document.querySelector('#card-targets').textContent.includes('Stale station')"),false);
  assert.equal(await evaluate("Lab.map.layers.targets.points(Lab.state).some(p=>p.name==='Old response')"),false);
  await find();
  assert.match(await evaluate("document.querySelector('[data-trade-powerplay-context]').textContent"),/refresh required/);
  await capture('trade-powerplay-stale-desktop',1440,1000,'#card-targets');
  await evaluate("document.querySelector('[data-plan-powerplay=buy]').click();true");
  await waitFor(input('ref')+".value==='Sol' && "+input('power')+".value==='Felicia Winters'");
  assert.equal(await evaluate("document.querySelector('[data-personal-search] [name=destination]').value"),'Keep this filter');
  // The live return leg updates the available handoff, not the existing one.
  fs.writeFileSync(path.join(journals,'Cargo.json'),JSON.stringify({event:'Cargo',timestamp:'2026-10-22T10:04:00Z',Count:0,Inventory:[]}));
  append([{event:'MarketSell',timestamp:'2026-10-22T10:04:01Z',MarketID:2,Type:'Gold',Count:100,SellPrice:400,TotalSale:40000}]);
  await waitFor("Lab.state.personal.powerplay_handoff.leg===1");
  assert.match(await evaluate("document.querySelector('[data-trade-powerplay-context]').textContent"),/refresh required/);
  await evaluate("document.querySelector('[data-plan-powerplay=sell]').click();true");
  await waitFor("document.querySelector('[data-trade-powerplay-context]').textContent.includes('100 t Silver planned')");
  assert.equal(await evaluate(input('ref')+'.value'),'Sol');
  // Preview failure retains both the plan and typed filters; retry succeeds.
  await evaluate("window.previewApi=Lab.api;Lab.api=(p,q)=>p==='/api/personal/powerplay'?Promise.reject(Error('Test handoff unavailable')):window.previewApi.call(Lab,p,q);document.querySelector('[data-plan-powerplay=buy]').click();true");
  await waitFor("document.querySelector('#card-personal').textContent.includes('Test handoff unavailable')");
  await evaluate("Lab.api=window.previewApi;document.querySelector('[data-plan-powerplay=buy]').click();true");
  await waitFor(input('ref')+".value==='Alpha'");
  // Hostile names in the handoff render as text, never nodes or handlers.
  await evaluate("var r=Lab.state.personal.ui_powerplay;Lab.set('personal',{ui_powerplay:{...r,request_id:'escape-test',stop:{...r.stop,station:'<img src=x onerror=window.handoffXss=1>'}}});true");
  await waitFor("document.querySelector('[data-trade-powerplay-context]').textContent.includes('<img')");
  assert.equal(await evaluate("!!document.querySelector('[data-trade-powerplay-context] img')||!!window.handoffXss"),false);
  // Manual mode is explicit; a failed provider request can be retried.
  await evaluate("document.querySelector('[data-handoff-manual]').click();true");
  await waitFor("document.querySelector('[data-trade-powerplay-context]').hidden");
  await evaluate(`${input('ref')}.value='Unavailable test';${input('ref')}.dispatchEvent(new Event('input',{bubbles:true}));true`);
  await find();await waitFor(`${status}.toLowerCase().includes('unavailable') || ${status}.toLowerCase().includes('error')`);
  await evaluate(`${input('ref')}.value='Alpha';${input('ref')}.dispatchEvent(new Event('input',{bubbles:true}));true`);
  await find();await waitFor("document.querySelector('#card-targets').textContent.includes('Fixture Exchange')");
  append([{event:'Commander',timestamp:'2026-10-22T10:05:00Z',Name:'Different Tester',FID:'F3'}]);
  await waitFor("Lab.state.personal.powerplay_handoff.status==='commander_mismatch'");
  assert.equal(await evaluate("document.querySelectorAll('[data-plan-powerplay]:not(:disabled)').length"),0);
  assert.deepEqual(await evaluate("[...document.querySelectorAll('.render-error')].map(e=>e.textContent)"),[]);
  assert.deepEqual(errors,[]);assert.doesNotMatch(serverLog,/Traceback|handler failed/);
  console.log('Trade/Powerplay handoff real CLI, HTTP, journal/SSE, preserved filters/route, unknown eligibility, stale token/request/map rejection, return leg, commander/pledge changes, retry, escaping and desktop/mobile passed. Synthetic journals and station provider. Screenshots: '+outputDir);
  await send('Browser.close').catch(()=>{});
} finally {
  ws?.close();chrome?.kill();
  if(server&&server.exitCode===null){
    try{await fetch(base+'/api/shutdown',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',signal:AbortSignal.timeout(1000)});}catch{}
    for(let i=0;i<50&&server.exitCode===null;i++)await sleep(100);
    if(server.exitCode===null)server.kill();
  }
}
