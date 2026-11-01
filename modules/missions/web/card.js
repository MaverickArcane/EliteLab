/* Mission requirements update live; supplier requests are deliberate. */
(() => {
  const {esc, fmt} = Lab.util;
  const place = p => [p?.station, p?.system].filter(Boolean).join(', ') || 'Location unknown';
  const qty = x => x == null ? '?' : fmt(x);
  const stamp = x => x ? new Date(x).toLocaleString() : 'unknown';
  Lab.card({
    id: 'missions', requires: ['missions'],
    mount(el) {
      el.innerHTML = `<form data-mission-search class="toolbar" style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
        <label>Radius <input name="radius" type="number" min="1" max="500" value="25" style="width:65px"> Ly</label>
        <label>Pad <select name="pad"><option>L</option><option>M</option><option>S</option></select></label>
        <label><input name="carriers" type="checkbox"> Include carriers (access unknown)</label>
        <button type="submit">Find supplies</button></form>
        <div data-mission-list></div><div data-mission-results aria-live="polite"></div>`;
      el._missionRevision = 0;
      el.querySelector('form').onsubmit = async e => {
        e.preventDefault();
        const form = e.currentTarget, button = form.querySelector('button');
        const output = el.querySelector('[data-mission-results]');
        const revision = el._missionRevision;
        button.disabled = true;
        output.textContent = 'Checking nearby reported stock...';
        try {
          const d = await Lab.api('/api/missions/sources', {max_distance_ly:form.elements.radius.value,
            pad:form.elements.pad.value, carriers:form.elements.carriers.checked ? 'include' : 'exclude'});
          if (!el.isConnected) return;
          if (revision !== el._missionRevision) {
            output.textContent = 'Your missions, cargo or location changed during the search. Find supplies again for the current checklist.';
            return;
          }
          output.innerHTML = `<div class="note">Search from ${esc(d.search.reference || 'unknown')}, within ${esc(d.search.max_distance_ly)} Ly. Reports up to ${esc(d.search.max_days)} days old.</div>` +
            (d.supplies.length ? d.supplies.map(r => `<div style="margin-top:12px"><strong>${qty(r.quantity)} t ${esc(r.commodity)}</strong>
              ${r.error ? `<div class="bad">Search failed: ${esc(r.error)}</div>` : !r.sources.length ? '<div class="muted">No matching stock reports in this radius.</div>' :
                r.sources.map(s => `<div style="margin:6px 0">${esc(s.station)}, <button class="mini" data-copy="${esc(s.system)}">${esc(s.system)}</button>
                  <div class="muted">${qty(s.distance_ly)} Ly / ${qty(s.distance_to_arrival_ls)} Ls arrival / ${qty(s.stock)} t stock / ${qty(s.cost_for_quantity)} Cr total / reported ${esc(stamp(s.updated_at))}</div>
                  ${s.carrier_location_verified_live === false ? '<div class="bad">Carrier location and docking access unverified.</div>' : ''}</div>`).join('')}</div>`).join('') :
              '<div class="note">No confirmed market shortages. Check the checklist for salvage, depot pickups or missing cargo data.</div>') +
            `<div class="note">${esc(d.search_note)}</div>`;
        } catch (err) { if (el.isConnected) output.textContent = `Search failed: ${err.message}`; }
        finally { button.disabled = false; }
      };
    },
    render(el, state) {
      const p = state.missions?.plan;
      if (!p) return;
      el._missionRevision++;
      const results = el.querySelector('[data-mission-results]');
      if (results.textContent) results.textContent = 'Checklist updated. Find supplies again to refresh supplier results.';
      el.querySelector('[data-mission-list]').innerHTML =
        `<div class="note">${p.missions.length} active missions / ${qty(p.shopping_tonnes)} t to buy / ${qty(p.free_space)} t free. Cargo observed ${esc(stamp(p.cargo_observed_at))}.</div>` +
        (p.fits_current_hold === false ? '<div class="bad">The shopping list needs more space than your current free hold. Split the purchases into trips.</div>' : '') +
        p.missions.map(m => `<details style="margin:10px 0"><summary><strong>${esc(m.title || m.name || `Mission ${m.mission_id}`)}</strong>${m.expired ? ' - deadline passed' : ''}</summary>
          <div class="muted">${esc(m.kind.replaceAll('_',' '))} / ${esc(m.faction || 'Issuer unknown')} / deadline ${esc(stamp(m.expiry))}</div>
          ${m.commodity_key ? `<div>${esc(m.commodity_name || m.commodity_key)}: ${qty(m.required)} required / ${qty(m.delivered)} delivered / ${qty(m.aboard_allocated)} aboard / ${qty(m.shortfall)} still needed</div>` : ''}
          <div>${esc(m.next_action)}</div>
          ${m.kind === 'salvage' ? `<div>Search: ${esc(place(m.destination))}</div>` : ''}
          ${m.kind === 'delivery' ? `<div>Pickup: ${esc(place(m.origin))}</div>` : ''}
          <div>Hand in: ${esc(place(m.hand_in))}</div></details>`).join('') +
        (!p.missions.length ? '<div class="muted">No active missions recorded.</div>' : '') +
        '<div class="note">Aboard quantities are allocated once across missions. Unknown delivery progress shows ?. Reward choices and local commodity legality are not available here.</div>';
    }
  });
})();
