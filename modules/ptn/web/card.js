/* Hauler-first discovery and a journal-backed, owner-reviewed PTN posting workflow. */
(() => {
  const {esc,fmt,ls}=Lab.util, KEY='ptn.preferences.v1';
  const money=n=>`${fmt(n)} Cr`, short=n=>n==null?'Unknown':`${(n/1e6).toLocaleString(undefined,{maximumFractionDigits:2})}m`;
  const age=iso=>{const t=Date.parse(iso);if(!Number.isFinite(t))return 'Age unknown';const m=Math.max(0,Math.floor((Date.now()-t)/60000));return m<60?`${m} min ago`:`${Math.floor(m/60)} h ago`;};
  const button=(action,text,cls='',disabled=false)=>`<button type="button" data-ptn-action="${action}" class="${cls}" ${disabled?'disabled':''}>${text}</button>`;
  const copy=(text,label)=>`<button type="button" class="mini" data-ptn-copy="${esc(text)}">${label}</button>`;
  const link=(href,text)=>`<a href="${esc(href)}" target="_blank" rel="noopener noreferrer">${text}</a>`;
  const metric=(label,value,sub='',cls='')=>`<div class="ptn-metric ${cls}"><span class="k">${label}</span><strong>${value}</strong>${sub?`<small>${sub}</small>`:''}</div>`;
  const field=(name,label,value,min=0,max=1e9)=>`<label>${label}<input name="${name}" type="number" min="${min}" max="${max}" step="1" value="${esc(value)}" required></label>`;
  const stages=['scouting','loading','transit','unloading','complete'];
  const stageNames=['Scout','Load','Move','Unload','Complete'];
  const tabs={find:'Find trades',run:'Scout & run',advert:'Advert',board:'Public board'};
  const stop=(s,title,scouted=false)=>`<section class="ptn-stop"><div class="ptn-stop-label"><span class="k">${title}</span><span class="tag ${scouted?'ok':''}">${scouted?'Scouted':'Reported'}</span></div>
    <h4>${esc(s.station)}</h4><div class="ptn-system">${esc(s.system)}</div><div class="ptn-stop-price">${money(s.price)}<small> / t</small></div>
    <div class="note">${fmt(s.volume)} t ${title.includes('Load')?'supply':'demand'} &middot; ${fmt(Math.round(s.arrival_ls))} Ls from arrival</div>
    <div class="note ptn-body">Park near <b>${esc(s.body||'body to confirm in system map')}</b></div>
    <div class="ptn-actions">${copy(s.system,'Copy system')}${copy(s.station,'Copy station')}${link(Lab.util.inaraMarket(s.station,s.system),'Inara')}</div>
    <small class="muted">${esc(s.source)} &middot; ${age(s.observed_at)}</small></section>`;

  function searchForm(u,d){
    const p=u.prefs;
    return `<form data-ptn-search class="ptn-search"><div class="k">Route search</div><h3>Search settings</h3>
      <p class="note">Payout floors apply to each leg. Nearby orbital stations with large pads only.</p>
      <button type="submit" class="primary ptn-scan" ${u.busy||d.searching?'disabled':''}>${u.busy||d.searching?'Searching markets...':'Search routes'}</button>
      <div class="ptn-presets">${[20000,30000,40000].map(n=>`<button type="button" class="mini ${p.loading_floor===n&&p.unloading_floor===n?'primary':''}" data-ptn-payout="${n}">${n/1000}k / leg</button>`).join('')}</div>
      <div class="ptn-fields">${field('loading_floor','Loading profit / t',p.loading_floor,1,1000000)}${field('unloading_floor','Unloading profit / t',p.unloading_floor,1,1000000)}${field('quantity','Order size / t',p.quantity,1,25000)}${field('owner_floor','Carrier margin / t',p.owner_floor,0,1000000)}</div>
      <label class="ptn-check-line"><span><input type="checkbox" name="share_surplus" ${p.share_surplus?'checked':''}> Share remaining spread with haulers</span><small>Split the remaining spread across both legs after reserving your carrier margin.</small></label>
      <div class="ptn-check-line"><label><input type="checkbox" name="skip_common" ${p.skip_common?'checked':''}> Skip common carrier cargo</label><small>${esc((d.common||[]).join(', '))}</small></div>
      <label class="ptn-check-line"><span><input type="checkbox" name="avoid_active" ${p.avoid_active?'checked':''}> Skip commodities on the public PTN board</span><small>Official adverts only; affiliate competition remains unknown.</small></label>
      <label>Also exclude<input name="excluded" value="${esc(p.excluded)}" placeholder="Comma-separated commodities"></label>
      ${button('exclude-cargo','Exclude cargo already aboard','mini')}
      <details class="ptn-more"><summary>Distance, freshness & hauler scenario</summary><div class="ptn-fields">
        ${field('radius','Both stops within / Ly',p.radius,1,500)}${field('max_hop','Carrier leg at most / Ly',p.max_hop,1,500)}${field('hours','Report age / hours',p.hours,1,24)}${field('arrival','Arrival approach / Ls',p.arrival,1,50000)}
        ${field('breadth','Commodities to scan',p.breadth,1,48)}${field('cost_reserve','Fuel & fees reserve / Cr',p.cost_reserve,0,1e10)}${field('hauler_capacity','Example hold / t',p.hauler_capacity,1,1000)}${field('cycle_minutes','Example round trip / min',p.cycle_minutes,1,60)}${field('haulers','Example haulers',p.haulers,1,50)}</div><p class="note">Cycle time and hauler count are your assumptions, not measured traffic. The reserve is deducted from carrier margin.</p></details>
      <p class="note">Both stations must support the full order. Zero demand is left unconfirmed, never treated as unlimited.</p></form>`;
  }

  function routeCard(r,u,index){
    const c=r.pricing,p=r.settings,selected=u.data.plan?.route.id===r.id;
    const requiredSpread=p.loading_floor+p.unloading_floor+Math.max(p.owner_floor,Math.ceil(p.cost_reserve/r.quantity)),shortfall=Math.max(0,requiredSpread-c.gross_per_ton);
    return `<article class="ptn-route ${r.viable?'':'ptn-prospect'}"><div class="ptn-route-top"><div class="ptn-route-name"><span class="ptn-rank">${String(index+1).padStart(2,'0')}</span><div><span class="k">${r.viable?'Meets payout requirements':'Rejected candidate'}</span><h3>${esc(r.name)}</h3></div></div><span class="tag ${r.viable?'ok':'warn'}">${r.viable?'Requires station checks':shortfall?`${fmt(shortfall)} Cr/t shortfall`:'Requirements not met'}</span></div>
      <div class="ptn-route-numbers">${r.viable?`${metric('Hauler / loading',money(c.loading_per_ton)+'/t',`${short(c.loading_per_ton*p.hauler_capacity)} Cr / ${fmt(p.hauler_capacity)} t`,'ptn-hauler')}${metric('Hauler / unloading',money(c.unloading_per_ton)+'/t',`${short(c.unloading_per_ton*p.hauler_capacity)} Cr / ${fmt(p.hauler_capacity)} t`,'ptn-hauler')}${metric('Carrier after reserve',short(c.owner_after_reserve)+' Cr',`${money(c.owner_per_ton)}/t margin`)}`:`${metric('Available station spread',money(c.gross_per_ton)+'/t')}${metric('Required minimum spread',money(requiredSpread)+'/t')}${metric('Payout shortfall',shortfall?money(shortfall)+'/t':'See rejection details','','warn')}`}</div>
      <div class="ptn-stops">${stop(r.buy,'Load from')}${stop(r.sell,'Unload to')}</div>
      <div class="ptn-route-foot"><div class="note">${fmt(r.quantity)} t &middot; ${fmt(r.route_distance)} Ly carrier leg &middot; ${r.supply_buffer}&times; supply buffer<br>${r.official_competitors==null?'Official competition unknown':`${r.official_competitors} other official loading adverts at source`}${r.viable?`<br>Scenario: ${short(r.hauler_hour_scenario)} Cr/h at your ${p.cycle_minutes} min round trip`:''}</div>
      <button type="button" class="${r.viable?'primary':''}" data-ptn-select="${esc(r.id)}" ${u.busy?'disabled':''}>${selected?'Restart station checks':r.viable?'Check this route':'Inspect candidate'}</button></div>
      ${r.reasons.length?`<p class="ptn-reasons">${r.reasons.map(esc).join(' ')}</p>`:''}</article>`;
  }

  function discovery(u,d){
    const r=d.result,qualified=r?.rows.filter(row=>row.viable)||[],near=r?.rows.filter(row=>!row.viable)||[];
    const rows=u.near?near:qualified;
    return `<div class="ptn-discovery">${searchForm(u,d)}<section class="ptn-opportunities"><div class="ptn-section-heading"><div><span class="k">Search results</span><h3>${r?`${qualified.length} matching routes`:'Carrier routes'}</h3></div><div class="ptn-actions">${button('qualified',`Matching ${qualified.length}`,`mini ${!u.near?'primary':''}`)}${button('near',`Rejected ${near.length}`,`mini ${u.near?'primary':''}`)}</div></div>
      ${r?`<p class="note">${r.scanned} commodities scanned near ${esc(r.origin)} &middot; ${age(r.checked_at)}. ${esc(r.scope)}</p>`:''}
      ${r?.warnings.length?`<details class="ptn-more"><summary class="warn">${r.warnings.length} data notes</summary>${r.warnings.map(w=>`<p class="note">${esc(w)}</p>`).join('')}</details>`:''}
      ${rows.length?rows.map((row,i)=>routeCard(row,u,i)).join(''):`<div class="ptn-empty"><h3>${r?u.near?'No rejected candidates.':'No routes match these filters.':'Search carrier routes'}</h3><p>${r?'Change the search area, commodity exclusions or payout minimums to search again. Rejected candidates show which requirements failed.':'Compare station prices, supply, demand and carrier margin using the settings on the left.'}</p>${r&&near.length&&!u.near?button('near','View rejected candidates'):''}</div>`}
    </section></div>`;
  }

  function operation(u,d){
    const p=d.plan,o=d.operation;
    if(!p)return `<div class="ptn-empty"><span class="k">Your next operation</span><h3>Choose a route to start scouting.</h3><p>Station visits, actual carrier prices and owner checks build one dependable trade advert.</p>${button('find','Find a trade','primary')}</div>`;
    const s=p.route.settings,price=o.pricing;
    const next={scouting:['loading','Open loading'],loading:['transit','Load finished: ready to move'],transit:['unloading','Open unloading'],unloading:['complete','Unload finished: complete']};
    const draft=u.draft;
    return `<div class="ptn-run"><div class="ptn-operation-title"><div><span class="k">${esc(p.carrier)} (${esc(p.callsign)})</span><h3>${esc(p.name)} <span class="muted">/ ${fmt(p.route.quantity)} t</span></h3></div><span class="tag">${esc(p.stage)}</span></div>
      <ol class="ptn-stages">${stages.map((stage,i)=>`<li class="${stage===p.stage?'is-current':stages.indexOf(p.stage)>i?'is-done':''}"><span>${i+1}</span>${stageNames[i]}</li>`).join('')}</ol>
      <div class="ptn-run-grid"><div><div class="ptn-stops">${['buy','sell'].map((side,i)=>`<div>${stop(o[side],i===0?'Load from':'Unload to',!!p.scouts[side])}<button type="button" class="ptn-capture" data-ptn-capture="${side}" ${u.busy?'disabled':''}>Capture this station's current market</button></div>`).join('')}</div>
        <p class="note">Dock at each station and open Commodities, then capture its journal snapshot. Station price, volume and carrier 100% reference are saved with their observation time. Rechecking a market clears affected order confirmations.</p>
        <div class="ptn-route-numbers">${metric('Carrier buy setting',price.buy_percent==null?'Unknown':price.buy_percent+'%',money(price.carrier_buy)+'/t')}${metric('Carrier sell setting',price.sell_percent==null?'Unknown':price.sell_percent+'%',money(price.carrier_sell)+'/t')}${metric('Carrier after reserve',short(price.owner_after_reserve)+' Cr',`${short(price.hauler_total)} Cr to haulers`)}</div>
        <div class="ptn-economics"><div><span>Gross station spread</span><b>${money(price.gross_total)}</b></div><div><span>Loading + unloading haulers</span><b>${money(price.hauler_total)}</b></div><div><span>Fuel & fees reserve</span><b>${money(price.cost_reserve)}</b></div><div><span>Estimated carrier remainder</span><b>${money(price.owner_after_reserve)}</b></div></div>
        <p class="note">Suggested settings preserve both minimum payouts after rounding. Confirm the displayed game prices below. Your ${fmt(s.hauler_capacity)} t hold / ${s.cycle_minutes} min cycle scenario is ${o.runs} round trips per leg; about ${o.scenario_minutes} min per leg with ${s.haulers} haulers, assuming continuous work.</p>
      </div><aside class="ptn-flight-checks"><span class="k">${o.phase==='loading'?'Loading':'Unloading'} / posting checks</span><h3>${o.ready?'Ready to generate advert':'Posting requirements'}</h3>
        ${['loading','unloading'].includes(p.stage)?`<form data-ptn-confirm><div class="ptn-fields">${field('actual_price','Actual carrier order / Cr',draft.price,1)}${field('remaining','Tonnes still available',draft.remaining,0,p.route.quantity)}</div>
        ${[['near_station','Carrier parked close to the station body'],['docking_open','Docking access open to haulers'],['funds_checked','Order funded; commodity market open'],['competition_checked','Other carriers and current supply/demand checked']].map(([name,label])=>`<label class="ptn-owner-check"><input name="${name}" type="checkbox" ${draft.checks[name]?'checked':''}>${label}</label>`).join('')}
        <label class="ptn-owner-check"><input name="sco" type="checkbox" ${draft.sco?'checked':''}>Add "SCO FSD recommended" below advert</label>
        <button type="submit" class="primary" ${u.busy?'disabled':''}>Save checked game values</button></form>`:`<p class="note">${p.stage==='transit'?'Move the carrier to the buyer body, then open unloading.':p.stage==='scouting'?'Capture both station markets before opening loading.':'This operation has ended.'}</p>`}
        <div class="ptn-readiness"><b>${o.blockers.length?`${o.blockers.length} checks remaining`:'Ready to prepare advert'}</b>${o.blockers.length?`<ul>${o.blockers.map(t=>`<li>${esc(t)}</li>`).join('')}</ul>`:'<p class="ok">Scouts, actual payout and owner checks pass.</p>'}</div>
        ${button('advert','Prepare Discord advert','primary',!o.ready)}
        ${next[p.stage]?`<button type="button" data-ptn-stage="${next[p.stage][0]}" ${u.busy?'disabled':''}>${next[p.stage][1]}</button>`:''}
        ${['loading','unloading'].includes(p.stage)?button('zero','Confirm zero tonnes remain','mini'):''}
        ${next[p.stage]?`<details class="ptn-more"><summary>End this plan</summary><p class="note">This only ends the EliteLab plan. Close the Discord advert and cancel any in-game order separately.</p><button type="button" class="mini" data-ptn-stage="cancelled">Mark cancelled</button></details>`:''}
      </aside></div></div>`;
  }

  function advertPane(u,d){
    const p=d.plan,o=d.operation;
    if(!p)return `<div class="ptn-empty"><h3>Select and check a route before generating an advert.</h3>${button('find','Search routes','primary')}</div>`;
    return `<div class="ptn-advert-layout"><section><span class="k">Affiliate trade alert</span><h3>Generate trade advert</h3><p class="note">Discord Markdown using the confirmed prices and remaining order. Use /aco trade to generate the required string, review it, then paste in affiliate-trade-alerts.</p>
      <div class="ptn-advert-preview"><span class="k">Copy-ready text</span><pre data-ptn-advert-text>${esc(u.advert?.copy_text||'Resolve the posting checks, then generate your advert.')}</pre></div>
      <div class="ptn-actions">${button('generate','Generate checked advert','primary',u.busy||!o.ready)}${button('copy-advert','Copy advert','',u.busy||!o.ready)}</div>
      <p class="note">${u.advert?esc(u.advert.instructions):'The server checks readiness again when you generate or copy. The desk never sends a Discord message.'}</p>
      <div class="ptn-posted"><h4>After you post</h4><label>Discord message link (optional)<input name="discord_link" value="${esc(u.postLink)}" placeholder="https://discord.com/channels/..."></label>${button('posted','I posted and confirmed it with Roomba','',!o.ready||u.busy)}
      ${o.posted?`<p class="${o.advert_expired?'warn':'ok'}">Recorded ${age(o.posted.at)}. ${o.advert_expired?'48-hour timeout reached: check Discord before reposting.':'48-hour timeout tracked from your confirmation.'}</p>`:''}
      <p class="note">Update remaining stock with /aco stock_update and your original message link. Close completed or cancelled adverts using Roomba's reactions.</p></div>
    </section><aside><div class="ptn-advert-payoff">${metric('Hauler profit / t',money(o.pricing[o.phase==='loading'?'loading_per_ton':'unloading_per_ton']),'Calculated from your checked carrier order','ptn-hauler')}${metric('Remaining order',fmt(o.remaining)+' t',o.phase==='loading'?'Station to carrier':'Carrier to station')}</div>
      <div class="ptn-readiness"><b>${o.ready?'Posting checks pass':'Resolve before posting'}</b><ul>${o.blockers.map(t=>`<li>${esc(t)}</li>`).join('')}</ul></div>${button('run','Back to operation','primary')}</aside></div>`;
  }

  function boardPane(u,d){
    const b=d.board;
    return `<div class="ptn-board"><div class="ptn-section-heading"><div><span class="k">Public board</span><h3>Official PTN trade adverts</h3></div>${button('board-refresh',u.busy?'Refreshing...':'Refresh public board','primary',u.busy)}</div>
      <p class="note">${esc(b?.scope||'Public official missions only. Affiliate adverts and unadvertised carriers are outside this feed.')}</p>
      ${b&&!b.available?`<p class="warn">Public board unavailable: ${esc(b.error)}</p>`:''}
      <div class="ptn-board-metrics">${['loading','unloading'].map(phase=>metric(`${phase} median`,b?.benchmarks?.[phase]==null?'Unknown':money(b.benchmarks[phase])+'/t','Current public official adverts','ptn-hauler')).join('')}${metric('Official missions',fmt(b?.missions?.length),b?.updated_at?'Feed updated '+age(b.updated_at):'Refresh to compare')}</div>
      ${b?.available?`<div class="ptn-actions">${button('beat-board','Set targets 1k above these medians','mini')} ${link('https://pilotstradenetwork.com/missions/','Open PTN missions')}</div><div class="ptn-board-table"><table><thead><tr><th>Offer</th><th>Commodity / carrier</th><th>Station / system</th><th>Profit / t</th><th>Order</th></tr></thead><tbody>${b.missions.map(m=>`<tr><td><span class="tag">${esc(m.phase)}</span></td><td><b>${esc(m.commodity)}</b><br><small>${esc(m.carrier)} (${esc(m.callsign)})</small></td><td>${esc(m.station)}<br><small class="muted">${esc(m.system)}</small></td><td class="ok">${money(m.profit)}</td><td>${esc(m.quantity_text)}k t</td></tr>`).join('')}</tbody></table></div>`:'<div class="ptn-empty"><h3>Compare your payout with the public board.</h3><p>Refresh to see current official offers and exclude their commodities from discovery.</p></div>'}
    </div>`;
  }

  Lab.card({id:'ptn',requires:['ptn','journal','trade'],
    mount(el){
      const u=el._ptn={tab:ls.get('ptn.tab.v1','find'),prefs:{},data:{},draft:{},draftId:'',busy:false,near:false,status:'',advert:null,postLink:''};
      const draw=()=>{
        const d=u.data;if(!d.defaults)return;
        const active=document.activeElement,focus=el.contains(active)?active.name||active.dataset.ptnTab:null;
        const selection=focus?{start:active.selectionStart,end:active.selectionEnd}:null;
        const scroller=el.querySelector('.ptn-content'),scroll=scroller?.scrollTop||0;
        const c=d.context||{},o=d.operation,p=d.plan;
        const draftId=p?p.id+':'+p.stage:'';
        if(draftId!==u.draftId||!u.draftDirty){if(draftId!==u.draftId)u.advert=null;u.draftId=draftId;u.draftDirty=false;u.draft={price:o?.order?.price??o?.pricing[o.phase==='unloading'?'carrier_sell':'carrier_buy']??'',remaining:o?.remaining??0,checks:{...o?.checks},sco:p?.sco!==false};}
        if(!tabs[u.tab])u.tab='find';
        el.innerHTML=`<div class="ptn-desk"><div class="ptn-hero"><div><span class="ptn-eyebrow">PTN affiliate trade</span><h3>${esc(c.carrier||'Carrier not identified')}<span>${c.callsign?` (${esc(c.callsign)})`:''}</span></h3><p>${c.carrier?`Carrier location: ${esc(c.system||'Unknown')}`:'Open Carrier Management to identify your carrier.'}</p></div><div class="ptn-hero-state"><span class="ptn-live-dot"></span>${p?esc(p.stage):'No active plan'}</div></div>
          <div class="ptn-overview">${metric('Loading target',money(u.prefs.loading_floor)+'/t',`${short(u.prefs.loading_floor*u.prefs.hauler_capacity)} Cr per example hold`,'ptn-hauler')}${metric('Unloading target',money(u.prefs.unloading_floor)+'/t',`${short(u.prefs.unloading_floor*u.prefs.hauler_capacity)} Cr per example hold`,'ptn-hauler')}${metric('Carrier space',c.free_space==null?'Unknown':fmt(c.free_space)+' t',`${fmt(c.reserved_space)} t reserved by buy orders`)}${metric('Public loading median',d.board?.benchmarks?.loading==null?'Refresh board':money(d.board.benchmarks.loading)+'/t','Official adverts; affiliate offers unknown')}</div>
          <nav class="view-tabs ptn-tabs" role="tablist" aria-label="PTN trade desk">${Object.entries(tabs).map(([id,label])=>`<button id="ptn-tab-${id}" type="button" data-ptn-tab="${id}" role="tab" aria-selected="${u.tab===id}" aria-controls="ptn-pane" tabindex="${u.tab===id?0:-1}">${label}</button>`).join('')}</nav>
          <div class="ptn-status ${u.error?'bad':''}" role="status" aria-live="polite">${esc(u.status)}</div><div class="ptn-content" id="ptn-pane" role="tabpanel" aria-labelledby="ptn-tab-${u.tab}">${u.tab==='find'?discovery(u,d):u.tab==='run'?operation(u,d):u.tab==='advert'?advertPane(u,d):boardPane(u,d)}</div></div>`;
        Lab.util.tabKeys(el.querySelector('.ptn-tabs'),'[data-ptn-tab]');
        const restore=focus?(el.querySelector(`[name="${CSS.escape(focus)}"]`)||el.querySelector(`[data-ptn-tab="${CSS.escape(focus)}"]`)):null;
        if(restore){restore.focus({preventScroll:true});try{if(selection.start!=null)restore.setSelectionRange(selection.start,selection.end);}catch{}}
        el.querySelector('.ptn-content').scrollTop=scroll;
        fit();
      };
      const fit=()=>{const box=el.querySelector('.ptn-desk');if(box)box.style.setProperty('--ptn-height',Math.max(410,Math.min(1000,innerHeight-box.getBoundingClientRect().top-16))+'px');};
      u.draw=draw;
      const request=async(fn,message='')=>{if(u.busy)return;u.busy=true;u.error=false;u.status=message;draw();try{await fn();}catch(error){u.error=true;u.status=error.message||String(error);}finally{u.busy=false;draw();}};
      const post=async(path,values)=>{const data=await Lab.post(path,{revision:u.data.revision,...values});u.data=data;return data;};
      const tab=name=>{u.tab=name;ls.set('ptn.tab.v1',name);draw();};
      el.addEventListener('input',event=>{const t=event.target;if(t.closest('[data-ptn-search]')){u.prefs[t.name]=t.type==='checkbox'?t.checked:t.type==='number'?Number(t.value):t.value;ls.set(KEY,u.prefs);}else if(t.closest('[data-ptn-confirm]')){u.draftDirty=true;if(['near_station','docking_open','funds_checked','competition_checked'].includes(t.name))u.draft.checks[t.name]=t.checked;else if(t.name==='actual_price')u.draft.price=t.value;else if(t.name==='remaining')u.draft.remaining=t.value;else if(t.name==='sco')u.draft.sco=t.checked;}else if(t.name==='discord_link')u.postLink=t.value;});
      el.addEventListener('submit',event=>{event.preventDefault();const form=event.target;
        if(form.matches('[data-ptn-search]'))request(async()=>{const result=await Lab.api('/api/ptn/search',u.prefs);u.data={...u.data,result,searching:false};u.near=false;u.status=`Search complete: ${result.scanned} commodities checked. ${result.rows.filter(r=>r.viable).length} matching routes.`;},'Checking markets and public adverts...');
        if(form.matches('[data-ptn-confirm]'))request(async()=>{await post('/api/ptn/update',{action:'confirm',price:Number(u.draft.price),remaining:Number(u.draft.remaining),checks:{near_station:false,docking_open:false,funds_checked:false,competition_checked:false,...u.draft.checks},sco:u.draft.sco});u.draftDirty=false;u.advert=null;u.status='Checked game values saved.';});
      });
      el.addEventListener('click',event=>{
        const t=event.target.closest('button');if(!t)return;
        if(t.dataset.ptnTab){tab(t.dataset.ptnTab);return;}
        if(t.dataset.ptnCopy!==undefined){request(async()=>{if(!navigator.clipboard)throw Error('Clipboard unavailable. Select and copy the text manually.');await navigator.clipboard.writeText(t.dataset.ptnCopy);u.status='Copied.';});return;}
        if(t.dataset.ptnPayout){u.prefs.loading_floor=u.prefs.unloading_floor=Number(t.dataset.ptnPayout);ls.set(KEY,u.prefs);draw();return;}
        if(t.dataset.ptnSelect){request(async()=>{await post('/api/ptn/select',{id:t.dataset.ptnSelect});u.status='Route saved. Scout both stations before opening loading.';tab('run');});return;}
        if(t.dataset.ptnCapture){request(async()=>{await post('/api/ptn/capture',{side:t.dataset.ptnCapture});u.status='Current station market captured from your journal.';u.advert=null;});return;}
        if(t.dataset.ptnStage){request(async()=>{await post('/api/ptn/update',{action:'stage',stage:t.dataset.ptnStage});u.status='PTN stage updated. Game orders and Discord messages are managed in game and Discord.';});return;}
        const action=t.dataset.ptnAction;
        if(['find','run','advert','board'].includes(action)){tab(action);return;}
        if(action==='near'||action==='qualified'){u.near=action==='near';draw();return;}
        if(action==='exclude-cargo'){u.prefs.excluded=[...new Set([...u.prefs.excluded.split(',').map(v=>v.trim()).filter(Boolean),...Object.entries(u.data.context.inventory).filter(([,r])=>r.stock>0).map(([k])=>k)])].join(', ');ls.set(KEY,u.prefs);draw();return;}
        if(action==='beat-board'){for(const [phase,name] of [['loading','loading_floor'],['unloading','unloading_floor']])if(u.data.board?.benchmarks?.[phase]!=null)u.prefs[name]=u.data.board.benchmarks[phase]+1000;ls.set(KEY,u.prefs);tab('find');return;}
        if(action==='board-refresh')request(async()=>{u.data={...u.data,board:await Lab.api('/api/ptn/board')};u.status=u.data.board.available?'Public official board refreshed.':'Public board unavailable; competition remains unknown.';});
        if(action==='zero')request(async()=>{await post('/api/ptn/update',{action:'remaining',remaining:0});u.draft.remaining=0;u.status='Recorded zero outstanding tonnes. Close your Discord advert with Roomba.';});
        if(action==='generate'||action==='copy-advert')request(async()=>{u.advert=await Lab.api('/api/ptn/advert',{revision:u.data.revision});if(action==='copy-advert'){if(!navigator.clipboard)throw Error('Clipboard unavailable. Copy the preview manually.');await navigator.clipboard.writeText(u.advert.copy_text);}u.status=action==='copy-advert'?'Exact advert copied. Review /aco trade and post it yourself.':'Advert generated from checked game prices.';});
        if(action==='posted')request(async()=>{await post('/api/ptn/update',{action:'posted',link:u.postLink});u.status='Posted time recorded. This does not send a Discord message.';});
      });
      addEventListener('resize',fit);addEventListener('lab:relayout',fit);u.cleanup=()=>{removeEventListener('resize',fit);removeEventListener('lab:relayout',fit);};
    },
    render(el,S){const u=el._ptn;if(!u)return;const d=S.ptn||{};u.data=d;if(!Object.keys(u.prefs).length&&d.defaults)u.prefs={...d.defaults,...ls.get(KEY,{})};u.draw();},
    unmount(el){el._ptn?.cleanup();}
  });
})();
