/* recipes card: look up blueprints, experimental effects and tech broker unlocks (materials per grade, engineers).
   Read-only; "+ wishlist" hands the recipe to the Engineering wishlist card, where grade and quantity are picked. */
(() => {
  const { esc, fmt } = Lab.util;
  let timer = null;
  Lab.card({
    id: 'recipes', requires: ['recipes'],
    mount(el) {
      el.innerHTML = `<div class="row"><input id="rc-q" placeholder="search: fsd range, dirty drives, mass manager, guardian" size="32"></div>
        <div class="row" style="margin-top:6px"><select id="rc-module"><option value="">any module</option></select>
          <select id="rc-kind"><option value="">blueprints, effects, unlocks</option><option value="blueprint">blueprints only</option><option value="experimental">experimental effects only</option><option value="unlock">tech broker unlocks only</option></select>
          <select id="rc-eng"><option value="">any engineer</option></select><button class="mini" id="rc-reset">reset</button></div>
        <div class="rc-results"></div>
        <div class="note">Reference only: click a recipe for its materials per grade and who offers it. "+ wishlist" sends it to the Engineering wishlist card, where you pick the grades and quantity.</div>`;
      const q = el.querySelector('#rc-q'), res = el.querySelector('.rc-results');
      const sel = { module: el.querySelector('#rc-module'), kind: el.querySelector('#rc-kind'), engineer: el.querySelector('#rc-eng') };
      const search = async () => {
        const params = { query: q.value.trim(), module: sel.module.value, kind: sel.kind.value, engineer: sel.engineer.value, limit: 60 };
        if (!params.query && !params.module && !params.kind && !params.engineer) { res.innerHTML = ''; return; }
        try {
          const r = await Lab.api('/api/recipes', params);
          res.innerHTML = r.count ? `<table><tbody>` + r.results.map(h => `<tr><td><a href="#" class="rc-open" data-key="${esc(h.key)}">${esc(h.module)}: ${esc(h.name)}</a>
            <span class="muted">${h.kind === 'blueprint' ? (h.engineer_grade ? `G1-${h.engineer_grade} here, G${h.max_grade} max` : `G1-${h.max_grade}`) : h.kind === 'unlock' ? `${esc(h.broker || '')} tech broker` : 'experimental'}</span></td>
            <td class="num"><button class="mini rc-add" data-key="${esc(h.key)}" data-kind="${esc(h.kind)}" data-module="${esc(h.module)}" title="pick grades and quantity in the wishlist card">+ wishlist</button></td></tr><tr class="rc-detail" data-for="${esc(h.key)}" style="display:none"><td colspan="2"></td></tr>`).join('') + `</tbody></table>` +
            (r.count > 60 ? `<div class="muted">${r.count} matches, showing 60; narrow it down</div>` : `<div class="muted">${r.count} match${r.count === 1 ? '' : 'es'}</div>`) : `<div class="muted">no match</div>`;
        } catch (e) { res.innerHTML = `<div class="bad">${esc(e.message)}</div>`; }
      };
      q.oninput = () => { clearTimeout(timer); timer = setTimeout(search, 250); };
      Object.values(sel).forEach(s => s.onchange = search);
      el.querySelector('#rc-reset').onclick = () => { q.value = ''; Object.values(sel).forEach(s => s.value = ''); res.innerHTML = ''; };
      res.onclick = async (ev) => {
        const open = ev.target.closest('.rc-open'), add = ev.target.closest('.rc-add');
        if (open) {
          ev.preventDefault();
          const row = res.querySelector(`.rc-detail[data-for="${CSS.escape(open.dataset.key)}"]`), cell = row.firstElementChild;
          if (row.style.display !== 'none') { row.style.display = 'none'; return; }
          row.style.display = '';
          cell.innerHTML = '<span class="muted">loading</span>';
          try {
            const d = await Lab.api('/api/recipes/get', { key: open.dataset.key });
            if (d.kind === 'blueprint') {
              cell.innerHTML = Object.entries(d.grades).map(([g, ms]) => `<div><b>G${g}</b> ${ms.map(m => `${m.count} x ${esc(m.name)}`).join(', ')}</div>`).join('') +
                `<div class="muted">engineers: ${Object.entries(d.engineers).sort((a, b) => b[1] - a[1]).map(([n, g]) => `${esc(n)} (G${g})`).join(', ') || 'none listed'}</div>`;
            } else if (d.kind === 'unlock') {
              cell.innerHTML = `<div>${d.materials.map(m => `${m.count} x ${esc(m.name)}`).join(', ')}</div>` +
                (Object.keys(d.commodities || {}).length ? `<div class="muted">plus cargo: ${Object.entries(d.commodities).map(([n, q]) => `${q} x ${esc(n)}`).join(', ')}</div>` : '');
            } else {
              cell.innerHTML = `<div>${d.materials.map(m => `${m.count} x ${esc(m.name)}`).join(', ')}</div><div class="muted">for: ${d.modules.map(esc).join(', ')}</div>`;
            }
          } catch (e) { cell.innerHTML = `<span class="bad">${esc(e.message)}</span>`; }
        } else if (add) {
          // hand over to the wishlist card's picker (client-only namespace); it selects the recipe and the user sets grades and qty there
          Lab.set('wishlist_ui', { preselect: { key: add.dataset.key, kind: add.dataset.kind, module: add.dataset.module, at: Date.now() } });
          const card = document.getElementById('card-wishlist');
          if (card) { card.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); Lab.toast('Selected in the Engineering wishlist card; pick grades and quantity there'); }
          else Lab.toast('Show the Engineering wishlist card (Layout menu) to add recipes', 'bad');
        }
      };
    },
    render(el, S) {
      const R = S.recipes || {};
      const fill = (id, list) => { const s = el.querySelector(id); if (!s || s.dataset.n == (list || []).length) return; const keep = s.value; s.innerHTML = s.firstElementChild.outerHTML + (list || []).map(v => `<option value="${esc(v)}">${esc(v)}</option>`).join(''); s.value = keep; s.dataset.n = (list || []).length; };
      fill('#rc-module', R.modules); fill('#rc-eng', R.engineers);
      const n = el.querySelector('.note');
      if (n && !n.dataset.done) { n.dataset.done = 1; n.insertAdjacentHTML('afterbegin', `<span class="muted">${fmt(R.blueprints)} blueprints, ${fmt(R.experimentals)} experimental effects, ${fmt(R.unlocks)} tech broker unlocks. </span>`); }
    },
  });
})();
