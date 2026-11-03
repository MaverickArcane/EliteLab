/* Trading: ship-aware searches, a comparison table, and one selected route with its next action. */
(() => {
  const {esc, fmt, ls} = Lab.util;
  const KEY = 'personal.search.v2', TOP = 10;
  const price = n => `${fmt(n)} Cr`;
  const hours = iso => { const t = Date.parse(iso); return Number.isFinite(t) ? Math.max(0, (Date.now() - t) / 36e5) : null; };
  const ageClass = h => h == null ? 'muted' : h < 12 ? 'ok' : h < 48 ? 'warn' : 'bad';
  const ageText = h => h == null ? 'age unknown' : h < 1 ? 'under 1 h' : `${Math.round(h)} h`;
  const external = (href, label) => `<a class="mini" href="${esc(href)}" target="_blank" rel="noopener noreferrer">${label}</a>`;
  const routeLink = (r, settings) => {
    const first = r.legs[0];
    const p = new URLSearchParams({ps1: `${first.buy.station} [${first.buy.system}]`, ps2: `${first.sell.station} [${first.sell.system}]`,
      pi7: '1', pi10: String(r.quantity), pi4: String({S: 1, M: 2, L: 3}[settings.pad]), pi5: settings.surface ? '0' : '1'});
    // Inara only offers discrete age/approach choices. Exact pair is prefilled;
    // do not imply the external website shares unsupported search filters.
    return `https://inara.cz/elite/market-traderoutes-search/?${p}`;
  };
  const oldest = r => { const ages = r.legs.flatMap(l => [hours(l.buy.observed_at), hours(l.sell.observed_at)]); return ages.some(h => h == null) ? null : Math.max(...ages); };
  const stop = (m, label) => `<div class="trade-pair-stop"><div class="row"><span class="tag">${label}</span><strong>${price(m.price)}/t</strong></div>
    <div class="trading-station">${esc(m.station)}</div><div class="muted">${esc(m.system)}</div>
    <div class="row trading-actions"><button type="button" class="mini" data-copy="${esc(m.system)}">Copy system</button><button type="button" class="mini" data-copy="${esc(m.station)}">Copy station</button>${external(Lab.util.inaraMarket(m.station, m.system), 'Inara market')}</div>
    <div class="note">${fmt(m.volume)} t ${label === 'Buy' ? 'supply' : 'demand'} | ${esc(m.pad)} pad | ${m.arrival_ls == null ? 'Approach unknown' : fmt(m.arrival_ls) + ' Ls'}<br>Reported ${esc(new Date(m.observed_at).toLocaleString())}</div></div>`;
  const route = (r, result, selected) => `<article class="trade-pair trading-route">
    <div class="trading-summary"><div><span class="tag">${r.route_type === 'round_trip' ? 'Round trip' : 'One way'}</span><h3>${esc(r.legs[0].buy.station)} to ${esc(r.legs[0].sell.station)}${r.legs.length === 2 ? ' and back' : ''}</h3></div><div class="trading-total"><strong class="ok">${price(r.profit)}</strong><span class="note">estimated profit / ${r.legs.length === 2 ? 'round trip' : 'load'}</span></div></div>
    <div class="trading-metrics"><span>${fmt(r.quantity)} t per leg</span><span>${fmt(r.distance)} Ly each way</span><span>${r.estimated_jumps == null ? 'Laden jump estimate unavailable' : fmt(r.estimated_jumps) + ' estimated jumps per leg'}</span><span>${Number(r.return_on_cost).toFixed(1)}% return on purchase costs</span></div>
    ${r.legs.map((leg, i) => `<section class="trading-leg"><div class="row trade-pair-heading"><b>${i === 0 ? 'Outbound' : 'Return'}: ${esc(leg.commodity)}</b><span class="ok">+${price(leg.profit)} <span class="muted">(${price(leg.per_ton)}/t)</span></span></div><div class="trade-pair-stops">${stop(leg.buy, 'Buy')}${stop(leg.sell, 'Sell')}</div></section>`).join('')}
    <div class="row trade-pair-footer"><span class="note">${price(r.required_credits)} starting credits needed | ${price(r.cost)} total purchases</span><span class="row">${external(routeLink(r, result.settings), 'View route on Inara')}<button type="button" class="mini primary" data-select="${esc(r.id)}" ${selected ? 'disabled' : ''}>${selected ? 'Selected route' : 'Select this route'}</button></span></div>
    ${result.credits != null && r.required_credits > result.credits ? '<p class="warn">Starting credits needed exceed your reported balance. Reduce the load.</p>' : ''}
    ${result.ship_capacity != null && r.quantity > result.ship_capacity ? '<p class="warn">Load exceeds your reported ship capacity.</p>' : ''}</article>`;
  const table = (u, planId) => {
    const result = u.result, rows = u.all ? result.rows : result.rows.slice(0, TOP);
    if (!result.rows.length) return '<p class="note">No routes found in the markets checked. Try a smaller load, older reports, more stations, a wider distance, or one-way trades. Round trips need a profitable full-load trade in both directions.</p>';
    const line = (r, i) => {
      const age = oldest(r), selected = r.id === planId, open = r.id === u.expanded;
      return `<tr data-route="${esc(r.id)}" class="${selected ? 'sel' : ''}"><td class="num">${i + 1}</td>
        <td><b>${esc(r.legs[0].buy.station)}</b> <span class="muted">${esc(r.legs[0].buy.system)}</span><br>to <b>${esc(r.legs[0].sell.station)}</b> <span class="muted">${esc(r.legs[0].sell.system)}</span>${r.legs.length === 2 ? ' <span class="tag">and back</span>' : ''}</td>
        <td>${r.legs.map(l => esc(l.commodity)).join('<br>')}</td><td class="num ok">${fmt(r.profit)}</td><td class="num">${fmt(Math.round(r.per_ton))}</td>
        <td class="num">${fmt(r.distance)}</td><td class="num">${r.estimated_jumps == null ? '-' : fmt(r.estimated_jumps)}</td><td class="num">${Number(r.return_on_cost).toFixed(0)}%</td>
        <td class="num">${fmt(r.required_credits)}</td><td class="${ageClass(age)}">${ageText(age)}</td><td>${esc(r.legs.map(l => l.buy.pad + '/' + l.sell.pad).join(' '))}</td>
        <td class="trade-row-actions"><button type="button" class="mini primary" data-select="${esc(r.id)}" ${selected ? 'disabled' : ''}>${selected ? 'Selected' : 'Select'}</button> <button type="button" class="mini" data-details="${esc(r.id)}" aria-expanded="${open}">${open ? 'Hide' : 'Details'}</button></td></tr>
        ${open ? `<tr class="trade-detail"><td colspan="12">${route(r, result, selected)}</td></tr>` : ''}`;
    };
    return `<div class="trade-table"><table><thead><tr><th class="num">#</th><th>Route</th><th>Goods</th><th class="num" title="Estimated profit for the whole route, before fuel and fees">Profit Cr</th><th class="num" title="Combined profit per tonne of hold">Cr/t</th><th class="num" title="Straight line per leg">Ly</th><th class="num" title="Estimated laden jumps per leg">Jumps</th><th class="num" title="Return on purchase costs">Return</th><th class="num" title="Starting credits needed">Credits</th><th title="Oldest market report in the route">Reports</th><th title="Landing pad at buy/sell">Pad</th><th></th></tr></thead><tbody>${rows.map(line).join('')}</tbody></table></div>
      ${result.rows.length > TOP ? `<div class="row"><button type="button" class="mini" data-personal-show aria-pressed="${u.all}">${u.all ? `Show top ${TOP}` : `Show all ${result.rows.length} routes`}</button></div>` : ''}`;
  };
  const legStatus = (l, known) => l.done ? `Sold ${fmt(l.sold)} t` : l.sold ? `${fmt(l.sold)} t sold so far` : known ? (l.aboard ? `${fmt(l.aboard)} t aboard` : 'Nothing aboard yet') : l.bought ? `${fmt(l.bought)} t bought (cargo unseen)` : 'Not started';
  const plan = S => {
    const P = S.personal || {}, p = P.plan, g = P.progress;
    if (!p || !g) return `<div class="trade-plan trade-plan-empty"><div class="k">Selected route</div><p>No route selected. Find routes below and choose Select; the next action, your cargo and the destination then follow you here and on the map.</p></div>`;
    const n = g.next, q = g.quotes || {}, known = g.cargo_known, current = g.leg == null ? null : g.legs[g.leg];
    const facts = [
      n ? (n.dist == null ? 'Distance unknown' : `${fmt(n.dist)} Ly straight line`) : `${fmt(g.legs.reduce((s, l) => s + l.sale_total, 0))} Cr recorded sales`,
      current ? (known ? `${fmt(current.aboard)} t ${esc(current.commodity)} aboard` : 'Cargo unknown') : '',
      `<span class="${ageClass(q.age_hours)}">Reports ${ageText(q.age_hours)} old${q.status && q.status !== 'unknown' ? ', ' + esc(q.status) : ''}</span>`,
      g.credits_short === true ? '<span class="bad">Credits short for this purchase</span>' : g.credits_short === false ? 'Credits cover this purchase' : '',
    ].filter(Boolean);
    return `<div class="trade-plan ${g.stage === 'complete' ? 'is-complete' : ''}">
      <div class="row trade-plan-head"><span class="tag">${esc(g.title)}</span><b>${p.legs.map(l => esc(l.commodity)).join(' / ')}</b><span class="muted">${p.route_type === 'round_trip' ? 'Round trip' : 'One way'} | ${fmt(p.quantity)} t per leg${g.leg == null ? '' : ` | Leg ${g.leg + 1} of ${g.leg_count}`}</span></div>
      <div class="trade-plan-action"><div class="k">Your next action</div><h3>${esc(g.action)}</h3><p>${esc(g.reason)}</p></div>
      <div class="trading-metrics">${facts.map(f => `<span>${f}</span>`).join('')}</div>
      <div class="row trade-plan-actions">${n ? `<button type="button" class="mini primary" data-plan-map aria-pressed="${!!P.ui_selected}">${P.ui_selected ? 'Shown on map' : 'Show on map'}</button><button type="button" class="mini" data-copy="${esc(n.system)}">Copy system</button><button type="button" class="mini" data-copy="${esc(n.station)}">Copy station</button>${external(Lab.util.inaraMarket(n.station, n.system), 'Inara market')}` : ''}<button type="button" class="mini" data-plan-focus="cargo">View cargo</button><button type="button" class="mini" data-plan-clear>Clear route</button></div>
      <div class="trade-plan-legs">${p.legs.map((l, i) => `<div class="${g.legs[i].done ? 'done' : i === g.leg ? 'is-next' : ''}"><span class="tag">${i + 1}</span><b>${esc(l.commodity)}</b> <span class="muted">${esc(l.buy.station)} to ${esc(l.sell.station)} | ${price(l.buy.price)} to ${price(l.sell.price)}/t</span><span class="trade-leg-status">${legStatus(g.legs[i], known)}</span></div>`).join('')}</div>
      <section class="trade-powerplay-source"><b>Plan a Powerplay destination</b><p class="note">${esc(P.powerplay_handoff?.message || 'Waiting for route context.')} Eligibility and expected merits for these planned goods remain unknown.</p><div class="row">${(P.powerplay_handoff?.stops||[]).map(s=>`<button type="button" class="mini" data-plan-powerplay="${esc(s.role)}" data-context-token="${esc(P.powerplay_handoff.token)}" ${P.powerplay_handoff.ready?'':'disabled'}>Use ${esc(s.role)} stop: ${esc(s.system)}</button>`).join('')}</div><p class="note">Copies only the search origin and observed pledge into the finder. Review its distance and pad filters before searching; your trade route stays selected.</p></section>
      ${g.commander_changed ? `<p class="warn">Selected by commander ${esc(p.cmdr)}; the journal now shows a different commander. Clear or reselect the route.</p>` : ''}
      <p class="note">${esc(q.message || '')} Cargo aboard is not a purchase receipt; a leg counts as sold only from MarketSell events at the planned station. Distances are straight lines, not plotted routes. Selected ${esc(new Date(p.selected_at).toLocaleString())}.</p></div>`;
  };

  Lab.card({
    id: 'personal', requires: ['journal', 'personal'],
    mount(el) {
      const u = el._personal = {destroyed: false, result: null, expanded: null, all: false, planHtml: ''};
      el.classList.add('trading-body');
      el.innerHTML = `<div data-personal-plan></div>
        <div class="row trade-nav"><b>Find a trade route</b>${external('https://inara.cz/elite/market-traderoutes-search/', 'Open Inara')}</div>
        <form data-personal-search class="trade-form trading-form">
          <label>Route type<select name="route_type"><option value="round_trip">Round trip (return to start)</option><option value="one_way">One way</option></select></label>
          <label>Starting system<input name="origin" maxlength="160" placeholder="Current system"></label>
          <label>Destination system (optional)<input name="destination" maxlength="160" placeholder="Any system within range"></label>
          <label>Load per leg (t)<input name="quantity" type="number" min="1" max="1000000" placeholder="Current ship capacity"></label>
          <label>Distance limit<select name="distance_mode"><option value="ly">Light-years per leg</option><option value="jumps">Estimated laden jumps per leg</option></select></label>
          <label data-ly>Maximum distance per leg (Ly)<input name="distance" type="number" min="0.1" max="500" step="0.1" value="80" required></label>
          <label data-jumps hidden>Maximum estimated jumps per leg<input name="jumps" type="number" min="1" max="20" value="2" required disabled></label>
          <details class="trade-wide trade-details" data-personal-more><summary>More filters: station, pad, report age, approach, goods, breadth</summary><div class="trade-form trading-form">
            <label>Starting station (optional)<input name="station" maxlength="160" placeholder="Any eligible station in system"></label>
            <label>Minimum landing pad<select name="pad"><option>L</option><option>M</option><option>S</option></select></label>
            <label>Maximum report age<select name="hours"><option value="3">3 hours</option><option value="6">6 hours</option><option value="12">12 hours</option><option value="24" selected>24 hours</option><option value="72">72 hours</option></select></label>
            <label>Maximum station approach<select name="arrival"><option value="2000">2,000 Ls</option><option value="10000" selected>10,000 Ls</option><option value="50000">50,000 Ls</option><option value="0">Any distance</option></select></label>
            <label>Surface stations<select name="surface"><option value="0">Exclude</option><option value="1">Include</option></select></label>
            <label>Outbound commodity<select name="commodity"><option value="">All available goods</option></select></label>
            <label>Search breadth<select name="breadth"><option value="100">100 nearest eligible stations</option><option value="200">200 nearest eligible stations</option><option value="300">300 nearest eligible stations</option></select></label>
          </div></details>
          <div class="trade-wide note" data-ship-context></div>
          <div class="trade-wide row"><button type="submit" class="mini primary">Find routes</button><span class="note">Fleet carriers excluded. Round trips return to the same station; return cargo is chosen independently.</span></div>
        </form><p class="note trading-status" data-personal-status role="status">Choose your filters and find routes. Blank load uses your ship capacity.</p><div class="trade-pairs" data-personal-results></div>`;
      const form = el.querySelector('form'), status = el.querySelector('[data-personal-status]'), results = el.querySelector('[data-personal-results]');
      const old = ls.get('personal.search.v1', {});
      const saved = ls.get(KEY, {...old, breadth: '100'});
      for (const [k, v] of Object.entries(saved)) {
        if (k !== 'commodity' && form.elements[k]) form.elements[k].value = v;
      }
      if (saved.commodity) {
        const option = document.createElement('option'); option.value = saved.commodity; option.textContent = saved.commodity;
        form.elements.commodity.append(option); form.elements.commodity.value = saved.commodity;
      }
      const defaults = {station: '', pad: 'L', hours: '24', arrival: '10000', surface: '0', commodity: '', breadth: '100'};
      el.querySelector('[data-personal-more]').open = Object.entries(defaults).some(([k, v]) => String(form.elements[k].value) !== v);
      const mode = () => {
        const jumps = form.elements.distance_mode.value === 'jumps';
        el.querySelector('[data-ly]').hidden = jumps; el.querySelector('[data-jumps]').hidden = !jumps;
        form.elements.distance.disabled = jumps; form.elements.jumps.disabled = !jumps;
      };
      form.elements.distance_mode.onchange = mode; mode();
      const draw = () => { if (u.result) { results.innerHTML = u.result.warnings.map(w => `<p class="warn">${esc(w)}</p>`).join('') + table(u, Lab.state.personal?.plan?.id); Lab.relayout(); } };
      u.draw = draw;
      form.onsubmit = async event => {
        event.preventDefault();
        const params = Object.fromEntries(new FormData(form));
        ls.set(KEY, params);
        const j = Lab.state.journal || {};
        params.origin = params.origin.trim() || j.system || '';
        params.quantity = params.quantity || j.cargo_capacity || '';
        const button = form.querySelector('[type=submit]'); button.disabled = true;
        status.textContent = 'Comparing Spansh station markets and checking each trade leg...';
        results.innerHTML = '';
        try {
          const result = await Lab.api('/api/personal/routes', params);
          if (u.destroyed) return;
          const selected = form.elements.commodity.value;
          form.elements.commodity.innerHTML = '<option value="">All available goods</option>' + result.commodities.map(c => `<option value="${esc(c.key)}">${esc(c.name)}</option>`).join('');
          form.elements.commodity.value = selected;
          const s = result.settings;
          status.textContent = `${result.rows.length} routes | ${result.source} | ${s.origin}${s.destination ? ' to ' + s.destination : ''} | ${fmt(s.quantity)} t per leg | ${fmt(s.distance)} Ly limit | ${fmt(result.screened)} of ${fmt(result.available)} nearby stations checked | Searched ${new Date(result.queried_at).toLocaleString()}. ${result.note}`;
          u.result = result; u.all = false; u.expanded = result.rows[0]?.id || null;
          draw();
        } catch (error) {
          if (!u.destroyed) status.textContent = error.message;
        } finally { if (!u.destroyed) button.disabled = false; }
      };
      el.addEventListener('click', async event => {
        const select = event.target.closest('[data-select]'), details = event.target.closest('[data-details]'), show = event.target.closest('[data-personal-show]');
        const focus = event.target.closest('[data-plan-focus]'), map = event.target.closest('[data-plan-map]'), clear = event.target.closest('[data-plan-clear]');
        const powerplay = event.target.closest('[data-plan-powerplay]');
        if(powerplay) {
          const generation=u.handoffGeneration=(u.handoffGeneration||0)+1, token=powerplay.dataset.contextToken;
          status.textContent='Checking the active trade leg and pledge...';
          try {
            if(!Lab.cards.targets)throw Error('The Powerplay sell-target module is unavailable.');
            const context=await Lab.api('/api/personal/powerplay',{role:powerplay.dataset.planPowerplay,token});
            if(u.destroyed||generation!==u.handoffGeneration)return;
            if(!context.ready)throw Error(context.message);
            if(Lab.state.personal?.powerplay_handoff?.token!==context.token)throw Error('Route or pledge changed. Review the current route and retry.');
            Lab.set('personal',{ui_powerplay:{...context,request_id:Date.now()+':'+generation}});
            Lab.focusCard('targets');
            status.textContent='Planning origin and pledge sent to the Powerplay finder. Review its filters before searching.';
          } catch(error) {if(!u.destroyed&&generation===u.handoffGeneration)status.textContent=error.message;}
        }
        if (details) { u.expanded = u.expanded === details.dataset.details ? null : details.dataset.details; draw(); }
        if (show) { u.all = !u.all; draw(); }
        if (focus) Lab.focusCard(focus.dataset.planFocus);
        if (map) { Lab.set('personal', {ui_selected: !Lab.state.personal?.ui_selected}); if (Lab.state.personal.ui_selected) Lab.focusCard('map'); }
        if (select || clear) {
          const buttons = el.querySelectorAll('[data-select],[data-plan-clear]'); buttons.forEach(b => b.disabled = true);
          status.textContent = select ? 'Selecting route...' : 'Clearing route...';
          try {
            await (select ? Lab.post('/api/personal/plan', {id: select.dataset.select}) : Lab.post('/api/personal/plan/clear'));
            if (!u.destroyed) status.textContent = select ? 'Route selected. The next action follows your journal; the map shows both stops.' : 'Route cleared.';
          } catch (error) { if (!u.destroyed) status.textContent = error.message; }
          finally { if (!u.destroyed) { buttons.forEach(b => b.disabled = false); draw(); } }
        }
      });
    },
    render(el, S) {
      const u = el._personal, j = S.journal || {}, form = el.querySelector('form');
      form.elements.origin.placeholder = j.system || 'Enter starting system';
      form.elements.quantity.placeholder = j.cargo_capacity ? `${fmt(j.cargo_capacity)} t` : 'Enter load size';
      el.querySelector('[data-ship-context]').textContent = `${j.ship_name || j.ship || 'Current ship'} | ${j.system || 'Location unknown'} | ${j.cargo_capacity == null ? 'Capacity unknown' : fmt(j.cargo_capacity) + ' t capacity'} | ${j.jump_range_laden == null ? 'Laden range unknown; use light-years' : fmt(j.jump_range_laden) + ' Ly fully laden'}. Jump limits are straight-line estimates, not plotted navigation. Results retain their search settings and prices until searched again.`;
      const html = plan(S);
      if (html !== u.planHtml) { u.planHtml = html; el.querySelector('[data-personal-plan]').innerHTML = html; }
      const planId = S.personal?.plan?.id || null;
      if (u.result && u.planId !== planId) { u.planId = planId; u.draw(); }
    },
    unmount(el) { el._personal.destroyed = true; },
  });

  Lab.map.addLayer('personal', {
    label: 'trade route', color: '#e6b422', z: 2,
    points: S => {
      const P = S.personal || {}, p = P.plan, g = P.progress;
      if (!p || !g) return [];
      const next = g.next, seen = new Set();
      return p.legs.flatMap((l, i) => [['buy', l.buy], ['sell', l.sell]].map(([role, s]) => ({role, s, i}))).filter(({s}) => Array.isArray(s.pos) && s.pos.every(Number.isFinite) && !seen.has(s.market_id) && seen.add(s.market_id)).map(({role, s, i}) => {
        const isNext = next && next.market_id === s.market_id;
        return {name: s.system, x: s.pos[0], y: s.pos[1], z: s.pos[2], r: isNext ? 5 : 4, label: true, selected: !!(P.ui_selected && isNext),
          color: g.legs[i].done && !isNext ? '#8a7a3a' : role === 'buy' ? '#e6b422' : '#6fb3ff',
          sub: `${s.station} | ${role === 'buy' ? 'buy' : 'sell'} ${p.legs[i].commodity}${isNext ? ' | next stop' : ''}`,
          onClick: () => Lab.set('personal', {ui_selected: !(S.personal || {}).ui_selected})};
      });
    },
    lines: S => {
      const P = S.personal || {}, n = P.progress?.next, ship = Lab.shipPos(S);
      return P.ui_selected && n && Array.isArray(n.pos) && ship ? [{a: ship, b: {x: n.pos[0], z: n.pos[2]}, color: 'rgba(230,180,34,.8)', dash: [4, 4], label: n.dist == null ? '' : `${n.dist.toFixed(1)} Ly`}] : [];
    },
  });
})();
