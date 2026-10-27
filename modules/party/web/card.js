(() => {
  const { esc, fmt } = Lab.util;
  const when = s => s ? esc(new Date(s).toLocaleString()) : 'Unknown';
  Lab.card({
    id: 'party', requires: ['party', 'journal'],
    mount(el) {
      el.innerHTML = `<div data-party-status></div><div data-party-controls>
        <div class="note">Connect your EliteLab clients over LAN or Tailscale. Share commander name, location, ship and cargo every three seconds while joined.</div>
        <form data-party-host class="trade-form"><label>Listen address<input name="bind" value="0.0.0.0" placeholder="Your Tailscale IPv4" required></label><label>Party port<input name="port" type="number" min="1024" max="65535" value="8767" required></label><button class="primary trade-wide" type="submit">Create party as leader</button></form>
        <div class="note">Use your Tailscale IPv4 to listen only on the tailnet. 0.0.0.0 listens on all local network interfaces. Friends use their own EliteLab to join.</div>
        <details class="trade-details"><summary>Join a leader</summary><form data-party-join class="trade-form">
          <label class="trade-wide">Leader party URL<input name="url" type="url" placeholder="http://100.x.x.x:8767" required></label>
          <label class="trade-wide">Party code<input name="code" type="password" autocomplete="off" required></label><button type="submit" class="primary trade-wide">Join &amp; share my cargo</button>
        </form></details></div>
        <div data-party-connected hidden><details class="trade-filters"><summary>Connection &amp; invitation</summary><div data-party-invite></div></details><button class="mini" data-party-leave>Close party</button></div>
        <div data-party-plan></div>
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
      const instructions = !working ? 'Waiting for the owner to start a trade.' : op.paused ? 'Paused. No new runs; completed deliveries can still be reported.' : loading ? `Buy at ${plan.source}. Deliver to ${carrierName}; carrier pays ${price == null ? 'an unconfirmed price' : fmt(price)+' Cr/t'}.` : unloading ? `Buy from ${carrierName} for ${price == null ? 'an unconfirmed price' : fmt(price)+' Cr/t'}. Sell at ${plan.destination}.` : `Carrier in transit. Wait for unloading to open at ${plan.destination}.`;
      el.querySelector('[data-party-plan]').innerHTML = active ? `<div class="trade-stop"><div class="k">Current crew task</div><b>${esc(working ? (op.paused ? 'Paused' : loading ? 'Load' : unloading ? 'Unload' : 'Wait')+' '+plan.commodity : op?.stage === 'complete' ? 'Trade complete' : 'No active trade')}</b><p>${esc(instructions)}</p>${op?.notes ? `<div><b>Owner:</b> ${esc(op.notes)}</div>` : ''}${p.stale ? '<div class="warn">Leader connection is stale. Confirm instructions before another run.</div>' : ''}</div>` : '';
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
      el.querySelector('[data-party-members]').innerHTML = active ? `${plan ? `<div class="ship-sec">${fmt(matching)} t ${esc(plan.commodity)} reported aboard connected ships</div><div class="note">Ship cargo is not confirmed delivery and is never added to carrier stock automatically.</div>` : ''}${members.map(m => `<div class="party-member"><div class="row"><b>${esc(m.cmdr || 'Unknown commander')}</b><span class="tag ${m.stale ? 'warn' : 'ok'}">${m.stale ? 'Stale' : m.leader ? 'Leader' : esc(m.activity || 'ready')}</span></div><div>${esc(m.system || 'Unknown system')}${m.station ? ' / ' + esc(m.station) : ''}</div><div class="note">${esc(m.ship || 'Unknown ship')} | ${fmt(m.cargo_count)} / ${fmt(m.capacity)} t | ${m.docked ? 'Docked' : 'In flight'}</div><div>${(m.cargo || []).filter(i => i.count).map(i => `${fmt(i.count)} t ${esc(i.name || i.key)}`).join(', ') || 'No cargo reported'}</div><div class="note">Cargo observed ${when(m.cargo_at)} | Report received ${when(m.last_seen)}</div></div>`).join('')}` : '';
    },
  });
})();
