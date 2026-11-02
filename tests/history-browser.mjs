/* Exercise the real CLI, journal watcher, API and SSE in Chrome. Node 22+. */
import {spawn} from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'elitelab-history-browser-'));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const listener=http.createServer();
await new Promise(r=>listener.listen(0,'127.0.0.1',r));
const port=listener.address().port;
await new Promise(r=>listener.close(r));
const base=`http://127.0.0.1:${port}`;
const journals=path.join(temporary,'journals');fs.mkdirSync(journals);
const journal=path.join(journals,'Journal.20261022100000.01.log');
fs.copyFileSync(path.join(root,'tests/fixtures/history/Journal.2026-10-01T100000.01.log'),journal);
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
  const waitFor=async expression=>{for(let i=0;i<450;i++){if(await evaluate(expression))return;await sleep(100);}assert.fail('Timed out: '+expression+'\n'+JSON.stringify(await evaluate("({map:document.querySelector('#card-map')?.textContent,history:Lab.state.history,errors:[...document.querySelectorAll('.render-error')].map(e=>e.textContent)})"))+'\n'+serverLog);};
  await send('Runtime.enable');await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url:base});

  await waitFor("!!document.querySelector('#card-history [data-history-results]')");
  await evaluate("[...document.querySelectorAll('#layout-menu input[data-id]')].filter(c=>c.checked&&c.dataset.id!=='history').map(c=>c.dataset.id).forEach(id=>document.querySelector('#layout-menu input[data-id='+id+']').click());true");
  await evaluate("var f=document.querySelector('#card-history form');f.elements.days.value='0';f.requestSubmit();true");
  await waitFor("document.querySelector('[data-history-merits]')?.textContent==='7,500'");
  assert.match(await evaluate("document.querySelector('#card-history').textContent"),/28,700,000 Cr/);
  assert.equal(await evaluate("document.querySelectorAll('.history-chart circle').length"),5);
  const first=await (await fetch(base+'/api/history/analytics?days=0')).json();
  assert.equal(first.index.files_read,0,'Warm cache must not reread journals');
  assert.equal(first.totals.material.amount,21);
  const outputDir=process.env.ELITELAB_SCREENSHOT_DIR||path.join(temporary,'screenshots');fs.mkdirSync(outputDir,{recursive:true});
  for(const [name,width,height] of [['desktop',1440,1100],['mobile',390,844]]) {
    await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<500});await sleep(200);
    await evaluate("scrollTo(0,0);true");
    assert.ok(await evaluate('document.body.scrollWidth')<=width,'Horizontal page overflow');
    const shot=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(outputDir,`history-${name}.png`),Buffer.from(shot.data,'base64'));
  }
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});
  // Unsaved edits survive live updates; submitting applies and saves them.
  await evaluate("var f=document.querySelector('#card-history form');f.elements.material.value='iron';f.elements.material.dispatchEvent(new Event('input',{bubbles:true}));true");
  append([{event:'PowerplayMerits',timestamp:'2026-10-30T11:00:00Z',Power:'Edmund Mahon',MeritsGained:50,TotalMerits:4000}]);
  await sleep(1000);
  assert.match(await evaluate("document.querySelector('[data-history-status]').textContent"),/Filters changed/);
  await evaluate("document.querySelector('#card-history form').requestSubmit();true");
  await waitFor("document.querySelector('[data-history-merits]')?.textContent==='7,550'");
  assert.doesNotMatch(await evaluate("document.querySelector('.history-columns').textContent"),/Chemical Manipulators/);
  await send('Page.reload');
  await waitFor("document.querySelector('[data-history-merits]')?.textContent==='7,550'");
  assert.equal(await evaluate("document.querySelector('#card-history [name=material]').value"),'iron');
  // Rebuild is a cache operation, and reconstructs exactly the same totals.
  await evaluate("document.querySelector('[data-history-rebuild]').click();true");
  await waitFor("document.querySelector('[data-history-merits]')?.textContent==='7,550'");
  assert.equal(fs.readdirSync(env.ELITELAB_DATA_DIR).filter(n=>n.startsWith('history.sqlite3.backup-')).length,1);
  // Commander switch and hostile material text are real journal events.
  const hostile='<img src=x onerror="window.historyInjected=true">';
  append([{event:'LoadGame',timestamp:'2026-10-30T12:00:00Z',Commander:'Second Explorer',FID:'F-SECOND',Credits:500},
    {event:'MaterialCollected',timestamp:'2026-10-30T12:00:01Z',Name:'iron',Name_Localised:hostile,Category:'Raw',Count:2}]);
  await waitFor("document.querySelector('#card-history').textContent.includes('500 Cr')");
  assert.equal(await evaluate("document.querySelectorAll('#card-history img').length"),0);
  assert.equal(await evaluate('!!window.historyInjected'),false);
  assert.ok(await evaluate("document.querySelector('#card-history').textContent.includes('<img')"));
  assert.equal(await evaluate("document.querySelector('[data-history-merits]').textContent"),'0');
  await evaluate("var f=document.querySelector('#card-history form');f.elements.commander.value='fid:F-HISTORY';f.requestSubmit();true");
  await waitFor("document.querySelector('[data-history-merits]')?.textContent==='7,550'");
  assert.equal(await evaluate("Lab.state.history.selected_commander"),'fid:F-HISTORY');
  // Error clears old data; refresh retries. Late responses cannot overwrite newer ones.
  await evaluate("window.historyApi=Lab.api;Lab.api=(p,q)=>p==='/api/history/analytics'?Promise.reject(new Error('Test history unavailable')):window.historyApi(p,q);document.querySelector('#card-history form').requestSubmit();true");
  await waitFor("document.querySelector('[data-history-status]').textContent.includes('Test history unavailable')");
  assert.equal(await evaluate("document.querySelector('[data-history-results]').textContent"),'');
  await evaluate("Lab.api=window.historyApi;document.querySelector('#card-history form').requestSubmit();true");
  await waitFor("document.querySelector('[data-history-merits]')?.textContent==='7,550'");
  await evaluate("window.historyResolvers=[];Lab.api=(p,q)=>p==='/api/history/analytics'?new Promise(r=>window.historyResolvers.push(r)):window.historyApi(p,q);document.querySelector('#card-history form').requestSubmit();document.querySelector('#card-history form').requestSubmit();true");
  const response=await (await fetch(base+'/api/history/analytics?days=0&commander=fid%3AF-HISTORY')).json();
  await evaluate(`window.historyResolvers[1](${JSON.stringify(response)});true`);
  await waitFor("document.querySelector('[data-history-merits]')?.textContent==='7,550'");
  response.totals.merits.amount=99999;
  await evaluate(`window.historyResolvers[0](${JSON.stringify(response)});true`);await sleep(100);
  assert.equal(await evaluate("document.querySelector('[data-history-merits]').textContent"),'7,550');
  await evaluate("Lab.api=window.historyApi;document.querySelector('#layout-menu input[data-id=map]').click();true");
  await waitFor("document.querySelector('#card-map .map-stats')?.textContent.includes('2 systems')");
  await evaluate("document.querySelector('#layout-menu input[data-id=map]').click();document.querySelector('#layout-menu input[data-id=map]').click();true");
  await waitFor("document.querySelector('#card-map .map-stats')?.textContent.includes('2 systems')");
  assert.deepEqual(errors,[]);
  assert.deepEqual(await evaluate("[...document.querySelectorAll('.render-error')].map(e=>e.textContent)"),[]);
  // Chrome reload can abort an idle Windows keep-alive socket before request parsing.
  const applicationLog=serverLog.replace(/-{20,}\r?\nException occurred during processing of request[\s\S]*?ConnectionAbortedError: \[WinError 10053\][^\n]*\n-{20,}/g,'');
  assert.doesNotMatch(applicationLog,/Traceback|handler failed/);
  console.log('History real CLI, SQLite, journal/SSE, credits, cycles, collection locations, identities, rebuild, saved filters, dirty edits, errors/retry, response ordering and desktop/mobile checks passed. Synthetic journals. Screenshots: '+outputDir);
  await send('Browser.close').catch(()=>{});
} finally {
  ws?.close();chrome?.kill();
  if(server && server.exitCode===null) {
    try{await fetch(base+'/api/shutdown',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',signal:AbortSignal.timeout(1000)});}catch{}
    for(let i=0;i<50&&server.exitCode===null;i++)await sleep(100);
    if(server.exitCode===null)server.kill();
  }
}
