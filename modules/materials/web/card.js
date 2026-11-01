/* materials card: the inventory as the game reports it (Materials event at login, then live changes). Needs live in the
   Engineering wishlist card; this card is just "what do I have". */
(() => {
  const { esc, fmt } = Lab.util;
  Lab.card({
    id: 'materials', requires: ['materials'],
    mount(el) {
      el._materials = { rows: null, revision: 0, loaded: -1, pending: false };
      el.innerHTML = `<div class="mat-summary"></div>
        <div class="mat-session"></div>
        <div class="row" style="margin-top:8px"><input id="mat-q" placeholder="filter: tellurium, G5, encoded" size="22"><select id="mat-cat"><option value="">all categories</option><option>Raw</option><option>Manufactured</option><option>Encoded</option></select>
          <select id="mat-view"><option value="all">current inventory</option><option value="gained">gained this session</option></select><button id="mat-refresh" class="mini">refresh</button></div>
        <div class="mat-status muted" role="status"></div>
        <div class="mat-list" style="max-height:320px;overflow:auto"></div>
        <div class="note">Have is your current inventory. Gained counts pickups, mission rewards and trader receipts this game session; spending reduces Have, not Gained. A new game login starts a new session. Track requirements in the Engineering wishlist.</div>`;
      const filter = () => draw(el);
      el.querySelector('#mat-q').oninput = filter; el.querySelector('#mat-cat').onchange = filter;
      el.querySelector('#mat-view').onchange = filter;
      el.querySelector('#mat-refresh').onclick = () => { el._materials.revision++; draw(el); };
    },
    render(el, S) {
      const M = S.materials || {}; const t = M.totals || {};
      el.querySelector('.mat-summary').innerHTML = `<div class="grid2" style="margin-top:0">
          <div><div class="k">Raw</div><div class="v">${fmt(t.Raw)}</div></div>
          <div><div class="k">Manufactured</div><div class="v">${fmt(t.Manufactured)}</div></div>
          <div><div class="k">Encoded</div><div class="v">${fmt(t.Encoded)}</div></div>
          <div><div class="k">Distinct</div><div class="v">${fmt(M.inventory_count)}</div></div></div>`;
      session(el, M.session);
      el._materials.revision++; draw(el);
    },
  });
  function session(el, value) {
    const known = value?.started_at && value.gained != null;
    const last = value?.last_gain;
    el.querySelector('.mat-session').innerHTML = known
      ? `<div style="margin-top:8px"><b>Gained this session: +${fmt(value.gained)}</b>
          <span class="muted">since ${esc(new Date(value.started_at).toLocaleTimeString())}</span></div>
         <div class="muted">Raw +${fmt(value.totals?.Raw || 0)} / Manufactured +${fmt(value.totals?.Manufactured || 0)} / Encoded +${fmt(value.totals?.Encoded || 0)}</div>` +
        (last ? `<div>Latest gain: +${fmt(last.count)} ${esc(last.name)}${last.at ? ` <span class="muted">${esc(new Date(last.at).toLocaleTimeString())}</span>` : ''}</div>` : '')
      : '<div class="muted" style="margin-top:8px">Session gains unavailable until a game login is read.</div>';
  }
  async function draw(el) {
    const state = el._materials;
    if (state.pending) return;
    if (state.loaded !== state.revision || !state.rows) {
      const revision = state.revision;
      state.pending = true;
      el.querySelector('.mat-status').textContent = 'Updating inventory...';
      try {
        const response = await Lab.api('/api/materials');
        if (revision === state.revision) {
          state.rows = response.materials; state.loaded = revision;
          session(el, response.session);
          el.querySelector('.mat-status').textContent = `Updated ${new Date().toLocaleTimeString()}`;
        }
      } catch (e) {
        if (revision === state.revision) {
          el.querySelector('.mat-status').textContent = `Update failed: ${e.message}. Press refresh to retry.`;
          return;
        }
      } finally { state.pending = false; }
      // A newer journal update arrived while fetching. Discard that response
      // and fetch again, even if no more journal events arrive.
      if (revision !== state.revision) return draw(el);
    }
    // Read filters after the request finishes so pending responses cannot undo edits.
    const cat = el.querySelector('#mat-cat').value;
    const gainedOnly = el.querySelector('#mat-view').value === 'gained';
    const words = el.querySelector('#mat-q').value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const list = state.rows.filter(r => (gainedOnly ? r.gained > 0 : r.count > 0 || r.gained > 0) && (!cat || r.category === cat) && words.every(w => (`${r.name} g${r.grade} ${r.category}`).toLowerCase().includes(w)))
      .sort((a, b) => (a.category || '').localeCompare(b.category || '') || (b.grade || 0) - (a.grade || 0) || a.name.localeCompare(b.name));
    el.querySelector('.mat-list').innerHTML = list.length ? `<table><thead><tr><th>Material</th><th>G</th><th class="num">Have</th><th class="num">Gained</th></tr></thead><tbody>` +
      list.map(r => `<tr><td>${esc(r.name)} <span class="muted">${esc((r.category || '').slice(0, 3))}</span></td><td>${r.grade ?? ''}</td><td class="num ${r.cap && r.count >= r.cap ? 'warn' : ''}">${fmt(r.count)}${r.cap ? `<span class="muted">/${r.cap}</span>` : ''}</td><td class="num">${r.gained == null ? '--' : '+' + fmt(r.gained)}</td></tr>`).join('') + `</tbody></table>` : `<div class="muted">${gainedOnly ? 'No gains match this session.' : 'Nothing matches.'}</div>`;
  }
})();
