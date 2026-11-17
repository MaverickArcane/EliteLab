import assert from 'node:assert/strict';
import {EventEmitter} from 'node:events';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import {test} from 'node:test';
import {setTimeout as sleep} from 'node:timers/promises';
import {waitForChromePage} from './chrome-ready.mjs';

test('waits through missing/empty port file, refused connection and missing target',async()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'chrome-ready-'));
  const file=path.join(dir,'DevToolsActivePort');
  const chrome=Object.assign(new EventEmitter(),{exitCode:null,signalCode:null});
  let requests=0,port;
  const server=http.createServer((req,res)=>{
    res.setHeader('Content-Type','application/json');
    res.end(JSON.stringify(++requests===1?[]:[{type:'page',webSocketDebuggerUrl:'ws://127.0.0.1/devtools/page/test'}]));
  });
  // Reserve then release a real local port to exercise ECONNREFUSED before startup.
  const reserve=http.createServer();
  await new Promise(resolve=>reserve.listen(0,'127.0.0.1',resolve));
  port=reserve.address().port;
  await new Promise(resolve=>reserve.close(resolve));
  try{
    const waiting=waitForChromePage(chrome,file,5000);
    await sleep(150);fs.writeFileSync(file,'');
    await sleep(150);fs.writeFileSync(file,String(port)+'\n');
    await sleep(150);await new Promise(resolve=>server.listen(port,'127.0.0.1',resolve));
    const page=await waiting;
    assert.equal(page.webSocketDebuggerUrl,'ws://127.0.0.1/devtools/page/test');
    assert.ok(requests>=2);
    assert.equal(chrome.listenerCount('error'),0);
  }finally{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));if(fs.existsSync(file))fs.unlinkSync(file);fs.rmdirSync(dir);}
});

test('fails with a bounded timeout or exited Chrome instead of hanging',async()=>{
  const chrome=Object.assign(new EventEmitter(),{exitCode:null,signalCode:null});
  await assert.rejects(waitForChromePage(chrome,'missing-debug-file',100),/did not become ready/);
  chrome.exitCode=1;
  await assert.rejects(waitForChromePage(chrome,'missing-debug-file'),/Chrome exited/);
  assert.equal(chrome.listenerCount('error'),0);
});
