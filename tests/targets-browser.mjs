/* Exercise the real CLI, journal watcher, API and SSE in Chrome. Node 22+. */
import {spawn} from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'elitelab-target-browser-'));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const listener=http.createServer();
await new Promise(r=>listener.listen(0,'127.0.0.1',r));
const port=listener.address().port;
await new Promise(r=>listener.close(r));
const base=`http://127.0.0.1:${port}`;
const journals=path.join(temporary,'journals');fs.mkdirSync(journals);
const journal=path.join(journals,'Journal.20261022100000.01.log');
fs.writeFileSync(journal,[{event:'LoadGame',timestamp:'2026-11-02T01:00:00Z',Commander:'Target Tester',FID:'F2'}, {event:'Powerplay',timestamp:'2026-11-02T01:00:01Z',Power:'Edmund Mahon'}, {event:'Location',timestamp:'2026-11-02T01:00:02Z',StarSystem:'Zaonce',StarPos:process.env.ELITELAB_TARGETS_LIVE==='1'?undefined:[0,0,0],Docked:true,StationName:'Ridley Scott',StationType:'Orbis'}, {event:'Loadout',timestamp:'2026-11-02T01:00:03Z',Ship:'Python',ShipID:1,UnladenMass:500,CargoCapacity:128,FuelCapacity:{Main:32},Modules:[{Slot:'FrameShiftDrive',Item:'int_hyperdrive_size5_class5'}]}, {event:'MarketBuy',timestamp:'2026-11-02T01:00:04Z',Type:'alieneggs',Count:10,BuyPrice:500}].map(e=>JSON.stringify(e)).join('\n')+'\n');
const env={...process.env,ELITELAB_SETTINGS:path.join(temporary,'settings.json'),ELITELAB_HOST:'127.0.0.1',ELITELAB_PORT:String(port),
  ELITELAB_OFFLINE:'1',ELITELAB_JOURNAL_DIR:journals,ELITELAB_DATA_DIR:path.join(temporary,'data'),
  ELITELAB_INSTANCE_DIR:path.join(temporary,'instance'),ELITELAB_AUTH_TOKEN:''};
