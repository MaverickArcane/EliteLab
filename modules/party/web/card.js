(() => {
  const { esc, fmt } = Lab.util;
  let profits;
  import('/modules/trade/earnings.js').then(module=>{profits=module;Lab.emit('party');}).catch(error=>console.error('Individual profits',error));
  const when = s => s ? esc(new Date(s).toLocaleString()) : 'Unknown';
  const number = n => Number.isFinite(n) ? n.toLocaleString(undefined, {maximumFractionDigits:2}) : 'Unknown';
  const age = s => {
    const seconds = Math.max(0, Math.floor((Date.now() - Date.parse(s)) / 1000));
    return !Number.isFinite(seconds) ? 'unknown' : seconds < 60 ? `${seconds}s ago` : seconds < 3600 ? `${Math.floor(seconds/60)}m ago` : `${Math.floor(seconds/3600)}h ago`;
  };
  const flight = (t, m) => t.game_running === false ? 'Game closed' : t.vehicle === 'foot' ? 'On foot' : t.vehicle === 'taxi' ? 'In taxi' : t.vehicle === 'crew' ? 'Multicrew' : t.vehicle === 'srv' ? 'In SRV' : t.vehicle === 'fighter' ? 'In fighter' : t.fsd_jump ? 'Hyperspace' : t.fsd_charging ? 'FSD charging' : t.supercruise ? 'Supercruise' : (t.docked ?? m.docked) ? 'Docked' : t.landed ? 'Landed' : t.status_at ? 'Normal space' : 'Flight status unknown';
  const meter = (value, capacity, label) => Number.isFinite(value) && Number.isFinite(capacity) && capacity > 0 ? `<progress max="${capacity}" value="${Math.min(value, capacity)}" aria-label="${label}"></progress>` : '';
  const copyButton = (value, label) => value ? `<button class="mini" data-copy="${esc(value)}">${label}</button>` : '';
  function routeStop(label, station, system, carrier=false) {
    const url=Lab.util.inaraMarket(station,carrier ? null : system);
    return `<div class="party-route-stop"><b>${label}</b><div>${esc(station || 'Unknown stop')}${system ? ' / '+esc(system) : ''}</div><div class="row">${copyButton(system,'Copy system')}${copyButton(station,'Copy station')}${url ? `<a class="mini" data-party-inara href="${esc(url)}" target="_blank" rel="noopener noreferrer">Inara market</a>` : ''}</div></div>`;
  }
  function planStop(label, value) {
    const split=(value || '').lastIndexOf(' / ');
    return routeStop(label,split<0 ? value : value.slice(0,split),split<0 ? null : value.slice(split+3));
  }
  function crewReadings(m) {
    const t=m.telemetry || {};
    const fuel=Number.isFinite(t.fuel) ? (Number.isFinite(t.fuel_capacity) && t.fuel_capacity>0 ? Math.round(t.fuel/t.fuel_capacity*100)+'%' : number(t.fuel)+' t') : '?';
    const shield=t.shields_up==null ? '?' : t.shields_up ? 'up' : 'down';
    const alerts=m.connected ? [['low_fuel','Low fuel'],['overheating','Overheating'],['interdicted','Interdicted'],['in_danger','In danger']].filter(([k])=>t[k]).map(([,v])=>v) : [];
    return `<div class="crew-ship-line">${esc(m.ship || 'Ship unknown')} | ${esc(flight(t,m))}</div><div class="crew-readings ${m.connected ? '' : 'muted'}" title="${m.connected ? 'Last observed game readings' : 'Stale readings'}: ${when(t.status_at)}"><span>Cargo ${number(m.cargo_count)} / ${number(m.capacity)} t</span><span>Fuel ${esc(fuel)}</span><span>Shields ${shield}</span></div>${alerts.length ? `<div class="crew-inline-alerts">${alerts.map(a=>`<span class="tag warn">${a}</span>`).join('')}</div>` : ''}`;
  }
  function assignedProgress(m, phase) {
    const a=m.assignment;
    return `<div>${fmt(m[phase])}${a ? ' / '+fmt(a[phase+'_target']) : ''} t</div>${a ? `<div class="note">${a[phase+'_runs_left']==null ? 'Loads unknown' : fmt(a[phase+'_runs_left'])+(a[phase+'_runs_left']===1 ? ' load left' : ' loads left')}</div>${a.pickup_phase===phase ? `<div class="note" data-crew-next-pickup>Next pickup: ${fmt(a.next_pickup)} t</div>` : ''}` : ''}`;
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
      el.innerHTML = `<div class="row"><div data-party-status></div><button class="mini" data-party-leave hidden>Leave party</button></div><div data-party-controls>
        <div class="note">Connect your EliteLab clients over LAN or Tailscale. Share location, ship, cargo, shields, fuel and flight status every second while joined.</div>
        <form data-party-host class="trade-form"><label>Listen address<input name="bind" value="0.0.0.0" placeholder="Your Tailscale IPv4" required></label><label>Party port<input name="port" type="number" min="1024" max="65535" value="8767" required></label><button class="primary trade-wide" type="submit">Create party as leader</button></form>
        <div class="note">Use your Tailscale IPv4 to listen only on the tailnet. 0.0.0.0 listens on all local network interfaces. Friends use their own EliteLab to join.</div>
        <details class="trade-details"><summary>Join a leader</summary><form data-party-join class="trade-form">
          <label class="trade-wide">Leader party URL<input name="url" type="text" inputmode="url" spellcheck="false" autocapitalize="off" placeholder="100.x.x.x:8767" required></label>
          <label class="trade-wide">Party code<input name="code" type="password" autocomplete="off" required></label><button type="submit" class="primary trade-wide">Join &amp; share my status</button>
        <div data-party-join-error class="note warn trade-wide" role="status"></div></form></details></div>
        <div data-party-connected hidden><details class="trade-filters"><summary>Connection &amp; invitation</summary><div data-party-invite></div></details></div>
        <div data-crew-summary></div>
        <div data-party-stops></div>
        <div data-crew-roster></div>
        <details class="trade-details" data-telemetry><summary>Ship status and telemetry</summary><div data-party-members></div></details>`;
      for (const action of ['host', 'join']) {
        const form = el.querySelector(`[data-party-${action}]`);
        form.onsubmit = async e => {
          e.preventDefault(); const button = form.querySelector('button'); button.disabled = true;
          const body = Object.fromEntries(new FormData(form)); if (action === 'host') body.port = Number(body.port);
          if (action === 'join') {
            body.url = body.url.trim(); body.code = body.code.trim();
            if (body.url && !body.url.includes('://')) body.url = 'http://' + body.url;
            form.elements.url.value = body.url; form.elements.code.value = body.code;
            el.querySelector('[data-party-join-error]').textContent = '';
          }
          try { await Lab.post('/api/party/' + action, body); if (action === 'join') form.elements.code.value = ''; }
          catch (error) { if (action === 'join') el.querySelector('[data-party-join-error]').textContent = error.message; Lab.toast(error.message, 'bad'); }
          finally { button.disabled = false; }
        };
      }
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
      el.querySelector('[data-party-leave]').hidden = !active;
      el.querySelector('[data-party-status]').innerHTML = `<div class="row"><span class="tag ${active && !p.stale ? 'ok' : ''}">${p.mode === 'leader' ? 'Leading' : p.mode === 'member' ? 'Reporting' : 'Solo'}</span>${active ? `<span>${(p.members || []).filter(m => !m.stale).length} connected</span>` : '<span class="muted">No cargo shared</span>'}</div>${p.error ? `<div class="note warn" role="status">${esc(p.error)}</div>` : ''}`;
      el.querySelector('[data-party-invite]').innerHTML = p.mode === 'leader' ? `<div class="note">Friends join <b>http://YOUR-TAILSCALE-IP:${fmt(p.port).replaceAll(',', '')}</b> with this code:</div><div class="party-code"><code>${esc(p.code)}</code><button class="mini" data-copy="${esc(p.code)}">Copy code</button></div><div class="note">Party port ${esc(p.port)}. Closing the party invalidates the code. Only the trade plan and member reports are shared.</div>` : `<div class="note">Connected to ${esc(p.url)}. Leave to stop sharing.</div>`;
      const d = p.desk, op = p.operation;
      const running=d && ['loading','transit','unloading'].includes(d.phase);
      const lifecycle=JSON.stringify([p.mode,p.stale,p.closing,op?.id,d?.phase,d?.commodity,p.plan?.source,p.plan?.destination]);
      const changed=el._partyLifecycle!==lifecycle;el._partyLifecycle=lifecycle;
      const update = (selector, html) => {
        const node = el.querySelector(selector), selection = window.getSelection();
        // Preserve selected destination names until the user has copied them.
        if (!changed && selection && !selection.isCollapsed && node.contains(selection.anchorNode)) return;
        if (node._html !== html) {node.innerHTML = html; node._html = html;}
      };
      const tons = n => n == null ? 'Unknown' : fmt(n)+' t';
      const carrier=p.carrier || {};
      update('[data-party-stops]',active && p.plan ? `<div class="party-route">${planStop('Buy',p.plan.source)}${routeStop('Carrier',carrier.callsign || carrier.name,carrier.system,true)}${planStop('Sell',p.plan.destination)}</div>` : '');
      // Leader-supplied numbers are coerced before they reach attributes; anything else counts as unknown.
      const num = v => v == null || v === '' || !Number.isFinite(Number(v)) ? null : Number(v);
      const progress = (label, rawValue, rawTarget) => {const value = num(rawValue) ?? 0, target = num(rawTarget); return `<div class="crew-progress-leg"><div class="row"><b>${label}</b><span>${tons(value)} / ${tons(target)}</span></div><progress max="${target || 1}" value="${Math.min(value, target || 1)}" aria-label="Crew ${label.toLowerCase()}"></progress><div class="note">${target == null ? 'Target unknown' : tons(Math.max(0,target-value))+' remaining'}</div></div>`;};
      update('[data-crew-summary]', active && running ? `<div class="crew-job"><div class="row"><h3>${esc(d.commodity)}</h3><span class="tag ${d.stale ? 'warn' : 'ok'}">${esc(d.paused ? 'Paused' : d.phase)}</span></div><div class="note">${esc(p.plan.source)} &gt; ${esc(p.plan.destination)}</div><div class="crew-progress">${progress('Loading',d.loaded,d.target)}${progress('Unloading',d.unloaded,d.target)}</div>${d.over_target ? '<div class="warn">Reports exceed the job target. Check deliveries before advancing.</div>' : ''}${d.stale ? '<div class="warn">Leader unavailable. Showing last acknowledged progress.</div>' : ''}<div class="note">Acknowledged deliveries. Cargo aboard ships is counted separately.</div></div>` : active && d?.phase==='ready' ? `<p class="note"><b>Route prepared - not started.</b> ${esc(d.commodity)}: ${esc(p.plan.source)} &gt; ${esc(p.plan.destination)}. Wait for the owner to start loading.</p>` : active && ['cancelled','complete'].includes(d?.phase) ? `<p class="note"><b>${d.phase==='cancelled' ? 'Trade cancelled' : 'Trade complete'}.</b> No active haul. Previous totals remain in Carrier job.</p>` : active ? '<p class="muted">Waiting for the owner to choose a route in Carrier job.</p>' : '');
      update('[data-crew-roster]', active && running ? `<div class="ship-sec">Crew contributions</div><div class="table-scroll"><table class="crew-roster"><thead><tr><th>Commander</th><th class="num">Loaded</th><th class="num">Unloaded</th><th class="num">Individual profit*</th></tr></thead><tbody>${d.crew.map(m=>`<tr class="${m.you ? 'crew-you' : ''}"><td><b>${esc(m.cmdr)}</b>${m.you ? ' <span class="tag">You</span>' : ''}${m.owner ? ' <span class="tag">Owner</span>' : ''}<div class="note ${m.connected ? '' : 'warn'}">${esc(m.connected ? m.activity : 'Disconnected / stale')}${m.system ? ' | '+esc(m.system) : ''}</div>${crewReadings(m)}</td><td class="num">${assignedProgress(m,'loading')}</td><td class="num">${assignedProgress(m,'unloading')}</td><td class="num">${profits ? profits.profitSummary(p.plan,m,m.assignment,d.phase,m.owner,p.workload?.economics?.owner_profit ?? p.plan?.crew_split?.owner_profit) : m.owner ? 'Carrier owner' : m.earnings == null ? 'Unknown' : fmt(m.earnings)+' Cr'}</td></tr>`).join('')}</tbody></table></div><div class="note">*At agreed prices on recorded deliveries, before expenses. Contributions stay visible after a player leaves.</div>` : '');
      el.querySelector('[data-telemetry]').hidden = !active;
      update('[data-party-members]', active ? `<div class="note">Connection reports every second; game readings update when the journal changes.</div>${(p.members || []).map(memberPanel).join('')}` : '');
    },
  });
})();
