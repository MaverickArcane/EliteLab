/* materials card: the inventory as the game reports it (Materials event at login, then live changes). Needs live in the
   Engineering wishlist card; this card is just "what do I have". */
(() => {
  const { esc, fmt } = Lab.util;
  let rows = null, stale = true, filter = '';
  Lab.card({
    id: 'materials', requires: ['materials'],
    mount(el) {
      el.innerHTML = `<div class="mat-summary"></div>
        <div class="row" style="margin-top:8px"><input id="mat-q" placeholder="filter: tellurium, G5, encoded" size="22"><select id="mat-cat"><option value="">all</option><option>Raw</option><option>Manufactured</option><option>Encoded</option></select></div>
        <div class="mat-list" style="max-height:320px;overflow:auto"></div>
        <div class="note">Counts come from the game's own inventory dump at login and every collect, trade, craft and synthesis since. Track what you need in the Engineering wishlist card.</div>`;
      const refresh = () => { filter = el.querySelector('#mat-q').value.trim().toLowerCase(); draw(el); };
      el.querySelector('#mat-q').oninput = refresh; el.querySelector('#mat-cat').onchange = refresh;
    },
    render(el, S) {
      const M = S.materials || {}; const t = M.totals || {};
      el.querySelector('.mat-summary').innerHTML = `<div class="grid2" style="margin-top:0">
          <div><div class="k">Raw</div><div class="v">${fmt(t.Raw)}</div></div>
          <div><div class="k">Manufactured</div><div class="v">${fmt(t.Manufactured)}</div></div>
          <div><div class="k">Encoded</div><div class="v">${fmt(t.Encoded)}</div></div>
          <div><div class="k">Distinct</div><div class="v">${fmt(M.inventory_count)}</div></div></div>`;
      stale = true; draw(el);
    },
  });
  async function draw(el) {
    const cat = el.querySelector('#mat-cat').value;
    if (stale || !rows) { try { rows = (await Lab.api('/api/materials')).materials; stale = false; } catch (e) { el.querySelector('.mat-list').innerHTML = `<div class="bad">${esc(e.message)}</div>`; return; } }
    const words = filter.split(/\s+/).filter(Boolean);
    const list = rows.filter(r => r.count > 0 && (!cat || r.category === cat) && words.every(w => (`${r.name} g${r.grade} ${r.category}`).toLowerCase().includes(w)))
      .sort((a, b) => (a.category || '').localeCompare(b.category || '') || (b.grade || 0) - (a.grade || 0) || a.name.localeCompare(b.name));
    el.querySelector('.mat-list').innerHTML = list.length ? `<table><thead><tr><th>Material</th><th>G</th><th class="num">Have</th></tr></thead><tbody>` +
      list.map(r => `<tr><td>${esc(r.name)} <span class="muted">${esc((r.category || '').slice(0, 3))}</span></td><td>${r.grade ?? ''}</td><td class="num ${r.cap && r.count >= r.cap ? 'warn' : ''}">${fmt(r.count)}${r.cap ? `<span class="muted">/${r.cap}</span>` : ''}</td></tr>`).join('') + `</tbody></table>` : `<div class="muted">nothing matches</div>`;
  }
})();
