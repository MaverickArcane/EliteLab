/* Real CLI, watcher, API, SSE and responsive Rhino UI. No external providers. */
import {spawn} from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';

const fetch=(url,options={})=>globalThis.fetch(url,{...options,headers:{Connection:'close',...options.headers}});
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'elitelab-rhino-browser-'));
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const listener=http.createServer(); await new Promise(resolve=>listener.listen(0,'127.0.0.1',resolve));
const port=listener.address().port; await new Promise(resolve=>listener.close(resolve));
const base=`http://127.0.0.1:${port}`, journals=path.join(temporary,'journals'); fs.mkdirSync(journals);
const journal=path.join(journals,'Journal.2026-11-15T120000.01.log');
const offset=Date.now()-Date.parse('2026-11-15T12:02:03Z');
const shifted=value=>new Date(Date.parse(value)+offset).toISOString();
const events=fs.readFileSync(path.join(root,'tests/fixtures/rhino/Journal.2026-11-15T120000.01.log'),'utf8').trim().split('\n').map(JSON.parse).map(e=>({...e,timestamp:shifted(e.timestamp)}));
for(const e of events){if(e.event==='Location')e.StarPos=[0,0,0];if(e.event==='Loadout')e.MaxJumpRange=40;}
fs.writeFileSync(journal,events.map(JSON.stringify).join('\n')+'\n');
const append=rows=>fs.appendFileSync(journal,rows.map(e=>JSON.stringify({timestamp:new Date().toISOString(),...e})).join('\n')+'\n');
const status={event:'Status',timestamp:new Date().toISOString(),Flags:(1<<21)|(1<<26),BodyName:'Shinrarta Dezhra AB 2 j',Latitude:35.950340,Longitude:-31.233133,PlanetRadius:5963896};
fs.writeFileSync(path.join(journals,'Status.json'),JSON.stringify(status));
const env={...process.env,ELITELAB_SETTINGS:path.join(temporary,'settings.json'),ELITELAB_HOST:'127.0.0.1',ELITELAB_PORT:String(port),
  ELITELAB_OFFLINE:'1',ELITELAB_JOURNAL_DIR:journals,ELITELAB_DATA_DIR:path.join(temporary,'data'),ELITELAB_INSTANCE_DIR:path.join(temporary,'instance'),ELITELAB_AUTH_TOKEN:''};
