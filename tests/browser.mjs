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
const chrome = spawn(process.env.CHROME_BIN || (process.platform === 'win32' ? 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe' : 'google-chrome'), ['--headless=new', '--no-sandbox', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'], {windowsHide:true, stdio:'ignore'});
const attacker = http.createServer((req,res) => {res.writeHead(200, {'Content-Type':'text/html'}); res.end('<!doctype html><title>Audit cross-origin test</title>');});
await new Promise(r => attacker.listen(0,'127.0.0.1',r));
let ws;
try {
  for(let i=0;i<100 && (!serverText.trim() || !fs.existsSync(path.join(profile, 'DevToolsActivePort')));i++) await sleep(100);
  const port = Number(serverText.trim());
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
  // the materials filter and the wishlist picker's quantity must survive a live materials update (issue 23)
  await evaluate("document.querySelector('#mat-q').value='arsenic';document.querySelector('#wl-qty').value='5';document.querySelector('#mat-q').focus();true");
  await fetch(`http://127.0.0.1:${port}/audit/emit`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
  await sleep(250);
  const inputAfter=await evaluate("({name:document.querySelector('#mat-q').value,qty:document.querySelector('#wl-qty').value,focus:document.activeElement.id})");
  // Confirm a preset and restoration both mount cleanly.
  await evaluate("document.querySelector('[data-preset=Engineering]').click();true");
  await sleep(200); const engineeringCards=await evaluate("document.querySelectorAll('#grid > .card').length");
  await evaluate("document.querySelector('[data-preset=Default]').click();true");
  await sleep(200);
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await sleep(200);
  await evaluate("scrollTo(0,0);true");
  const mobile=await evaluate("({bodyWidth:document.body.scrollWidth,viewport:innerWidth,clientWidth:document.documentElement.clientWidth,cards:document.querySelectorAll('#grid > .card').length,overflow:[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>395&&getComputedStyle(e).position!=='fixed').slice(0,15).map(e=>({tag:e.tagName,id:e.id,cls:e.className,right:e.getBoundingClientRect().right}))})");
  const shot=await send('Page.captureScreenshot',{format:'png'});
  await evaluate("(async()=>{window.originalApi=Lab.api;Lab.api=async path=>path==='/api/health'?{journal_found:false,journal_dir:'<dir>&'}:window.originalApi(path);await Lab.checkHealth();return true})()");
  assert.equal(await evaluate("!!document.querySelector('#journal-warning a[href=\"/setup/\"]')"),true);
  assert.equal(await evaluate("!!document.querySelector('#journal-warning dir')"),false);
  await evaluate("(async()=>{await Lab.checkHealth();Lab.api=window.originalApi;await Lab.checkHealth();return true})()");
  assert.equal(await evaluate("!!document.querySelector('#journal-warning')"),false);
  await send('Page.navigate',{url:`http://127.0.0.1:${port}/setup/`});
  for(let i=0;i<50;i++){await sleep(100);if(await evaluate("!!document.querySelector('[data-candidates] input')"))break;}
  assert.equal(await evaluate("!!document.querySelector('[data-candidates] input:checked')"),true);
  assert.equal(await evaluate("document.body.textContent.includes('Nothing to connect yet. Inara and other services will appear here.')"),true);
  await evaluate("document.querySelector('[name=port]').value='8799';document.querySelector('[data-setup-form]').requestSubmit();true");
  for(let i=0;i<50;i++){await sleep(100);if(await evaluate("!document.querySelector('[data-restart]').hidden"))break;}
  assert.equal(await evaluate("!document.querySelector('[data-restart]').hidden"),true);
  const setupState=await (await fetch(`http://127.0.0.1:${port}/api/setup`)).json();
  assert.deepEqual(JSON.parse(fs.readFileSync(setupState.path,'utf8')), {port:8799});
  assert.equal(await evaluate("document.querySelector('[data-status]').textContent.includes('Restart')"),true);
  await fetch(`http://127.0.0.1:${port}/api/materials/wishlist`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({items:{arsenic:10}})});
  await send('Page.navigate',{url:`http://127.0.0.1:${attacker.address().port}`});await sleep(250);
  const crossOrigin=await evaluate(`fetch('http://127.0.0.1:${port}/api/materials/wishlist',{method:'POST',mode:'no-cors',headers:{'Content-Type':'text/plain'},body:JSON.stringify({items:{},mode:'clear'})}).then(r=>({type:r.type})).catch(e=>({error:String(e)}))`);
  const wishlistAfter=await (await fetch(`http://127.0.0.1:${port}/api/materials/wishlist`)).json();
  const results={desktop:before,inputAfter,engineeringCards,mobile,crossOrigin,wishlistAfter,browserExceptions:errors};
  assert.equal(inputAfter.name,'arsenic'); assert.equal(inputAfter.qty,'5'); assert.equal(inputAfter.focus,'mat-q'); assert.equal(mobile.bodyWidth,390); assert.equal(wishlistAfter.wishlist[0].need,10); assert.deepEqual(errors,[]); assert.deepEqual(before.renderErrors,[]);console.log(JSON.stringify(results,null,2));
  await send('Browser.close').catch(()=>{});
} finally {ws?.close();server.kill();chrome.kill();attacker.close();}