fs.writeFileSync(path.join(journals,'Cargo.json'),JSON.stringify({timestamp:'2026-11-02T01:00:05Z',event:'Cargo',Vessel:'Ship',Count:10,Inventory:[{Name:'alieneggs',Name_Localised:'Leathery Eggs',Count:10,Stolen:0}]}));
let server,chrome,ws,serverLog='';
const append=events=>fs.appendFileSync(journal,events.map(e=>JSON.stringify(e)).join('\n')+'\n');
try {
  server=spawn(process.env.PYTHON||'python',['-u',path.join(root,'tests/targets_server.py')],{cwd:root,env,windowsHide:true});
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
  const waitFor=async expression=>{for(let i=0;i<(process.env.ELITELAB_TARGETS_LIVE==='1'?1800:450);i++){if(await evaluate(expression))return;await sleep(100);}assert.fail('Timed out: '+expression+'\nStatuses: '+await evaluate("[...document.querySelectorAll('[data-target-status]')].map(e=>e.textContent).join(' | ')")+'\n'+serverLog);};
  await send('Runtime.enable');await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await send('Page.addScriptToEvaluateOnNewDocument',{source:"localStorage.setItem('workspace.v1',JSON.stringify('all'))"});
  await send('Page.navigate',{url:base});
  await waitFor("!!document.querySelector('[data-target-form]') && Lab.state.targets.pledge==='Edmund Mahon' && Lab.state.journal.cargo?.items?.some(r=>r.key==='alieneggs')");
  await evaluate("[...document.querySelectorAll('#layout-menu input[data-id]')].filter(c=>c.checked&&c.dataset.id!=='targets').map(c=>c.dataset.id).forEach(id=>document.querySelector('#layout-menu input[data-id='+id+']').click());true");
  await evaluate("var f=document.querySelector('[data-target-form]');f.elements.min.value='0';f.elements.max.value='200';f.elements.rate_mode.value='mahon_observed';f.dispatchEvent(new Event('input'));f.requestSubmit();true");
  await waitFor("document.querySelector('[data-target-status]').textContent.includes('markets checked')");
  const result=await evaluate('Lab.state.targets.last');
  assert.equal(result.rate_mode,'mahon_observed');
  assert.equal(result.cargo[0].key,'alieneggs');
  if(process.env.ELITELAB_TARGETS_LIVE!=='1') {
    assert.equal(result.results[0].system,'Test Near');
    assert.ok(result.results[0].merits_per_jump>result.results[1].merits_per_jump);
    assert.equal(result.results[2].estimated_merits,null);
    await evaluate("var f=document.querySelector('[data-target-form]');f.elements.interpolate.value='true';f.dispatchEvent(new Event('input'));f.requestSubmit();true");
    await waitFor("Lab.state.targets.last?.interpolate===true");
    assert.equal(await evaluate("Lab.state.targets.last.results.find(r=>r.system==='Test Middle').goods.alieneggs.price"),25000);
    await evaluate("document.querySelector('[data-target-select]').click();document.querySelector('.target-curves').open=true;document.querySelectorAll('.target-result details')[0].open=true;true");
    await waitFor("document.querySelector('[data-target-selection]').textContent.includes('Selected sell target')");
    assert.equal(await evaluate("Lab.map.layers.targets.points(Lab.state).filter(p=>p.selected).length"),1);
    await evaluate("Lab.map.layers.targets.points(Lab.state).find(p=>p.name==='Test Far').onClick();true");
    await waitFor("document.querySelector('[data-target-selection]').textContent.includes('Test Far')");
    assert.equal(await evaluate("document.querySelectorAll('[data-target-chart] circle').length"),2);
  }
  const outputDir=process.env.ELITELAB_SCREENSHOT_DIR||path.join(temporary,'screenshots');fs.mkdirSync(outputDir,{recursive:true});
  for(const [name,width,height] of [['desktop',1440,1100],['mobile',390,1000]]) {
    await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<500});await sleep(150);
    await evaluate('scrollTo(0,0);true');
    assert.ok(await evaluate('document.body.scrollWidth')<=width,'Page overflow');
    const shot=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(outputDir,`targets-${name}.png`),Buffer.from(shot.data,'base64'));
  }
  await evaluate("document.querySelector('[data-target-results]').scrollIntoView({block:'start'});scrollBy(0,-120);true");await sleep(100);
  const detail=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(outputDir,'targets-mobile-results.png'),Buffer.from(detail.data,'base64'));
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await evaluate("document.querySelector('.target-curves').open=true;document.querySelector('.target-curves').scrollIntoView({block:'start'});scrollBy(0,-70);true");await sleep(100);
  const graph=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(outputDir,'targets-distance-curve.png'),Buffer.from(graph.data,'base64'));
  for(const [ref,expected] of [['Empty test','No reported markets'],['Unavailable test','Spansh target search unavailable']]) {
    await evaluate(`var f=document.querySelector('[data-target-form]');f.elements.ref.value=${JSON.stringify(ref)};f.dispatchEvent(new Event('input'));f.requestSubmit();true`);
    await waitFor(`document.querySelector('#card-targets').textContent.includes(${JSON.stringify(expected)})`);
    assert.equal(await evaluate("document.querySelectorAll('[data-target-select]').length"),0);
    assert.equal(await evaluate('Lab.map.layers.targets.points(Lab.state).length'),0);
  }
  await evaluate("var f=document.querySelector('[data-target-form]');f.elements.ref.value='Zaonce';f.dispatchEvent(new Event('input'));f.requestSubmit();true");
  await waitFor("document.querySelector('[data-target-status]').textContent.includes('markets checked')");
  // Reverse completions and a filter edit cannot resurrect an old result/map.
  await evaluate("window.targetApi=Lab.api;window.targetResolvers=[];Lab.api=(p,q)=>p==='/api/targets'?new Promise(r=>targetResolvers.push(r)):targetApi(p,q);document.querySelector('[data-target-form]').requestSubmit();document.querySelector('[data-target-form]').requestSubmit();true");
  const empty={request_id:5000,results:[],curves:[],stations_checked:0,ref:'Newest response',rate_note:'',note:''};
  await evaluate(`targetResolvers[1](${JSON.stringify(empty)});true`);
  await waitFor("document.querySelector('[data-target-status]').textContent.includes('Newest response')");
  await evaluate(`targetResolvers[0](${JSON.stringify({...empty,request_id:4999,ref:'Old response'})});true`);await sleep(100);
  assert.equal(await evaluate("document.querySelector('[data-target-status]').textContent.includes('Old response')"),false);
  await evaluate("Lab.api=targetApi;var f=document.querySelector('[data-target-form]');f.elements.ref.value='Zaonce';f.dispatchEvent(new Event('input'));f.requestSubmit();true");
  await waitFor("document.querySelector('[data-target-status]').textContent.includes('markets checked')");
  append([{event:'ShipyardSwap',timestamp:new Date().toISOString(),ShipType:'sidewinder'}]);
  await waitFor("document.querySelector('[data-target-status]').textContent.includes('changed') && document.querySelectorAll('[data-target-select]').length===0");
  assert.equal(await evaluate('Lab.map.layers.targets.points(Lab.state).length'),0);
  // External provider text never becomes executable markup.
  await evaluate(`Lab.api=async(p,q)=>p==='/api/targets'?({request_id:6000,results:[],curves:[],ref:'<img src=x onerror="window.targetInjected=true">',note:'<svg onload=alert(1)>',rate_note:'',stations_checked:0}):targetApi(p,q);document.querySelector('[data-target-form]').requestSubmit();true`);
  await waitFor("document.querySelector('[data-target-status]').textContent.includes('<img')");
  assert.equal(await evaluate("document.querySelectorAll('#card-targets img').length"),0);
  assert.equal(await evaluate('!!window.targetInjected'),false);
  const hostile='<img src=x onerror="window.targetInjected=true">';
  const row={system:hostile,station:hostile,dist:1,jumps:1,pad:'L',ls:1,age_hours:1,priced_goods:1,goods_count:1,estimated_sale:1,estimated_merits:1,merits_per_jump:1,goods:{test:{name:hostile,origin:hostile,price:1,tons:1,source_distance:1,status:'reported'}}};
  await evaluate(`Lab.api=async(p,q)=>p==='/api/targets'?(${JSON.stringify({...empty,request_id:6001,results:[row]})}):targetApi(p,q);document.querySelector('[data-target-form]').requestSubmit();true`);
  await waitFor("document.querySelector('.target-title')?.textContent.includes('<img')");
  await evaluate("document.querySelector('[data-target-select]').click();true");
  await waitFor("document.querySelector('[data-target-selection]').textContent.includes('<img')");
  assert.equal(await evaluate("document.querySelectorAll('#card-targets img').length"),0);
  assert.equal(await evaluate('!!window.targetInjected'),false);
  await evaluate('Lab.api=targetApi;true');
  await send('Page.reload');
  await waitFor("document.querySelector('[data-target-form] [name=rate_mode]')?.value==='mahon_observed'");
  assert.equal(await evaluate("document.querySelector('[data-target-form] [name=interpolate]').value"),process.env.ELITELAB_TARGETS_LIVE==='1'?'false':'true');
  assert.deepEqual(errors,[]);
  assert.doesNotMatch(serverLog,/Traceback|handler failed/);
  console.log('Targets real CLI/API/SSE: rankings, origin distances, optional curve, selected map target, empty/error/retry, stale responses, ship change, escaped text, persistence and responsive screenshots passed. Provider: '+(process.env.ELITELAB_TARGETS_LIVE==='1'?'live Spansh':'synthetic fixture')+'. Screenshots: '+outputDir);
  await send('Browser.close').catch(()=>{});
} finally {
  ws?.close();chrome?.kill();
  if(server && server.exitCode===null) {
    try{await fetch(base+'/api/shutdown',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',signal:AbortSignal.timeout(1000)});}catch{}
    for(let i=0;i<50&&server.exitCode===null;i++)await sleep(100);
    if(server.exitCode===null)server.kill();
  }
}
