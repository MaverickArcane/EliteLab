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
fs.writeFileSync(journal,events.map(JSON.stringify).join('\n')+'\n');
const append=rows=>fs.appendFileSync(journal,rows.map(e=>JSON.stringify({timestamp:new Date().toISOString(),...e})).join('\n')+'\n');
const status={event:'Status',timestamp:new Date().toISOString(),Flags:(1<<21)|(1<<26),BodyName:'Shinrarta Dezhra AB 2 j',Latitude:35.950340,Longitude:-31.233133,PlanetRadius:5963896};
fs.writeFileSync(path.join(journals,'Status.json'),JSON.stringify(status));
const env={...process.env,ELITELAB_SETTINGS:path.join(temporary,'settings.json'),ELITELAB_HOST:'127.0.0.1',ELITELAB_PORT:String(port),
  ELITELAB_OFFLINE:'1',ELITELAB_JOURNAL_DIR:journals,ELITELAB_DATA_DIR:path.join(temporary,'data'),ELITELAB_INSTANCE_DIR:path.join(temporary,'instance'),ELITELAB_AUTH_TOKEN:''};
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
    await evaluate("document.querySelector('#card-rhino').scrollIntoView({block:'start'});true"); await sleep(200);
    assert.ok(await evaluate('document.body.scrollWidth')<=width,'Horizontal overflow: '+name);
    const r=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(output,name+'.png'),Buffer.from(r.data,'base64'));
  };
  await send('Runtime.enable');await send('Page.enable');await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url:base});await wait("typeof Lab!=='undefined'&&!!Lab.state.rhino");
  await click('[data-workspace=mining]'); await wait("!!document.querySelector('[data-rhino-destination]')");
  assert.equal(await evaluate("document.querySelector('#card-rhino').classList.contains('workspace-off')"),false);
  assert.match(await evaluate("document.querySelector('[data-rhino-metrics]').textContent"),/3 t/);
  await evaluate("var select=document.querySelector('[data-rhino-destination]');select.value='shinrarta-tritium';select.dispatchEvent(new Event('change',{bubbles:true}));true");
  await wait("Lab.state.rhino.summary.selected_site?.id==='shinrarta-tritium'");
  assert.match(await evaluate("document.querySelector('[data-rhino-navigation]').textContent"),/144 m/);
  await evaluate("document.querySelector('[data-rhino-rigs]').requestSubmit();true");await wait('Lab.state.rhino.summary.rigs.count===3');
  await shot('rhino-mining-desktop'); await shot('rhino-mining-mobile',390,1050);
  await click('[data-rhino-tab=sites]'); await click('[data-rhino-capture]');
  assert.equal(await evaluate("document.querySelector('[name=latitude]').value"),'35.95034');
  await evaluate("document.querySelector('[name=name]').value='My tritium route';document.querySelector('[name=notes]').value='Keep this draft through telemetry';true");
  append([{event:'MiningRefined',Type:'$tritium_name;',Type_Localised:'Tritium'}]);
  await wait('Lab.state.rhino.summary.session.refined_tons===4');
  assert.equal(await evaluate("document.querySelector('[name=notes]').value"),'Keep this draft through telemetry');
  await evaluate("document.querySelector('[data-rhino-site-form]').requestSubmit();true");
  await wait("Lab.state.rhino.summary.selected_site?.name==='My tritium route'");
  const id=await evaluate('Lab.state.rhino.summary.selected_site.id');
  await shot('rhino-sites-desktop');await shot('rhino-sites-mobile',390,1050);
  await send('Page.reload');await wait(`typeof Lab!=='undefined'&&Lab.state?.rhino?.summary?.selected_site?.id===${JSON.stringify(id)}`);
  await click('[data-rhino-tab=sites]'); await click(`[data-rhino-edit="${id}"]`);
  await evaluate("document.querySelector('[name=notes]').value='<img src=x onerror=alert(1)>';document.querySelector('[data-rhino-site-form]').requestSubmit();true");
  await wait("Lab.state.rhino.summary.selected_site?.notes.includes('<img')");
  assert.equal(await evaluate("document.querySelectorAll('.rhino-site img').length"),0);
  append([{event:'Cargo',Vessel:'SRV',Count:72},{event:'CargoTransfer',timestamp:new Date(Date.now()+1000).toISOString(),Transfers:[{Type:'tritium',Count:72,Direction:'toship'}]}]);
  await wait('Lab.state.rhino.summary.session.unloads===2');
  assert.equal(await evaluate('Lab.state.rhino.summary.session.refined_tons'),4);
  assert.equal(await evaluate('Lab.state.rhino.summary.session.active'),true);
  await click('[data-rhino-tab=mine]');assert.match(await evaluate("document.querySelector('[data-rhino-cargo]').textContent"),/175 t/);
  append([{event:'DockSRV',SRVType:'mev_rhino'}]);await wait('Lab.state.rhino.summary.session.active===false');
  await wait("document.querySelector('[data-rhino-rigs] button').disabled");
  await click('[data-rhino-tab=guide]');assert.match(await evaluate("document.querySelector('#rhino-guide').textContent"),/Stay|staying in the Rhino/);
  assert.deepEqual(await evaluate("[...document.querySelectorAll('.render-error')].map(e=>e.textContent)"),[]);
  assert.deepEqual(errors,[]);assert.doesNotMatch(serverLog,/Traceback|handler failed/);
  console.log('Rhino browser passed: navigation, manual rig count, local save/edit/reload, draft preservation, escaping, separate cargo, unload without ending deployment, boarding and desktop/mobile. Screenshots: '+output);
  await send('Browser.close').catch(()=>{});
} finally {
  ws?.close();chrome?.kill();
  if(server&&server.exitCode===null){try{await fetch(base+'/api/shutdown',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',signal:AbortSignal.timeout(1000)});}catch{} for(let i=0;i<50&&server.exitCode===null;i++)await sleep(100);if(server.exitCode===null)server.kill();}
}
