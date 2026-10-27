(() => {
  const { esc, fmt } = Lab.util;
  const when = s => s ? esc(new Date(s).toLocaleString()) : 'Unknown';
  const number = n => Number.isFinite(n) ? n.toLocaleString(undefined, {maximumFractionDigits:2}) : 'Unknown';
  const age = s => {
    const seconds = Math.max(0, Math.floor((Date.now() - Date.parse(s)) / 1000));
    return !Number.isFinite(seconds) ? 'unknown' : seconds < 60 ? `${seconds}s ago` : seconds < 3600 ? `${Math.floor(seconds/60)}m ago` : `${Math.floor(seconds/3600)}h ago`;
  };
  const flight = (t, m) => t.game_running === false ? 'Game closed' : t.vehicle === 'foot' ? 'On foot' : t.vehicle === 'taxi' ? 'In taxi' : t.vehicle === 'crew' ? 'Multicrew' : t.vehicle === 'srv' ? 'In SRV' : t.vehicle === 'fighter' ? 'In fighter' : t.fsd_jump ? 'Hyperspace' : t.fsd_charging ? 'FSD charging' : t.supercruise ? 'Supercruise' : (t.docked ?? m.docked) ? 'Docked' : t.landed ? 'Landed' : t.status_at ? 'Normal space' : 'Flight status unknown';
  const meter = (value, capacity, label) => Number.isFinite(value) && Number.isFinite(capacity) && capacity > 0 ? `<progress max="${capacity}" value="${Math.min(value, capacity)}" aria-label="${label}"></progress>` : '';
  const copyButton = (value, label) => value ? `<button class="mini" data-copy="${esc(value)}">${label}</button>` : '';
  function routeStop(label, value) {
    if (!value) return '';
    const split=value.lastIndexOf(' / '), station=split<0 ? value : value.slice(0,split), system=split<0 ? '' : value.slice(split+3);
    return `<div class="party-route-stop"><b>${label}</b><div>${esc(station)}${system ? ' / '+esc(system) : ''}</div><div class="row">${copyButton(system,'Copy system')}${copyButton(station,system ? 'Copy station' : 'Copy stop')}</div></div>`;
  }
  function loadSuggestion(s, localId) {
    if (!s) return '';
    const rows=s.members || [], own=rows.find(r=>r.id===localId);
    return `<div class="trade-stop"><b>Suggested crew loads</b>${!s.round_capacity ? '<div class="note">Waiting for participating ships to report usable cargo space.</div>' : `<div>${fmt(s.round_capacity)} t per full crew round</div><div class="note">${s.phase==='ready' ? `Suggested total: ${fmt(s.suggested_quantity)} t. ` : ''}${fmt(s.remaining)} t remaining fits ${fmt(s.full_rounds)} full rounds${s.tail ? ' + '+fmt(s.tail)+' t in a final partial round' : ''}.</div><div class="note">${fmt(s.aboard)} t already aboard participating ships; ${fmt(s.next_buy)} t suggested to pick up next.</div>${own ? `<div class="party-next-load"><b>Your next ${own.leader && s.phase==='unloading' ? 'transfer' : 'purchase'}: ${fmt(own.next_buy)} t</b> ${copyButton(String(own.next_buy),'Copy amount')}</div>` : ''}<div class="table-scroll"><table><thead><tr><th>Commander</th><th>Aboard</th><th>Next pickup</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.cmdr || 'Unknown')}${r.id===localId ? ' (you)' : ''}</td><td>${fmt(r.aboard)} t</td><td>${fmt(r.next_buy)} t</td></tr>`).join('')}</tbody></table></div>`}${!s.enabled ? '<div class="note warn">No pickups requested in the current phase.</div>' : s.phase==='ready' ? '<div class="note">Planning only. Wait for Start loading before hauling.</div>' : ''}${s.excluded?.length ? `<div class="note">Excluded: ${s.excluded.map(m=>esc(m.cmdr || 'Unknown')+' ('+esc(m.reason)+')').join(', ')}</div>` : ''}<div class="note">Advisory, not reserved. Updates with ship capacity, cargo and crew status. Check before buying; the saved trade quantity stays unchanged.</div></div>`;
  }
  function memberPanel(m) {
    const t=m.telemetry || {}, ship=t.vehicle === 'ship', old=m.stale || t.game_running === false;
    const alerts=[['low_fuel','Low fuel'],['overheating','Overheating'],['interdicted','Being interdicted'],['in_danger','In danger'],['silent_running','Silent running'],['hardpoints','Hardpoints deployed'],['scooping','Fuel scooping']].filter(([k])=>t[k]);
    const shields=t.vehicle === 'foot' ? 'Not in ship' : t.shields_up == null ? 'Unknown' : t.shields_up ? 'Up' : 'Down';
    return `<article class="party-member ${old ? 'party-old' : ''}">
      <div class="row"><b>${esc(m.cmdr || 'Unknown commander')}</b><span class="tag ${m.stale ? 'warn' : 'ok'}">${m.stale ? 'Connection stale' : 'Connected'}</span>${m.leader ? '<span class="tag">Leader</span>' : ''}<span class="muted">${esc(m.activity || 'ready')}</span></div>
      <div class="party-location"><b>${esc(m.system || 'Unknown system')}</b>${m.station ? ' / '+esc(m.station) : ''}${t.body && t.body !== m.station ? `<div class="note">Near ${esc(t.body)}</div>` : ''}</div>
      <div class="row"><span class="tag">${flight(t,m)}</span><span>${esc(m.ship || 'Unknown ship')}</span></div>
      ${m.ship_name || m.ship_ident ? `<div class="note">${esc([m.ship_name,m.ship_ident].filter(Boolean).join(' / '))}</div>` : ''}
      ${t.destination ? `<div class="note">Target: ${esc(t.destination)}</div>` : ''}
      ${old ? '<div class="note warn">Last reported values</div>' : ''}
      <div class="party-telemetry">
        <div><span class="k">Shields</span><b class="${t.shields_up === false && t.vehicle !== 'foot' ? 'warn' : ''}">${shields}</b><small>Up/down only</small></div>
        <div><span class="k">Fuel</span><b class="${t.low_fuel ? 'warn' : ''}">${number(t.fuel)}${Number.isFinite(t.fuel) ? (Number.isFinite(t.fuel_capacity) ? ' / '+number(t.fuel_capacity) : '')+' t' : ''}</b>${meter(t.fuel,t.fuel_capacity,'Fuel remaining')}<small>${Number.isFinite(t.fuel_reservoir) ? number(t.fuel_reservoir)+' t reservoir' : 'Reservoir unknown'}</small></div>
        <div><span class="k">Cargo</span><b>${number(m.cargo_count)} / ${number(m.capacity)} t</b>${meter(m.cargo_count,m.capacity,'Cargo capacity used')}</div>
        <div title="Hull observed ${when(t.hull_at)}"><span class="k">Ship hull</span><b>${ship && Number.isFinite(t.hull_health) ? number(t.hull_health*100)+'%' : 'Unknown'}</b><small>Last reported${ship && t.hull_at ? ' '+age(t.hull_at) : ''}</small></div>
      </div>
      ${alerts.length ? `<div class="party-alerts">${alerts.map(([,label])=>`<span class="tag warn">${label}</span>`).join('')}</div>` : ''}
      <div class="note">${(m.cargo || []).filter(i=>i.count).map(i=>`${fmt(i.count)} t ${esc(i.name || i.key)}`).join(', ') || 'No cargo reported'}${t.legal ? ' | '+esc(t.legal) : ''}</div>
      <div class="party-freshness">Report ${age(m.last_seen)} | Status change ${age(t.status_at)}${t.fuel_at && t.fuel_at !== t.status_at ? ' | Fuel reading '+age(t.fuel_at) : ''}<br>Cargo observed ${when(m.cargo_at)}</div>
    </article>`;
  }
  Lab.card({
    id: 'party', requires: ['party', 'journal'],
    mount(el) {
      el.innerHTML = `<div data-party-status></div><div data-party-controls>
        <div class="note">Connect your EliteLab clients over LAN or Tailscale. Share location, ship, cargo, shields, fuel and flight status every second while joined.</div>
        <form data-party-host class="trade-form"><label>Listen address<input name="bind" value="0.0.0.0" placeholder="Your Tailscale IPv4" required></label><label>Party port<input name="port" type="number" min="1024" max="65535" value="8767" required></label><button class="primary trade-wide" type="submit">Create party as leader</button></form>
        <div class="note">Use your Tailscale IPv4 to listen only on the tailnet. 0.0.0.0 listens on all local network interfaces. Friends use their own EliteLab to join.</div>
        <details class="trade-details"><summary>Join a leader</summary><form data-party-join class="trade-form">
          <label class="trade-wide">Leader party URL<input name="url" type="url" placeholder="http://100.x.x.x:8767" required></label>
          <label class="trade-wide">Party code<input name="code" type="password" autocomplete="off" required></label><button type="submit" class="primary trade-wide">Join &amp; share my status</button>
        </form></details></div>
        <div data-party-connected hidden><details class="trade-filters"><summary>Connection &amp; invitation</summary><div data-party-invite></div></details><button class="mini" data-party-leave>Close party</button></div>
        <div data-party-plan></div>
        <div data-party-stops></div><div data-load-suggestion></div>
        <div data-crew-work hidden><div class="row"><label>My status <select data-activity><option value="ready">Ready</option><option value="hauling">Hauling</option><option value="away">Away</option></select></label></div>
        <div data-auto-tracking class="note"></div><details class="trade-filters"><summary>Manual delivery fallback</summary><div class="note">Only use if a delivery was missed. Reporting a journal-recorded load here would count it twice.</div><form data-delivery class="row"><label>Delivered tonnes<input name="tonnes" type="number" min="1" max="1000000" required placeholder="Actual delivered amount"></label><button class="mini primary" type="submit">Report delivery</button></form></details><div data-delivery-status class="note" role="status"></div><div data-my-deliveries class="note"></div></div>
        <div data-party-members></div>`;
      for (const action of ['host', 'join']) {
        const form = el.querySelector(`[data-party-${action}]`);
        form.onsubmit = async e => {
          e.preventDefault(); const button = form.querySelector('button'); button.disabled = true;
          const body = Object.fromEntries(new FormData(form)); if (action === 'host') body.port = Number(body.port);
          try { await Lab.post('/api/party/' + action, body); if (action === 'join') form.elements.code.value = ''; }
          catch (error) { Lab.toast(error.message, 'bad'); }
          finally { button.disabled = false; }
        };
      }
      el.querySelector('[data-activity]').onchange = async e => { try {await Lab.post('/api/party/work', {activity:e.target.value});} catch(error){Lab.toast(error.message,'bad');} };
      el.querySelector('[data-delivery]').onsubmit = async e => {
        e.preventDefault(); const form=e.target, button=form.querySelector('button'); button.disabled=true;
        try { const state=await Lab.post('/api/party/work', {id:Lab.state.party.operation?.id, tonnes:Number(form.elements.tonnes.value)});
          form.reset(); el.querySelector('[data-delivery-status]').textContent=state.error || 'Delivery recorded. Do not report the same load again.';
        } catch(error){el.querySelector('[data-delivery-status]').textContent=error.message;}
        finally{button.disabled=false;}
      };
      el.querySelector('[data-party-leave]').onclick = async e => {
        const button = e.currentTarget; button.disabled = true;
        try { await Lab.post('/api/party/leave'); } catch (error) { Lab.toast(error.message, 'bad'); }
        finally { button.disabled = false; }
      };
    },
    render(el, S) {
      const p = S.party || {}, active = p.mode && p.mode !== 'idle';
      el.querySelector('[data-party-controls]').hidden = active;
      el.querySelector('[data-party-connected]').hidden = !active;
      el.querySelector('[data-party-leave]').textContent = p.mode === 'leader' ? 'Close party' : 'Leave party';
      el.querySelector('[data-party-status]').innerHTML = `<div class="row"><span class="tag ${active && !p.stale ? 'ok' : ''}">${p.mode === 'leader' ? 'Leading' : p.mode === 'member' ? 'Reporting' : 'Solo'}</span>${active ? `<span>${(p.members || []).filter(m => !m.stale).length} connected</span>` : '<span class="muted">No cargo shared</span>'}</div>${p.error ? `<div class="note warn" role="status">${esc(p.error)}</div>` : ''}`;
      el.querySelector('[data-party-invite]').innerHTML = p.mode === 'leader' ? `<div class="note">Friends join <b>http://YOUR-TAILSCALE-IP:${fmt(p.port).replaceAll(',', '')}</b> with this code:</div><div class="party-code"><code>${esc(p.code)}</code><button class="mini" data-copy="${esc(p.code)}">Copy code</button></div><div class="note">Party port ${esc(p.port)}. Closing the party invalidates the code. Only the trade plan and member reports are shared.</div>` : `<div class="note">Connected to ${esc(p.url)}. Leave to stop sharing.</div>`;
      const plan = p.plan, op = p.operation, working = op && ['loading','transit','unloading'].includes(op.stage);
      const carrier = p.carrier || {}, carrierName = [carrier.name || 'Carrier',carrier.callsign].filter(Boolean).join(' / ');
      const loading = op?.stage === 'loading', unloading = op?.stage === 'unloading';
      const price = plan?.crew_split?.[loading ? 'carrier_buy_price' : 'carrier_sell_price'] ?? (plan?.carrier_price_known ? plan.carrier_price : null);
      const owner=p.mode==='leader';
      const instructions = !working ? (plan ? 'Route prepared. The owner starts loading in Manage trade when the carrier order is ready.' : 'Waiting for the owner to prepare a trade.') : op.paused ? 'Paused. No new runs; completed deliveries can still be reported.' : loading ? (owner ? `Buy at ${plan.source}, then transfer cargo directly into ${carrierName}. Your journal records the delivery; no sale to your own carrier is needed.` : `Buy at ${plan.source}. Deliver to ${carrierName}; carrier pays ${price == null ? 'an unconfirmed price' : fmt(price)+' Cr/t'}.`) : unloading ? (owner ? `Transfer cargo from ${carrierName} into your ship, then sell at ${plan.destination}. The destination sale records delivery.` : `Buy from ${carrierName} for ${price == null ? 'an unconfirmed price' : fmt(price)+' Cr/t'}. Sell at ${plan.destination}.`) : `Carrier in transit. Wait for unloading to open at ${plan.destination}.`;
      el.querySelector('[data-party-plan]').innerHTML = active ? `<div class="trade-stop"><div class="k">Current crew task</div><b>${esc(working ? (op.paused ? 'Paused' : loading ? 'Load' : unloading ? 'Unload' : 'Wait')+' '+plan.commodity : op?.stage === 'complete' ? 'Trade complete' : op?.stage === 'cancelled' ? 'Trade cancelled' : plan ? 'Prepared - waiting to start' : 'No trade selected')}</b><p>${esc(instructions)}</p>${op?.notes ? `<div><b>Owner:</b> ${esc(op.notes)}</div>` : ''}${p.stale ? '<div class="warn">Leader connection is stale. Confirm instructions before another run.</div>' : ''}</div>` : '';
      el.querySelector('[data-party-stops]').innerHTML=active && plan ? `<div class="party-route">${routeStop('Buy',plan.source)}<div class="party-route-stop"><b>Carrier</b><div>${esc(carrierName)}${carrier.system ? ' / '+esc(carrier.system) : ''}</div><div class="row">${copyButton(carrier.system,'Copy system')}${copyButton(carrier.callsign,'Copy callsign')}</div></div>${routeStop('Sell',plan.destination)}</div>` : '';
      el.querySelector('[data-load-suggestion]').innerHTML=active && !p.stale ? loadSuggestion(p.load_suggestion,p.local_id) : '';
      el.querySelector('[data-crew-work]').hidden = !active;
      el.querySelector('[data-activity]').value = p.activity || 'ready';
      const canDeliver = active && working && !p.stale && (loading || unloading);
      const delivery = el.querySelector('[data-delivery]');
      delivery.elements.tonnes.disabled = !canDeliver; delivery.querySelector('button').disabled = !canDeliver;
      const trackedPhase = unloading ? 'unloading' : 'loading';
      const tracking = p.auto_tracking?.[trackedPhase];
      const lastAuto = p.last_auto_delivery?.operation_id === op?.id ? p.last_auto_delivery : null;
      el.querySelector('[data-auto-tracking]').textContent = working ? (tracking ? 'Delivery tracking: automatic from your journal. ' : 'This plan has no verified market ID for this leg. Use manual fallback. ') + (lastAuto ? `Last recorded: ${fmt(lastAuto.tonnes)} t ${lastAuto.phase}.` : '') : 'Deliveries will track automatically while you are joined to an active trade.';
      const own = p.work?.operation_id === op?.id ? p.work : null;
      const accepted = op?.reports?.[p.local_id] || {};
      const pending = own && (own.loading > (accepted.loading || 0) || own.unloading > (accepted.unloading || 0));
      el.querySelector('[data-my-deliveries]').textContent = own ? `Recorded ${fmt(own.loading)} t loaded / ${fmt(own.unloading)} t unloaded.${pending ? ' Waiting for leader acknowledgement; do not submit again.' : ''}` : 'Matching journal sales update progress automatically. Cargo aboard your ship is not a delivery.';
      const members = p.members || [];
      const matching = members.filter(m => !m.stale).reduce((sum, m) => sum + (m.cargo || []).filter(i => i.key === plan?.commodity).reduce((s, i) => s + (i.count || 0), 0), 0);
      el.querySelector('[data-party-members]').innerHTML = active ? `<div class="note">Reports every second. Status changes when the game writes it; connection activity alone does not confirm fresh game data.</div>${plan ? `<div class="ship-sec">${fmt(matching)} t ${esc(plan.commodity)} reported aboard connected ships</div><div class="note">Ship cargo is not confirmed delivery and is never added to carrier stock automatically.</div>` : ''}${members.map(memberPanel).join('')}` : '';
    },
  });
})();
