/* Mining desk: stable forms, journal accounting and explicit community searches. */
(() => {
  const {esc, fmt, ls, spanshSys, inaraSt} = Lab.util;
  const money = n => n == null ? '--' : `${fmt(Math.round(n))} Cr`;
  const pct = v => v == null ? 'unknown' : `${fmt(v)}%`;
  const age = h => h == null ? 'date unknown' : h < 1 ? 'under 1h old' : `${fmt(Math.round(h))}h old`;
  const date = s => Number.isFinite(Date.parse(s)) ? new Date(s).toLocaleString() : 'unknown';
  const canon = s => {const n = String(s || '').toLowerCase().replace(/[^a-z0-9]/g, ''); return n === 'lowtemperaturediamond' ? 'lowtemperaturediamonds' : n;};
  const fields = f => Object.fromEntries(new FormData(f));
  const selectionHandlers = new Set();
  const selectSpot = r => {Lab.set('mining', {selected:r}); selectionHandlers.forEach(fn => fn());};
  const prefKey = 'elitelab.mining.filters.v1';
  const input = (label, name, value = '', type = 'text', max = 160) => `<label>${label}<input name="${name}" type="${type}" ${type === 'number' ? `min="1" max="${max}" required` : 'maxlength="160"'} value="${value}"></label>`;

  function drawSession(el, S) {
    const m = S.mining?.summary || {}, p = m.profit || {}, last = m.last_prospect, left = p.remaining || {};
    const pp = m.powerplay || {};
    const held = Object.values(left).reduce((n, v) => n + v, 0);
    el.querySelector('[data-metrics]').innerHTML = `
      <div class="mine-metric mine-net"><div class="k">${p.unknown_market_sale_tons ? 'Known' : 'Recorded'} sale proceeds</div><strong data-market-proceeds>${money(p.market_sale_proceeds || 0)}</strong><small>Full commodity sales this game session; before costs</small></div>
      <div class="mine-metric"><div class="k">Refined / still tracked</div><strong data-mining-total>${fmt(m.refined_tons || 0)} t</strong><small>${fmt(held)} t unsold in ship</small></div>
      <div class="mine-metric"><div class="k">Recorded production</div><strong>${m.tons_per_hour == null ? '--' : fmt(m.tons_per_hour)} t/h</strong><small>${money(p.net_per_hour)} / h attributed net</small></div>
      <div class="mine-metric"><div class="k">Attributed mining net</div><strong>${money(p.net_profit || 0)}</strong><small>${fmt(p.sold_tons || 0)} / ${fmt(p.market_sold_tons || 0)} sold tons attributed since reload; ${money(p.operating_costs || 0)} recorded costs</small></div>`;
    const meritDetailsOpen = el.querySelector('[data-mining-powerplay] details')?.open;
    el.querySelector('[data-mining-powerplay]').innerHTML = `<div class="mine-title"><b>Powerplay merits</b><span class="tag">${esc(pp.power || 'Pledge unknown / unpledged')}</span></div>
      <div class="grid2"><div><div class="k">Recorded session gains</div><div class="v">${fmt(pp.session_merits || 0)}</div><div class="note">Total merits: ${pp.total_merits == null ? 'unknown' : fmt(pp.total_merits)}</div></div><div><div class="k">Associated with mining sales (estimated)</div><div class="v" data-mining-merits>${fmt(pp.sale_associated_merits || 0)}</div><div class="note">${fmt(pp.unassociated_merits || 0)} merits not associated with a mining sale</div></div></div>
      <div class="note">Sale association is estimated and can include bonuses.</div><details><summary>How merit association works</summary><div class="note">${esc(pp.note || '')}</div></details>
      ${(pp.recent || []).slice(0, 3).map(g => `<div class="note">+${fmt(g.gained)} | ${esc(g.timestamp)} | ${g.sale_associated ? 'Estimated association: ' + esc(g.sale?.commodity) + ' sale at ' + esc(g.sale?.station || g.sale?.system || 'unknown location') : 'Not associated with a mining sale'}</div>`).join('')}`;
    if (meritDetailsOpen) el.querySelector('[data-mining-powerplay] details').open = true;
    el.querySelector('[data-session-status]').textContent = `${m.ended ? 'Last game session ended.' : 'Current game session.'} ${m.partial ? 'Partial journal history. ' : ''}${m.as_of ? 'As of ' + m.as_of : 'Waiting for mining activity.'}`;
    el.querySelector('[data-production]').innerHTML = m.refined_tons ? `<table><thead><tr><th>Refinery output</th><th class="num">Produced</th><th class="num">Unsold</th></tr></thead><tbody>${(m.commodities || []).map(r => `<tr><td>${esc(r.name)}</td><td class="num">${fmt(r.tons)} t</td><td class="num">${fmt(left[r.key] || 0)} t</td></tr>`).join('')}${m.other_tons ? `<tr><td>Other / unknown</td><td>${fmt(m.other_tons)} t</td><td>--</td></tr>` : ''}</tbody></table>` : '<div class="mine-empty">No refinery output recorded. Refine mining fragments to start counting tons.</div>';
    el.querySelector('[data-prospect]').innerHTML = last ? `<div class="mine-title"><b>Latest prospector report</b><span class="tag">${fmt(m.prospector_reports)} reports</span></div>
      ${last.motherlode ? `<div class="mine-core">Core: <b>${esc(last.motherlode)}</b></div>` : ''}<div class="note">${esc(last.content || 'Material content unknown')} | Remaining: ${pct(last.remaining)}</div>
      <div class="mine-composition">${(last.materials || []).map(r => `<div><div class="mine-title"><b>${esc(r.name)}</b><span>${pct(r.proportion)}</span></div><div class="bar"><i style="width:${Number.isFinite(r.proportion) ? Math.max(0, Math.min(100, r.proportion)) : 0}%"></i></div></div>`).join('') || '<div class="note">No composition reported.</div>'}</div>
      <div class="note">Recorded ${esc(last.timestamp || 'at an unknown time')}. Reports may revisit the same asteroid.</div>` : '<div class="mine-empty"><b>No prospector report recorded.</b><p>Prospect an asteroid to see its composition, core and remaining percentage.</p></div>';
    const ledgerOpen = el.querySelector('[data-ledger] details')?.open;
    el.querySelector('[data-ledger]').innerHTML = `<div class="mine-title"><b>Session ledger</b><span class="tag">${p.estimated ? 'Estimated attribution' : 'Journal evidence'}</span></div>
      <div class="note">Full sale receipts include cargo held before a game reload. Attributed mining net covers only refinery units tracked in this game session and subtracts recorded operating costs. It is not the full haul's profit.</div>${p.unknown_market_sale_tons ? `<div class="note bad">Incomplete sale receipts: ${fmt(p.unknown_market_sale_tons)} sold tons have no recorded price.</div>` : ''}
      <div class="mine-transactions">${(p.transactions || []).map(t => `<div class="mine-transaction"><div><b>${esc(t.label)}</b><small>${esc(t.timestamp)}${t.tons ? ' | ' + fmt(t.tons) + ' t sold' : ''}${t.tracked_tons != null ? ' | ' + fmt(t.tracked_tons) + ' t / ' + money(t.tracked_credits) + ' attributed to this mining session' : ''}</small></div><span class="${t.credits < 0 ? 'warn' : 'ok'}">${t.credits > 0 ? '+' : ''}${money(t.credits)}</span></div>`).join('') || '<div class="note">Sales, limpets, fuel, repairs and ammunition appear here as the journal records them.</div>'}</div>
      <details><summary>How profit and rates are calculated</summary><div class="note">${esc(p.note || '')}</div><div class="note">${esc(m.rate_note || '')} ${m.timing_incomplete ? 'Rate unavailable: a mining timestamp is missing or invalid.' : ''}</div></details>`;
    if (ledgerOpen) el.querySelector('[data-ledger] details').open = true;
    const cargo = S.journal?.cargo || {}, capacity = S.journal?.cargo_capacity;
    el.querySelector('[data-hold]').textContent = `Ship hold: ${cargo.count == null ? 'unknown' : fmt(cargo.count) + ' t'}${capacity ? ' / ' + fmt(capacity) + ' t' : ''}. ${cargo.count == null ? 'Limpet count unknown' : fmt((cargo.items || []).find(r => r.key === 'drones')?.count || 0) + ' limpets reported'}.`;
    el.querySelector('[data-commodities]').innerHTML = [...new Set(['Platinum', 'Painite', 'Osmium', 'Low Temperature Diamonds', 'Alexandrite', 'Monazite', ...(m.commodities || []).map(r => r.name)])].map(s => `<option value="${esc(s)}"></option>`).join('');
    const quote = el._mine.quote, row = (m.commodities || []).find(r => canon(r.name) === canon(quote?.commodity)), tons = row ? left[row.key] || 0 : 0;
    el.querySelector('[data-valuation]').innerHTML = quote ? `<b>Unsold estimate: ${money(tons * quote.price)}</b><div class="note">${fmt(tons)} tracked tons of ${esc(quote.commodity)} at ${money(quote.price)} / t. ${esc(quote.station)} (${esc(quote.system)}), ${esc(quote.updated_at)}. Separate from realized profit; prices and demand may change.${tons > quote.demand ? ' Load exceeds reported demand.' : ''} ${esc(quote.merit_route?.reason || 'Merit eligibility unverified.')}</div>` : '<b>Unsold cargo value</b><div class="note">Find buyers and use a quote to value the tracked unsold portion of that commodity.</div>';
    const selected = S.mining?.selected;
    el.querySelector('[data-destination]').innerHTML = selected ? `<span class="k">Selected mining spot</span><b>${esc(selected.ring)}</b><div class="note">${esc(selected.system)} | ${fmt(selected.distance)} Ly from the search origin. Selected in EliteLab; buyer searches start here. Highlighted on the map when coordinates are available. This does not plot an in-game route.</div><button class="mini" data-copy="${esc(selected.system)}">Copy system</button>` : '<span class="k">Mining spot selection</span><div class="note">Select a mining spot to highlight it and search for buyers from that system.</div>';
  }

  function opportunity(r) {
    if (!r.merit_eligibility) return '';
    const b = r.buyer, e = r.merit_estimate;
    return `<div class="mine-panel"><b>${e ? `Conditional estimate: ${fmt(e.merits)} merits / ${fmt(r.quantity)} t` : 'Merit yield unknown'}</b>
      <div class="note">${esc(r.commodity)} | ${esc(r.powerplay_mode)}${b ? ` | Sell at ${esc(b.station)}, ${esc(b.system)} (${fmt(b.from_ring_ly)} Ly from this ring's system). ${money(b.price)} / t; demand ${fmt(b.demand)} t; pad ${esc(b.pad)}; ${age(b.age_hours)}.` : ' | No matching fresh sell destination in the markets checked.'}</div>
      ${e ? `<div class="note">${fmt(e.sample_merits)} merits associated with ${fmt(e.sample_tons)} t on ${esc(date(e.timestamp))}. ${esc(e.note)}</div>` : ''}
      <div class="note">${esc(r.merit_note)}</div>${b ? `<button class="mini" data-copy="${esc(b.system)}">Copy sell system</button>` : ''}</div>`;
  }

  function syncPlanning(el, S) {
    const u = el._mine, j = S.journal || {}, f = el.querySelector('[data-form="spots"]');
    const valid = Number.isFinite(j.jump_range_laden) && j.jump_range_laden > 0 && Number.isFinite(j.jump_range_now) && j.jump_range_now > 0;
    const cap = valid ? Math.min(j.jump_range_laden, j.jump_range_now, 200) : null;
    const context = JSON.stringify([cap,j.system,j.ship_info?.id,j.status?.cargo_tons,j.status?.fuel,j.cargo,S.mining?.summary?.powerplay?.power]);
    if (u.context !== context) {
      const changed = u.context !== undefined; u.context = context;
      if (changed) {
        ++u.generation.spots; ++u.generation.buyers; u.spots = []; u.buyers = []; u.quote = null;
        el.querySelector('[data-results=buyers]').innerHTML = '';
        el.querySelector('[data-search-status=buyers]').textContent = 'Ship, cargo, pledge or location changed. Search to refresh buyers.';
        el.querySelector('[data-results="spots"]').innerHTML = '';
        el.querySelector('[data-search-status="spots"]').textContent = 'Ship, cargo, fuel, pledge or location changed. Search to refresh results.';
        if (S.mining?.spots?.length || S.mining?.selected) Lab.set('mining', {spots:[],selected:null});
      }
      const bf=el.querySelector('[data-form=buyers]'); if (!bf.elements.ref.value || bf.elements.ref.value===u.origin) bf.elements.ref.value=j.system || '';
      if (!f.elements.ref.value || f.elements.ref.value === u.origin) f.elements.ref.value = j.system || '';
      u.origin = j.system;
    }
    const radius = f.elements.radius; radius.step = 'any'; radius.min = '0.01'; radius.max = cap ?? 200;
    if (cap && (!radius.value || Number(radius.value) > cap)) radius.value = String(cap);
    radius.disabled = !valid; f.querySelector('[type="submit"]').disabled = !valid;
    el.querySelector('[data-range-status]').textContent = valid
      ? `Ship range cap: ${fmt(cap)} Ly. Full hold and tank, limited by current fuel/cargo; no temporary boost assumed. Other origins are planning locations, not reachability from your ship.`
      : 'Laden range unavailable or current range is zero. Load the current ship and check its fuel in game.';
    const selected = S.mining?.selected;
    if (selected !== u.selection) {
      u.selection = selected;
      const buyers = el.querySelector('[data-form="buyers"]');
      if (selected) {
        buyers.elements.ref.value = selected.system;
        buyers.elements.mined_in.value = selected.system;
        if (selected.commodity) {
          buyers.elements.commodity.value = selected.commodity;
          buyers.elements.quantity.value = selected.quantity;
          buyers.elements.powerplay_mode.value = selected.powerplay_mode;
          buyers.elements.power.value = selected.planning_power;
          buyers.elements.pad.value = selected.planning_pad;
          buyers.elements.hours.value = selected.planning_hours;
        }
      }
      buyers.dispatchEvent(new Event('input'));
    }
  }

  function buyerGuide(el) {
    const f=el.querySelector('[data-form=buyers]'), mode=f.elements.powerplay_mode.value;
    f.elements.mined_in.required=mode!=='none';
    el.querySelector('[data-buyer-guide]').textContent=mode==='none'
      ? 'Credits only: buyers are ranked by sale value. For mining merit routes, start with MeritMiner above. A high price does not mean this sale earns Powerplay merits.'
      : mode==='reinforcement'
      ? 'Reinforcement: mine and sell in the same system controlled by your power. Enter the actual mining source, even if you have travelled since. Confirm the local activity before selling.'
      : 'Acquisition: mine in your power\'s Fortified or Stronghold system, then sell at an eligible acquisition destination within its 20 or 30 Ly control range. Enter the actual source; transferred or purchased cargo is not verified.';
  }

  function drawResults(el, kind, d) {
    const u = el._mine; u[kind] = (d.results || []).map(r => kind === 'spots' ? {...r, search_origin:d.ref, manual_origin:d.manual_origin, planning_power:d.power, planning_pad:d.pad, planning_hours:d.hours} : r); u.buyerQuery = kind === 'buyers' ? d : u.buyerQuery;
    el.querySelector(`[data-results="${kind}"]`).innerHTML = (kind === 'buyers' ? `<div class="mine-panel" data-buyer-purpose><b>${d.purpose === 'credit_quotes' ? 'Credit buyers - merits not checked' : 'Powerplay candidates - rewards unverified'}</b><p>${esc(d.purpose_note)}</p>${d.mined_in ? `<p>Entered mining source: ${esc(d.mined_in)}. Travel from: ${esc(d.ref)}.</p>` : ''}</div>` : '') + (kind === 'buyers' && d.powerplay_mode && d.powerplay_mode !== 'none' ? `<div class="note">${esc(d.power)} | ${esc(d.powerplay_mode)} candidates. Merit eligibility unverified; check local activities and mining origin in game.</div>` : '') + (d.ranking_note ? `<p class="note">${esc(d.ranking_note)}</p>` : '') + `<details><summary>Data coverage and estimate limits</summary><div class="note">${esc(d.note)} ${esc(d.market_note || '')}</div></details>` + (u[kind].length ? u[kind].map((r, i) => kind === 'spots' ? `<article class="mine-result">
      <div class="mine-title"><div><b>${esc(r.ring)}</b><small>${esc(r.system)} | ${esc(r.ring_type)}</small></div><strong>${fmt(r.distance)} Ly</strong></div>
      <div class="mine-tags"><span class="tag ${r.reserve === 'Pristine' ? 'ok' : ''}">${esc(r.reserve)} reserves</span><span>${r.jumps == null ? 'Jumps unknown' : '~' + fmt(r.jumps) + ' jumps'}</span><span>${r.arrival_ls == null ? 'Arrival unknown' : fmt(Math.round(r.arrival_ls)) + ' ls'}</span><span>${esc(r.power_state)}</span></div>
      <div class="mine-signals">${r.signals.length ? r.signals.map(s => `<span>${esc(s.name)} <b>${fmt(s.count)}</b></span>`).join('') : '<span>No hotspot reports; scan this ring to check.</span>'}</div>
      <div class="note">Body ${esc(date(r.updated_at))} (${age(r.age_hours)}). Hotspots ${esc(date(r.signals_updated_at))}. ${r.permit_required === true ? 'Permit required.' : r.permit_required == null ? 'Permit status unknown.' : ''}</div>
      ${opportunity(r)}<div class="row"><button class="mini primary" data-pin="${i}">Select mining spot</button><button class="mini" data-copy="${esc(r.system)}">Copy system</button><a href="${spanshSys(r.system)}" target="_blank" rel="noopener noreferrer">Spansh</a></div></article>` : `<article class="mine-result">
      <div class="mine-title"><div><b>${esc(r.station)}</b><small>${esc(r.system)} | ${fmt(r.distance)} Ly</small></div><strong class="ok">${money(r.estimated_sale)}</strong></div>
      <div class="mine-tags"><span>${money(r.price)} / t</span><span>Demand ${fmt(r.demand)} t</span><span>Pad ${esc(r.pad)}</span><span>${esc(r.power_state || 'Unknown power state')}</span><span>${age(r.age_hours)}</span><span>${r.arrival_ls == null ? 'Arrival unknown' : fmt(Math.round(r.arrival_ls)) + ' ls'}</span></div>
      <p class="note" data-route-status>${esc(r.merit_route?.reason || 'Merit eligibility unverified.')}</p><div class="row"><button class="mini primary" data-quote="${i}">Use credit quote</button><button class="mini" data-copy="${esc(r.system)}">Copy system</button><a href="${inaraSt(r.station)}" target="_blank" rel="noopener noreferrer">Check station</a></div></article>`).join('') : `<div class="mine-empty">${kind === 'spots' ? 'No reported rings matched. Try another ring type or clear the hotspot filter. Searches stay within the ship range cap.' : 'No compatible fresh quotes cover this load in the markets checked. Check the mining source and goal before changing price filters.'}</div>`);
    if (kind === 'spots') Lab.set('mining', {spots: u.spots, selected: null});
  }

  Lab.card({
    id: 'mining', requires: ['mining', 'journal', 'powerplay'],
    mount(el) {
      el.classList.add('mining-desk');
      const u = el._mine = {generation: {spots: 0, buyers: 0}, destroyed: false, spots: [], buyers: [], quote: null};
      el.innerHTML = `<div class="mine-heading"><h3>Mining overview</h3></div><div class="mine-metrics" data-metrics></div><div class="note" data-session-status></div><div class="mine-panel" data-mining-powerplay></div>
        <div class="mine-panel" data-meritminer><b>Mining for merits</b><p>Plan your route with MeritMiner. Choose your power, goal and mineral there, then track your haul and recorded merits here.</p><a href="https://meritminer.cc/" target="_blank" rel="noopener noreferrer">Open MeritMiner</a></div>
        <div class="mine-columns"><div class="mine-workbench"><div class="mine-tabs" role="tablist" aria-label="Mining planning"><button role="tab" aria-selected="true" data-tab="spots">01 Nearby rings</button><button role="tab" aria-selected="false" data-tab="buyers">02 Sell your haul</button></div>
        <section data-pane="spots"><form data-form="spots" class="mine-form">${input('From system', 'ref')}${input('Radius (Ly)', 'radius', '', 'number', 200)}<label>Ring type<select name="ring_type"><option>Metallic</option><option>Metal Rich</option><option>Icy</option><option>Rocky</option><option>Any</option></select></label><label>Reported hotspot<input name="hotspot" list="mine-commodities" maxlength="160" placeholder="Any; e.g. Platinum"></label><label>Reserves<select name="pristine"><option value="false">Any reserve level</option><option value="true">Pristine only</option></select></label><label>Powerplay<select name="power"><option value="">Any / pledged for merits</option></select></label><label>Order by<select name="sort"><option value="distance">Distance</option><option value="merits">Merit opportunities</option></select></label><label>Mining goal<select name="powerplay_mode"><option value="reinforcement">Reinforcement: same system</option><option value="acquisition">Acquisition: nearby target</option></select></label>${input('Planned load (tons)', 'quantity', 1, 'number', 1000000)}<label>Minimum pad<select name="pad"><option>L</option><option>M</option><option>S</option></select></label>${input('Market age (hours)', 'hours', 24, 'number', 72)}<button class="primary" type="submit">Find mining spots</button><button type="button" data-here>Use current system</button></form><div class="note" data-range-status></div><div class="note" role="status" data-search-status="spots">Choose a ring type and search. Check reported hotspots with your DSS.</div><div class="mine-results" data-results="spots"></div></section>
        <section data-pane="buyers" hidden><div class="mine-panel" data-buyer-guide></div><form data-form="buyers" class="mine-form">${input('Travel from system', 'ref')}${input('Cargo mined in (confirm source)', 'mined_in')}<label>Commodity<input name="commodity" list="mine-commodities" maxlength="160" value="Platinum" required></label>${input('Load (tons)', 'quantity', 1, 'number', 1000000)}${input('Radius (Ly)', 'radius', 100, 'number', 200)}<label>Minimum pad<select name="pad"><option>L</option><option>M</option><option>S</option></select></label>${input('Market age (hours)', 'hours', 24, 'number', 72)}<label>Sale goal<select name="powerplay_mode"><option value="none">Credits only - any market</option><option value="acquisition">Acquisition candidates</option><option value="reinforcement">Reinforcement candidates</option></select></label><label>Power<select name="power"><option value="pledged">My pledged power</option></select></label><button class="primary" type="submit">Find buyers</button><button type="button" data-load>Use tracked haul</button></form><div class="note" role="status" data-search-status="buyers">Compare fresh reported quotes for your commodity and load.</div><div class="mine-results" data-results="buyers"></div></section>
        <datalist id="mine-commodities" data-commodities></datalist><div class="mine-destination" data-destination></div><div class="mine-valuation" data-valuation></div></div>
        <div class="mine-session"><div class="mine-panel" data-prospect></div><div class="mine-panel"><div class="mine-title"><b>Your production</b></div><div data-production></div><div class="note" data-hold></div></div><div class="mine-panel" data-ledger></div></div></div>`;
      u.syncSelection = () => syncPlanning(el, Lab.state); selectionHandlers.add(u.syncSelection);
      const saved = ls.get(prefKey, {});
      el.querySelectorAll('form').forEach(form => {
        const kind = form.dataset.form, status = el.querySelector(`[data-search-status="${kind}"]`);
        for (const [name, value] of Object.entries(saved?.[kind] || {})) {const field = form.elements.namedItem(name); if (field && typeof value === 'string' && value.length <= 160 && name !== 'power') field.value = value;}
        form.addEventListener('input', () => {if (kind === 'buyers') {u.quote = null; drawSession(el, Lab.state);} ++u.generation[kind]; buyerGuide(el); status.textContent = 'Filters changed. Search to refresh results.'; el.querySelector(`[data-results="${kind}"]`).innerHTML = ''; if (kind === 'spots') {u.spots = []; Lab.set('mining', {spots: [], selected: null});} ls.set(prefKey, Object.fromEntries([...el.querySelectorAll('form')].map(f => [f.dataset.form, fields(f)])));});
        form.onsubmit = async event => {
          event.preventDefault(); syncPlanning(el, Lab.state); if (kind === 'buyers') {u.quote = null; drawSession(el, Lab.state);} const generation = ++u.generation[kind]; if (kind === 'spots') {u.spots = []; Lab.set('mining', {spots: [], selected: null});} status.textContent = 'Searching community reports...'; el.querySelector(`[data-results="${kind}"]`).innerHTML = '';
          try {const d = await Lab.api('/api/mining/' + kind, fields(form)); if (u.destroyed || generation !== u.generation[kind]) return; drawResults(el, kind, d); status.textContent = kind === 'spots' ? `${d.results.length} rings from ${d.bodies_checked} bodies checked within ${fmt(d.radius)} Ly of ${d.ref}. ${d.manual_origin ? 'Manual planning origin; not reachability from your ship.' : ''}` : `${d.results.length} quotes from ${d.stations_checked} markets checked. ${fmt(d.quantity)} t ${d.commodity}.`;}
          catch (error) {if (u.destroyed || generation !== u.generation[kind]) return; status.textContent = error.message; if (kind === 'spots') Lab.set('mining', {spots: [], selected: null});}
        };
      });
      el.addEventListener('click', event => {
        const tab = event.target.closest('[data-tab]'); if (tab) {el.querySelectorAll('[data-tab]').forEach(b => b.setAttribute('aria-selected', String(b === tab))); el.querySelectorAll('[data-pane]').forEach(p => p.hidden = p.dataset.pane !== tab.dataset.tab);}
        if (event.target.closest('[data-here]')) {const f = el.querySelector('[data-form="spots"]'); f.elements.ref.value = Lab.state.journal?.system || ''; f.dispatchEvent(new Event('input'));}
        if (event.target.closest('[data-load]')) {const m = Lab.state.mining?.summary || {}, left = m.profit?.remaining || {}, row = (m.commodities || []).filter(r => left[r.key] > 0).sort((a,b) => left[b.key] - left[a.key])[0]; if (row) {const f = el.querySelector('[data-form="buyers"]'); f.elements.commodity.value = row.name; f.elements.quantity.value = left[row.key]; f.dispatchEvent(new Event('input'));} else el.querySelector('[data-search-status="buyers"]').textContent = 'No tracked unsold refinery output in the ship.';}
        const pin = event.target.closest('[data-pin]'); if (pin && u.spots[Number(pin.dataset.pin)]) {selectSpot(u.spots[Number(pin.dataset.pin)]);}
        const quote = event.target.closest('[data-quote]'); if (quote && u.buyers[Number(quote.dataset.quote)]) {u.quote = {...u.buyers[Number(quote.dataset.quote)], commodity:u.buyerQuery.commodity}; drawSession(el, Lab.state);}
      });
    },
    render(el, S) {
      syncPlanning(el, S); buyerGuide(el);
      el.querySelectorAll('[name="power"]').forEach(power => {
        if (!power.dataset.loaded && S.powerplay?.powers?.length) {const kind = power.form.dataset.form; S.powerplay.powers.forEach(p => {const o = document.createElement('option'); o.value = p; o.textContent = p; power.appendChild(o);}); const savedPower = ls.get(prefKey, {})?.[kind]?.power; if (S.powerplay.powers.includes(savedPower) || (kind === 'buyers' && savedPower === 'pledged')) power.value = savedPower; power.dataset.loaded = '1';}
      });
      el.querySelectorAll('[name="ref"]').forEach(f => {if (!f.value && S.journal?.system) f.value = S.journal.system;});
      drawSession(el, S);
    },
    unmount(el) {el._mine.destroyed = true; selectionHandlers.delete(el._mine.syncSelection);},
  });
  Lab.map.addLayer('mining', {label:'mining rings', color:'#f0b062', z:2,
    points:S => (S.mining?.spots || []).filter(r => [r.x,r.y,r.z].every(Number.isFinite)).map(r => ({name:r.system,x:r.x,y:r.y,z:r.z,r:4,sub:`${r.ring} | ${r.reserve} | ${r.distance} Ly`, selected:S.mining?.selected?.ring === r.ring && S.mining?.selected?.system === r.system,onClick:() => selectSpot(r)})),
  });
})();
