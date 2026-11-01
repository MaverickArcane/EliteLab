(() => {
  const {esc, bar} = Lab.util;
  const val = x => x == null ? '?' : esc(x);
  function display(el, d) {
    if (!d) return;
    el._neutron = d;
    if (!el._rangeEdited) el.querySelector('[name=range_ly]').value = d.ship?.suggested_range_ly ?? '';
    const r = d.route, s = d.ship || {}, p = d.palin || {};
    const fitted = x => x === true ? 'fitted' : x === false ? 'missing' : 'unverified';
    el.querySelector('[data-neutron-status]').innerHTML =
      `<div class="note">From ${esc(d.location?.system || 'unknown')} / ${val(s.suggested_range_ly)} Ly loaded / auto ${val(s.suggested_supercharge_multiplier)}x neutron boost.</div>
       <div>Fuel scoop ${fitted(s.fuel_scoop_fitted)} / AFMU ${fitted(s.afmu_fitted)} / FSD health at last loadout: ${s.fsd_health_at_loadout == null ? '?' : val(Math.round(s.fsd_health_at_loadout * 100)) + '%'}</div>
       ${(s.notices || []).map(x => `<div class="bad">${esc(x)}</div>`).join('')}
       ${p.greatest_distance_from_start_ly != null ? bar('Palin distance', Math.min(100,p.greatest_distance_from_start_ly / 50), `${Math.round(p.greatest_distance_from_start_ly).toLocaleString()} / 5,000 Ly`, 'var(--accent-2)') : ''}
       <div class="note">${p.distance_requirement_met_when_observed ? 'Distance milestone recorded.' : 'Distance milestone not yet recorded.'}
       ${p.destination_distance_from_career_start_ly == null ? 'Career starting system unverified.' : `Destination: ${val(p.destination_distance_from_career_start_ly)} Ly from career start.`}</div>
       ${d.boost_observation ? `<div>Boost evidence: ${esc(d.boost_observation.status.replaceAll('_',' '))}. Injections and neutron boosts do not stack.</div>` : ''}
       ${r ? `<div style="margin-top:10px"><strong>${esc(r.request.from)} to ${esc(r.request.to)}</strong> / ${esc(r.status)}
         <a href="${esc(r.spansh_url)}" target="_blank" rel="noopener">Open Spansh</a> <button data-neutron-clear>Clear</button>
         ${['queued','running'].includes(r.status) ? '<button data-neutron-refresh>Check result</button>' : ''}
         ${r.status === 'ready' ? '<button data-neutron-export>Download CSV</button>' : ''}</div>
         ${r.error || r.last_poll_error ? `<div class="bad">${esc(r.error || r.last_poll_error)}</div>` : ''}
         ${d.waypoint_count > 1 ? bar('Waypoints reached', Math.max(0, (d.waypoint_count - d.remaining_waypoints - 1) / (d.waypoint_count - 1) * 100), `${Math.max(0,d.waypoint_count - d.remaining_waypoints - 1)} / ${d.waypoint_count - 1}`) : ''}
         <div>${esc(d.navigation_status.replaceAll('_',' '))} / ${val(d.remaining_waypoints)} waypoints remaining${r.estimated_total_jumps != null ? ` / about ${val(r.estimated_total_jumps)} jumps total` : ''}</div>
         ${d.ship_changed || d.fit_changed ? '<div class="bad">Ship or fit changed: verify normal range and plan again.</div>' : ''}
         ${d.next_waypoint ? `<div>Next waypoint: <button data-copy="${esc(d.next_waypoint.system)}">${esc(d.next_waypoint.system)}</button></div>` : ''}
         <div class="expedition-waypoints">${(d.waypoints || []).map(w => `<div><span class="tag ${w.neutron_star ? 'ok' : ''}">${w.neutron_star ? 'NEUTRON' : 'WAYPOINT'}</span> <strong>${esc(w.system)}</strong><div class="muted">${val(Math.round(w.distance_from_previous_ly*10)/10)} Ly leg / about ${val(w.estimated_jumps_from_previous)} jumps</div></div>`).join('')}</div>` : ''}
       <details><summary>Route notes</summary>${(d.notes || []).map(x => `<p>${esc(x)}</p>`).join('')}</details>`;
  }
  const mapPoints = S => (S.neutron?.summary?.waypoints || []).filter(w => w.coordinates?.length === 3).map(w => ({
    name:w.system, x:w.coordinates[0], y:w.coordinates[1], z:w.coordinates[2], r:4,
    color:w.neutron_star ? '#68d5ed' : '#f2ae60', label:true, copy:w.system,
    sub:`${w.neutron_star ? 'Neutron' : 'Waypoint'} / about ${w.estimated_jumps_from_previous} jumps from previous waypoint`
  }));
  Lab.map.addLayer('neutron', {label:'next neutron waypoints', color:'#68d5ed', z:4, points:mapPoints,
    lines:S => { const p = mapPoints(S); return p.slice(1).map((b,i) => ({a:p[i],b,color:'#68d5ed',dash:[4,5]})); }
  });
  Lab.card({id:'neutron', requires:['neutron'],
    mount(el) {
      el.innerHTML = `<form data-neutron-plan style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
        <label>Destination <input name="destination" required maxlength="100" style="width:190px"></label>
        <label>Normal range <input name="range_ly" type="number" min="1" max="200" step="0.01" style="width:75px"> Ly</label>
        <details><summary>Route options</summary><label>Origin <input name="source" placeholder="Current system"></label>
          <label>Efficiency <input name="efficiency" type="number" min="1" max="100" value="60" style="width:65px"></label>
          <label>Neutron multiplier <select name="supercharge"><option value="auto">Auto from fitted FSD</option><option value="4">4x</option><option value="6">6x</option></select></label>
          <label>Confirmed career start (optional) <input name="career_start"></label></details>
        <button type="submit">Plan neutron route</button></form>
        <div data-neutron-message aria-live="polite"></div><div data-neutron-status></div>`;
      const f = el.querySelector('form'), msg = el.querySelector('[data-neutron-message]');
      f.elements.range_ly.oninput = () => { el._rangeEdited = true; };
      el._polls = 0;
      el._action = async (path, body) => {
        if (el._busy) return;
        el._busy = true; f.querySelector('button[type=submit]').disabled = true;
        try { const d = await Lab.post(path, body); if (el.isConnected) { display(el, d); msg.textContent = ''; } }
        catch(err) { if (el.isConnected) msg.textContent = err.message; }
        finally { el._busy = false; f.querySelector('button[type=submit]').disabled = false; }
      };
      f.onsubmit = e => {
        e.preventDefault(); el._polls = 0;
        const body = Object.fromEntries(new FormData(f));
        if (body.range_ly) body.range_ly = Number(body.range_ly); else delete body.range_ly;
        body.efficiency = Number(body.efficiency); msg.textContent = 'Submitting route to Spansh...';
        el._action('/api/neutron/plan', body);
      };
      el.onclick = async e => {
        const r = el._neutron?.route; if (!r) return;
        if (e.target.closest('[data-neutron-clear]')) await el._action('/api/neutron/clear', {id:r.id});
        if (e.target.closest('[data-neutron-refresh]')) { el._polls = 0; await el._action('/api/neutron/refresh', {id:r.id}); }
        if (e.target.closest('[data-neutron-export]')) {
          try {
            const d = await Lab.api('/api/neutron/export'); if (!el.isConnected) return;
            const url = URL.createObjectURL(new Blob([d.csv], {type:'text/csv;charset=utf-8'}));
            const a = document.createElement('a'); a.href = url; a.download = d.filename; a.click();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
          } catch(err) { msg.textContent = err.message; }
        }
      };
      el._timer = setInterval(() => {
        const r = el._neutron?.route;
        if (!el.isConnected || el._busy || !r || !['queued','running'].includes(r.status)) return;
        if (el._polls >= 60) { msg.textContent = 'Automatic checks paused. Use Check result to continue.'; return; }
        el._polls++; el._action('/api/neutron/refresh', {id:r.id});
      }, 5000);
    },
    render(el, state) { display(el, state.neutron?.summary); },
    unmount(el) { clearInterval(el._timer); }
  });
})();
