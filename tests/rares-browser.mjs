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
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'elitelab-rares-browser-'));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const listener=http.createServer();
await new Promise(r=>listener.listen(0,'127.0.0.1',r));
const port=listener.address().port;
await new Promise(r=>listener.close(r));
const base=`http://127.0.0.1:${port}`;
const journals=path.join(temporary,'journals');fs.mkdirSync(journals);
const journal=path.join(journals,'Journal.20261022100000.01.log');
fs.writeFileSync(journal,JSON.stringify({event:'LoadGame',timestamp:'2026-10-22T10:00:00Z',Commander:'Rare Tester',FID:'F2'})+'\n');
const env={...process.env,ELITELAB_SETTINGS:path.join(temporary,'settings.json'),ELITELAB_HOST:'127.0.0.1',ELITELAB_PORT:String(port),
  ELITELAB_OFFLINE:'1',ELITELAB_JOURNAL_DIR:journals,ELITELAB_DATA_DIR:path.join(temporary,'data'),
  ELITELAB_INSTANCE_DIR:path.join(temporary,'instance'),ELITELAB_AUTH_TOKEN:''};
let server,chrome,ws,serverLog='';
const append=events=>fs.appendFileSync(journal,events.map(e=>JSON.stringify(e)).join('\n')+'\n');
try {
  server=spawn(process.env.PYTHON||'python',['-u','-m','elitelab','serve','--no-browser'],{cwd:root,env,windowsHide:true});
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
  await waitFor("!!document.querySelector('[data-rares-next]') && !!Lab.state.loop?.workflow");
  assert.match(await evaluate("document.querySelector('#card-loop').textContent"),/cargo unknown/);
  assert.equal(await evaluate("[...document.querySelectorAll('[data-rares-visit]')].every(e=>e.disabled)"),true);
  assert.match(await evaluate("document.querySelector('#card-cargo').textContent"),/Cargo unknown/);
  assert.match(await evaluate("document.querySelector('#card-market').textContent"),/No market recorded/);
  await evaluate("document.querySelector('[data-workspace=trade]').click();true");
  assert.equal(await evaluate("['selling','cargo','personal'].every(id=>!document.querySelector('#card-'+id).classList.contains('workspace-off'))"),true);
  assert.equal(await evaluate("document.querySelector('#card-loop').classList.contains('workspace-off')"),true);
  // Use the supported preset and layout controls for an uncluttered screenshot.
  await evaluate("[...document.querySelectorAll('[data-preset]')].find(b=>b.dataset.preset==='Rare goods').click();true");
  assert.equal(await evaluate("['loop','cargo','market','targets'].every(id=>!document.querySelector('#card-'+id).classList.contains('workspace-off'))"),true);
  const saveFile=(name,data)=>fs.writeFileSync(path.join(journals,name+'.json'),JSON.stringify(data));
  const cargo=(count,stamp='2026-10-22T10:01:00Z')=>saveFile('Cargo',{event:'Cargo',timestamp:stamp,Vessel:'Ship',Count:count,
    Inventory:count?[{Name:'alieneggs',Name_Localised:'Leathery Eggs',Count:count,Stolen:0}]:[]});
  const market=(stamp,name='Leathery Eggs')=>saveFile('Market',{event:'Market',timestamp:stamp,StationName:'Ridley Scott',StarSystem:'Zaonce',MarketID:123,
    Items:[{Name:'alieneggs',Name_Localised:name,Rare:true,Stock:12,BuyPrice:24500}]});
  append([{event:'Loadout',timestamp:'2026-10-22T10:00:01Z',Ship:'Python',CargoCapacity:64,Modules:[]},
    {event:'Location',timestamp:'2026-10-22T10:00:02Z',StarSystem:'Zaonce',StationName:'Another Station',Docked:true,StarPos:[0,0,0]}]);
  cargo(0);
  await waitFor("Lab.state.loop?.workflow?.cargo_known && Lab.state.loop.workflow.free_capacity===64");
  assert.match(await evaluate("document.querySelector('#card-cargo').textContent"),/Empty hold/);
  assert.equal(await evaluate("Lab.state.loop.stations.some(s=>s.docked_here)"),false);
  assert.match(await evaluate("document.querySelector('[data-rares-next]').textContent"),/Distance unknown/);
  await evaluate("document.querySelector('[data-rares-select]').click();true");
  await waitFor("document.querySelector('[data-rares-summary]').textContent.includes('Selected: George Lucas')");
  assert.match(await evaluate("document.querySelector('[data-rares-summary]').textContent"),/Selected: George Lucas/);
  assert.equal(await evaluate("document.querySelector('[data-rares-next] [data-copy]').dataset.copy"),'Leesti');
  await evaluate("document.querySelector('[data-rares-visit]').click();true");
  await waitFor("document.querySelector('[data-rares-next]').textContent.includes('Shifnalport')");
  assert.match(await evaluate("document.querySelector('[data-rares-next]').textContent"),/Shifnalport/);
  await send('Page.reload');
  await waitFor("document.querySelector('[data-rares-next]')?.textContent.includes('Shifnalport')");
  cargo(4,'2026-10-22T10:02:00Z');
  await waitFor("Lab.state.loop?.tons_total===4 && document.querySelector('[data-rares-next]').textContent.includes('George Lucas')");
  assert.equal(await evaluate("document.querySelector('#card-loop').textContent.includes('Manual visit mark')"),false);
  assert.match(await evaluate("document.querySelector('#card-cargo').textContent"),/4 t aboard/);
  assert.equal(await evaluate("Lab.state.loop.workflow.free_capacity"),60);
  market('2026-10-22T09:00:00Z');
  await waitFor("Lab.state.loop.workflow.market.status==='previous_station'");
  append([{event:'Docked',timestamp:'2026-10-22T10:03:00Z',StarSystem:'Zaonce',StationName:'Ridley Scott'}]);
  await waitFor("Lab.state.loop.workflow.market.status==='previous_visit'");
  assert.equal(await evaluate("Lab.state.loop.stations.filter(s=>s.docked_here).length"),1);
  const outputDir=process.env.ELITELAB_SCREENSHOT_DIR||path.join(temporary,'screenshots');fs.mkdirSync(outputDir,{recursive:true});
  const screenshot=async(name,width=1440,height=1100,target='#card-loop')=>{
    await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<500});
    await evaluate(`document.querySelector(${JSON.stringify(target)}).scrollIntoView({block:'start'});true`);await sleep(350);
    assert.ok(await evaluate('document.body.scrollWidth')<=width,'Horizontal overflow at '+width);
    const shot=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(outputDir,name+'.png'),Buffer.from(shot.data,'base64'));
  };
  await screenshot('rares-previous-visit',1440,1000,'#card-market');
  market('2026-10-22T10:03:01Z');
  await waitFor("Lab.state.loop.workflow.market.status==='current_snapshot'");
  assert.match(await evaluate("document.querySelector('#card-market').textContent"),/24,500 Cr/);
  assert.match(await evaluate("document.querySelector('#card-market').textContent"),/12 t/);
  await screenshot('rares-buying-desktop');
  await screenshot('rares-cargo-market-desktop',1440,1000,'#card-cargo');
  await screenshot('rares-buying-mobile',390,1000);
  await screenshot('rares-market-mobile',390,1000,'#card-market');
  // Market-derived text must stay text even when the local game file is hostile.
  market('2026-10-22T10:03:02Z','<img src=x onerror="window.raresXss=1">');
  await waitFor("document.querySelector('#card-market').textContent.includes('<img')");
  assert.equal(await evaluate("!!document.querySelector('#card-market img') || !!window.raresXss"),false);
  // Exercise the real endpoint, then inject a failed browser request and recover.
  await evaluate("document.querySelector('[data-rares-loop]').dispatchEvent(new Event('change'));true");
  await waitFor("document.querySelector('[data-rares-status]').textContent==='Rare loop selected.'");
  await evaluate("window.raresPost=Lab.post;Lab.post=async()=>{throw new Error('Test: connection unavailable')};document.querySelector('[data-rares-loop]').dispatchEvent(new Event('change'));true");
  await waitFor("document.querySelector('[data-rares-status]').textContent.includes('connection unavailable')");
  assert.equal(await evaluate("document.querySelector('[data-rares-loop]').disabled"),false);
  assert.equal(await evaluate("document.querySelector('[data-rares-loop]').value"),'lave');
  await evaluate("Lab.post=window.raresPost;document.querySelector('[data-rares-loop]').dispatchEvent(new Event('change'));true");
  await waitFor("document.querySelector('[data-rares-status]').textContent==='Rare loop selected.'");
  // A manual mark belongs to the commander and cargo snapshot, not the browser forever.
  await evaluate("document.querySelector('[data-rares-visit]').click();true");
  append([{event:'LoadGame',timestamp:'2026-10-22T10:04:00Z',Commander:'Another Tester',FID:'F3'}]);
  await waitFor("!Lab.state.loop.workflow.cargo_known && Lab.state.journal.cmdr==='Another Tester'");
  assert.equal(await evaluate("document.querySelector('#card-cargo').textContent.includes('4 t aboard')"),false);
  cargo(0,'2026-10-22T10:04:01Z');
  await waitFor("Lab.state.loop.workflow.cargo_known && Lab.state.loop.tons_total===0");
  assert.equal(await evaluate("document.querySelector('#card-loop').textContent.includes('Manual visit mark')"),false);
  await evaluate("document.querySelector('[data-rares-visit]').click();document.querySelector('[data-rares-reset]').click();true");
  await sleep(100);
  assert.equal(await evaluate("document.querySelector('#card-loop').textContent.includes('Manual visit mark')"),false);
  // All handoffs reveal the intended card without destroying saved custom ordering.
  for(const id of ['cargo','market','targets']) {
    await evaluate(`document.querySelector('[data-rares-focus=${id}]').click();true`);
    assert.equal(await evaluate(`document.querySelector('#card-${id}').classList.contains('workspace-off')`),false);
  }
  const api=await (await fetch(base+'/api/loop')).json();
  assert.equal(api.workflow.cargo_known,true);assert.equal(api.tons_total,0);
  // Deterministic coordinates exercise map selection separately from offline journal screenshots.
  await evaluate("Lab.set('loop',{stations:Lab.state.loop.stations.map((s,i)=>({...s,coords:{x:i*10,y:0,z:i*20}}))});Lab.map.layers.loop.points(Lab.state).find(p=>p.name==='Diso').onClick();true");
  await waitFor("document.querySelector('[data-rares-summary]').textContent.includes('Selected: Shifnalport')");
  assert.deepEqual(await evaluate("Lab.map.layers.loop.points(Lab.state).filter(p=>p.selected).map(p=>p.name)"),['Diso']);
  await evaluate("Lab.set('loop',{stations:[...Lab.state.loop.stations].reverse()});true");
  await sleep(100);
  assert.match(await evaluate("document.querySelector('.rares-stop.selected').textContent"),/Shifnalport/);
  // A state update can reorder stops before the next animation-frame render.
  await evaluate("var stop=[...document.querySelectorAll('.rares-stop')].find(e=>e.textContent.includes('George Lucas'));Lab.state.loop.stations.reverse();stop.querySelector('[data-rares-select]').click();true");
  await waitFor("document.querySelector('[data-rares-summary]').textContent.includes('Selected: George Lucas')");
  assert.deepEqual(await evaluate("[...document.querySelectorAll('.render-error')].map(e=>e.textContent)"),[]);
  assert.deepEqual(errors,[]);assert.doesNotMatch(serverLog,/Traceback|handler failed/);
  console.log('Rare workflow CLI, journal watcher/SSE, exact station arrival, cargo resets, manual marks/reload, market freshness, HTML escaping, API retry, handoffs and desktop/mobile passed. Synthetic journals; network providers offline. Screenshots: '+outputDir);
  await send('Browser.close').catch(()=>{});
} finally {
  ws?.close();chrome?.kill();
  if(server && server.exitCode===null) {
    try{await fetch(base+'/api/shutdown',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',signal:AbortSignal.timeout(1000)});}catch{}
    for(let i=0;i<50&&server.exitCode===null;i++)await sleep(100);
    if(server.exitCode===null)server.kill();
  }
}
