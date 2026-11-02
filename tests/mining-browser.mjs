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
  const waitFor=async expression=>{for(let i=0;i<100;i++){if(await evaluate(expression))return;await sleep(100);}assert.fail('Timed out: '+expression+'\n'+serverLog);};
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
  const outputDir=process.env.ELITELAB_SCREENSHOT_DIR||path.join(temporary,'screenshots');fs.mkdirSync(outputDir,{recursive:true});
  for(const [name,width,height] of [['desktop',1440,1000],['mobile',390,844]]) {
    await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<500});await sleep(200);
    await evaluate("scrollTo(0,0);true");
    assert.ok(await evaluate('document.body.scrollWidth')<=width,'Horizontal page overflow');
    assert.ok(await evaluate("document.querySelector('#card-mining').scrollWidth<=document.querySelector('#card-mining').clientWidth+2"),'Mining card overflow');
    const shot=await send('Page.captureScreenshot',{format:'png'});
    fs.writeFileSync(path.join(outputDir,`mining-${name}.png`),Buffer.from(shot.data,'base64'));
  }
  const hostile='<img src=x onerror="window.miningInjected=true">';
  append([{event:'LoadGame',timestamp:'2026-10-22T14:00:00Z',Commander:'Test Miner',FID:'F2'},
    {event:'ProspectedAsteroid',timestamp:'2026-10-22T14:01:00Z',Content_Localised:hostile,MotherlodeMaterial:hostile,Remaining:100,Materials:[{Name:hostile,Proportion:25}]},
    {event:'MiningRefined',timestamp:'2026-10-22T14:02:00Z',Type:'Gold',Type_Localised:hostile}]);
  await waitFor("document.querySelector('[data-mining-total]').textContent==='1 t'");
  assert.equal(await evaluate("document.querySelectorAll('#card-mining img').length"),0);
  assert.equal(await evaluate('!!window.miningInjected'),false);
  assert.ok(await evaluate("document.querySelector('#card-mining').textContent.includes('<img')"));
  assert.ok(await evaluate('document.body.scrollWidth')<=390);
  await send('Page.reload');
  await waitFor("document.querySelector('#card-mining [data-mining-total]')?.textContent==='1 t'");
  assert.equal(await evaluate("!!document.querySelector('#card-cargo') && !document.querySelector('#card-ship')"),true);
  assert.deepEqual(await evaluate("[...document.querySelectorAll('.render-error')].map(e=>e.textContent)"),[]);
  assert.deepEqual(errors,[]);
  assert.doesNotMatch(serverLog,/Traceback|handler failed/);
  console.log('Mining CLI, API, live journal/SSE, replay, session reset, desktop/mobile, saved layout and HTML escaping passed. Screenshots: '+outputDir);
  await send('Browser.close').catch(()=>{});
} finally {
  ws?.close();chrome?.kill();
  if(server && server.exitCode===null) {
    try{await fetch(base+'/api/shutdown',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',signal:AbortSignal.timeout(1000)});}catch{}
    for(let i=0;i<50&&server.exitCode===null;i++)await sleep(100);
    if(server.exitCode===null)server.kill();
  }
}
