/* Real HTTP/SSE, offline provider boundaries, owner workflow and responsive PTN desk. */
import {spawn} from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'elitelab-release-browser-'));
const env={...process.env,ELITELAB_INSTANCE_DIR:path.join(temporary,'instance')};
const server=spawn(process.env.PYTHON||'python',['-u','tests/release_server.py'],{cwd:root,env,windowsHide:true});
let output='',serverLog='',ws,chrome;
server.stdout.on('data',d=>output+=d);server.stderr.on('data',d=>serverLog+=d);
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const screenshots=process.env.ELITELAB_SCREENSHOT_DIR||path.join(temporary,'screenshots');fs.mkdirSync(screenshots,{recursive:true});
try{
  for(let i=0;i<200&&!output.includes('\n');i++){assert.equal(server.exitCode,null,serverLog);await sleep(100);}
  const port=Number(output.trim().split('\n')[0]);assert.ok(port,serverLog);
  const base=`http://127.0.0.1:${port}`;
  const post=async(p,q={})=>{const r=await fetch(base+p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(q)});const d=await r.json();assert.ok(r.ok,JSON.stringify(d));return d;};
  const profile=path.join(temporary,'chrome');
  chrome=spawn(process.env.CHROME_BIN||(process.platform==='win32'?'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe':'google-chrome'),['--headless=new','--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'],{windowsHide:true,stdio:'ignore'});
  const debugFile=path.join(profile,'DevToolsActivePort');
  for(let i=0;i<300&&!fs.existsSync(debugFile);i++)await sleep(100);
  assert.ok(fs.existsSync(debugFile),'Chrome debugger not available');
  const debugPort=Number(fs.readFileSync(debugFile,'utf8').split('\n')[0]);
  const pages=await(await fetch(`http://127.0.0.1:${debugPort}/json`)).json();
  ws=new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl);
  await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j;});
  let sequence=0;const pending=new Map(),errors=[];
  ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(m.error):p.resolve(m.result);}else if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails);};
  const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence,timer=setTimeout(()=>reject(Error('CDP timeout '+method)),15000);pending.set(id,{resolve:r=>{clearTimeout(timer);resolve(r);},reject:e=>{clearTimeout(timer);reject(e);}});ws.send(JSON.stringify({id,method,params}));});
  const evaluate=async expression=>{const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;};
  const wait=async expression=>{for(let i=0;i<450;i++){if(await evaluate(expression))return;await sleep(100);}throw Error('Timed out: '+expression+'\n'+JSON.stringify(await evaluate("({url:location.href,title:document.title,body:document.body?.textContent.slice(0,900),error:document.querySelector('.ptn-status')?.textContent,renderErrors:[...document.querySelectorAll('.render-error')].map(e=>e.textContent),errors:typeof Lab==='undefined'?null:Lab.state.ptn})"))+'\n'+serverLog);};
  const click=selector=>evaluate(`document.querySelector(${JSON.stringify(selector)}).click();true`);

  const shot=async(name,width=1440,height=1000)=>{await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<500});await evaluate('scrollTo(0,0);true');await sleep(250);assert.ok(await evaluate('document.body.scrollWidth')<=width,'Horizontal overflow: '+name);const r=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(screenshots,name+'.png'),Buffer.from(r.data,'base64'));};
  const visible=id=>evaluate(`!!document.querySelector('#card-${id}:not(.workspace-off)')`);
  await send('Runtime.enable');await send('Page.enable');await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url:base});await wait("!!document.querySelector('[data-workspace=trade]')");
  assert.ok(await visible('credits'));assert.ok(await visible('map'));
  await click('[data-workspace=trade]');await wait("!!document.querySelector('.sale-filters')");
  assert.equal(await visible('trade'),false);assert.equal(await visible('map'),false);
  await evaluate("document.querySelector('.sale-filters').requestSubmit();true");
  await wait("document.querySelectorAll('[data-sale-strategy]').length===3");
  assert.match(await evaluate("document.querySelector('[data-sale-results]').textContent"),/2,550 Cr/);
  await click('[data-sale-select]');await wait("!!document.querySelector('[data-sale-clear]')");
  await shot('trading-buyers');await shot('trading-buyers-mobile',390,844);
  const before=await(await fetch(base+'/api/selling')).json();assert.equal(before.plan.sold_quantity,30);
  await post('/audit/selling/sale');await wait("Lab.state.selling.plan?.sold['1:gold']===3");
  assert.equal(await evaluate('Lab.state.selling.plan.cargo_changed'),false);
  await send('Page.reload');await wait("!!document.querySelector('[data-sale-clear]')");
  assert.equal(await evaluate("Lab.state.selling.plan.sold['1:gold']"),3);
  await click('[data-sale-roundtrips]');assert.equal(await evaluate("document.querySelector('#card-personal').classList.contains('collapsed')"),false);
  await click('[data-workspace=carrier]');await wait("!!document.querySelector('[data-mining-plan]')");
  await evaluate("document.querySelector('[data-mining-plan]').closest('details').open=true;var form=document.querySelector('[data-mining-plan]');for(const [key,value] of Object.entries({commodity:'platinum',source:'Ring A / Sol',destination:'Buyer / Lave',quantity:101,starting_stock:20,miner_price:200000,destination_price:280000,destination_market_id:456})){form.elements.namedItem(key).value=value;}form.requestSubmit();true");
  await wait("Lab.state.trade.plan?.activity==='mining'");
  assert.equal(await evaluate('Lab.state.trade.plan.target'),121);
  await shot('carrier-mining');await shot('carrier-mining-mobile',390,844);
  for(const name of ['mining','ship','powerplay','history','materials','ptn']){
    await click(`[data-workspace=${name}]`);assert.equal(await visible('map'),false);
    await shot('workspace-'+name+'-mobile',390,844);
  }
  await click('[data-workspace=ship]');assert.match(await evaluate("document.querySelector('#card-ship').textContent"),/Shield|shield/);
  await shot('ship-status');
  await click('[data-workspace=all]');
  assert.deepEqual(await evaluate("[...document.querySelectorAll('#layout-tabs [data-layout-kind=preset]')].map(e=>e.dataset.layoutName)"),['Expedition','Rare goods','Second screen']);
  await evaluate("document.querySelector('[data-layout-name=\"Second screen\"]').click();true");
  assert.equal(await visible('map'),false);await shot('second-screen');await shot('second-screen-mobile',390,844);
  assert.deepEqual(errors,[]);assert.deepEqual(await evaluate("[...document.querySelectorAll('.render-error')].map(e=>e.textContent)"),[]);
  console.log('Release workspaces, cargo search/selection/sales/reload, mining setup, layout choices and responsive checks passed. '+screenshots);
  await send('Browser.close').catch(()=>{});
}finally{ws?.close();chrome?.kill();server.kill();}
