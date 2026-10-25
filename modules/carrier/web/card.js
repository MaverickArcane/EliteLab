/* Follow a visited carrier; retain the owner view when no carrier is pinned. */
(() => {
  const { esc, fmt, inaraSys } = Lab.util;
  const when = value => value ? esc(new Date(value).toLocaleString()) : 'unknown';

  Lab.map.addLayer('pinned-carrier', {
    label: 'Pinned carrier', color: '#2fd4ff', z: 9,
    points(S) {
      const c = S.carrier?.pinned, p = c?.star_pos;
      return p ? [{ name: c.callsign, x: p[0], y: p[1], z: p[2], r: 5, color: '#2fd4ff',
        kind: 'carrier', label: true, sub: `Last reported: ${c.system}`, copy: c.system }] : [];
    },
  });

  Lab.card({
    id: 'carrier', requires: ['carrier', 'journal'],
    mount(el) {
      el.innerHTML = `<div class="row"><label>Visited carrier <select data-carrier-select aria-label="Visited fleet carrier"></select></label>
        <button class="mini" data-carrier-action="pin">Pin</button>
        <button class="mini" data-carrier-action="unpin">Unpin</button>
        <button class="mini" data-carrier-action="refresh">Refresh</button></div>
        <div data-carrier-content></div>`;
      el.addEventListener('click', async e => {
        const button = e.target.closest('[data-carrier-action]');
        if (!button || button.disabled) return;
        const action = button.dataset.carrierAction;
        const marketId = el.querySelector('[data-carrier-select]').value;
        button.dataset.pending = 'true';
        button.disabled = true;
        try {
          const result = await Lab.post('/api/carrier/' + action, action === 'pin' ? { market_id: Number(marketId) } : {});
          if (result.error && !('pinned' in result)) throw new Error(result.error);
          // State arrives through SSE; keep version ordering authoritative.
        } catch (error) {
          Lab.toast(error.message || 'Could not update the carrier.', 'bad');
        } finally {
          delete button.dataset.pending;
          Lab.emit('carrier');
        }
      });
    },
    render(el, S) {
      const state = S.carrier || {}, c = state.pinned;
      const select = el.querySelector('[data-carrier-select]');
      const visited = state.visited || [];
      const options = visited.map(r => `<option value="${esc(r.market_id)}">${esc(r.callsign)} - ${esc(r.system)}</option>`).join('');
      if (select.dataset.options !== options) {
        const previous = select.value;
        select.innerHTML = options || '<option value="">No carriers visited yet</option>';
        select.dataset.options = options;
        const preferred = previous || String(c?.market_id || '');
        if (visited.some(r => String(r.market_id) === preferred)) select.value = preferred;
      }
      select.disabled = !visited.length;
      el.querySelector('[data-carrier-action="pin"]').disabled = !visited.length;
      el.querySelector('[data-carrier-action="unpin"]').disabled = !c;
      const refresh = el.querySelector('[data-carrier-action="refresh"]');
      refresh.disabled = !c || state.offline || state.refreshing;
      refresh.textContent = state.refreshing ? 'Checking...' : 'Refresh';
      el.querySelectorAll('[data-carrier-action][data-pending]').forEach(button => { button.disabled = true; });
      const content = el.querySelector('[data-carrier-content]');
      if (c) {
        content.innerHTML = `<div class="big">${esc(c.callsign)} <span class="tag">Pinned</span></div>
          <div class="grid2">
            <div><div class="k">Last reported system</div><div class="v"><a href="${inaraSys(c.system)}" target="_blank" rel="noopener">${esc(c.system)}</a></div></div>
            <div><div class="k">Distance from you</div><div class="v">${c.distance != null ? fmt(c.distance) + ' Ly' : 'Unknown'}</div></div>
            <div><div class="k">Docking access</div><div class="v">${esc(c.docking || 'Unknown')}</div></div>
            <div><div class="k">Source</div><div class="v">${esc(c.source === 'journal' ? 'Your journal' : c.source)}</div></div>
          </div>
          <div class="note">Services: ${esc((c.services || []).join(', ') || 'Unknown')}</div>
          <div class="note">Last reported: ${when(c.observed_at)}<br>Last checked: ${when(state.checked_at)}</div>
          <div class="note">${state.offline ? 'Offline: showing saved observations.' : 'Checks every five minutes. Reports may lag behind carrier movements.'}</div>
          ${state.error ? `<div class="note warn">${esc(state.error)}</div>` : ''}`;
        return;
      }
      const owned = S.journal?.carrier;
      if (!owned?.name) {
        content.innerHTML = `<div class="note">${visited.length ? 'Pin a visited carrier to follow its last reported location and services.' : 'Dock at a fleet carrier to add it here. Previous visits are discovered from your journals.'}</div>`;
        return;
      }
      content.innerHTML = `<div class="big">${esc(owned.name)} <span class="muted">(${esc(owned.callsign)})</span></div>
        <div class="grid2">
          <div><div class="k">System</div><div class="v">${esc(owned.system || 'Unknown')}</div></div>
          <div><div class="k">Tritium</div><div class="v">${owned.fuel != null ? fmt(owned.fuel) + ' / 1000' : 'Unknown'}</div></div>
          <div><div class="k">Balance</div><div class="v">${fmt(owned.balance)}</div></div>
          <div><div class="k">Free space</div><div class="v">${owned.free_space != null ? fmt(owned.free_space) + ' t' : 'Unknown'}</div></div>
        </div>
        <div class="note">Services: ${esc((owned.services || []).join(', '))}${owned.stats_time ? '<br>Stats from ' + when(owned.stats_time) : ''}</div>`;
    },
  });
})();
