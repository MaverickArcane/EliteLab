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
  // Optional documentation frames capture the same fixture-driven UI under test.
  const frames={};
  const record=async(name,tab)=>{
    if(!process.env.ELITELAB_GIF_FRAMES)return;
    if(tab)await evaluate(`document.querySelector('[data-plan-tab=${tab}]').click();true`);
    await send('Emulation.setDeviceMetricsOverride',{width:1280,height:900,deviceScaleFactor:1,mobile:false});
    await evaluate('scrollTo(0,0);true');await sleep(350);
    const dir=path.join(process.env.ELITELAB_GIF_FRAMES,name);fs.mkdirSync(dir,{recursive:true});
    const shot=await send('Page.captureScreenshot',{format:'png'});
    fs.writeFileSync(path.join(dir,String(frames[name]=(frames[name]||0)+1).padStart(2,'0')+'.png'),Buffer.from(shot.data,'base64'));
  };
  await send('Runtime.enable');await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url:base});

  await waitFor("!!document.querySelector('[data-workspace=materials]')");
  assert.equal(await evaluate("document.querySelector('[data-workspace=overview]').getAttribute('aria-pressed')"),'true');
  await evaluate("document.querySelector('[data-workspace=materials]').click();true");
  await waitFor("document.querySelector('[data-plan-preview]')?.textContent.includes('crafts available')");
  assert.equal(await evaluate("document.querySelector('#card-wishlist').classList.contains('workspace-off')"),false);
  const layoutBefore=await evaluate("localStorage.getItem('layout.v1')");
  await record('materials-recipes','add');
  await evaluate("document.querySelector('#wl-qty').value='4';document.querySelector('#wl-qty').dispatchEvent(new Event('input'));document.querySelector('[data-plan-form]').requestSubmit();true");
  await waitFor("Lab.state.wishlist.entries?.some(e=>e.kind==='synthesis'&&e.qty===4)");
  // SSE can publish the entry before the submit handler finishes its refresh.
  // Wait for the same enabled control a user needs before the next submission.
  await waitFor("!document.querySelector('#wl-add').disabled");
  await evaluate("document.querySelector('#wl-recipe').value='fsd_injection_standard';document.querySelector('#wl-recipe').dispatchEvent(new Event('change'));document.querySelector('#wl-qty').value='2';document.querySelector('#wl-qty').dispatchEvent(new Event('input'));document.querySelector('[data-plan-form]').requestSubmit();true");
  await waitFor("Lab.state.wishlist.entries?.filter(e=>e.kind==='synthesis').length===2");
  await record('materials-recipes','add');await record('materials-recipes','plan');await record('materials-recipes','requirements');
  const plan=await (await fetch(base+'/api/wishlist')).json();
  assert.equal(plan.entries.filter(e=>e.kind==='synthesis')[1].craftable,0);
  assert.equal(plan.needs.find(r=>r.key==='germanium').need,6);
  assert.equal(plan.needs.find(r=>r.key==='germanium').short,3);
  await record('materials-progress','requirements');
  // Composer and unsaved quantity edits survive journal/SSE changes.
  await evaluate("document.querySelector('[data-plan-tab=plan]').click();true");
  await evaluate("document.querySelector('#wl-qty').value='7';document.querySelector('#wl-qty').dispatchEvent(new Event('input'));var row=[...document.querySelectorAll('[data-plan-entry]')].find(e=>e.textContent.includes('FSD Injection'));row.querySelector('input').value='3';row.querySelector('input').focus();row.querySelector('details').open=true;true");
  append([{event:'MaterialCollected',timestamp:'2026-11-01T10:01:00Z',Name:'germanium',Category:'Raw',Count:2}]);
  await waitFor("Lab.state.wishlist.needs?.find(r=>r.key==='germanium')?.have===5");
  assert.equal(await evaluate("document.querySelector('#wl-qty').value"),'7');
  assert.equal(await evaluate("document.activeElement.value"),'3');
  assert.equal(await evaluate("document.activeElement.closest('[data-plan-entry]').querySelector('details').open"),true);
  await evaluate("document.activeElement.closest('[data-plan-entry]').querySelector('[data-plan-edit]').click();true");
  await waitFor("Lab.state.wishlist.entries?.some(e=>e.kind==='synthesis'&&e.qty===3)");
  await record('materials-progress','requirements');await record('materials-progress','inventory');
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
  await waitFor("document.querySelector('[data-plan-evidence]').textContent.includes('FSD Basic')");
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
  // Fixed build requirements survive loadouts and reloads; resuming tracks again.
  const target={Ship:'sidewinder',ShipName:'Engineering ship',Modules:[{Slot:'FrameShiftDrive',Item:'int_hyperdrive_size2_class5',Engineering:{BlueprintName:'FSD_LongRange',Level:5,Quality:1}}]};
  await evaluate(`Lab.post('/api/build/pin',{url:${JSON.stringify(JSON.stringify(target))}})`);
  await evaluate("document.querySelector('#wl-kind').value='build';document.querySelector('#wl-kind').dispatchEvent(new Event('change'));true");
  await waitFor("!document.querySelector('[data-plan-follow-option]').hidden");
  await evaluate("document.querySelector('[data-plan-form]').requestSubmit();true");
  await waitFor("!!document.querySelector('[data-plan-follow]') && !document.querySelector('#wl-add').disabled");
  const buildUnits=await evaluate("Lab.state.wishlist.entries.find(e=>e.kind==='build').units");
  assert.ok(buildUnits>0);
  await evaluate("document.querySelector('[data-plan-follow]').click();true");
  await waitFor("Lab.state.wishlist.entries.find(e=>e.kind==='build')?.follow_ship===false");
  append([{event:'Loadout',timestamp:'2026-11-01T10:03:00Z',Ship:'sidewinder',ShipID:901,ShipName:'Finished ship',Modules:target.Modules}]);
  await waitFor("Lab.state.build.progress?.materials.length===0");
  assert.equal(await evaluate("Lab.state.wishlist.entries.find(e=>e.kind==='build').units"),buildUnits);
  await send('Page.reload');
  await waitFor("!!document.querySelector('[data-plan-follow]')");
  assert.equal(await evaluate("document.querySelector('[data-plan-follow]').checked"),false);
  assert.match(await evaluate("document.querySelector('[data-plan-follow]').closest('article').textContent"),/Fixed requirements saved/);
  await capture('wishlist-fixed-ship-mobile',390,844);
  await evaluate("window.followPost=Lab.post;Lab.post=function(p,q){return p==='/api/wishlist/update'?Promise.reject(Error('Toggle save unavailable')):window.followPost.call(this,p,q)};document.querySelector('[data-plan-follow]').click();true");
  await waitFor("document.querySelector('[data-plan-message]').textContent.includes('Toggle save unavailable')");
  assert.equal(await evaluate("document.querySelector('[data-plan-follow]').checked"),false);
  await evaluate("Lab.post=window.followPost;document.querySelector('[data-plan-follow]').click();true");
  await waitFor("Lab.state.wishlist.entries.find(e=>e.kind==='build')?.follow_ship===true");
  assert.equal(await evaluate("Lab.state.wishlist.entries.find(e=>e.kind==='build').units"),0);
  // Detailed exchanges use real planner data; provider fixtures make station comparison deterministic.
  append([{event:'Materials',timestamp:'2026-11-01T10:04:00Z',Raw:[{Name:'iron',Count:20},{Name:'carbon',Count:10},{Name:'vanadium',Count:10},{Name:'germanium',Count:10}],Manufactured:[{Name:'pharmaceuticalisolators',Count:30}],Encoded:[]}]);
  await evaluate("Lab.post('/api/wishlist/add',{item:'chemicalmanipulators',kind:'material',qty:6})");
  await evaluate("document.querySelector('[data-plan-tab=trading]').click();true");
  await waitFor("document.querySelector('[data-plan-exchange]')?.textContent.includes('G5')");
  await record('materials-exchanges','requirements');await record('materials-exchanges','trading');
  const tradeText=await evaluate("document.querySelector('.wl-trades').textContent");
  assert.match(tradeText,/G4/);assert.match(tradeText,/Manufactured/);assert.match(tradeText,/Chemical/);
  assert.match(tradeText,/Stock/);assert.match(tradeText,/give : receive/);
  const traderFixture={ref:'Leesti',pad:'L',traders:{Manufactured:[
    {station:'Nearby Harbour',system:'Nearby',dist:8,ls:5000,pad:'L',jumps:1,type:'Coriolis Starport',economy:'Industrial'},
    {station:'Quick Approach',system:'Quick',dist:15,ls:10,pad:'L',jumps:2,type:'Orbis Starport',economy:'Industrial'},
    {station:'Unknown <img src=x onerror=window.traderInjected=true>',system:'Unknown',dist:20,ls:null,pad:'L',jumps:2,type:'Coriolis Starport',economy:'Industrial'}]}};
  await evaluate(`window.traderFixture=${JSON.stringify(traderFixture)};window.stationApi=Lab.api;Lab.api=function(p,q){if(p==='/api/wishlist/traders'){window.traderQuery=q;return Promise.resolve(window.traderFixture);}return window.stationApi.call(this,p,q);};document.querySelector('[data-plan-trader-category]').value='Manufactured';document.querySelector('[data-plan-trader-category]').dispatchEvent(new Event('change'));document.querySelector('[data-plan-trader-pad]').value='L';document.querySelector('[data-plan-trader-pad]').dispatchEvent(new Event('change'));document.querySelector('#wl-traders').click();true`);
  await waitFor("document.querySelectorAll('[data-plan-trader]').length===3");
  assert.deepEqual(await evaluate('window.traderQuery'),{types:'Manufactured',pad:'L',limit:5});
  assert.match(await evaluate("document.querySelector('[data-plan-traders]').textContent"),/5,000 Ls/);
  assert.match(await evaluate("document.querySelector('[data-plan-traders]').textContent"),/Coriolis Starport/);
  assert.equal(await evaluate("document.querySelectorAll('[data-plan-traders] img').length"),0);
  assert.equal(await evaluate('!!window.traderInjected'),false);
  await evaluate("document.querySelector('[data-plan-trader-sort]').value='arrival';document.querySelector('[data-plan-trader-sort]').dispatchEvent(new Event('change'));true");
  assert.match(await evaluate("document.querySelector('[data-plan-trader]').textContent"),/Quick Approach/);
  assert.equal(await evaluate("[...document.querySelectorAll('[data-plan-arrival]')].at(-1).textContent"),'Unknown');
  await evaluate("window.realMaterialCopy=Lab.util.copy;Lab.util.copy=value=>{window.materialCopied=value;};document.querySelector('[data-plan-trader] [data-copy]').click();true");
  assert.equal(await evaluate('window.materialCopied'),'Quick');
  await record('materials-exchanges','trading');
  await evaluate("Lab.util.copy=window.realMaterialCopy;true");
  assert.match(await evaluate("document.querySelector('[data-plan-trader] a').href"),/Quick%20Approach%20%5BQuick%5D/);
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});
  const traderScroll=await evaluate("document.querySelector('[data-plan-page=trading]').getBoundingClientRect().top+scrollY-100");
  await capture('material-trading-desktop',1440,1100,traderScroll);
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await sleep(100);
  await capture('material-exchanges-mobile',390,844,await evaluate("document.querySelector('.plan-sourcing').getBoundingClientRect().top+scrollY-70"));
  await capture('material-traders-mobile',390,844,await evaluate("document.querySelector('[data-plan-trader-category]').closest('section').getBoundingClientRect().top+scrollY-70"));
  // A failed request is visible and retryable; a stale response cannot undo a new category.
  await evaluate("Lab.api=function(p,q){return p==='/api/wishlist/traders'?Promise.reject(Error('Trader lookup unavailable')):window.stationApi.call(this,p,q);};document.querySelector('#wl-traders').click();true");
  await waitFor("document.querySelector('[data-plan-traders]').textContent.includes('Trader lookup unavailable')");
  await evaluate("Lab.api=function(p,q){return p==='/api/wishlist/traders'?new Promise(r=>window.delayedTrader=r):window.stationApi.call(this,p,q);};document.querySelector('#wl-traders').click();true");
  await waitFor('!!window.delayedTrader');
  await evaluate("document.querySelector('[data-plan-trader-category]').value='Raw';document.querySelector('[data-plan-trader-category]').dispatchEvent(new Event('change'));window.delayedTrader(window.traderFixture);true");await sleep(100);
  assert.equal(await evaluate("document.querySelectorAll('[data-plan-trader]').length"),0);
  assert.match(await evaluate("document.querySelector('[data-plan-traders]').textContent"),/Selection changed/);
  await evaluate("Lab.api=window.stationApi;true");
  await send('Page.reload');
  await waitFor("document.querySelector('[data-plan-tab=trading]')?.getAttribute('aria-selected')==='true'");
  assert.equal(await evaluate("document.querySelector('[data-plan-trader-category]').value"),'Raw');
  assert.equal(await evaluate("document.querySelector('[data-plan-trader-pad]').value"),'L');
  assert.equal(await evaluate("document.querySelector('[data-plan-trader-sort]').value"),'arrival');
  // The material desk stays within common widescreen viewports, with internal lists.
  await evaluate("document.querySelector('[data-workspace=materials]').click();true");
  await evaluate("(async()=>{const rows=document.querySelector('#card-wishlist > .body')._plan.options.materials.Raw.slice(0,16);for(const row of rows)await Lab.post('/api/wishlist/add',{item:row.key,kind:'material',qty:30});})()");
  for(const [width,height] of [[3440,1440],[1920,1080],[1366,768],[1280,720]]){
    await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
    await evaluate("scrollTo(0,0);document.querySelector('[data-plan-tab=plan]').click();true");await sleep(250);
    const geometry=await evaluate("({bottom:document.querySelector('#card-wishlist').getBoundingClientRect().bottom,width:document.querySelector('#card-wishlist').getBoundingClientRect().width,viewport:innerHeight,scrollHeight:document.querySelector('.wl-entries').scrollHeight,listHeight:document.querySelector('.wl-entries').clientHeight,visible:[...document.querySelectorAll('[data-plan-page]')].filter(p=>!p.hidden).length})");
    assert.ok(geometry.bottom<=height+2,JSON.stringify({width,height,...geometry}));
    assert.ok(geometry.width<=1800,JSON.stringify(geometry));
    assert.ok(geometry.scrollHeight>geometry.listHeight);assert.equal(geometry.visible,1);
    await capture(`materials-wishlist-${width}x${height}`,width,height);
  }
  await send('Emulation.setDeviceMetricsOverride',{width:1920,height:1080,deviceScaleFactor:1,mobile:false});
  await evaluate("var desk=document.querySelector('#card-wishlist > .body');var module=desk._plan.options.modules.find(m=>m.blueprints.some(b=>b.key==='FSD_LongRange'));desk._preselect({kind:'blueprint',module:module.module,key:'FSD_LongRange'});true");
  await waitFor("document.querySelector('[data-plan-preview]').textContent.toLowerCase().includes('increased range')");
  assert.equal(await evaluate("document.querySelector('[data-plan-tab=add]').getAttribute('aria-selected')"),'true');
  await capture('materials-add-recipes-1920x1080',1920,1080);
  await evaluate("document.querySelector('[data-plan-tab=requirements]').click();document.querySelector('[data-plan-needs-category]').value='Manufactured';document.querySelector('[data-plan-needs-category]').dispatchEvent(new Event('change'));document.querySelector('[data-plan-needs-filter]').value='chemical';document.querySelector('[data-plan-needs-filter]').dispatchEvent(new Event('input'));true");
  assert.match(await evaluate("document.querySelector('.wl-needs tbody').textContent"),/Chemical Manipulators/);
  await capture('materials-requirements-1920x1080',1920,1080);
  await evaluate("var tab=document.querySelector('[data-plan-tab=plan]');tab.click();tab.focus();tab.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}));true");
  assert.equal(await evaluate("document.activeElement.dataset.planTab"),'add');
  assert.equal(await evaluate("document.querySelector('[data-plan-page=add]').hidden"),false);
  // Built-in and saved layout tabs retain independent panel arrangements.
  await evaluate("document.querySelector('[data-workspace=all]').click();true");
  assert.equal(await evaluate("document.querySelector('#layout-tabs').hidden"),false);
  const customLayout=await evaluate("(()=>{const copy=Lab.util.copy;Lab.util.copy=text=>window.exportedLayout=JSON.parse(text);document.querySelector('#lm-export').click();Lab.util.copy=copy;return window.exportedLayout;})()");
  await evaluate("[...document.querySelectorAll('#layout-tabs button')].find(b=>b.dataset.layoutName==='Second screen').click();true");
  assert.equal(await evaluate("document.querySelector('#workspace-heading h2').textContent"),'Second screen');
  await evaluate("document.querySelector('#layout-menu input[data-id=ship]').click();true");
  assert.ok(await evaluate("JSON.parse(localStorage.getItem('layout.v1')).hidden.includes('ship')"));
  await evaluate("[...document.querySelectorAll('#layout-tabs button')].find(b=>b.dataset.layoutName==='Expedition').click();[...document.querySelectorAll('#layout-tabs button')].find(b=>b.dataset.layoutName==='Second screen').click();true");
  assert.ok(await evaluate("JSON.parse(localStorage.getItem('layout.v1')).hidden.includes('ship')"));
  await evaluate("document.querySelector('#lm-name').value='Test widescreen';document.querySelector('#lm-save').click();true");
  assert.ok(await evaluate("[...document.querySelectorAll('#layout-tabs button')].some(b=>b.dataset.layoutKind==='saved'&&b.dataset.layoutName==='Test widescreen')"));
  await evaluate("[...document.querySelectorAll('#layout-tabs button')].find(b=>b.dataset.layoutKind==='saved').click();true");
  await capture('dashboard-layout-tabs',1920,1080);
  await send('Page.reload');
  await waitFor("document.querySelector('#layout-tabs [aria-selected=true]')?.dataset.layoutName==='Test widescreen'");
  assert.ok(await evaluate("JSON.parse(localStorage.getItem('layout.v1')).hidden.includes('ship')"));
  await evaluate("document.querySelector('#layout-menu [data-del]').click();true");
  assert.equal(await evaluate("document.querySelector('#layout-tabs [aria-selected=true]').dataset.layoutKind"),'custom');
  const restored=await evaluate("JSON.parse(localStorage.getItem('layout.v1'))");
  for(const key of ['order','spans','hidden','collapsed','locked'])assert.deepEqual(restored[key],customLayout[key]);
  await evaluate("var tab=document.querySelector('#layout-tabs [data-layout-kind=custom]');tab.focus();tab.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}));true");
  assert.equal(await evaluate("document.activeElement.dataset.layoutName"),'Expedition');
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
