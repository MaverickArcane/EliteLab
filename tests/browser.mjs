import {spawn} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import assert from 'node:assert/strict';
import os from 'node:os';
import './profits.mjs';
const dir = path.dirname(new URL(import.meta.url).pathname.replace(/^\/(\w:)/, '$1'));
const sleep = ms => new Promise(r => setTimeout(r, ms));
const server = spawn(process.env.PYTHON || 'python', ['-u', path.join(dir, 'browser_server.py')], {windowsHide:true});
server.stderr.on('data', d => process.stderr.write(d));
let serverText = ''; server.stdout.on('data', d => serverText += d);
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'elitelab-chrome-'));
const chrome = spawn(process.env.CHROME_BIN || (process.platform === 'win32' ? 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe' : 'google-chrome'), ['--headless=new', '--no-sandbox', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'], {windowsHide:true, stdio:'ignore'});
const attacker = http.createServer((req,res) => {res.writeHead(200, {'Content-Type':'text/html'}); res.end('<!doctype html><title>Audit cross-origin test</title>');});
await new Promise(r => attacker.listen(0,'127.0.0.1',r));
let ws, joinServer, memberServer;
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
  // Exercise the carrier desk and real party listener through the browser.
  await evaluate(`document.querySelector('[data-preset="Carrier ops"]').click();true`);
  await sleep(200);
  assert.equal(await evaluate("document.querySelector('#card-trade [data-ptn-missions]')===null"),true);
  await evaluate("document.querySelector('[data-edit-operation]').open=true;document.querySelector('[data-inventory]').open=true;true");
  await evaluate(`(() => {const f=document.querySelector('[data-trade-plan]'); f.elements.commodity.value='gold';f.elements.target.value='1000';f.elements.ship_capacity.value='100';f.elements.source_price.value='100';f.elements.carrier_price.value='200';f.elements.destination_price.value='300';f.requestSubmit();return true;})()`);
  for(let i=0;i<50;i++){await sleep(100);if(await evaluate("Lab.state.trade?.plan?.commodity==='gold'"))break;}
  await evaluate(`(() => {const f=document.querySelector('[data-trade-count]');f.elements.commodity.value='gold';f.elements.stock.value='200';f.requestSubmit();return true;})()`);
  for(let i=0;i<50;i++){await sleep(100);if(await evaluate("Lab.state.trade?.calculation?.runs===8"))break;}
  assert.equal(await evaluate('Lab.state.trade.calculation.runs'),8);
  await evaluate(`document.querySelector('[data-trade-plan] [name=target]').value='1250';document.querySelector('[data-trade-plan] [name=target]').dispatchEvent(new Event('input',{bubbles:true}));true`);
  await fetch(`http://127.0.0.1:${port}/api/trade/reconcile`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({commodity:'gold',stock:300})});
  await sleep(200);
  assert.equal(await evaluate("document.querySelector('[data-trade-plan] [name=target]').value"),'1250');
  const probe=http.createServer();await new Promise(r=>probe.listen(0,'127.0.0.1',r));const partyPort=probe.address().port;await new Promise(r=>probe.close(r));
  await evaluate(`(() => {const f=document.querySelector('[data-party-host]');f.elements.bind.value='127.0.0.1';f.elements.port.value='${partyPort}';f.requestSubmit();return true;})()`);
  for(let i=0;i<50;i++){await sleep(100);if(await evaluate("Lab.state.party?.mode==='leader'"))break;}
  const partyCode=await evaluate('Lab.state.party.code');assert.ok(partyCode);
  const guestReport={cmdr:'<Hauler>',ship:'Type-9',ship_name:'Cargo Runner',system:'Sol',capacity:790,cargo_count:100,cargo:[{key:'gold',name:'Gold',count:100}],telemetry:{vehicle:'ship',game_running:true,shields_up:true,fuel:7.5,fuel_capacity:64,fuel_reservoir:.42,hull_health:.8,supercruise:true,low_fuel:true,destination:'<Galileo>',status_at:new Date().toISOString(),fuel_at:new Date().toISOString()}};
  const reportGuest=()=>fetch(`http://127.0.0.1:${partyPort}/report`,{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+partyCode},body:JSON.stringify({id:'b'.repeat(32),report:guestReport})});
  const guest=await reportGuest();
  assert.equal(guest.status,200);
  await sleep(250);
  assert.ok(await evaluate("document.querySelector('[data-party-members]').textContent.includes('<Hauler>')"));
  assert.equal(await evaluate("document.querySelector('[data-party-members] hauler')===null"),true);
  assert.ok(await evaluate("document.querySelector('[data-party-members]').textContent.includes('7.5 / 64 t') && document.querySelector('[data-party-members]').textContent.includes('Low fuel') && document.querySelector('[data-party-members]').textContent.includes('Supercruise')"));
  assert.equal(await evaluate("document.querySelector('[data-party-members] galileo')===null"),true);
  guestReport.system='Lave';guestReport.telemetry={...guestReport.telemetry,shields_up:false,fuel:5.25,low_fuel:false,supercruise:false,interdicted:true};
  await reportGuest();await sleep(250);
  assert.ok(await evaluate("document.querySelector('[data-party-members]').textContent.includes('5.25 / 64 t') && document.querySelector('[data-party-members]').textContent.includes('Being interdicted') && document.querySelector('[data-party-members]').textContent.includes('Down') && document.querySelector('[data-party-members]').textContent.includes('Lave')"));
  // Inspect the expanded telemetry itself, including at mobile width.
  await evaluate("document.querySelector('[data-telemetry]').open=true;document.querySelector('#card-party').scrollIntoView();true");
  const partyDesktop=await send('Page.captureScreenshot',{format:'png'});
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await sleep(200);
  await evaluate("document.querySelector('[data-telemetry]').open=true;document.querySelector('#card-party').scrollIntoView();true");
  assert.equal(await evaluate('document.body.scrollWidth'),390);
  const partyMobile=await send('Page.captureScreenshot',{format:'png'});
  if(process.env.ELITELAB_SCREENSHOT_DIR){fs.mkdirSync(process.env.ELITELAB_SCREENSHOT_DIR,{recursive:true});fs.writeFileSync(path.join(process.env.ELITELAB_SCREENSHOT_DIR,'party-desktop.png'),Buffer.from(partyDesktop.data,'base64'));fs.writeFileSync(path.join(process.env.ELITELAB_SCREENSHOT_DIR,'party-mobile.png'),Buffer.from(partyMobile.data,'base64'));}
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  // A route is one paired result, with both prices and the distance between stops.
  await evaluate(`window.__realApi=Lab.api;window.__routeQueries=[];Lab.api=async(path,q)=>{if(path!=='/api/trade/opportunities')return window.__realApi.call(Lab,path,q);window.__routeQueries.push(q);return {source:'Ardent / EDDN (fixture)',queried_at:new Date().toISOString(),screened:1,available:1,commodities:[{key:'gold',name:'Gold'}],warnings:[],outdated:false,rows:[{id:'test-op',commodity:'gold',name:'Gold',mean_price:100,stock:300,stock_needs_check:false,quantity:200,runs:2,value:40000,value_label:'Gross spread',per_ton:200,route_distance:25,reported_high:300,sell_percent:100,purchase_cost:20000,buy:{station:'Source Port',system:'Lave',price:100,volume:400,observed_at:new Date().toISOString(),distance:12,arrival_ls:300,pad:'L'},sell:{station:'Destination Port',system:'Sol',price:300,volume:200,observed_at:new Date().toISOString(),distance:30,arrival_ls:400,pad:'L'}}]}};document.querySelector('[data-edit-operation]').open=false;document.querySelector('[data-inventory]').open=false;document.querySelector('[data-refresh]').click();true`);
  for(let i=0;i<50;i++){await sleep(100);if(await evaluate("!!document.querySelector('[data-select-op]:not(:disabled)')"))break;}
  assert.equal(await evaluate("document.querySelector('[data-profile]')===null"),true);
  assert.ok(await evaluate("document.querySelector('[data-opportunities]').textContent.includes('Source Port') && document.querySelector('[data-opportunities]').textContent.includes('Destination Port') && document.querySelector('[data-opportunities]').textContent.includes('25 Ly between stops')"));
  assert.equal(await evaluate("window.__routeQueries.at(-1).route_distance"),100);
  assert.deepEqual(await evaluate("[...document.querySelectorAll('[data-opportunities] [data-inara-market]')].map(a=>({search:new URL(a.href).searchParams.get('search'),path:new URL(a.href).pathname,target:a.target,rel:a.rel}))"),[
    {search:'Source Port [Lave]',path:'/elite/station-market/',target:'_blank',rel:'noopener noreferrer'},
    {search:'Destination Port [Sol]',path:'/elite/station-market/',target:'_blank',rel:'noopener noreferrer'}]);
  assert.ok(await evaluate("[...document.querySelectorAll('[data-opportunities] [data-copy]')].some(b=>b.dataset.copy==='Source Port')"));
  const specialStation='Port "A&B" #1', specialSystem='Test + Sector';
  const specialURL=new URL(await evaluate(`Lab.util.inaraMarket(${JSON.stringify(specialStation)},${JSON.stringify(specialSystem)})`));
  assert.equal(specialURL.searchParams.get('search'),specialStation+' ['+specialSystem+']');
  assert.equal([...specialURL.searchParams].length,1);assert.equal(specialURL.hash,'');
  assert.equal(await evaluate("Lab.util.inaraMarket('Unknown stop', 'Sol')"),null);
  assert.equal(await evaluate("Lab.util.inaraMarket('', '')"),null);
  assert.equal(await evaluate("document.querySelector('[data-opportunities] [data-total-profit]').textContent"),'40,000 Cr');
  assert.equal(await evaluate("document.querySelector('[data-opportunities] [data-owner-profit]').textContent"),'20,000 Cr');
  assert.equal(await evaluate("document.querySelector('[data-opportunities] [data-carrier-buy]').textContent"),'150% | 150 Cr/t');
  assert.equal(await evaluate("document.querySelector('[data-opportunities] [data-carrier-sell]').textContent"),'250% | 250 Cr/t');
  const searchesBeforeSplit = await evaluate('window.__routeQueries.length');
  await evaluate("document.querySelector('[data-crew-load]').value='10';document.querySelector('[data-crew-unload]').value='20';document.querySelector('[data-crew-load]').dispatchEvent(new Event('input'));true");
  await sleep(100);
  assert.equal(await evaluate("document.querySelector('[data-opportunities] [data-owner-profit]').textContent"),'28,000 Cr');
  assert.equal(await evaluate("document.querySelector('[data-opportunities] [data-carrier-buy]').textContent"),'120% | 120 Cr/t');
  assert.equal(await evaluate("document.querySelector('[data-opportunities] [data-carrier-sell]').textContent"),'260% | 260 Cr/t');
  assert.equal(await evaluate('window.__routeQueries.length'),searchesBeforeSplit);
  await evaluate("document.querySelector('[data-crew-load]').value='90';document.querySelector('[data-crew-load]').dispatchEvent(new Event('input'));true");
  await sleep(100);
  assert.equal(await evaluate("document.querySelector('[data-select-op]').disabled"),true);
  await evaluate("document.querySelector('[data-crew-load]').value='25';document.querySelector('[data-crew-unload]').value='25';document.querySelector('[data-crew-load]').dispatchEvent(new Event('input'));true");

  assert.equal(await evaluate("window.__routeQueries.at(-1).min_volume"),0);
  assert.equal(await evaluate("document.querySelector('[data-volume]').disabled"),true);
  assert.equal(await evaluate("Number(document.querySelector('[data-volume]').value)"),await evaluate("Lab.state.journal.carrier.free_space"));
  await evaluate("document.querySelector('[data-auto-volume]').click();document.querySelector('[data-volume]').value='500';document.querySelector('[data-volume]').dispatchEvent(new Event('change'));true");
  await sleep(800);
  assert.equal(await evaluate("window.__routeQueries.at(-1).min_volume"),500);
  assert.equal(await evaluate("document.querySelector('[data-volume]').disabled"),false);
  await evaluate("Lab.state.journal.carrier.free_space=12000;Lab.emit('trade_ui');true");
  assert.equal(await evaluate("document.querySelector('[data-volume]').value"),'500');
  await evaluate("document.querySelector('[data-auto-volume]').click();true");
  await sleep(800);
  assert.equal(await evaluate("window.__routeQueries.at(-1).min_volume"),0);
  assert.equal(await evaluate("document.querySelector('[data-volume]').value"),'12000');

  assert.equal(await evaluate("document.querySelector('[data-commodity]').options.length"),2);
  await evaluate("document.querySelector('[data-route-distance]').value='50';document.querySelector('[data-route-distance]').dispatchEvent(new Event('change'));true");
  await sleep(800);
  assert.equal(await evaluate("window.__routeQueries.at(-1).route_distance"),50);
  await evaluate("document.querySelector('[data-radius]').value='25';document.querySelector('[data-radius]').dispatchEvent(new Event('change'));true");
  await sleep(800);
  assert.equal(await evaluate("window.__routeQueries.at(-1).radius"),25);
  assert.ok(await evaluate("document.querySelector('.trade-toolbar [data-radius]') !== null && document.querySelector('[data-context]').textContent.includes('Both stops: within 25 Ly')"));
  // Manage the trade through owner controls and report actual delivered tonnage.
  await evaluate("document.querySelector('[data-trade-tab=operation]').click();document.querySelector('[data-edit-operation]').open=true;true");
  await evaluate(`(() => {const f=document.querySelector('[data-trade-plan]');f.elements.source.value='Source Port / Lave';f.elements.destination.value='Destination Port / Sol';f.elements.target.value='1300';f.elements.planned_quantity.value='1000';f.elements.crew_enabled.checked=true;f.elements.carrier_mean_price.value='100';f.requestSubmit();return true;})()`);
  for(let i=0;i<50;i++){await sleep(100);if(await evaluate("Lab.state.trade?.plan?.planned_quantity===1000"))break;}
  // Workload previews exclude the owner's direct-transfer share and preserve typed weights.
  assert.equal(await evaluate("document.querySelector('[data-wl-mode]').value"),'live');
  await evaluate("{const mode=document.querySelector('[data-wl-mode]');mode.value='equal';mode.dispatchEvent(new Event('input',{bubbles:true}));}true");
  for(let i=0;i<50;i++){await sleep(100);if(await evaluate("document.querySelector('[data-wl-order]')?.textContent==='500 t'"))break;}
  assert.equal(await evaluate("document.querySelector('[data-wl-order]').textContent"),'500 t');
  await evaluate("document.querySelector('[data-wl-owner]').click();true");
  for(let i=0;i<50;i++){await sleep(100);if(await evaluate("document.querySelector('[data-wl-order]').textContent==='1,000 t'"))break;}
  assert.equal(await evaluate("document.querySelector('[data-wl-order]').textContent"),'1,000 t');
  await evaluate("document.querySelector('[data-wl-owner]').click();var mode=document.querySelector('[data-wl-mode]');mode.value='custom';mode.dispatchEvent(new Event('input',{bubbles:true}));true");
  await evaluate(`const share=document.querySelector('[data-wl-share="${'b'.repeat(32)}"]');share.value='3';share.dispatchEvent(new Event('input',{bubbles:true}));share.focus();true`);
  await reportGuest();await sleep(400);
  assert.equal(await evaluate(`document.querySelector('[data-wl-share="${'b'.repeat(32)}"]').value`),'3');
  assert.equal(await evaluate("document.activeElement.hasAttribute('data-wl-share')"),true);
  assert.equal(await evaluate("document.querySelector('[data-wl-order]').textContent"),'750 t');
  // A slow save cannot accept edits that would be overwritten by its response.
  await evaluate("window.__wlPost=Lab.post;Lab.post=async function(path,body){if(path==='/api/trade/workload' && body.action==='apply')await new Promise(resolve=>window.__releaseApply=resolve);return window.__wlPost.call(this,path,body)};document.querySelector('[data-wl-apply]').click();true");
  for(let i=0;i<50;i++){await sleep(50);if(await evaluate("typeof window.__releaseApply==='function'"))break;}
  await reportGuest();await sleep(150);
  assert.equal(await evaluate("[...document.querySelectorAll('[data-wl-mode], [data-wl-owner], [data-wl-share]')].every(input=>input.disabled)"),true);
  await evaluate("Lab.post=window.__wlPost;window.__releaseApply();true");
  for(let i=0;i<50;i++){await sleep(100);if(await evaluate("Lab.state.trade.workload?.mode==='custom' && !document.querySelector('[data-wl-mode]').disabled"))break;}
  assert.equal(await evaluate("Lab.state.trade.workload.mode"),'custom');
  // Invalid settings must not leave a copyable order from the previous preview.
  await evaluate("for(const input of document.querySelectorAll('[data-wl-share]'))input.value='0';document.querySelector('[data-wl-share]').dispatchEvent(new Event('input',{bubbles:true}));true");
  assert.equal(await evaluate("[...document.querySelectorAll('[data-wl-preview] [data-copy]')].every(button=>button.disabled)"),true);
  for(let i=0;i<50;i++){await sleep(100);if(await evaluate("document.querySelector('[data-wl-message]').textContent.includes('Choose at least one')"))break;}
  assert.equal(await evaluate("document.querySelector('[data-wl-order]')===null"),true);
  await evaluate("var mode=document.querySelector('[data-wl-mode]');mode.value='equal';mode.dispatchEvent(new Event('input',{bubbles:true}));true");
  await evaluate("document.querySelector('[data-op-action=start]').click();true");
  for(let i=0;i<50;i++){await sleep(100);if(await evaluate("Lab.state.party?.operation?.stage==='loading'"))break;}
  assert.equal(await evaluate('Lab.state.trade.operation.stage'),'loading');
  assert.deepEqual(await evaluate("[...document.querySelectorAll('[data-operation] [data-inara-market]')].map(a=>new URL(a.href).searchParams.get('search'))"),['Source Port [Lave]','TST-001','Destination Port [Sol]']);
  assert.ok(await evaluate("document.querySelector('#card-haul [data-copy=\"Lave\"]') !== null && document.querySelector('#card-haul [data-copy=\"Source Port\"]') !== null"));
  assert.ok(await evaluate("document.querySelector('#card-haul').textContent.includes('Transfer to carrier')"));
  assert.equal(await evaluate('Lab.state.party.load_suggestion.next_buy'),400);
  guestReport.capacity=450;await reportGuest();await sleep(250);
  assert.equal(await evaluate('Lab.state.party.load_suggestion.next_buy'),350);
  assert.ok(await evaluate("document.querySelector('[data-crew-roster]').textContent.includes('<Hauler>')"));
  assert.ok(await evaluate("document.querySelector('[data-operation]').textContent.includes('Buy gold at Source Port / Lave')"));
  await evaluate("document.querySelector('[data-operation-notes] textarea').value='Dock at the carrier; wait for departure.';document.querySelector('[data-operation-notes]').requestSubmit();true");
  await sleep(200);
  await evaluate("document.querySelector('[data-delivery] [name=tonnes]').value='100';document.querySelector('[data-delivery]').requestSubmit();true");
  for(let i=0;i<50;i++){await sleep(100);if(await evaluate("Lab.state.trade?.operation?.loaded===100"))break;}
  assert.equal(await evaluate('Lab.state.trade.operation.loaded'),100);
  // Exercise the actual summary controls, including successive DOM rebuilds.
  await evaluate("document.querySelector('[data-op-details=prices] summary').click();document.querySelector('[data-op-details=reports] summary').click();true");
  for(let revision=1;revision<=3;revision++) {
    await evaluate(`Lab.post('/api/trade/operation',{action:'notes',id:Lab.state.trade.operation.id,notes:'Panel update ${revision}'})`);
    await reportGuest();await sleep(1200);
    assert.ok(await evaluate(`document.querySelector('[data-operation]').textContent.includes('Panel update ${revision}')`));
    assert.ok(await evaluate("document.querySelector('[data-op-details=prices]').open && document.querySelector('[data-op-details=reports]').open"));
  }
  await evaluate("document.querySelector('[data-op-details=reports] summary').click();true");
  await evaluate("Lab.post('/api/trade/operation',{action:'notes',id:Lab.state.trade.operation.id,notes:'Reports closed; prices still open.'})");
  await reportGuest();await sleep(1200);
  assert.ok(await evaluate("document.querySelector('[data-op-details=prices]').open && !document.querySelector('[data-op-details=reports]').open"));
  assert.equal(await evaluate('Lab.state.trade.inventory.gold.stock'),300);
  await evaluate("document.querySelector('[data-op-action=pause]').click();true");
  for(let i=0;i<30;i++){await sleep(100);if(await evaluate("Lab.state.trade.operation.paused"))break;}
  assert.ok(await evaluate("document.querySelector('[data-operation]').textContent.includes('Do not begin another run')"));
  await evaluate("document.querySelector('[data-op-action=resume]').click();true");
  for(let i=0;i<30;i++){await sleep(100);if(await evaluate("!Lab.state.trade.operation.paused"))break;}
  assert.equal(await evaluate("document.querySelector('[data-search-view]').hidden"),true);
  assert.equal(await evaluate("document.querySelector('[data-edit-operation]').hidden"),true);
  await evaluate("document.querySelector('[data-telemetry]').open=false;scrollTo(0,0);true");
  const carrierDesktop=await send('Page.captureScreenshot',{format:'png'});
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await sleep(200);
  assert.equal(await evaluate('document.body.scrollWidth'),390);
  const carrierMobile=await send('Page.captureScreenshot',{format:'png'});
  if(process.env.ELITELAB_SCREENSHOT_DIR){fs.mkdirSync(process.env.ELITELAB_SCREENSHOT_DIR,{recursive:true});fs.writeFileSync(path.join(process.env.ELITELAB_SCREENSHOT_DIR,'carrier-desktop.png'),Buffer.from(carrierDesktop.data,'base64'));fs.writeFileSync(path.join(process.env.ELITELAB_SCREENSHOT_DIR,'carrier-mobile.png'),Buffer.from(carrierMobile.data,'base64'));}
  // A second independent EliteLab and browser view exercise the actual crew UI.
  memberServer = spawn(process.env.PYTHON || 'python', ['-u', path.join(dir, 'browser_server.py')], {windowsHide:true});
  let memberText = ''; memberServer.stdout.on('data', d => memberText += d);
  memberServer.stderr.on('data', d => process.stderr.write(d));
  for(let i=0;i<100 && !memberText.trim();i++) await sleep(100);
  const memberPort = Number(memberText.trim()); assert.ok(memberPort);
  const postMember = async (route, body) => {const response=await fetch(`http://127.0.0.1:${memberPort}${route}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}); assert.equal(response.status,200);return response.json();};
  await postMember('/audit/ship', {cmdr:'CMDR Crew',capacity:200,count:0});
  await postMember('/api/party/join',{url:`http://127.0.0.1:${partyPort}`,code:partyCode});
  // A mid-haul join receives an equal share without owner interaction.
  for(let i=0;i<50;i++){await sleep(100);if(await evaluate("Lab.state.trade.workload.members.some(m=>m.cmdr==='CMDR Crew' && m.loading_target===300)"))break;}
  assert.ok(await evaluate("Lab.state.trade.workload.members.some(m=>m.cmdr==='CMDR Crew' && m.loading_target===300)"));
  assert.equal(await evaluate("document.querySelector('[data-wl-order]').textContent"),'600 t');
  assert.ok(await evaluate("document.querySelector('[data-wl-message]').textContent.includes('split automatically')"));

  await send('Page.navigate',{url:`http://127.0.0.1:${memberPort}`});
  for(let i=0;i<50;i++){await sleep(100);if(await evaluate("!!document.querySelector('[data-preset=\"Carrier ops\"]')"))break;}
  await evaluate("document.querySelector('[data-preset=\"Carrier ops\"]').click();true");
  for(let i=0;i<50;i++){await sleep(100);if(await evaluate("document.querySelector('[data-value=action]')?.textContent==='Buy your next load'"))break;}
  assert.equal(await evaluate("document.querySelector('[data-value=action]').textContent"),'Buy your next load');
  assert.ok(await evaluate("!document.querySelector('[data-party-leave]').hidden && !document.querySelector('[data-party-leave]').closest('details') && document.querySelector('[data-party-leave]').textContent==='Leave party'"));
  assert.equal(await evaluate("document.querySelector('[data-value=quantity]').textContent"),'200 t');
  assert.equal(await evaluate("document.querySelector('[data-value=rate]').textContent"),'50 Cr');
  assert.equal(await evaluate("document.querySelector('[data-value=run-pay]').textContent"),'10,000 Cr');
  for(let i=0;i<30;i++){await sleep(100);if(await evaluate("document.querySelector('[data-value=profit-estimated]')?.textContent.endsWith(' Cr')"))break;}
  const expectedPersonalProfit=await evaluate("document.querySelector('[data-value=profit-estimated]').textContent");
  assert.ok(['31,650 Cr','31,700 Cr'].includes(expectedPersonalProfit));
  assert.equal(await evaluate("document.querySelector('[data-value=profit-remaining]').textContent"),expectedPersonalProfit);
  assert.deepEqual(await evaluate("[...document.querySelectorAll('[data-haul-inara]')].map(a=>({search:new URL(a.href).searchParams.get('search'),hidden:a.hidden,target:a.target,rel:a.rel}))"),[
    {search:'Source Port [Lave]',hidden:false,target:'_blank',rel:'noopener noreferrer'},
    {search:'TST-001',hidden:false,target:'_blank',rel:'noopener noreferrer'}]);
  await send('Browser.grantPermissions',{origin:`http://127.0.0.1:${memberPort}`,permissions:['clipboardReadWrite','clipboardSanitizedWrite']});
  await send('Emulation.setFocusEmulationEnabled',{enabled:true});
  await evaluate("document.querySelector('[data-haul-copy=pickup-system]').click();true");await sleep(150);
  assert.equal(await evaluate('navigator.clipboard.readText()'),'Lave');
  await evaluate("document.querySelector('[data-haul-copy=pickup-station]').click();true");await sleep(150);
  assert.equal(await evaluate('navigator.clipboard.readText()'),'Source Port');
  await evaluate("document.querySelector('[data-haul-copy=quantity]').click();true");await sleep(150);
  assert.equal(await evaluate('navigator.clipboard.readText()'),'200');
  // Missing stops remove stale links, and live rendering restores them without replacing nodes.
  assert.ok(await evaluate("(() => {const el=document.querySelector('#card-haul .body'),card=Lab.cards.haul,S=structuredClone(Lab.state);S.party.desk.pickup={station:'Unknown stop',system:null};card.render(el,S);const link=el.querySelector('[data-haul-inara=pickup]');const hidden=link.hidden && !link.hasAttribute('href');card.render(el,Lab.state);return hidden && !link.hidden && link===el.querySelector('[data-haul-inara=pickup]');})()"));
  // Persistent destination nodes preserve text selection during live cargo changes.
  await evaluate("window.__pickupNode=document.querySelector('[data-value=pickup-system]');const range=document.createRange();range.selectNodeContents(window.__pickupNode);getSelection().removeAllRanges();getSelection().addRange(range);true");
  await postMember('/audit/ship',{cmdr:'CMDR Crew',capacity:200,count:80});
  for(let i=0;i<30;i++){await sleep(100);if(await evaluate("document.querySelector('[data-value=quantity]')?.textContent==='120 t'"))break;}
  assert.equal(await evaluate('getSelection().toString()'),'Lave');
  assert.equal(await evaluate("window.__pickupNode===document.querySelector('[data-value=pickup-system]')"),true);
  assert.equal(await evaluate("document.querySelector('[data-value=quantity]').textContent"),'120 t');
  await evaluate("getSelection().removeAllRanges();document.querySelector('[data-manual-details]').open=true;const input=document.querySelector('[data-delivery] [name=tonnes]');input.value='80';input.dispatchEvent(new Event('input',{bubbles:true}));input.focus();true");
  await postMember('/audit/ship',{cmdr:'CMDR Crew',capacity:180,count:80});await sleep(300);
  assert.equal(await evaluate("document.querySelector('[data-delivery] [name=tonnes]').value"),'80');
  assert.equal(await evaluate("document.activeElement===document.querySelector('[data-delivery] [name=tonnes]')"),true);
  await evaluate("document.querySelector('[data-delivery]').requestSubmit();true");
  for(let i=0;i<30;i++){await sleep(100);if(await evaluate("document.querySelector('[data-value=loaded]')?.textContent==='80 / 300 t'"))break;}
  assert.equal(await evaluate("document.querySelector('[data-value=loaded]').textContent"),'80 / 300 t');
  assert.equal(await evaluate("document.querySelector('[data-value=earned]').textContent"),'4,000 Cr');
  assert.equal(await evaluate("document.querySelector('[data-value=profit-estimated]').textContent"),expectedPersonalProfit);
  assert.ok(await evaluate("document.querySelector('[data-value=profit-breakdown]').textContent.includes('loading 4,000 Cr | unloading 0 Cr')"));
  assert.ok(await evaluate("[...document.querySelectorAll('[data-crew-roster] tr')].some(r=>r.textContent.includes('CMDR Crew') && r.querySelector('[data-profit-recorded]')?.textContent==='4,000 Cr')"));
  await postMember('/audit/ship',{cmdr:'CMDR Crew',capacity:200,count:0});
  await evaluate("document.querySelector('[data-manual-details]').open=false;true");
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});await evaluate('scrollTo(0,0);true');await sleep(300);
  const crewDesktop=await send('Page.captureScreenshot',{format:'png'});
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await evaluate('scrollTo(0,0);true');await sleep(200);
  assert.equal(await evaluate('document.body.scrollWidth'),390);
  const crewMobile=await send('Page.captureScreenshot',{format:'png'});
  if(process.env.ELITELAB_SCREENSHOT_DIR){fs.writeFileSync(path.join(process.env.ELITELAB_SCREENSHOT_DIR,'crew-desktop.png'),Buffer.from(crewDesktop.data,'base64'));fs.writeFileSync(path.join(process.env.ELITELAB_SCREENSHOT_DIR,'crew-mobile.png'),Buffer.from(crewMobile.data,'base64'));}
  await postMember('/api/party/leave',{});
  await send('Page.navigate',{url:`http://127.0.0.1:${port}`});
  for(let i=0;i<50;i++){await sleep(100);if(await evaluate("!!document.querySelector('[data-op-action=depart]')"))break;}
  assert.ok(await evaluate("document.querySelector('[data-crew-roster]').textContent.includes('CMDR Crew')"));
  for(let i=0;i<30;i++){await sleep(100);if(await evaluate("!!document.querySelector('[data-op-details=reports] [data-profit-recorded]')"))break;}
  assert.ok(await evaluate("[...document.querySelectorAll('[data-op-details=reports] tr')].some(r=>r.textContent.includes('CMDR Crew') && r.querySelector('[data-profit-recorded]')?.textContent==='4,000 Cr')"));
  await evaluate("document.querySelector('[data-op-action=depart]').click();true");
  for(let i=0;i<30;i++){await sleep(100);if(await evaluate("Lab.state.trade.operation.stage==='transit'"))break;}
  await evaluate("document.querySelector('[data-op-action=unload]').click();true");
  for(let i=0;i<30;i++){await sleep(100);if(await evaluate("Lab.state.trade.operation.stage==='unloading'"))break;}
  assert.equal(await evaluate('Lab.state.trade.plan.target'),300);
  assert.equal(await evaluate('Lab.state.trade.plan.carrier_price'),250);
  await evaluate("document.querySelector('[data-op-action=complete]').click();true");
  for(let i=0;i<30;i++){await sleep(100);if(await evaluate("Lab.state.trade.operation.stage==='complete'"))break;}
  assert.equal(await evaluate('Lab.state.trade.operation.stage'),'complete');
  // Review a correction against live progress, then download anonymized evidence.
  const auditMember=await evaluate("Object.entries(Lab.state.trade.operation.reports).find(([,r])=>r.cmdr==='CMDR Crew')[0]");
  const auditJob=await evaluate('Lab.state.trade.operation.id');
  await evaluate(`document.querySelector('[data-haul-history]').open=true;var f=document.querySelector('[data-haul-correction]');f.elements.member.value='${auditMember}';f.elements.member.dispatchEvent(new Event('change'));f.elements.tonnes.value='70';f.elements.reason.value='<audit-correction> duplicate report';f.elements.tonnes.dispatchEvent(new Event('input',{bubbles:true}));true`);
  const lateReport=await fetch(`http://127.0.0.1:${partyPort}/report`,{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+partyCode},body:JSON.stringify({id:auditMember,report:{cmdr:'CMDR Crew',capacity:200,cargo_count:0,cargo:[],work:{operation_id:auditJob,loading:90,unloading:0}}})});
  assert.equal(lateReport.status,200);
  for(let i=0;i<50;i++){await sleep(100);if(await evaluate("document.querySelector('[data-correction-status]').textContent.includes('New progress')"))break;}
  assert.equal(await evaluate("document.querySelector('[data-haul-correction] [name=tonnes]').value"),'70');
  assert.equal(await evaluate("document.querySelector('[data-haul-correction] [type=submit]').disabled"),true);
  await evaluate("document.querySelector('[data-correction-refresh]').click();var f=document.querySelector('[data-haul-correction]');f.elements.tonnes.value='70';f.elements.reason.value='<audit-correction> duplicate report';f.elements.reason.dispatchEvent(new Event('input',{bubbles:true}));f.requestSubmit();true");
  for(let i=0;i<50;i++){await sleep(100);if(await evaluate(`Lab.state.trade.operation.reports['${auditMember}'].loading===70`))break;}
  assert.equal(await evaluate(`Lab.state.trade.operation.reports['${auditMember}'].loading`),70);
  assert.equal(await evaluate("document.querySelector('[data-haul-history-list] audit-correction')===null"),true);
  assert.ok(await evaluate("document.querySelector('[data-haul-history-list]').textContent.includes('<audit-correction> duplicate report')"));
  await evaluate("window.__objectURL=URL.createObjectURL.bind(URL);URL.createObjectURL=function(blob){blob.text().then(text=>window.__exportText=text);return window.__objectURL(blob)};document.querySelector('[data-haul-export]').click();true");
  for(let i=0;i<50;i++){await sleep(100);if(await evaluate("!!window.__exportText"))break;}
  const exportedText=await evaluate('window.__exportText');
  const exported=JSON.parse(exportedText);
  assert.equal(exported.format,'elitelab-hauling-diagnostics-v1');
  for(const secret of [partyCode,auditMember,'CMDR Crew','<Hauler>','<audit-correction>'])assert.ok(!exportedText.includes(secret));
  assert.ok(exported.reports.some(r=>r.reported.loading===90 && r.credited.loading===70 && r.adjustments.loading===-20));
  assert.equal(await evaluate('document.body.scrollWidth'),390);
  // Preparing another plan clears an ended operation, then starting it gets a new id.
  const endedOperation=await evaluate('Lab.state.trade.operation.id');
  await evaluate("document.querySelector('[data-edit-operation]').open=true;true");
  await evaluate(`(() => {const f=document.querySelector('[data-trade-plan]');f.elements.mode.value='load';f.elements.target.value='1300';f.elements.planned_quantity.value='0';f.requestSubmit();return true;})()`);
  for(let i=0;i<50;i++){await sleep(100);if(await evaluate('Lab.state.trade.operation===null'))break;}
  assert.equal(await evaluate('Lab.state.trade.operation'),null);
  assert.equal(await evaluate("document.querySelector('[data-op-action=start]').textContent"),'Start loading');
  assert.ok(await evaluate("document.querySelector('[data-crew-summary]').textContent.includes('not started') && !document.querySelector('[data-crew-summary] progress')"));
  await evaluate("const ownerToggle=document.querySelector('[data-wl-owner]');if(ownerToggle.checked)ownerToggle.click();true");
  await reportGuest();
  await evaluate("document.querySelector('[data-op-action=start]').click();true");
  for(let i=0;i<50;i++){await sleep(100);if(await evaluate("Lab.state.trade.operation?.stage==='loading'"))break;}
  assert.equal(await evaluate('Lab.state.trade.operation?.stage'),'loading',await evaluate("document.querySelector('#toasts').textContent+' '+document.querySelector('[data-wl-message]').textContent"));
  assert.notEqual(await evaluate('Lab.state.trade.operation.id'),endedOperation);
  assert.equal(await evaluate('Lab.state.trade.operation.quantity'),1000);
  assert.equal(await evaluate('Lab.state.trade.workload.owner_hauls'),false);
  await evaluate("const range=document.createRange();range.selectNodeContents(document.querySelector('[data-crew-summary]'));getSelection().removeAllRanges();getSelection().addRange(range);true");
  await evaluate("document.querySelector('[data-op-action=cancel]').click();true");
  for(let i=0;i<50;i++){await sleep(100);if(await evaluate("Lab.state.trade.operation?.stage==='cancelled'"))break;}
  assert.equal(await evaluate("document.querySelector('[data-op-action=start]').textContent"),'Start new loading');
  assert.ok(await evaluate("document.querySelector('[data-crew-summary]').textContent.includes('Trade cancelled') && !document.querySelector('[data-crew-summary] progress')"));
  assert.equal(await evaluate("document.querySelector('[data-crew-roster]').textContent"),'');
  await evaluate("getSelection().removeAllRanges();true");
  // Live mode sends the final 1,160 t to the 1,200 t ship, then reallocates on leave.
  await fetch(`http://127.0.0.1:${partyPort}/report`,{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+partyCode},body:JSON.stringify({id:'b'.repeat(32),report:guestReport,leave:true})});
  await fetch(`http://127.0.0.1:${port}/audit/ship`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cmdr:'Owner',capacity:1136,count:0})});
  await postMember('/audit/ship',{cmdr:'CMDR Crew',capacity:1200,count:0});
  await postMember('/api/party/join',{url:`http://127.0.0.1:${partyPort}`,code:partyCode});
  await evaluate("Lab.post('/api/trade/plan',{...Lab.state.trade.plan,target:1160,planned_quantity:1160})");
  for(let i=0;i<50;i++){await sleep(100);if(await evaluate("Lab.state.trade.operation===null && document.querySelector('[data-wl-mode]').value==='live'"))break;}
  await evaluate("const toggle=document.querySelector('[data-wl-owner]');if(!toggle.checked)toggle.click();document.querySelector('[data-op-action=start]').click();true");
  for(let i=0;i<50;i++){await sleep(100);if(await evaluate("Lab.state.party.load_suggestion?.members.some(m=>m.cmdr==='CMDR Crew' && m.next_buy===1160)"))break;}
  assert.equal(await evaluate("Lab.state.trade.workload.mode"),'live');
  assert.equal(await evaluate("document.querySelector('[data-wl-order]').textContent"),'1,160 t');
  assert.deepEqual(await evaluate("[...document.querySelectorAll('[data-party-inara]')].map(a=>new URL(a.href).searchParams.get('search'))"),['Source Port [Lave]','TST-001','Destination Port [Sol]']);
  await send('Page.navigate',{url:`http://127.0.0.1:${memberPort}`});
  for(let i=0;i<50;i++){await sleep(100);if(await evaluate("document.querySelector('[data-value=quantity]')?.textContent==='1,160 t'"))break;}
  assert.equal(await evaluate("document.querySelector('[data-value=quantity]').textContent"),'1,160 t');
  assert.ok(await evaluate("document.querySelector('[data-crew-roster]').textContent.includes('Next pickup: 1,160 t')"));
  assert.equal(await evaluate("document.querySelectorAll('[data-party-inara]').length"),3);
  await postMember('/api/party/leave',{});
  await send('Page.navigate',{url:`http://127.0.0.1:${port}`});
  for(let i=0;i<50;i++){await sleep(100);if(await evaluate("document.querySelector('[data-value=quantity]')?.textContent==='1,136 t'"))break;}
  assert.equal(await evaluate("document.querySelector('[data-value=quantity]').textContent"),'1,136 t');
  assert.equal(await evaluate("document.querySelector('[data-wl-order]').textContent"),'0 t');
  await evaluate("Lab.post('/api/trade/operation',{action:'cancel',id:Lab.state.trade.operation.id})");
  await evaluate("document.querySelector('[data-party-leave]').click();true");
  for(let i=0;i<50;i++){await sleep(100);if(await evaluate("Lab.state.party?.mode==='idle'"))break;}
  assert.equal(await evaluate('Lab.state.party.mode'),'idle');
  // Submit the real join form to a loopback leader, including pasted whitespace.
  const joinCode='test_party_code_0123456789abcdef';let acceptJoin=false, receivedJoin=false;
  joinServer=http.createServer((req,res)=>{
    const chunks=[];req.on('data',chunk=>chunks.push(chunk));req.on('end',()=>{
      const valid=req.url==='/report' && req.headers.authorization==='Bearer '+joinCode;
      receivedJoin=valid;
      res.writeHead(valid && acceptJoin ? 200 : 403,{'Content-Type':'application/json'});
      res.end(JSON.stringify(valid && acceptJoin ? {members:[],plan:null,operation:null} : {error:'invalid party code'}));
    });
  });
  await new Promise(r=>joinServer.listen(0,'127.0.0.1',r));
  const joinAddress='127.0.0.1:'+joinServer.address().port;
  await evaluate(`(() => {const f=document.querySelector('[data-party-join]');f.closest('details').open=true;f.elements.url.value='  ${joinAddress}  ';f.elements.code.value='  ${joinCode}  ';Lab.emit('journal');return true;})()`);
  assert.equal(await evaluate("document.querySelector('[data-party-join] [name=code]').value"),'  '+joinCode+'  ');
  await evaluate("document.querySelector('[data-party-join]').requestSubmit();true");
  for(let i=0;i<50;i++){await sleep(100);if(await evaluate("document.querySelector('[data-party-join-error]').textContent.includes('Party code rejected')"))break;}
  assert.equal(receivedJoin,true);
  assert.ok(await evaluate("document.querySelector('[data-party-join-error]').textContent.includes('Party code rejected')"));
  assert.equal(await evaluate("document.querySelector('[data-party-join] [name=code]').value"),joinCode);
  acceptJoin=true;
  await evaluate("document.querySelector('[data-party-join]').requestSubmit();true");
  for(let i=0;i<50;i++){await sleep(100);if(await evaluate("Lab.state.party.mode==='member'"))break;}
  assert.equal(await evaluate('Lab.state.party.mode'),'member');
  assert.equal(await evaluate("document.querySelector('[data-party-join] [name=code]').value"),'');
  await evaluate("document.querySelector('[data-party-leave]').click();true");
  for(let i=0;i<50;i++){await sleep(100);if(await evaluate("Lab.state.party.mode==='idle'"))break;}
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
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
  await fetch(`http://127.0.0.1:${port}/api/materials/wishlist`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({items:{arsenic:10}})});
  await send('Page.navigate',{url:`http://127.0.0.1:${attacker.address().port}`});await sleep(250);
  const crossOrigin=await evaluate(`fetch('http://127.0.0.1:${port}/api/materials/wishlist',{method:'POST',mode:'no-cors',headers:{'Content-Type':'text/plain'},body:JSON.stringify({items:{},mode:'clear'})}).then(r=>({type:r.type})).catch(e=>({error:String(e)}))`);
  const wishlistAfter=await (await fetch(`http://127.0.0.1:${port}/api/materials/wishlist`)).json();
  const results={desktop:before,inputAfter,engineeringCards,mobile,crossOrigin,wishlistAfter,browserExceptions:errors};
  assert.equal(inputAfter.name,'arsenic'); assert.equal(inputAfter.qty,'5'); assert.equal(inputAfter.focus,'mat-q'); assert.equal(mobile.bodyWidth,390); assert.equal(wishlistAfter.wishlist[0].need,10); assert.deepEqual(errors,[]); assert.deepEqual(before.renderErrors,[]);console.log(JSON.stringify(results,null,2));
  await send('Page.navigate',{url:`http://127.0.0.1:${port}`});
  for(let i=0;i<50;i++){await sleep(100);if(await evaluate("!!document.querySelector('#app-quit') && !!window.Lab?.post && document.querySelectorAll('#grid .card').length>1"))break;}
  await evaluate("document.querySelector('#app-quit').click();true");
  for(let i=0;i<30;i++){await sleep(100);if(await evaluate("document.querySelector('#h-live').textContent==='stopped'"))break;}
  assert.equal(await evaluate("document.querySelector('#h-live').textContent"),'stopped');
  assert.equal(await evaluate("document.querySelectorAll('#grid .card').length"),1);
  assert.deepEqual(errors,[]);
  await send('Browser.close').catch(()=>{});
} finally {ws?.close();server.kill();memberServer?.kill();chrome.kill();attacker.close();joinServer?.close();}
