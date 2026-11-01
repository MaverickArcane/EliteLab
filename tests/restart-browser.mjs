/* Real CLI restart across ports, including the setup page's response CSP. */
import {spawn} from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'elitelab-restart-'));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function freePort() {
  const server=http.createServer();
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const port=server.address().port;
  await new Promise(r=>server.close(r));
  return port;
}
const oldPort=await freePort(), newPort=await freePort();
assert.notEqual(oldPort,newPort);
const settings=path.join(temporary,'settings.json');
fs.writeFileSync(settings,JSON.stringify({port:oldPort}));
const env={...process.env,ELITELAB_SETTINGS:settings,ELITELAB_HOST:'127.0.0.1',ELITELAB_OFFLINE:'1',
  ELITELAB_JOURNAL_DIR:path.join(temporary,'journals'),ELITELAB_DATA_DIR:path.join(temporary,'data'),
  ELITELAB_INSTANCE_DIR:path.join(temporary,'instance'),ELITELAB_AUTH_TOKEN:''};
delete env.ELITELAB_PORT;
let server,chrome,ws,stopping=false,starts=0,serverLog='';
const exits=[];
function launch() {
  starts++;
  server=spawn(process.env.PYTHON||'python',['-u','-m','elitelab','serve','--no-browser'],{cwd:root,env,windowsHide:true});
  server.stdout.on('data',d=>serverLog+=d);
  server.stderr.on('data',d=>serverLog+=d);
  server.on('exit',code=>{exits.push(code);if(code===75&&!stopping)launch();});
}
try {
  launch();
  const base=`http://127.0.0.1:${oldPort}`;
  let ready=false;
  for(let i=0;i<150;i++) {
    try {ready=(await (await fetch(base+'/api/health',{signal:AbortSignal.timeout(500)})).json()).ready;}catch{}
    if(ready)break;
    await sleep(100);
  }
  assert.ok(ready,serverLog);
  const profile=path.join(temporary,'chrome');
  chrome=spawn(process.env.CHROME_BIN||(process.platform==='win32'?'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe':'google-chrome'),
    ['--headless=new','--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'],
    {windowsHide:true,stdio:'ignore'});
  const debugFile=path.join(profile,'DevToolsActivePort');
  for(let i=0;i<150&&!fs.existsSync(debugFile);i++)await sleep(100);
  assert.ok(fs.existsSync(debugFile),'Chrome did not start');
  const debugPort=Number(fs.readFileSync(debugFile,'utf8').split('\n')[0]);
  const tabs=await (await fetch(`http://127.0.0.1:${debugPort}/json`)).json();
  ws=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);
  await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j;});
  let sequence=0;const pending=new Map();
  ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(m.error):p.resolve(m.result);}};
  const send=(method,params={})=>new Promise((resolve,reject)=>{
    const id=++sequence,timer=setTimeout(()=>reject(new Error('CDP timeout '+method)),10000);
    pending.set(id,{resolve:r=>{clearTimeout(timer);resolve(r);},reject:e=>{clearTimeout(timer);reject(e);}});
    ws.send(JSON.stringify({id,method,params}));
  });
  const evaluate=async expression=>{const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(JSON.stringify(r.exceptionDetails));return r.result.value;};
  await send('Page.enable');
  await send('Page.navigate',{url:base+'/setup/'});
  for(let i=0;i<100;i++){if(await evaluate("document.querySelector('[name=port]')?.value === '"+oldPort+"'"))break;await sleep(100);}
  const otherHostBlocked=await evaluate(`fetch('http://localhost:${oldPort}/api/health',{mode:'no-cors'}).then(()=>false,()=>true)`);
  assert.equal(otherHostBlocked,true);
  await evaluate(`document.querySelector('[name=port]').value='${newPort}';document.querySelector('[data-setup-form]').requestSubmit();true`);
  for(let i=0;i<100;i++){if(await evaluate("!document.querySelector('[data-restart]').hidden"))break;await sleep(100);}
  assert.equal(JSON.parse(fs.readFileSync(settings,'utf8')).port,newPort);
  await evaluate("document.querySelector('[data-restart]').click();true");
  let location='';
  for(let i=0;i<350;i++) {
    try{location=await evaluate('location.href');}catch{}
    if(location===`http://127.0.0.1:${newPort}/`)break;
    await sleep(100);
  }
  assert.equal(location,`http://127.0.0.1:${newPort}/`,serverLog);
  assert.equal(starts,2);assert.deepEqual(exits,[75]);
  assert.equal((await (await fetch(location+'api/health')).json()).ready,true);
  const dashboardPolicy=(await fetch(location)).headers.get('content-security-policy');
  assert.match(dashboardPolicy,/connect-src 'self';/);
  console.log('Changed-port restart passed: process exited 75, relaunched, and browser reached the new dashboard under CSP.');
  await send('Browser.close').catch(()=>{});
} finally {
  stopping=true;ws?.close();server?.kill();chrome?.kill();
}
