/* Exercise the real CLI, journal watcher, API and SSE in Chrome. Node 22+. */
import {spawn} from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'elitelab-material-plan-browser-'));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const listener=http.createServer();
await new Promise(r=>listener.listen(0,'127.0.0.1',r));
const port=listener.address().port;
await new Promise(r=>listener.close(r));
const base=`http://127.0.0.1:${port}`;
const journals=path.join(temporary,'journals');fs.mkdirSync(journals);
const journal=path.join(journals,'Journal.20261022100000.01.log');
fs.copyFileSync(path.join(root,'tests/fixtures/material-plan/Journal.20261101100000.01.log'),journal);
const env={...process.env,ELITELAB_SETTINGS:path.join(temporary,'settings.json'),ELITELAB_HOST:'127.0.0.1',ELITELAB_PORT:String(port),
  ELITELAB_OFFLINE:'1',ELITELAB_JOURNAL_DIR:journals,ELITELAB_DATA_DIR:path.join(temporary,'data'),
  ELITELAB_INSTANCE_DIR:path.join(temporary,'instance'),ELITELAB_AUTH_TOKEN:''};
fs.mkdirSync(env.ELITELAB_DATA_DIR);fs.writeFileSync(path.join(env.ELITELAB_DATA_DIR,'engineering_wishlist.json'),JSON.stringify([{id:'old-plan',kind:'material',key:'tellurium',name:'Tellurium',qty:3,label:'Saved before this update'}]));
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

  await waitFor("!!document.querySelector('[data-workspace=materials]')");
  assert.equal(await evaluate("document.querySelector('[data-workspace=overview]').getAttribute('aria-pressed')"),'true');
  await evaluate("document.querySelector('[data-workspace=materials]').click();true");
  await waitFor("document.querySelector('[data-plan-preview]')?.textContent.includes('crafts available')");
  assert.equal(await evaluate("document.querySelector('#card-wishlist').classList.contains('workspace-off')"),false);
  const layoutBefore=await evaluate("localStorage.getItem('layout.v1')");
  await evaluate("document.querySelector('#wl-qty').value='4';document.querySelector('#wl-qty').dispatchEvent(new Event('input'));document.querySelector('[data-plan-form]').requestSubmit();true");
  await waitFor("Lab.state.wishlist.entries?.some(e=>e.kind==='synthesis'&&e.qty===4)");
  // SSE can publish the entry before the submit handler finishes its refresh.
  // Wait for the same enabled control a user needs before the next submission.
  await waitFor("!document.querySelector('#wl-add').disabled");
  await evaluate("document.querySelector('#wl-recipe').value='fsd_injection_standard';document.querySelector('#wl-recipe').dispatchEvent(new Event('change'));document.querySelector('#wl-qty').value='2';document.querySelector('#wl-qty').dispatchEvent(new Event('input'));document.querySelector('[data-plan-form]').requestSubmit();true");
  await waitFor("Lab.state.wishlist.entries?.filter(e=>e.kind==='synthesis').length===2");
  const plan=await (await fetch(base+'/api/wishlist')).json();
  assert.equal(plan.entries.filter(e=>e.kind==='synthesis')[1].craftable,0);
  assert.equal(plan.needs.find(r=>r.key==='germanium').need,6);
  assert.equal(plan.needs.find(r=>r.key==='germanium').short,3);
  // Composer and unsaved quantity edits survive journal/SSE changes.
  await evaluate("document.querySelector('#wl-qty').value='7';document.querySelector('#wl-qty').dispatchEvent(new Event('input'));var row=[...document.querySelectorAll('[data-plan-entry]')].find(e=>e.textContent.includes('FSD Injection'));row.querySelector('input').value='3';row.querySelector('input').focus();row.querySelector('details').open=true;true");
  append([{event:'MaterialCollected',timestamp:'2026-11-01T10:01:00Z',Name:'germanium',Category:'Raw',Count:2}]);
  await waitFor("Lab.state.wishlist.needs?.find(r=>r.key==='germanium')?.have===5");
  assert.equal(await evaluate("document.querySelector('#wl-qty').value"),'7');
  assert.equal(await evaluate("document.activeElement.value"),'3');
  assert.equal(await evaluate("document.activeElement.closest('[data-plan-entry]').querySelector('details').open"),true);
  await evaluate("document.activeElement.closest('[data-plan-entry]').querySelector('[data-plan-edit]').click();true");
  await waitFor("Lab.state.wishlist.entries?.some(e=>e.kind==='synthesis'&&e.qty===3)");
  await evaluate("document.querySelector('#wl-qty').value='2';document.querySelector('#wl-qty').dispatchEvent(new Event('input'));true");
  await waitFor("document.querySelector('[data-plan-preview]').textContent.includes('crafts available')");
  // Workspace switching is navigation, not a rewrite of custom layout.
  await evaluate("document.querySelector('[data-workspace=flight]').click();document.querySelector('[data-workspace=materials]').click();true");
  assert.equal(await evaluate("localStorage.getItem('layout.v1')"),layoutBefore);
  assert.equal(await evaluate("document.querySelector('#wl-qty').value"),'2');
  await send('Page.reload');
  await waitFor("document.querySelector('[data-plan-preview]')?.textContent.includes('crafts available')");
  assert.equal(await evaluate("document.querySelector('[data-workspace=materials]').getAttribute('aria-pressed')"),'true');
  assert.equal(await evaluate("document.querySelector('#wl-recipe').value"),'fsd_injection_standard');
  assert.equal(await evaluate("Lab.state.wishlist.entries.filter(e=>e.kind==='synthesis').length"),2);
  const outputDir=process.env.ELITELAB_SCREENSHOT_DIR||path.join(temporary,'screenshots');fs.mkdirSync(outputDir,{recursive:true});
  const capture=async(name,width,height,scroll=0)=>{await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<500});await sleep(200);await evaluate(`scrollTo(0,${scroll});true`);assert.ok(await evaluate('document.body.scrollWidth')<=width,'Horizontal page overflow');const shot=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(outputDir,name+'.png'),Buffer.from(shot.data,'base64'));};
  await capture('materials-plan-desktop',1440,1100);
  await capture('materials-plan-mobile',390,844);
  await capture('materials-plan-mobile-requirements',390,844,1450);
  await capture('materials-plan-requirements',1440,1100,850);
  await evaluate("document.querySelector('[data-workspace=overview]').click();true");
  await capture('workspace-overview-desktop',1440,1100);
  await capture('workspace-overview-mobile',390,844);
  await evaluate("document.querySelector('[data-workspace=materials]').click();true");
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});
  // Planning never creates journal evidence; a real journal event does.
  assert.equal((await (await fetch(base+'/api/synthesis/status')).json()).history.length,0);
  append([{event:'Synthesis',timestamp:'2026-11-01T10:02:00Z',Name:'FSD Basic',Materials:[{Name:'carbon',Count:1},{Name:'vanadium',Count:1},{Name:'germanium',Count:1}]}]);
  await waitFor("Lab.state.synthesis.summary?.boost.status==='injection_observed'");
  await evaluate("document.querySelector('[data-plan-tab=evidence]').click();scrollTo(0,0);true");
  assert.match(await evaluate("document.querySelector('[data-plan-evidence]').textContent"),/FSD Basic/);
  await capture('materials-fsd-evidence',1440,1100);
  await evaluate("document.querySelector('[data-plan-tab=inventory]').click();true");
  await waitFor("document.querySelector('[data-plan-inventory]').textContent.includes('Germanium')");
  await evaluate("document.querySelector('[data-plan-inventory-filter]').value='germanium';document.querySelector('[data-plan-inventory-filter]').dispatchEvent(new Event('input'));true");
  assert.equal(await evaluate("document.querySelectorAll('[data-plan-inventory] tbody tr').length"),1);
  await evaluate("document.querySelector('[data-plan-tab=plan]').click();document.querySelector('[data-plan-farms]').click();true");
  await waitFor("!document.querySelector('[data-plan-sources]').textContent.includes('Finding sources')");
  assert.ok((await evaluate("document.querySelector('[data-plan-sources]').textContent")).length>20);
  // Failed saves leave the plan intact and recover on retry.
  const count=await evaluate('Lab.state.wishlist.entries.length');
  await evaluate("window.realPlanPost=Lab.post;Lab.post=function(p,q){return p==='/api/wishlist/add'?Promise.reject(Error('Test save unavailable')):window.realPlanPost.call(this,p,q)};document.querySelector('[data-plan-form]').requestSubmit();true");
  await waitFor("document.querySelector('[data-plan-message]').textContent.includes('Test save unavailable')");
  assert.equal(await evaluate('Lab.state.wishlist.entries.length'),count);
  await evaluate("Lab.post=window.realPlanPost;document.querySelector('[data-plan-form]').requestSubmit();true");
  await waitFor(`Lab.state.wishlist.entries.length===${count+1}`);
  // A delayed preview must not overwrite a newer selection, including an inventory update.
  await evaluate("window.previewPost=Lab.post;window.previewResolvers=[];Lab.post=function(p,q){return p==='/api/wishlist/preview'?new Promise(r=>window.previewResolvers.push(r)):window.previewPost.call(this,p,q)};document.querySelector('[data-preview-refresh]').click();document.querySelector('[data-preview-refresh]').click();true");
  const preview=await (await fetch(base+'/api/wishlist/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:'synthesis',item:'fsd_injection_basic',qty:1})})).json();
  preview.entry.name='Latest preview';
  await evaluate(`window.previewResolvers.at(-1)(${JSON.stringify(preview)});true`);
  await waitFor("document.querySelector('[data-plan-preview]').textContent.includes('Latest preview')");
  preview.entry.name='Stale preview';
  await evaluate(`window.previewResolvers[0](${JSON.stringify(preview)});true`);await sleep(100);
  assert.ok(await evaluate("document.querySelector('[data-plan-preview]').textContent.includes('Latest preview')"));
  await evaluate("Lab.post=window.previewPost;true");
  // Hostile legacy labels stay text.
  await evaluate("Lab.post('/api/wishlist/add',{item:'iron',qty:1,label:'<img src=x onerror=window.planInjected=true>'})");
  await waitFor("document.querySelector('.wl-entries').textContent.includes('<img')");
  assert.equal(await evaluate("document.querySelectorAll('.material-plan img').length"),0);
  assert.equal(await evaluate('!!window.planInjected'),false);
  // An existing synthesis-only saved layout reveals the unified planner without losing other choices.
  await evaluate("localStorage.setItem('layout.v1',JSON.stringify({order:['synthesis','ship'],spans:{synthesis:8,ship:4},hidden:['wishlist','cargo'],collapsed:['ship'],locked:true}));localStorage.setItem('workspace.v1',JSON.stringify('all'));true");
  await send('Page.reload');
  await waitFor("!!document.querySelector('[data-plan-form]') && document.querySelector('#wl-recipe')?.value==='fsd_injection_standard'");
  assert.equal(await evaluate("!!document.querySelector('#card-synthesis')"),false);
  assert.equal(await evaluate("document.querySelector('#card-ship').classList.contains('collapsed')"),true);
  assert.equal(await evaluate("!!document.querySelector('#card-cargo')"),false);
  assert.deepEqual(errors,[]);
  assert.deepEqual(await evaluate("[...document.querySelectorAll('.render-error')].map(e=>e.textContent)"),[]);
  const applicationLog=serverLog.replace(/Traceback \(most recent call last\):(?:(?!Traceback)[\s\S])*?ConnectionAbortedError: \[WinError 10053\][^\n]*\n/g,'').replace(/-{20,}\r?\nException occurred during processing of request[\s\S]*?ConnectionAbortedError: \[WinError 10053\][^\n]*\n-{20,}/g,'');
  assert.doesNotMatch(applicationLog,/Traceback|handler failed/);
  console.log('Materials workflow: real CLI, shared allocation, persistence, quantities, live stock, dirty edits, sourcing, inventory, FSD evidence, workspace preservation, error/retry, escaping and responsive screenshots passed. Synthetic journals. '+outputDir);
  await send('Browser.close').catch(()=>{});
} finally {
  ws?.close();chrome?.kill();
  if(server && server.exitCode===null) {
    try{await fetch(base+'/api/shutdown',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',signal:AbortSignal.timeout(1000)});}catch{}
    for(let i=0;i<50&&server.exitCode===null;i++)await sleep(100);
    if(server.exitCode===null)server.kill();
  }
}
