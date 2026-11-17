import fs from 'node:fs';
import {setTimeout as sleep} from 'node:timers/promises';

// Chrome publishes DevToolsActivePort before its contents/listener/page are ready.
export async function waitForChromePage(chrome, debugFile, timeout=30000) {
  const deadline=Date.now()+timeout;
  let lastError='No debugger page yet',spawnError;
  const failed=error=>{spawnError=error;};
  chrome.on('error',failed);
  try {
    while(Date.now()<deadline) {
      if(spawnError)throw spawnError;
      if(chrome.exitCode!==null||chrome.signalCode)
        throw Error('Chrome exited before its debugger was ready');
      try {
        const value=fs.readFileSync(debugFile,'utf8').split('\n')[0];
        const port=Number(value);
        if(!/^\d+$/.test(value)||!Number.isInteger(port)||port<1||port>65535)
          throw Error('Chrome debugger port is not ready');
        const response=await fetch(`http://127.0.0.1:${port}/json`,{
          signal:AbortSignal.timeout(Math.max(1,Math.min(500,deadline-Date.now()))),
        });
        if(!response.ok)throw Error('Chrome debugger HTTP '+response.status);
        const pages=await response.json();
        const page=pages.find(p=>p.type==='page'&&p.webSocketDebuggerUrl);
        if(page)return page;
        lastError='Chrome debugger has no page target yet';
      }catch(error){lastError=error.message;}
      await sleep(Math.min(100,Math.max(0,deadline-Date.now())));
    }
    throw Error('Chrome debugger did not become ready: '+lastError);
  }finally{chrome.off('error',failed);}
}
