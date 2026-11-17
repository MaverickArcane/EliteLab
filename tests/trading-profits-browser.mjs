/* Exercise the real CLI, journal watcher, API and SSE in Chrome. Node 22+. */
import {waitForChromePage} from './chrome-ready.mjs';
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
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'elitelab-trading-profits-browser-'));
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
const append=events=>{
  fs.appendFileSync(journal,events.map(e=>JSON.stringify(e)).join('\n')+'\n');
  const cargo=events.findLast(e=>e.event==='Cargo');
  if(cargo)fs.writeFileSync(path.join(journals,'Cargo.json'),JSON.stringify(cargo));
};
try {
  server=spawn(process.env.PYTHON||'python',['-u','-m','elitelab','serve'],{cwd:root,env,windowsHide:true});
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
  const page=await waitForChromePage(chrome,debugFile);
  ws=new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j;});
  let sequence=0;const pending=new Map(),errors=[];
  ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(m.error):p.resolve(m.result);}else if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails);};
  const send=(method,params={})=>new Promise((resolve,reject)=>{
    const id=++sequence,timer=setTimeout(()=>reject(new Error('CDP timeout '+method)),10000);
    pending.set(id,{resolve:r=>{clearTimeout(timer);resolve(r);},reject:e=>{clearTimeout(timer);reject(e);}});
    ws.send(JSON.stringify({id,method,params}));
  });
  const evaluate=async expression=>{const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(JSON.stringify(r.exceptionDetails));return r.result.value;};
  const waitFor=async expression=>{for(let i=0;i<150;i++){if(await evaluate(expression)){await evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(()=>r(true))))');return;}await sleep(100);}assert.fail('Timed out: '+expression+'\nStatuses: '+await evaluate("[...document.querySelectorAll('[data-search-status]')].map(e=>e.textContent).join(' | ')")+'\nProfit state: '+await evaluate('JSON.stringify({profits:Lab.state.profits,progress:Lab.state.personal.progress,cargo:Lab.state.journal.cargo})')+'\n'+serverLog);};
  await send('Runtime.enable');await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await send('Page.addScriptToEvaluateOnNewDocument',{source:"localStorage.setItem('workspace.v1',JSON.stringify('all'))"});
  await send('Page.navigate',{url:base});

  await waitFor("!!document.querySelector('[data-earned-profit]') && document.querySelectorAll('[data-inara-commodity] option').length>250");
  await evaluate("[...document.querySelectorAll('#layout-menu input[data-id]')].filter(c=>c.checked&&c.dataset.id!=='personal').map(c=>c.dataset.id).forEach(id=>document.querySelector('#layout-menu input[data-id='+id+']').click());true");
  const earned="document.querySelector('[data-earned-profit]').textContent";
  const run="document.querySelector('[data-run-estimate]').textContent";
  assert.equal(await evaluate(earned),'0 Cr');
  assert.equal(await evaluate("document.querySelector('[href=\"elitelab-hud:open?mode=profits\"]').textContent"),'Open profit HUD');
  assert.ok(await evaluate("!!document.querySelector('#hud-activity option[value=profits]')"));
  append([{event:'Location',timestamp:'2026-10-22T10:01:00Z',StarSystem:'Sol',StarPos:[0,0,0],Docked:true,MarketID:1,StationName:'Port 1'},
    {event:'MarketBuy',timestamp:'2026-10-22T10:01:01Z',MarketID:1,Type:'gold',Count:100,BuyPrice:100,TotalCost:10000},
    {event:'Cargo',timestamp:'2026-10-22T10:01:02Z',Vessel:'Ship',Count:100,Inventory:[{Name:'gold',Count:100}]}]);
  await waitFor("Lab.state.profits.estimate?.profit===30000");
  assert.equal(await evaluate(earned),'0 Cr');
  append([{event:'MarketSell',timestamp:'2026-10-22T10:02:00Z',MarketID:2,Type:'gold',Type_Localised:'Gold',Count:40,TotalSale:16000,AvgPricePaid:100},
    {event:'Cargo',timestamp:'2026-10-22T10:02:01Z',Vessel:'Ship',Count:60,Inventory:[{Name:'gold',Count:60}]}]);
  await waitFor("Lab.state.profits.session.profit===12000 && Lab.state.profits.estimate?.profit===18000");
  assert.equal(await evaluate(earned),'12,000 Cr');
  assert.equal(await evaluate(run),'18,000 Cr');
  assert.equal(await evaluate("document.querySelector('[data-last-profit]').textContent"),'12,000 Cr');
  const set=async(name,value)=>evaluate(`{const n=document.querySelector('[data-inara-search] [name=${name}]');n.value=${JSON.stringify(value)};n.dispatchEvent(new Event('change',{bubbles:true}));}true`);
  await set('commodity','42');await set('system','');await set('pad','2');await set('age','8');await set('carriers','1');await set('surface','2');
  let url=new URL(await evaluate("document.querySelector('[data-inara-buy]').href"));
  assert.equal(url.origin,'https://inara.cz');assert.equal(url.searchParams.get('pi1'),'1');
  assert.equal(url.searchParams.get('pa1[]'),'42');assert.equal(url.searchParams.get('ps1'),'Sol');
  assert.equal(url.searchParams.get('pi3'),'2');assert.equal(url.searchParams.get('pi5'),'8');
  assert.equal(url.searchParams.get('pi8'),'1');assert.equal(url.searchParams.get('pi4'),'2');
  assert.equal(new URL(await evaluate("document.querySelector('[data-inara-sell]').href")).searchParams.get('pi1'),'2');
  await set('system','A & B + C');
  append([{event:'FSDJump',timestamp:'2026-10-22T10:03:00Z',StarSystem:'Alpha',StarPos:[39,0,0],JumpDist:39}]);
  await waitFor("Lab.state.journal.system==='Alpha'");
  assert.equal(new URL(await evaluate("document.querySelector('[data-inara-sell]').href")).searchParams.get('ps1'),'A & B + C');
  await set('system','');
  assert.equal(new URL(await evaluate("document.querySelector('[data-inara-sell]').href")).searchParams.get('ps1'),'Alpha');
  assert.equal(await evaluate("document.querySelector('[data-inara-commodity]').value"),'42');
  assert.equal((await (await fetch(base+'/api/personal/plan')).json()).plan.id,'handoff-fixture');
  const output=path.join(root,'artifacts/trading-profits');fs.mkdirSync(output,{recursive:true});
  const capture=async(name,width,height)=>{
    await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
    await evaluate("window.scrollTo(0,0);true");await sleep(250);
    const shot=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(output,name+'.png'),Buffer.from(shot.data,'base64'));
    assert.ok(await evaluate('document.documentElement.scrollWidth<=window.innerWidth'),'Horizontal overflow');
  };
  await capture('desktop',1440,1200);await capture('narrow',390,1500);
  await evaluate("document.querySelector('[data-inara-search]').scrollIntoView({block:'start'});true");await sleep(200);
  const inaraShot=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(output,'inara-narrow.png'),Buffer.from(inaraShot.data,'base64'));
  await evaluate("document.querySelector('[data-trade-profits] details').open=true;true");
  append([{event:'MarketSell',timestamp:'2026-10-22T10:04:00Z',Type:'silver',Type_Localised:'<img src=x onerror=window.profitXss=1>',Count:1,TotalSale:1}]);
  await waitFor("Lab.state.profits.session.unknown_sales===1");
  assert.equal(await evaluate(earned),'Unknown');
  assert.equal(await evaluate("document.querySelector('[data-trade-profits] details').open"),true);
  assert.match(await evaluate("document.querySelector('[data-trade-profits]').textContent"),/Known profit subtotal: 12,000 Cr/);
  assert.equal(await evaluate("!!document.querySelector('[data-trade-profits] img')||!!window.profitXss"),false);
  append([{event:'LoadGame',timestamp:'2026-10-22T10:05:00Z',Commander:'Other Trader',FID:'F3'}]);
  await waitFor("Lab.state.profits.session.commander==='Other Trader' && !Lab.state.profits.estimate");
  assert.equal(await evaluate(earned),'0 Cr');
  assert.equal(await evaluate(run),'Unknown');
  assert.deepEqual(await evaluate("[...document.querySelectorAll('.render-error')].map(e=>e.textContent)"),[]);
  assert.deepEqual(errors,[]);assert.doesNotMatch(serverLog,/Traceback|handler failed/);
  console.log('Trading profits browser passed: real CLI/API/journal/SSE; receipt margins, partial costs, current-load estimates, HUD links, Inara filters/encoding/current location, stable input, commander changes, escaping, desktop/narrow screenshots: '+output);
  await send('Browser.close').catch(()=>{});
} finally {
  ws?.close();chrome?.kill();
  if(server&&server.exitCode===null){
    try{await fetch(base+'/api/shutdown',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',signal:AbortSignal.timeout(1000)});}catch{}
    for(let i=0;i<50&&server.exitCode===null;i++)await sleep(100);
    if(server.exitCode===null)server.kill();
  }
}