fs.mkdirSync(env.ELITELAB_DATA_DIR,{recursive:true});
fs.writeFileSync(path.join(env.ELITELAB_DATA_DIR,'rhino-coords.json'),JSON.stringify({'Wregoe GW-Y c28-2':{x:0,y:0,z:35}}));
const output=path.resolve(process.env.ELITELAB_SCREENSHOT_DIR||path.join(root,'artifacts/rhino')); fs.mkdirSync(output,{recursive:true});
let server,chrome,ws,serverLog='';
try {
  server=spawn(process.env.PYTHON||'python',['-u','-m','elitelab','serve','--no-browser'],{cwd:root,env,windowsHide:true});
  server.stdout.on('data',d=>serverLog+=d); server.stderr.on('data',d=>serverLog+=d);
  let ready=false;
  for(let i=0;i<200;i++){try{ready=(await(await fetch(base+'/api/health',{signal:AbortSignal.timeout(500)})).json()).ready;}catch{} if(ready)break; await sleep(100);}
  assert.ok(ready,serverLog);
  const profile=path.join(temporary,'chrome');
  chrome=spawn(process.env.CHROME_BIN||(process.platform==='win32'?'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe':'google-chrome'),
    ['--headless=new','--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'],{windowsHide:true,stdio:'ignore'});
  const debugFile=path.join(profile,'DevToolsActivePort');
  for(let i=0;i<200&&!fs.existsSync(debugFile);i++)await sleep(100);
  assert.ok(fs.existsSync(debugFile),'Chrome did not start');
  const debugPort=Number(fs.readFileSync(debugFile,'utf8').split('\n')[0]);
  const tabs=await(await fetch(`http://127.0.0.1:${debugPort}/json`)).json();
  ws=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  let sequence=0; const pending=new Map(),errors=[];
  ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(m.error):p.resolve(m.result);}else if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails);};
  const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence,timer=setTimeout(()=>reject(new Error('CDP timeout '+method)),10000);pending.set(id,{resolve:r=>{clearTimeout(timer);resolve(r);},reject:e=>{clearTimeout(timer);reject(e);}});ws.send(JSON.stringify({id,method,params}));});
  const evaluate=async expression=>{const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(JSON.stringify(r.exceptionDetails));return r.result.value;};
  const wait=async expression=>{for(let i=0;i<200;i++){if(await evaluate(expression))return;await sleep(100);}assert.fail('Timed out: '+expression+'\n'+serverLog+'\n'+await evaluate("document.body.innerText.slice(-3000)"));};
  const click=selector=>evaluate(`document.querySelector(${JSON.stringify(selector)}).click();true`);
  const shot=async(name,width=1440,height=1100)=>{
    await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<500});
    await evaluate("window.scrollTo(0,window.scrollY+document.querySelector('#card-rhino').getBoundingClientRect().top-125);true"); await sleep(200);
    assert.ok(await evaluate('document.body.scrollWidth')<=width,'Horizontal overflow: '+name);
    const r=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(output,name+'.png'),Buffer.from(r.data,'base64'));
  };
  await send('Runtime.enable');await send('Page.enable');await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url:base});await wait("typeof Lab!=='undefined'&&!!Lab.state.rhino");
  await click('[data-workspace=mining]'); await wait("!!document.querySelector('[data-rhino-site-list]')");
  assert.equal(await evaluate("document.querySelector('#card-rhino').classList.contains('workspace-off')"),false);
  assert.equal(await evaluate("document.querySelector('#card-materials').classList.contains('workspace-off')"),false);
  assert.equal(await evaluate("document.querySelector('#mat-view').value"),'gained');
  await wait("document.querySelector('.mat-list').textContent.includes('Iron')");
  assert.match(await evaluate("document.querySelector('.mat-session').textContent"),/Gained this session: \+3/);
  assert.equal(await evaluate("document.querySelector('[data-rhino-site-form]').hidden"),true);
  assert.equal(await evaluate("document.querySelectorAll('[data-rhino-rigs],[data-rhino-metrics],[data-rhino-cargo]').length"),0);
  assert.equal(await evaluate("document.querySelector('[data-rhino-tab=mining]').getAttribute('aria-selected')"),'true');
  assert.match(await evaluate("document.querySelector('[data-rhino-haul]').textContent"),/Tritium\s+2 t/);
  assert.match(await evaluate("document.querySelector('[data-rhino-holds]').textContent"),/Ship hold\s*103 t\s*\/\s*1,136 t/);
  // Unloading while still driving must update the ship through API/SSE/rendering.
  append([{event:'Cargo',Vessel:'SRV',Count:68},{event:'CargoTransfer',Transfers:[{Type:'tritium',Count:68,Direction:'toship'}]}]);
  await wait('Lab.state.rhino.summary.cargo.ship.count===171');
  await wait("document.querySelector('[data-rhino-holds]').textContent.includes('171 t')");
  assert.equal(await evaluate('Lab.state.rhino.summary.cargo.rhino.count'),0);
  assert.equal(await evaluate('Lab.state.rhino.summary.cargo.ship.free'),965);
  append([{event:'Cargo',Vessel:'Ship',Count:171}]);
  await wait('Lab.state.rhino.summary.cargo.ship.observed_at!==null');
  await click('[data-rhino-tab=spots]');
  await wait("document.querySelector('[data-rhino-travel=wregoe-iridium-31]').textContent.includes('35 Ly')");
  assert.match(await evaluate("document.querySelector('[data-rhino-travel=wregoe-iridium-31]').textContent"),/est\. 1\+ jump/);
  await click('[data-rhino-select=wregoe-iridium-31]');
  await wait("document.querySelector('[data-rhino-navigation]').textContent.includes('Jump to Wregoe GW-Y c28-2')");
  await click('[data-rhino-tab=mining]');
  await shot('rhino-travel-desktop');await shot('rhino-travel-mobile',390,1200);
  await click('[data-rhino-tab=spots]');
  assert.equal(await evaluate("document.querySelectorAll('[data-rhino-group=confirmed] .rhino-site').length"),2);
  assert.equal(await evaluate("document.querySelectorAll('[data-rhino-group=unconfirmed] .rhino-site').length"),6);
  assert.match(await evaluate("document.querySelector('[data-rhino-group=confirmed]').textContent"),/6 rigs observed/);
  assert.match(await evaluate("document.querySelector('[data-rhino-group=confirmed]').textContent"),/Reported depleted/);
  const leads=await(await fetch(base+'/api/rhino/sites?verification=unconfirmed&commodity=Tritium')).json();
  assert.deepEqual(leads.sites.map(s=>s.id),['hip63920-tritium']);
  assert.equal(await evaluate("document.querySelector('[data-site-notes=hip63920-tritium] a').href"),leads.sites[0].sources[0].url);
  await click('[data-rhino-select="shinrarta-tritium"]');
  await wait("Lab.state.rhino.summary.selected_site?.id==='shinrarta-tritium'");
  assert.match(await evaluate("document.querySelector('[data-rhino-navigation]').textContent"),/144 m/);
  await click('[data-rhino-tab=mining]');
  await shot('rhino-mining-desktop'); await shot('rhino-mining-mobile',390,1050);
  append([{event:'MiningRefined',Type:'tritium',Type_Localised:'Tritium'},{event:'Cargo',Vessel:'SRV',Count:68},{event:'Cargo',Vessel:'Ship',Count:103}]);
  await wait('Lab.state.rhino.summary.session.total_t===4');
  await wait("document.querySelector('[data-rhino-help]').textContent.includes('Make room')");
  assert.match(await evaluate("document.querySelector('[data-rhino-holds]').textContent"),/4 t free/);
  append([{event:'CargoTransfer',Transfers:[{Type:'tritium',Count:68,Direction:'toship'}]},{event:'Cargo',Vessel:'SRV',Count:0},{event:'Cargo',Vessel:'Ship',Count:171}]);
  await wait('Lab.state.rhino.summary.cargo.rhino.count===0');
  assert.equal(await evaluate('Lab.state.rhino.summary.session.total_t'),4);
  await click('[data-rhino-tab=spots]');
  await shot('rhino-spots-desktop'); await shot('rhino-spots-mobile',390,1200);
  // Confirm directly from a closed location card; no form or extra prompt.
  assert.equal(await evaluate("document.querySelector('[data-site-notes=hip39418-a11]').open"),false);
  await evaluate("window.rhinoOriginalPost=Lab.post;Lab.post=(url,...args)=>url==='/api/rhino/sites/confirm'?Promise.reject(new Error('Report temporarily unavailable')):window.rhinoOriginalPost(url,...args);true");
  await click('[data-rhino-confirm=hip39418-a11]');
  await wait("document.querySelector('[data-rhino-message]').textContent.includes('Report temporarily unavailable')");
  assert.equal(await evaluate("document.querySelectorAll('[data-rhino-group=confirmed] .rhino-site').length"),2);
  await evaluate('Lab.post=window.rhinoOriginalPost;true');
  await click('[data-rhino-confirm=hip39418-a11]');
  await wait("document.querySelectorAll('[data-rhino-group=confirmed] .rhino-site').length===3");
  assert.equal(await evaluate("document.querySelector('[data-rhino-report-form]').hidden"),true);
  assert.equal(await evaluate("Lab.state.rhino.summary.sites.find(s=>s.id==='hip39418-a11').rigs_estimated"),5);
  assert.match(await evaluate("Lab.state.rhino.summary.sites.find(s=>s.id==='hip39418-a11').evidence"),/Commander confirmed an on-site visit/);
  await click('[data-site-notes=hip39418-a11] summary'); await click('[data-rhino-report=hip39418-a11]');
  await evaluate("const f=document.querySelector('[data-rhino-report-form]');f.elements.verification.value='unconfirmed';f.elements.availability.value='reported_depleted';f.elements.evidence.value='Fixture visit: found monazite, then depleted. <img src=x onerror=alert(1)>'.padEnd(1196,'x')+'TAIL';true");
  append([{event:'MiningRefined',Type:'water'}]);await wait('Lab.state.rhino.summary.session.total_t===5');
  assert.match(await evaluate("document.querySelector('[data-rhino-report-form]').elements.evidence.value"),/Fixture visit/);
  await evaluate("document.querySelector('[data-rhino-report-form]').requestSubmit();true");
  await wait("document.querySelector('[data-rhino-report-form]').hidden");
  await wait("document.querySelectorAll('[data-rhino-group=confirmed] .rhino-site').length===2");
  await click('[data-rhino-confirm=hip39418-a11]');
  await wait("document.querySelectorAll('[data-rhino-group=confirmed] .rhino-site').length===3");
  assert.equal(await evaluate("Lab.state.rhino.summary.sites.find(s=>s.id==='hip39418-a11').availability"),'reported_depleted');
  assert.match(await evaluate("Lab.state.rhino.summary.sites.find(s=>s.id==='hip39418-a11').evidence"),/Fixture visit: found monazite/);
  assert.equal(await evaluate("Lab.state.rhino.summary.sites.find(s=>s.id==='hip39418-a11').evidence.length"),1200);
  assert.equal(await evaluate("Lab.state.rhino.summary.sites.find(s=>s.id==='hip39418-a11').evidence.endsWith('TAIL')"),true);
  assert.equal(await evaluate("document.querySelectorAll('.rhino-site img').length"),0);
  assert.equal(await evaluate("Lab.state.rhino.summary.selected_site.id"),'shinrarta-tritium');
  await click('[data-rhino-new]'); await click('[data-rhino-capture]');
  assert.equal(await evaluate("document.querySelector('[name=latitude]').value"),'35.95034');
  await evaluate("document.querySelector('[name=name]').value='My tritium route';document.querySelector('[name=notes]').value='Keep this draft through telemetry';true");
  append([{event:'MaterialCollected',Category:'Raw',Name:'nickel',Count:2}]);
  fs.writeFileSync(path.join(journals,'Status.json'),JSON.stringify({...status,timestamp:new Date().toISOString(),Latitude:35.9504}));
  await wait('Lab.state.rhino.summary.position.latitude===35.9504');
  await wait("document.querySelector('.mat-session').textContent.includes('Gained this session: +5')");
  assert.equal(await evaluate("document.querySelector('[name=notes]').value"),'Keep this draft through telemetry');
  await evaluate("document.querySelector('[data-rhino-site-form]').requestSubmit();true");
  await wait("Lab.state.rhino.summary.selected_site?.name==='My tritium route'");
  const id=await evaluate('Lab.state.rhino.summary.selected_site.id');
  await wait("document.querySelector('[data-rhino-site-form]').hidden");
  await send('Page.reload');await wait(`typeof Lab!=='undefined'&&Lab.state?.rhino?.summary?.selected_site?.id===${JSON.stringify(id)}`);
  await wait("!!document.querySelector('[data-rhino-site-list]')");
  assert.equal(await evaluate("Lab.state.rhino.summary.sites.find(s=>s.id==='hip39418-a11').availability"),'reported_depleted');
  await click('[data-rhino-tab=spots]');
  await click(`[data-site-notes="${id}"] summary`); await click(`[data-rhino-edit="${id}"]`);
  await evaluate("document.querySelector('[name=notes]').value='<img src=x onerror=alert(1)>';document.querySelector('[data-rhino-site-form]').requestSubmit();true");
  await wait("Lab.state.rhino.summary.selected_site?.notes.includes('<img')");
  assert.equal(await evaluate("document.querySelectorAll('.rhino-site img').length"),0);
  await evaluate("window.rhinoOriginalApi=Lab.api;Lab.api=(url,...args)=>url.startsWith('/api/rhino/guide')?Promise.reject(new Error('Guide temporarily unavailable')):window.rhinoOriginalApi(url,...args);true");
  await click('[data-rhino-tab=guide]'); await wait("!!document.querySelector('[data-rhino-retry]')");
  await evaluate('Lab.api=window.rhinoOriginalApi;true');await click('[data-rhino-retry]');
  await wait("document.querySelectorAll('[data-rhino-topic]').length===10");
  const guide=await(await fetch(base+'/api/rhino/guide?topic=unloading')).json();
  assert.ok(await evaluate(`document.querySelector('[data-rhino-topic=unloading]').textContent.includes(${JSON.stringify(guide.sections[0].steps[2])})`));
  assert.match(await evaluate("document.querySelector('[data-rhino-topic=troubleshooting]').textContent"),/reroll recommendation is disputed/);
  await click('[data-rhino-topic=overview] > summary'); await click('[data-rhino-topic=unloading] > summary');
  await shot('rhino-guide-desktop');await shot('rhino-guide-mobile',390,1050);
  await click('[data-rhino-tab=mining]');await click('[data-rhino-help-topic=placement]');
  assert.equal(await evaluate("document.querySelector('[data-rhino-topic=placement]').open"),true);
  assert.equal(await evaluate("document.querySelector('[data-rhino-tab=guide]').getAttribute('aria-selected')"),'true');
  // Client freshness also expires without waiting for a new journal event.
  await evaluate("window.rhinoNow=Date.now;Date.now=()=>window.rhinoNow()+121000;Lab.emit('rhino');true");
  await click('[data-rhino-tab=mining]');
  await wait("document.querySelector('[data-rhino-navigation]').textContent.includes('Waiting for a recent')");
  await evaluate('Date.now=window.rhinoNow;true');
  // Successful boarding transfers cargo automatically, with no CargoTransfer
  // or empty SRV Cargo event. The bearing still works in the main ship.
  append([{event:'LaunchSRV',SRVType:'mev_rhino',ID:66},{event:'Cargo',Vessel:'Ship',Count:0},
    ...Array.from({length:62},()=>({event:'MiningRefined',Type:'iridium'})),
    {event:'Cargo',Vessel:'SRV',Count:62},{event:'DockSRV',SRVType:'mev_rhino',ID:66},
    {event:'Loadout',Ship:'panthermkii',ShipID:10,CargoCapacity:1136,Modules:[{Item:'int_detailedsurfacescanner_tiny'},{Item:'int_mkiilargebuggybay_size2_class3'}]},
    {event:'Cargo',Vessel:'Ship',Count:62}]);
  const dockingStatus={...status,Latitude:status.Latitude+.001,timestamp:new Date().toISOString(),Flags:(1<<21)|(1<<24)};
  fs.writeFileSync(path.join(journals,'Status.json'),JSON.stringify(dockingStatus));
  await wait('Lab.state.rhino.summary.session.end_reason===\'DockSRV\'&&Lab.state.rhino.summary.cargo.ship.count===62');
  await wait("document.querySelector('[data-rhino-holds]').textContent.includes('1,074 t free')");
  assert.equal(await evaluate('Lab.state.rhino.summary.cargo.rhino.count'),0);
  assert.equal(await evaluate('Lab.state.rhino.summary.session.unloaded_t'),62);
  assert.equal(await evaluate('Lab.state.rhino.summary.session.total_t'),62);
  await wait('Lab.state.rhino.summary.navigation.bearing!==null');
  assert.match(await evaluate("document.querySelector('[data-rhino-navigation]').textContent"),/Heading/);
  await shot('rhino-docked-desktop');await shot('rhino-docked-mobile',390,1200);
  // An open form belongs to the commander who opened it, even across logins.
  await click('[data-rhino-tab=spots]');
  await click('[data-rhino-report=hip39418-a11]');
  await evaluate("document.querySelector('[data-rhino-report-form]').elements.evidence.value='First commander draft';true");
  append([{event:'Commander',Name:'Other Test',FID:'F-OTHER'}]);
  await wait("Lab.state.rhino.summary.commander_key==='fid:F-OTHER'");
  await evaluate("document.querySelector('[data-rhino-report-form]').requestSubmit();true");
  await wait("document.querySelector('[data-rhino-message]').textContent.includes('Commander changed')");
  assert.equal(await evaluate("Lab.state.rhino.summary.sites.find(s=>s.id==='hip39418-a11').verification"),'unconfirmed');
  await click('[data-rhino-new]');
  await evaluate("const f=document.querySelector('[data-rhino-site-form]');for(const [key,value] of Object.entries({name:'Old draft',system:'A',body:'A 1',latitude:1,longitude:2}))f.elements[key].value=value;true");
  append([{event:'Commander',Name:'Rhino Test',FID:'F-RHINO'}]);
  await wait("Lab.state.rhino.summary.commander_key==='fid:F-RHINO'");
  await evaluate("document.querySelector('[data-rhino-message]').textContent='';true");
  await evaluate("document.querySelector('[data-rhino-site-form]').requestSubmit();true");
  await wait("document.querySelector('[data-rhino-message]').textContent.includes('Commander changed')");
  assert.equal(await evaluate("Lab.state.rhino.summary.sites.some(s=>s.name==='Old draft')"),false);
  assert.deepEqual(await evaluate("[...document.querySelectorAll('.render-error')].map(e=>e.textContent)"),[]);
  assert.deepEqual(errors,[]);assert.doesNotMatch(serverLog,/Traceback|handler failed/);
  console.log('Rhino browser passed: confirmed/unconfirmed catalog, sources, report/persistence, live collection/holds, transfer continuity, contextual help, navigation, save/edit, stable drafts, escaping, Materials gains, guide/retry/shortcuts, stale position and desktop/mobile. Screenshots: '+output);
  await send('Browser.close').catch(()=>{});
} finally {
  ws?.close();chrome?.kill();
  if(server&&server.exitCode===null){try{await fetch(base+'/api/shutdown',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',signal:AbortSignal.timeout(1000)});}catch{} for(let i=0;i<50&&server.exitCode===null;i++)await sleep(100);if(server.exitCode===null)server.kill();}
}
