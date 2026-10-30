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
  for(let i=0;i<100 && (!serverText.includes('\n', serverText.indexOf('\n') + 1) || !fs.existsSync(path.join(profile, 'DevToolsActivePort')));i++) await sleep(100);
  const [portLine, settingsFile] = serverText.split('\n').map(l => l.trim());
  const port = Number(portLine);
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
  // journal banner: folder shown as text, link to /setup/, removed once journals are found
  const bannerProbe=await evaluate(`(async()=>{const orig=Lab.api;const out={};try{Lab.api=async p=>p==='/api/health'?{journal_found:false,journal_dir:'<dir>&'}:orig(p);await Lab.checkHealth();const b=document.getElementById('journal-warning');const a=b&&b.querySelector('a[href="/setup/"]');out.link=a?a.textContent:null;out.text=b?b.textContent:'';out.injected=b?b.querySelectorAll('dir').length:-1;Lab.api=async p=>p==='/api/health'?{journal_found:true,journal_dir:'x'}:orig(p);await Lab.checkHealth();out.gone=!document.getElementById('journal-warning');}finally{Lab.api=orig;}return out;})()`);
  assert.equal(bannerProbe.link,'Open setup'); assert.ok(bannerProbe.text.includes('No journal files found in <dir>&. Open setup to choose your journal folder.')); assert.ok(bannerProbe.text.includes('In Docker, mount the folder read-only at /journals.')); assert.equal(bannerProbe.injected,0); assert.ok(bannerProbe.gone);
  const shot=await send('Page.captureScreenshot',{format:'png'});
  await fetch(`http://127.0.0.1:${port}/api/materials/wishlist`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({items:{arsenic:10}})});
  await send('Page.navigate',{url:`http://127.0.0.1:${attacker.address().port}`});await sleep(250);
  const crossOrigin=await evaluate(`fetch('http://127.0.0.1:${port}/api/materials/wishlist',{method:'POST',mode:'no-cors',headers:{'Content-Type':'text/plain'},body:JSON.stringify({items:{},mode:'clear'})}).then(r=>({type:r.type})).catch(e=>({error:String(e)}))`);
  const wishlistAfter=await (await fetch(`http://127.0.0.1:${port}/api/materials/wishlist`)).json();
  // setup page: candidates listed, fixture folder selected, save a port change, restart offered, file written (Restart is never clicked)
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await send('Page.navigate',{url:`http://127.0.0.1:${port}/setup/`});
  for(let i=0;i<50;i++){await sleep(100);if(await evaluate("!!document.querySelector('[data-candidates] input')"))break;}
  const setupPage=await evaluate("({candidates:document.querySelectorAll('[data-candidates] input').length,selected:(document.querySelector('[data-candidates] input:checked')||{}).value||'',connections:document.body.textContent.includes('Nothing to connect yet. Inara and other services will appear here.'),restartHidden:document.querySelector('[data-restart]').hidden,bodyWidth:document.body.scrollWidth,viewport:innerWidth})");
  // custom path then radio: the last interaction wins
  const precedence=await evaluate("(()=>{const c=document.querySelector('[name=journal_dir_custom]');const r=document.querySelector('[data-candidates] input');c.value='/tmp/typed';c.dispatchEvent(new Event('input',{bubbles:true}));const afterType=document.querySelectorAll('[data-candidates] input:checked').length;r.click();return {afterType,custom:c.value,radio:r.checked}})()");
  assert.deepEqual(precedence,{afterType:0,custom:'',radio:true});
  // restart wait, with a fake fetch and clock (Restart is never clicked)
  const restartWait=await evaluate(`(async()=>{
    const ok={ok:true,json:async()=>({ok:true})};
    const mk=(steps)=>{const log=[];let i=0;const f=async()=>{const s=steps[Math.min(i++,steps.length-1)];log.push(s);if(s==='reject')throw new TypeError('down');if(s==='bad')return {ok:false,json:async()=>({})};if(s==='html')return {ok:true,json:async()=>{throw new Error('not json')}};return ok};return {f,log}};
    const clk=()=>{let t=0;return {now:()=>t,sleep:async ms=>{t+=ms}}};
    const W=window.SetupPage.waitForRestart;
    const a=mk(['ok','ok','reject','reject','ok']);const ra=await W(a.f,'',clk());
    const b=mk(['ok']);const rb=await W(b.f,'',clk());
    const c=mk(['ok','bad','html','ok']);const rc=await W(c.f,'',clk());
    const d=[];const rd=await W(async(u,o)=>{d.push([u,o&&o.mode]);if(d.length<3)return ok;if(d.length===3)throw new TypeError('down');return {type:'opaque'}},'http://127.0.0.1:8799',clk());
    return {ra,la:a.log.join(','),rb,lb:b.log.length,rc,lc:c.log.join(','),rd,d}})()`);
  assert.deepEqual(restartWait,{ra:'up',la:'ok,ok,reject,reject,ok',rb:'timeout',lb:60,rc:'up',lc:'ok,bad,html,ok',rd:'up',d:[['/api/health',null],['/api/health',null],['/api/health',null],['http://127.0.0.1:8799/api/health','no-cors']]});
  assert.ok(setupPage.candidates>=1); assert.equal(path.resolve(setupPage.selected),path.join(dir,'fixtures','journals')); assert.ok(setupPage.connections); assert.ok(setupPage.restartHidden); assert.equal(setupPage.bodyWidth,setupPage.viewport);
  await evaluate("document.querySelector('[name=port]').value='8799';document.querySelector('[data-setup-form]').requestSubmit();true");
  for(let i=0;i<50;i++){await sleep(100);if(await evaluate("!document.querySelector('[data-restart]').hidden"))break;}
  const setupSaved=await evaluate("({restartVisible:!document.querySelector('[data-restart]').hidden,status:document.querySelector('[data-status]').textContent})");
  assert.ok(setupSaved.restartVisible); assert.match(setupSaved.status,/restart/i);
  assert.deepEqual(JSON.parse(fs.readFileSync(settingsFile,'utf8')),{port:8799});
  const results={bannerProbe,setupPage,precedence,restartWait,setupSaved,desktop:before,inputAfter,engineeringCards,mobile,crossOrigin,wishlistAfter,browserExceptions:errors};
  assert.equal(inputAfter.name,'arsenic'); assert.equal(inputAfter.qty,'5'); assert.equal(inputAfter.focus,'mat-q'); assert.equal(mobile.bodyWidth,390); assert.equal(wishlistAfter.wishlist[0].need,10); assert.deepEqual(errors,[]); assert.deepEqual(before.renderErrors,[]);console.log(JSON.stringify(results,null,2));
  await send('Browser.close').catch(()=>{});
} finally {ws?.close();server.kill();chrome.kill();attacker.close();}
