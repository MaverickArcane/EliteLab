/* Carrier trade discovery, explicit payout arithmetic and checked PTN adverts. */
(() => {
  const {esc,fmt,ls}=Lab.util, KEY='ptn.preferences.v3';
  const money=n=>`${fmt(n)} Cr`, short=n=>n==null?'Unknown':`${(n/1e6).toLocaleString(undefined,{maximumFractionDigits:2})}m`;
  const age=iso=>{const t=Date.parse(iso);if(!Number.isFinite(t))return 'Age unknown';const m=Math.max(0,Math.floor((Date.now()-t)/60000));return m<60?`${m} min ago`:`${Math.floor(m/60)} h ago`;};
  const button=(action,text,cls='',disabled=false)=>`<button type="button" data-ptn-action="${action}" class="${cls}" ${disabled?'disabled':''}>${text}</button>`;
  const copy=(text,label)=>`<button type="button" class="mini" data-ptn-copy="${esc(text)}">${label}</button>`;
  const link=(href,text)=>`<a href="${esc(href)}" target="_blank" rel="noopener noreferrer">${text}</a>`;
  const metric=(label,value,sub='',cls='')=>`<div class="ptn-metric ${cls}"><span class="k">${label}</span><strong>${value}</strong>${sub?`<small>${sub}</small>`:''}</div>`;
  const field=(name,label,value,min=0,max=1e9)=>`<label>${label}<input name="${name}" type="number" min="${min}" max="${max}" step="1" value="${esc(value)}" required></label>`;
  const jumpField=(name,label,value)=>`<label>${label}<select name="${name}">${[500,1000,1500,2000,2500].map(n=>`<option value="${n}" ${Number(value)===n?'selected':''}>${n/500} jump${n===500?'':'s'}</option>`).join('')}</select></label>`;
  const stages=['scouting','loading','transit','unloading','complete'];
  const stageNames=['Scout','Load','Move','Unload','Complete'];
  const tabs={find:'Find trades',run:'Scout & run',advert:'Advert',board:'Public board'};
  const modes={both:'Haulers load and unload',self_load:'I load; haulers unload',self_unload:'Haulers load; I unload'};
  const paid=(p,phase)=>p.haul_mode!==(phase==='loading'?'self_load':'self_unload');
  const stationLabel=s=>s.surface?(s.station_type==='OnFootSettlement'||s.station_type==='Odyssey Settlement'?'Odyssey surface port':'Surface port'):'Orbital station';
  const volumeLabel=(s,side)=>side==='sell'&&s.demand_unlimited===true&&s.volume===0?'Unlimited demand (reported 0)':`${fmt(s.volume)} t ${side==='buy'?'supply':'demand'}`;
  const stop=(s,title,scouted=false)=>`<section class="ptn-stop"><div class="ptn-stop-label"><span class="k">${title}</span><span class="tag ${scouted?'ok':''}">${scouted?'Scouted':'Reported'}</span></div>
    <h4>${esc(s.station)}</h4><div class="ptn-system">${esc(s.system)}</div><div class="note">${stationLabel(s)} &middot; L pads</div><div class="ptn-stop-price">${money(s.price)}<small> / t</small></div>
    <div class="note">${volumeLabel(s,title==='Load from'?'buy':'sell')} &middot; ${fmt(Math.round(s.arrival_ls))} Ls from arrival</div>
    <div class="note ptn-body">Park near <b>${esc(s.body||'body to confirm in system map')}</b></div>
    <div class="ptn-actions">${copy(s.system,'Copy system')}${copy(s.station,'Copy station')}${link(Lab.util.inaraMarket(s.station,s.system),'Inara')}</div>
    <small class="muted">${esc(s.source)} &middot; ${age(s.observed_at)}</small></section>`;

  function searchForm(u,d){
    const p=u.prefs;
    return `<form data-ptn-search class="ptn-search"><h3>Find a trade</h3>
      <p class="note">Large pads. Unloading stays orbital. Prices must leave you a positive return after the reserve.</p>
      <label>Who does the hauling?<select name="haul_mode">${Object.entries(modes).map(([id,label])=>`<option value="${id}" ${p.haul_mode===id?'selected':''}>${label}</option>`).join('')}</select></label>
      <button type="submit" class="primary ptn-scan" ${u.busy||d.searching?'disabled':''}>${u.busy||d.searching?'Searching markets...':'Search routes'}</button>
      <div class="ptn-fields">${jumpField('radius','Carrier to loading station',p.radius)}${jumpField('max_hop','Loading to buyer',p.max_hop)}</div>
      <p class="note">All non-rare commodities by default. Jump counts are minimums at 500 Ly; intermediate systems and fuel must be checked.</p>
      <label class="ptn-check-line"><span><input type="checkbox" name="allow_surface_loading" ${p.allow_surface_loading?'checked':''}> Include surface loading</span><small>Off by default. Surface ports may have cheaper stock, with a longer trip for haulers.</small></label>
      <div class="ptn-fields">${field('loading_floor','Minimum loading payout / t',p.loading_floor,1,1000000)}${field('unloading_floor','Minimum unloading payout / t',p.unloading_floor,1,1000000)}</div>
      <div class="ptn-payout-presets"><span class="note">Set minimums and keep surplus:</span><div class="ptn-actions">${button('payout-20-20','20k load / 20k unload','mini')}${button('payout-30-20','30k load / 20k unload','mini')}</div><small class="muted">Both presets use public haulers on both legs. Search again to apply.</small></div>
      <label class="ptn-check-line"><span><input type="checkbox" name="share_surplus" ${p.share_surplus?'checked':''}> Give remaining spread to haulers</span><small>On: raise payouts until only your minimum carrier margin remains. Off: pay the minimums and keep the rest.</small></label>
      <div class="ptn-fields">${field('quantity','Maximum order / t',p.quantity,1,25000)}${field('payout_target','Preferred payout each leg / t',p.payout_target,1,1000000)}${field('owner_floor','Minimum carrier margin / t',p.owner_floor,0,1000000)}${field('cost_reserve','Costs to reserve / Cr',p.cost_reserve,0,1e10)}</div>
      <p class="note">Minimum payouts are hard limits on public legs. The preferred payout ranks offers without hiding alternatives. Carrier margin is before the reserve.</p>
      ${button('normal-search','Restore normal search settings','mini')}
      <label class="ptn-check-line"><span><input type="checkbox" name="allow_partial" ${p.allow_partial?'checked':''}> Include smaller orders</span><small>Reduce tonnes to fit reported supply and demand. Each result shows its actual order size.</small></label>
      <details class="ptn-more" data-ptn-detail="exclusions"><summary>Commodity exclusions</summary>
        <label class="ptn-check-line"><span><input type="checkbox" name="skip_common" ${p.skip_common?'checked':''}> Exclude common carrier cargo</span><small>${esc((d.common||[]).join(', '))}</small></label>
        <label class="ptn-check-line"><span><input type="checkbox" name="avoid_active" ${p.avoid_active?'checked':''}> Exclude cargo on the official PTN board</span><small>Affiliate competition is not included in this feed.</small></label>
        <label>Also exclude<input name="excluded" value="${esc(p.excluded)}" placeholder="Comma-separated commodities" maxlength="1000"></label>
        ${button('exclude-cargo','Exclude cargo recorded aboard','mini')}
      </details>
      <details class="ptn-more" data-ptn-detail="limits"><summary>Search limits</summary><div class="ptn-fields">
        ${field('min_quantity','Smallest order / t',p.min_quantity,1,25000)}${field('breadth','Commodity limit / 0 = all',p.breadth,0,500)}
        ${field('hours','Report age / hours',p.hours,1,24)}${field('arrival','Star approach / Ls (0 = any)',p.arrival,0,10000000)}
      </div><p class="note">Distance from the star matters when scouting. Haulers travel from your carrier; confirm parking near the station body.</p></details>
      <details class="ptn-more" data-ptn-detail="scenario"><summary>Hauler earnings example</summary><div class="ptn-fields">${field('hauler_capacity','Example hold / t',p.hauler_capacity,1,1000)}${field('cycle_minutes','Round trip / min',p.cycle_minutes,1,60)}${field('haulers','Number of haulers',p.haulers,1,50)}</div><p class="note">These are assumptions, not measured turnout or completion times.</p></details></form>`;
  }

  function routeCard(r,u,index){
    const c=r.pricing,p=r.settings,selected=u.data.plan?.route.id===r.id;
    const requiredSpread=c.required_spread,shortfall=c.spread_short;
    const payout=(phase,label)=>metric(label,paid(p,phase)?money(c[phase+'_per_ton'])+'/t':'You haul',paid(p,phase)?`${short(c[phase+'_per_ton']*p.hauler_capacity)} Cr / ${fmt(p.hauler_capacity)} t`:'No public payout','ptn-hauler');
    return `<article class="ptn-route ${r.viable?'':'ptn-prospect'}"><div class="ptn-route-top"><div class="ptn-route-name"><div><h3>${esc(r.name)}</h3><span class="note">${fmt(r.quantity)} t &middot; ${esc(modes[p.haul_mode]||modes.both)}</span></div></div><span class="tag ${r.viable?'ok':'warn'}">${r.viable?c.meets_target?'Meets preferred payout':'Profitable, below preferred payout':shortfall?`${fmt(shortfall)} Cr/t shortfall`:'Requirements not met'}</span></div>
      <div class="ptn-route-numbers">${r.viable?`${payout('loading','Hauler / loading')}${payout('unloading','Hauler / unloading')}${metric('Carrier after reserve',short(c.owner_after_reserve)+' Cr',`${money(c.owner_per_ton)}/t before costs`)}`:`${metric('Available station spread',money(c.gross_per_ton)+'/t')}${metric('Required minimum spread',money(requiredSpread)+'/t')}${metric('Payout shortfall',shortfall?money(shortfall)+'/t':'See rejection details','','warn')}`}</div>
      ${r.viable?`<p class="note ptn-profit-breakdown">Station spread ${money(c.gross_per_ton)}/t &minus; hauler payouts ${money(c.loading_per_ton+c.unloading_per_ton)}/t = your margin ${money(c.owner_per_ton)}/t before costs.</p>`:''}
      <div class="ptn-route-summary">${[['buy','Load'],['sell','Unload']].map(([side,label])=>`<div><span class="k">${label} &middot; ${money(r[side].price)}/t</span><b>${esc(r[side].station)}</b><span>${esc(r[side].system)}</span><small>${volumeLabel(r[side],side)} &middot; ${stationLabel(r[side])} &middot; L pads<br>${fmt(Math.round(r[side].arrival_ls))} Ls &middot; ${age(r[side].observed_at)}</small></div>`).join('')}</div>
      <div class="ptn-route-foot"><div class="note">${r.approach_jumps==null?'':`To load: ${r.approach_jumps} jump minimum (${fmt(r.approach_distance)} Ly) &middot; `}To sell: ${r.trade_jumps??Math.ceil(r.route_distance/500)} jump minimum (${fmt(r.route_distance)} Ly)<br>${r.supply_buffer}&times; supply buffer &middot; ${r.official_competitors==null?'Official competition unknown':`${r.official_competitors} official loading adverts here`}</div>
      <button type="button" class="${r.viable?'primary':''}" data-ptn-select="${esc(r.id)}" ${u.busy?'disabled':''}>${selected?'Restart station checks':r.viable?'Use this route':'Inspect candidate'}</button></div>
      <details class="ptn-route-detail" data-ptn-detail="${esc(r.id)}"><summary>Station details, funding and price settings</summary><div class="ptn-stops">${stop(r.buy,'Load from')}${stop(r.sell,'Unload to')}</div>
        ${r.viable?`<p class="note">Initial funding: ${money(c.funding)}. ${p.haul_mode==='self_load'?'Station purchase cost':`Carrier buy: ${money(c.carrier_buy)}/t (${c.buy_percent}%)`}. ${p.haul_mode==='self_unload'?'Unload at the station yourself':`Carrier sell: ${money(c.carrier_sell)}/t (${c.sell_percent}%)`}. Reserve: ${money(c.cost_reserve)}.</p><p class="note">Hauler scenario: ${short(r.hauler_hour_scenario)} Cr/h at your ${p.cycle_minutes} min round trip. Confirm actual prices in game.</p>`:''}</details>
      ${r.reasons.length?`<p class="ptn-reasons">${r.reasons.map(esc).join(' ')}</p>`:''}</article>`;
  }

  function discovery(u,d){
    const r=d.result,qualified=r?.rows.filter(row=>row.viable)||[],near=r?.rows.filter(row=>!row.viable)||[];
    const rows=u.near?near:u.targetOnly?qualified.filter(row=>row.pricing.meets_target):qualified;
    return `<div class="ptn-discovery">${searchForm(u,d)}<section class="ptn-opportunities"><div class="ptn-section-heading"><div><h3>${r?`${qualified.length} profitable routes`:'Carrier routes'}</h3></div><div class="ptn-actions">${button('qualified',`All profitable ${qualified.length}`,`mini ${!u.near&&!u.targetOnly?'primary':''}`)}${button('target-only',`At target ${qualified.filter(row=>row.pricing.meets_target).length}`,`mini ${u.targetOnly&&!u.near?'primary':''}`)}${button('near',`Rejected ${near.length}`,`mini ${u.near?'primary':''}`)}</div></div>
      ${d.searching?`<p class="ptn-search-progress" role="status">${esc(d.progress?.message||'Checking nearby markets...')}</p>`:''}
      ${d.context.free_space===0?`<p class="ptn-capacity-note">Your last carrier report has no free space; ${fmt(d.context.reserved_space)} t is reserved by buy orders. Check existing orders in Carrier Management before starting a new load. Report: ${age(d.context.stats_at)}.</p>`:''}
      ${r?`<p class="note">${esc(modes[r.settings.haul_mode]||modes.both)}. ${r.settings.allow_surface_loading?'Orbital or surface loading':'Orbital loading'}; orbital unloading. ${r.settings.share_surplus?'Surplus goes to haulers.':'You keep surplus above the payout minimums.'} Preferred payout ${money(r.settings.payout_target||20000)}/t on each paid leg. Figures are estimates until scouted.</p>`:''}
      ${r?.surface_excluded?.count?`<div class="ptn-surface-note"><b>${fmt(r.surface_excluded.count)} surface loading sources excluded by orbital-only</b><p class="note">These have an estimated profitable route to an orbital buyer at your selected payouts. Counts cover this scan only.</p><ul>${r.surface_excluded.examples.map(s=>`<li>${esc(s.commodity)} &middot; ${esc(s.station)} / ${esc(s.system)}</li>`).join('')}</ul>${button('surface-search','Search with surface loading','mini',u.busy||d.searching)}</div>`:''}
      ${r?`<p class="note">${r.coverage?.completed??r.scanned} / ${r.available} commodities fully checked from ${esc(r.origin)} &middot; ${age(r.checked_at)}. Sorted by carrier return after reserve. ${esc(r.scope)}</p>`:''}
      ${r?.warnings.length?`<details class="ptn-more"><summary class="warn">${r.warnings.length} data notes</summary>${r.warnings.map(w=>`<p class="note">${esc(w)}</p>`).join('')}</details>`:''}
      ${rows.length?rows.map((row,i)=>routeCard(row,u,i)).join(''):`<div class="ptn-empty"><h3>${r?u.near?'No rejected candidates.':u.targetOnly?'No offers reach the preferred payout.':'No routes match these filters.':'Search nearby carrier trades'}</h3><p>${r?u.targetOnly?'Profitable alternatives remain available under All profitable.':'Try including common cargo, allowing smaller orders, or adjusting each leg\'s payout. Prices must still cover both hauler payouts and your reserve.':'The search splits available profit between you and public haulers, then shows the actual payout on each leg.'}</p>${r&&u.targetOnly?button('qualified','Show all profitable routes'):r?button('normal-search','Restore normal search settings'):''}${r&&near.length&&!u.near?button('near','View rejected candidates'):''}</div>`}
    </section></div>`;
  }

  function operation(u,d){
    const p=d.plan,o=d.operation;
    if(!p)return `<div class="ptn-empty"><h3>Choose a route to start scouting.</h3><p>Save station prices and actual carrier order values before generating an advert.</p>${button('find','Find a trade','primary')}</div>`;
    const s=p.route.settings,price=o.pricing;
    const next={scouting:['loading','Open loading'],loading:['transit','Load finished: ready to move'],transit:['unloading','Open unloading'],unloading:['complete','Unload finished: complete']};
    const draft=u.draft;
    return `<div class="ptn-run"><div class="ptn-operation-title"><div><span class="k">${esc(p.carrier)} (${esc(p.callsign)})</span><h3>${esc(p.name)} <span class="muted">/ ${fmt(p.route.quantity)} t</span></h3></div><span class="tag">${esc(p.stage)}</span></div>
      <ol class="ptn-stages">${stages.map((stage,i)=>`<li class="${stage===p.stage?'is-current':stages.indexOf(p.stage)>i?'is-done':''}"><span>${i+1}</span>${stageNames[i]}</li>`).join('')}</ol>
      <div class="ptn-run-grid"><div><div class="ptn-stops">${['buy','sell'].map((side,i)=>`<div>${stop(o[side],i===0?'Load from':'Unload to',!!p.scouts[side])}<button type="button" class="ptn-capture" data-ptn-capture="${side}" ${u.busy?'disabled':''}>Capture this station's current market</button></div>`).join('')}</div>
        <p class="note">Dock at each station and open Commodities, then capture its journal snapshot. Station price, volume and carrier 100% reference are saved with their observation time. Rechecking a market clears affected order confirmations.</p>
        <div class="ptn-route-numbers">${metric(paid(s,'loading')?'Carrier buy price':'Your purchase cost',money(price.carrier_buy)+'/t',p.orders.loading?'Confirmed actual price':price.buy_percent==null?'Station price':price.buy_percent+'% suggested')}${metric(paid(s,'unloading')?'Carrier sell price':'Your sale proceeds',money(price.carrier_sell)+'/t',p.orders.unloading?'Confirmed actual price':price.sell_percent==null?'Station price':price.sell_percent+'% suggested')}${metric('Carrier after reserve',short(price.owner_after_reserve)+' Cr',`${short(price.hauler_total)} Cr to haulers`)}</div>
        <div class="ptn-economics"><div><span>Gross station spread</span><b>${money(price.gross_total)}</b></div><div><span>Loading + unloading haulers</span><b>${money(price.hauler_total)}</b></div><div><span>Fuel & fees reserve</span><b>${money(price.cost_reserve)}</b></div><div><span>Estimated carrier remainder</span><b>${money(price.owner_after_reserve)}</b></div></div>
        <p class="note">${esc(modes[s.haul_mode]||modes.both)}. Suggested public prices preserve minimum payouts after rounding. Confirm actual game prices below. At ${fmt(s.hauler_capacity)} t per trip, this order takes ${o.runs} trips per leg${s.haul_mode&&s.haul_mode!=='both'?' including your own hauling':''}.</p>
      </div><aside class="ptn-flight-checks"><span class="k">${o.phase==='loading'?'Loading':'Unloading'}</span><h3>${!o.public_phase?'Record your own hauling':o.ready?'Ready to generate advert':'Posting requirements'}</h3>
        ${['loading','unloading'].includes(p.stage)?`<form data-ptn-confirm><div class="ptn-fields">${field('actual_price',o.public_phase?'Actual carrier order / Cr':o.phase==='loading'?'Average price you paid / t':'Average sale proceeds / t',draft.price,1)}${field('remaining','Tonnes left to haul',draft.remaining,0,p.route.quantity)}</div>
        ${o.public_phase?[['near_station','Carrier parked close to the station body'],['docking_open','Docking access open to haulers'],['funds_checked','Order funded; commodity market open'],['competition_checked','Other carriers and current supply/demand checked']].map(([name,label])=>`<label class="ptn-owner-check"><input name="${name}" type="checkbox" ${draft.checks[name]?'checked':''}>${label}</label>`).join(''):'<p class="note">Buy or sell at the station yourself and transfer cargo to or from your carrier. Save the actual average station price; it is used to calculate your return.</p>'}
        ${o.public_phase?`<label class="ptn-owner-check"><input name="sco" type="checkbox" ${draft.sco?'checked':''}>Add "SCO FSD recommended" below advert</label>`:''}
        <button type="submit" class="primary" ${u.busy?'disabled':''}>Save checked game values</button></form>`:`<p class="note">${p.stage==='transit'?'Move the carrier to the buyer body, then open unloading.':p.stage==='scouting'?'Capture both station markets before opening loading.':'This operation has ended.'}</p>`}
        ${o.public_phase?`<div class="ptn-readiness"><b>${o.blockers.length?`${o.blockers.length} checks remaining`:'Ready to prepare advert'}</b>${o.blockers.length?`<ul>${o.blockers.map(t=>`<li>${esc(t)}</li>`).join('')}</ul>`:'<p class="ok">Scouts, actual payout and owner checks pass.</p>'}</div>${button('advert','Prepare Discord advert','primary',!o.ready)}`:'<p class="note">This leg has no public advert. Record zero remaining after finishing your transfers, then continue.</p>'}
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
      ${b?.available?`<div class="ptn-actions">${button('beat-board','Set preferred payout 1k above the median','mini')} ${link('https://pilotstradenetwork.com/missions/','Open PTN missions')}</div><div class="ptn-board-table"><table><thead><tr><th>Offer</th><th>Commodity / carrier</th><th>Station / system</th><th>Profit / t</th><th>Order</th></tr></thead><tbody>${b.missions.map(m=>`<tr><td><span class="tag">${esc(m.phase)}</span></td><td><b>${esc(m.commodity)}</b><br><small>${esc(m.carrier)} (${esc(m.callsign)})</small></td><td>${esc(m.station)}<br><small class="muted">${esc(m.system)}</small></td><td class="ok">${money(m.profit)}</td><td>${esc(m.quantity_text)}k t</td></tr>`).join('')}</tbody></table></div>`:'<div class="ptn-empty"><h3>Compare your payout with the public board.</h3><p>Refresh to see current official offers and exclude their commodities from discovery.</p></div>'}
    </div>`;
  }

  Lab.card({id:'ptn',requires:['ptn','journal','trade'],
    mount(el){
      const u=el._ptn={tab:ls.get('ptn.tab.v1','find'),prefs:{},data:{},draft:{},draftId:'',busy:false,near:false,targetOnly:false,status:'',advert:null,postLink:''};
      const draw=()=>{
        const d=u.data;if(!d.defaults)return;
        const active=document.activeElement,focus=el.contains(active)?active.name||active.dataset.ptnTab:null;
        const selection=focus?{start:active.selectionStart,end:active.selectionEnd}:null;
        const sameTab=u.drawnTab===u.tab;
        const scrolls=['.ptn-content','.ptn-search','.ptn-opportunities'].map(selector=>[selector,sameTab?el.querySelector(selector)?.scrollTop||0:0]);
        const openDetails=new Set(sameTab?[...el.querySelectorAll('details[open][data-ptn-detail]')].map(node=>node.dataset.ptnDetail):[]);
        const c=d.context||{},o=d.operation,p=d.plan,best=d.result?.rows.find(row=>row.viable);
        const draftId=p?p.id+':'+p.stage:'';
        if(draftId!==u.draftId||!u.draftDirty){if(draftId!==u.draftId)u.advert=null;u.draftId=draftId;u.draftDirty=false;u.draft={price:o?.order?.price??o?.pricing[o.phase==='unloading'?'carrier_sell':'carrier_buy']??'',remaining:o?.remaining??0,checks:{...o?.checks},sco:p?.sco!==false};}
        if(!tabs[u.tab])u.tab='find';
        el.innerHTML=`<div class="ptn-desk"><div class="ptn-hero"><div><h3>${esc(c.carrier||'Carrier not identified')}<span>${c.callsign?` (${esc(c.callsign)})`:''}</span></h3><p>${c.carrier?`Carrier location: ${esc(c.system||'Unknown')}`:'Open Carrier Management to identify your carrier.'}</p></div><div class="ptn-hero-state">${p?esc(p.stage):'No active plan'}</div></div>
          <div class="ptn-overview">${metric('Best route loading payout',best?paid(best.settings,'loading')?money(best.pricing.loading_per_ton)+'/t':'You haul':'Run a search',best?'Unloading: '+(paid(best.settings,'unloading')?money(best.pricing.unloading_per_ton)+'/t':'you haul'):'Both leg payouts appear on each route','ptn-hauler')}${metric('Best route carrier return',best?short(best.pricing.owner_after_reserve)+' Cr':'Run a search','After the selected cost reserve')}${metric('Carrier space',c.free_space==null?'Unknown':fmt(c.free_space)+' t',`${fmt(c.reserved_space)} t reserved by buy orders`)}${metric('Public loading median',d.board?.benchmarks?.loading==null?'Refresh board':money(d.board.benchmarks.loading)+'/t','Official adverts; affiliate offers unknown')}</div>
          <nav class="view-tabs ptn-tabs" role="tablist" aria-label="PTN trade desk">${Object.entries(tabs).map(([id,label])=>`<button id="ptn-tab-${id}" type="button" data-ptn-tab="${id}" role="tab" aria-selected="${u.tab===id}" aria-controls="ptn-pane" tabindex="${u.tab===id?0:-1}">${label}</button>`).join('')}</nav>
          <div class="ptn-status ${u.error?'bad':''}" role="status" aria-live="polite">${esc(u.status)}</div><div class="ptn-content" id="ptn-pane" role="tabpanel" aria-labelledby="ptn-tab-${u.tab}">${u.tab==='find'?discovery(u,d):u.tab==='run'?operation(u,d):u.tab==='advert'?advertPane(u,d):boardPane(u,d)}</div></div>`;
        Lab.util.tabKeys(el.querySelector('.ptn-tabs'),'[data-ptn-tab]');
        el.querySelectorAll('details[data-ptn-detail]').forEach(node=>{node.open=openDetails.has(node.dataset.ptnDetail);});
        const restore=focus?(el.querySelector(`[name="${CSS.escape(focus)}"]`)||el.querySelector(`[data-ptn-tab="${CSS.escape(focus)}"]`)):null;
        if(restore){restore.focus({preventScroll:true});try{if(selection.start!=null)restore.setSelectionRange(selection.start,selection.end);}catch{}}
        fit();
        for(const [selector,scroll] of scrolls){const node=el.querySelector(selector);if(node)node.scrollTop=scroll;}
        u.drawnTab=u.tab;
      };
      const fit=()=>{const box=el.querySelector('.ptn-desk');if(box)box.style.setProperty('--ptn-height',Math.max(410,Math.min(1000,innerHeight-box.getBoundingClientRect().top-16))+'px');};
      u.draw=draw;
      const request=async(fn,message='')=>{if(u.busy)return;u.busy=true;u.error=false;u.status=message;draw();try{await fn();}catch(error){u.error=true;u.status=error.message||String(error);if(u.status.includes('This plan changed')){try{u.data=await Lab.api('/api/ptn');u.advert=null;u.status='Plan refreshed after another update. Review the current values and retry.';}catch{}}}finally{u.busy=false;draw();}};
      const post=async(path,values)=>{const data=await Lab.post(path,{revision:u.data.revision,...values});u.data=data;return data;};
      const search=()=>request(async()=>{const result=await Lab.api('/api/ptn/search',u.prefs);u.data={...u.data,result,searching:false};u.near=false;u.targetOnly=false;u.status=`Search complete: ${result.scanned} commodities checked. ${result.rows.filter(r=>r.viable).length} profitable routes.`;},'Checking nearby markets and public adverts...');
      const tab=name=>{u.tab=name;ls.set('ptn.tab.v1',name);draw();};
      el.addEventListener('input',event=>{const t=event.target;if(t.closest('[data-ptn-search]')){u.prefs[t.name]=t.type==='checkbox'?t.checked:t.type==='number'?Number(t.value):t.value;ls.set(KEY,u.prefs);}else if(t.closest('[data-ptn-confirm]')){u.draftDirty=true;if(['near_station','docking_open','funds_checked','competition_checked'].includes(t.name))u.draft.checks[t.name]=t.checked;else if(t.name==='actual_price')u.draft.price=t.value;else if(t.name==='remaining')u.draft.remaining=t.value;else if(t.name==='sco')u.draft.sco=t.checked;}else if(t.name==='discord_link')u.postLink=t.value;});
      el.addEventListener('submit',event=>{event.preventDefault();const form=event.target;
        if(form.matches('[data-ptn-search]'))search();
        if(form.matches('[data-ptn-confirm]'))request(async()=>{await post('/api/ptn/update',{action:'confirm',price:Number(u.draft.price),remaining:Number(u.draft.remaining),checks:{near_station:false,docking_open:false,funds_checked:false,competition_checked:false,...u.draft.checks},sco:u.draft.sco});u.draftDirty=false;u.advert=null;u.status='Checked game values saved.';});
      });
      el.addEventListener('click',event=>{
        const t=event.target.closest('button');if(!t)return;
        if(t.dataset.ptnTab){tab(t.dataset.ptnTab);return;}
        if(t.dataset.ptnCopy!==undefined){request(async()=>{if(!navigator.clipboard)throw Error('Clipboard unavailable. Select and copy the text manually.');await navigator.clipboard.writeText(t.dataset.ptnCopy);u.status='Copied.';});return;}
        if(t.dataset.ptnSelect){request(async()=>{await post('/api/ptn/select',{id:t.dataset.ptnSelect});u.status='Route saved. Scout both stations before opening loading.';tab('run');});return;}
        if(t.dataset.ptnCapture){request(async()=>{await post('/api/ptn/capture',{side:t.dataset.ptnCapture});u.status='Current station market captured from your journal.';u.advert=null;});return;}
        if(t.dataset.ptnStage){request(async()=>{await post('/api/ptn/update',{action:'stage',stage:t.dataset.ptnStage});u.status='PTN stage updated. Game orders and Discord messages are managed in game and Discord.';});return;}
        const action=t.dataset.ptnAction;
        if(['find','run','advert','board'].includes(action)){tab(action);return;}
        if(['near','qualified','target-only'].includes(action)){u.near=action==='near';u.targetOnly=action==='target-only';draw();return;}
        if(action==='payout-20-20'||action==='payout-30-20'){u.prefs={...u.prefs,haul_mode:'both',loading_floor:action==='payout-30-20'?30000:20000,unloading_floor:20000,share_surplus:false};ls.set(KEY,u.prefs);u.status='Minimum payouts set for public haulers on both legs; you keep the surplus. Search routes to apply.';draw();return;}
        if(action==='surface-search'){if(u.busy||u.data.searching)return;u.prefs.allow_surface_loading=true;ls.set(KEY,u.prefs);search();return;}
        if(action==='normal-search'){u.prefs={...u.data.defaults};ls.set(KEY,u.prefs);u.near=false;u.targetOnly=false;u.status='Normal settings restored. Search routes to refresh the results.';draw();return;}
        if(action==='exclude-cargo'){u.prefs.excluded=[...new Set([...u.prefs.excluded.split(',').map(v=>v.trim()).filter(Boolean),...Object.entries(u.data.context.inventory).filter(([,r])=>r.stock>0).map(([k])=>k)])].join(', ');ls.set(KEY,u.prefs);draw();return;}
        if(action==='beat-board'){const values=['loading','unloading'].filter(phase=>paid(u.prefs,phase)).map(phase=>u.data.board?.benchmarks?.[phase]).filter(v=>v!=null);if(values.length)u.prefs.payout_target=Math.max(...values)+1000;ls.set(KEY,u.prefs);tab('find');return;}
        if(action==='board-refresh')request(async()=>{u.data={...u.data,board:await Lab.api('/api/ptn/board')};u.status=u.data.board.available?'Public official board refreshed.':'Public board unavailable; competition remains unknown.';});
        if(action==='zero')request(async()=>{await post('/api/ptn/update',{action:'remaining',remaining:0});u.draft.remaining=0;u.status='Recorded zero outstanding tonnes. Close your Discord advert with Roomba.';});
        if(action==='generate'||action==='copy-advert')request(async()=>{u.advert=await Lab.api('/api/ptn/advert',{revision:u.data.revision});if(action==='copy-advert'){if(!navigator.clipboard)throw Error('Clipboard unavailable. Copy the preview manually.');await navigator.clipboard.writeText(u.advert.copy_text);}u.status=action==='copy-advert'?'Exact advert copied. Review /aco trade and post it yourself.':'Advert generated from checked game prices.';});
        if(action==='posted')request(async()=>{await post('/api/ptn/update',{action:'posted',link:u.postLink});u.status='Posted time recorded. This does not send a Discord message.';});
      });
      addEventListener('resize',fit);addEventListener('lab:relayout',fit);u.cleanup=()=>{removeEventListener('resize',fit);removeEventListener('lab:relayout',fit);};
    },
    render(el,S){
      const u=el._ptn;if(!u)return;const d=S.ptn||{};
      // A POST response can arrive ahead of queued SSE fields. Keep that newer
      // snapshot, and wait for the matching operation before rendering a revision.
      if(d.revision<u.data.revision)return;
      if(d.plan&&(!d.operation||d.operation.revision!==d.revision||d.operation.plan_id!==d.plan.id||d.operation.stage!==d.plan.stage))return;
      if(!d.plan&&d.operation)return;
      u.data=d;if(!Object.keys(u.prefs).length&&d.defaults){
        const saved=ls.get(KEY,null),old=ls.get('ptn.preferences.v2',null);
        u.prefs={...d.defaults,...(saved||old||{})};
        if(!saved&&old){
          Object.assign(u.prefs,{radius:1500,max_hop:1500,arrival:0,breadth:0,share_surplus:false,haul_mode:'both'});
          for(const name of ['loading_floor','unloading_floor'])if(old[name]===10000)u.prefs[name]=d.defaults[name];
          u.status='Search updated: all commodities, three carrier jumps per leg, surplus kept by you. Review payouts before searching.';
        }
        ls.set(KEY,u.prefs);
      }u.draw();
    },
    unmount(el){el._ptn?.cleanup();}
  });
})();
