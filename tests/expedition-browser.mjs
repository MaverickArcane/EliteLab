import {spawn} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import assert from 'node:assert/strict';
import os from 'node:os';
const dir = path.dirname(new URL(import.meta.url).pathname.replace(/^\/(\w:)/, '$1'));
const sleep = ms => new Promise(r => setTimeout(r, ms));
const server = spawn(process.env.PYTHON || 'python', ['-u', path.join(dir, 'browser_server.py')], {windowsHide:true});
server.stderr.on('data', d => process.stderr.write(d));
let serverText = ''; server.stdout.on('data', d => serverText += d);
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'elitelab-chrome-'));
const chrome = spawn(process.env.CHROME_BIN || (process.platform === 'win32' ? 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe' : 'google-chrome'), ['--headless=new', '--no-sandbox', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'], {windowsHide:true, stdio:['ignore','ignore','pipe']});
let chromeLog='', chromeError;
chrome.stderr.on('data',d=>{chromeLog=(chromeLog+d).slice(-8000);});
chrome.on('error',error=>{chromeError=error;});
const attacker = http.createServer((req,res) => {res.writeHead(200, {'Content-Type':'text/html'}); res.end('<!doctype html><title>Audit cross-origin test</title>');});
await new Promise(r => attacker.listen(0,'127.0.0.1',r));
let ws, joinServer;
try {
  for(let i=0;i<300 && (!serverText.includes('\n') || !fs.existsSync(path.join(profile, 'DevToolsActivePort')));i++) {
    if(chromeError || chrome.exitCode!==null || chrome.signalCode!==null) throw new Error(`Chrome failed to start: ${chromeError || chrome.exitCode || chrome.signalCode}\n${chromeLog}`);
    await sleep(100);
  }
  assert.ok(fs.existsSync(path.join(profile,'DevToolsActivePort')),`Chrome debugger did not become ready within 30 seconds.\n${chromeLog}`);
  assert.ok(serverText.includes('\n'),'Browser fixture server did not become ready within 30 seconds.');
  const port = Number(serverText.split('\n')[0]);
  console.log('Server port', port);
  const debugPort = Number(fs.readFileSync(path.join(profile,'DevToolsActivePort'),'utf8').split('\n')[0]);
  const tabs = await (await fetch(`http://127.0.0.1:${debugPort}/json`, {signal:AbortSignal.timeout(10000)})).json();
  console.log('Browser debugger connected');
  ws = new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);
  await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j});
  let seq=0;const pending=new Map();const errors=[];
  ws.onmessage = e => {const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);if(m.error)p.reject(m.error);else p.resolve(m.result)}else if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails);};
  const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++seq;const timer=setTimeout(()=>reject(new Error('CDP timeout '+method)),15000);pending.set(id,{resolve:r=>{clearTimeout(timer);resolve(r)},reject:e=>{clearTimeout(timer);reject(e)}});ws.send(JSON.stringify({id,method,params}));});
  const evaluate=async expression=> {const v=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true}); if(v.exceptionDetails)throw new Error(JSON.stringify(v.exceptionDetails));return v.result.value;};
  await send('Runtime.enable');await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url:`http://127.0.0.1:${port}`});
  console.log('Navigated to dashboard');
  for(let i=0;i<50;i++){await sleep(100);if(await evaluate("!!document.querySelector('#mat-q') && !!document.querySelector('#wl-qty')"))break;}
  await sleep(400);
  const before=await evaluate("({cards:document.querySelectorAll('#grid > .card').length, renderErrors:[...document.querySelectorAll('.render-error')].map(e=>e.textContent),live:document.getElementById('h-live').className,bodyWidth:document.body.scrollWidth,viewport:innerWidth})");
  console.log('Dashboard', before);
  const desktop=await send('Page.captureScreenshot',{format:'png'});

  assert.deepEqual(before.renderErrors, []);
  const response = await fetch(`http://127.0.0.1:${port}/`);
  assert.equal(response.headers.get('x-frame-options'), 'DENY');
  assert.ok(response.headers.get('content-security-policy').includes("script-src 'self'"));
  await evaluate("document.querySelector('[data-preset=Expedition]').click();true");
  await sleep(200);
  assert.equal(await evaluate("!!document.querySelector('#card-neutron') && !!document.querySelector('#card-synthesis')"), true);
  await evaluate(`(() => {
    window.realPost = Lab.post; window.realApi = Lab.api; window.tripCalls = [];
    window.sampleTrip = {location:{system:'UGPS 0722-05'},ship:{suggested_range_ly:73.17,suggested_supercharge_multiplier:6,fuel_scoop_fitted:true,afmu_fitted:true,fsd_health_at_loadout:1,notices:[]},
      palin:{greatest_distance_from_start_ly:3781},boost_observation:{status:'injection_observed'},navigation_status:'at_waypoint',remaining_waypoints:2,waypoint_count:3,
      route:{id:'fixture',status:'queued',request:{from:'UGPS 0722-05',to:'Omega Sector VE-Q b5-15'},spansh_url:'https://spansh.co.uk/plotter/results/fixture'},
      next_waypoint:{system:'<img src=x onerror=alert(1)>'},waypoints:[{system:'<img src=x onerror=alert(1)>',neutron_star:true,distance_from_previous_ly:407.485,estimated_jumps_from_previous:6,coordinates:[0,0,400]}],notes:['Refuel on scoopable stars.']};
    Lab.post = async (path, body) => {
      window.tripCalls.push({path,body});
      if(path==='/api/neutron/plan') return structuredClone(window.sampleTrip);
      if(path==='/api/neutron/refresh') {window.sampleTrip.route.status='ready';return structuredClone(window.sampleTrip);}
      if(path==='/api/neutron/clear') return {...structuredClone(window.sampleTrip),route:null,waypoints:[],next_waypoint:null};
      if(path==='/api/synthesis/plan') return {affordable:false,materials:[{name:'Germanium',required:4,have:2,short:2}],note:'Nothing reserved.'};
      return window.realPost(path,body);
    };
    Lab.api = async (path,q) => path==='/api/synthesis/recipes' ? {note:'Counts share inventory.',recipes:[{key:'fsd_injection_basic',name:'FSD Injection',grade:'basic',quantity:Number(q.quantity),craftable:2,ingredients:[{name:'Germanium',have:2,required:Number(q.quantity),short:0}]}]} : window.realApi(path,q);
    Lab.set('neutron',{summary:{...structuredClone(window.sampleTrip),route:null}});
    const d=structuredClone(Lab.state.synthesis.summary); d.boost={status:'unknown'};
    d.injections.forEach((r,i)=>r.craftable=[2,2,1][i]);Lab.set('synthesis',{summary:d});
    return true;
  })()`);
  await sleep(150);
  assert.equal(await evaluate("document.querySelector('[name=range_ly]').value"),'73.17');
  await evaluate("document.querySelector('[name=range_ly]').value='70';document.querySelector('[name=range_ly]').dispatchEvent(new Event('input'));document.querySelector('[name=destination]').value='Omega Sector VE-Q b5-15';Lab.emit('neutron');true");
  await sleep(100);
  assert.equal(await evaluate("document.querySelector('[name=range_ly]').value"),'70');
  await evaluate("document.querySelector('[data-neutron-plan]').requestSubmit();true");
  await sleep(150);
  assert.equal(await evaluate('window.tripCalls[0].body.range_ly'),70);
  assert.equal(await evaluate("document.querySelector('#card-neutron img')===null"),true);
  assert.equal(await evaluate("document.querySelector('#card-neutron [data-copy]').dataset.copy"),'<img src=x onerror=alert(1)>');
  for(let i=0;i<65;i++){await sleep(100);if(await evaluate("window.tripCalls.some(c=>c.path==='/api/neutron/refresh')"))break;}
  assert.equal(await evaluate("!!document.querySelector('[data-neutron-export]')"),true);
  await evaluate("document.querySelector('[data-synthesis-search] [name=query]').value='FSD';document.querySelector('[data-synthesis-search] [name=quantity]').value='2';document.querySelector('[data-synthesis-search]').requestSubmit();true");
  await sleep(100);
  await evaluate("document.querySelector('[data-synthesis-add]').click();document.querySelector('[data-synthesis-add]').click();document.querySelector('[data-synthesis-budget]').click();true");
  await sleep(150);
  assert.equal(await evaluate("document.querySelector('[data-synthesis-budget-result]').textContent.includes('short 2')"),true);
  assert.equal(await evaluate("window.tripCalls.find(c=>c.path==='/api/synthesis/plan').body.items.length"),2);
  await evaluate("Lab.set('synthesis',{summary:{...Lab.state.synthesis.summary,inventory_revision:999}});true");
  await sleep(100);
  assert.equal(await evaluate("document.querySelector('[data-synthesis-search] [name=query]').value"),'FSD');
  assert.equal(await evaluate("document.querySelector('[data-synthesis-budget-result]').textContent.includes('again')"),true);
  // Old searches must not replace a newer result when replies arrive out of order.
  await evaluate(`window.workingRecipeApi=Lab.api;window.recipeResolvers=[];Lab.api=(path,q)=>path==='/api/synthesis/recipes'?new Promise(resolve=>window.recipeResolvers.push(resolve)):window.workingRecipeApi(path,q);document.querySelector('[data-synthesis-search]').requestSubmit();document.querySelector('[data-synthesis-search]').requestSubmit();window.recipeResolvers[1]({recipes:[],note:'Newest search'});true`);
  await sleep(100);
  await evaluate("window.recipeResolvers[0]({recipes:[],note:'Older search'});true");
  await sleep(100);
  assert.equal(await evaluate("document.querySelector('[data-synthesis-results]').textContent.includes('Newest search')"),true);
  await evaluate("Lab.api=window.workingRecipeApi;window.sampleTrip.next_waypoint.system='PSR J1752-2806';window.sampleTrip.waypoints[0].system='PSR J1752-2806';Lab.set('neutron',{summary:structuredClone(window.sampleTrip)});true");
  await sleep(100);
  const outputDir=process.env.ELITELAB_SCREENSHOT_DIR || path.join(os.tmpdir(),'elitelab-expedition-review');
  fs.mkdirSync(outputDir,{recursive:true});
  for(const [name,width,height] of [['desktop',1440,1000],['mobile',390,844]]) {
    await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<500});await sleep(150);
    await evaluate('scrollTo(0,0);true');
    assert.ok(await evaluate('document.body.scrollWidth') <= width);
    const shot=await send('Page.captureScreenshot',{format:'png'});
    fs.writeFileSync(path.join(outputDir,`expedition-${name}.png`),Buffer.from(shot.data,'base64'));
  }
  // Hiding a queued route stops polling; remounting creates exactly one timer.
  await evaluate("window.sampleTrip.route.status='queued';Lab.set('neutron',{summary:structuredClone(window.sampleTrip)});true");
  await sleep(100);
  await evaluate("document.querySelector('#layout-menu input[data-id=neutron]').click();true");
  const callsBeforeHide=await evaluate('window.tripCalls.length');
  await sleep(5200);
  assert.equal(await evaluate("document.querySelector('#card-neutron')===null"),true);
  assert.equal(await evaluate('window.tripCalls.length'),callsBeforeHide);
  await evaluate("document.querySelector('#layout-menu input[data-id=neutron]').click();true");
  await sleep(5200);
  assert.equal(await evaluate('window.tripCalls.length'),callsBeforeHide+1);
  await evaluate("Lab.post=window.realPost;Lab.api=window.realApi;true");
  assert.deepEqual(await evaluate("[...document.querySelectorAll('.render-error')].map(e=>e.textContent)"),[]);
  assert.deepEqual(errors,[]);
  console.log('Expedition browser checks passed; screenshots:',outputDir);
  await send('Browser.close').catch(()=>{});
} finally {ws?.close();server.kill();chrome.kill();attacker.close();joinServer?.close();}
